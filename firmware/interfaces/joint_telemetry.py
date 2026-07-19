"""Telemetry line parsing (host side of the Arduino->Orin serial wire).

Error-handling policy (see docs/M16-ERROR-HANDLING.md): this parse layer is
tolerant and Optional-returning. Corruption on the lossy serial stream is
expected steady state -- truncated lines at connect time, garbled bytes, AVR
non-finite float prints -- so a malformed segment is dropped, never raised;
the next tick almost certainly carries a good sample. The drop is observable
through the optional ParseStats hook; logging, counters, and throttling
belong to the SDK layer (firmware/krabby_mcu.py), not here.
"""
import enum
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# Wire format: must match firmware (actuator_manager.h + arduino.ino).
# Line starts with a role prefix "FRONT; ", "UNKNOWN; ", "LEFT; ", or "RIGHT; " then semicolon-separated segments.
# Forwarded lines from left/right already include their role (LEFT; / RIGHT; ).
# Example: "FRONT; FLHY 0.123 0 512 1 0 0 128 0;FLHL ...;..."
# Segment format: <name> <pos> <pot> <current> <enL> <enR> <pwmL> <pwmR> <saf>
# saf: cumulative HallA edge count since boot (pins depend on KRABBY_PIN_REV in board_pins.h).
#
# The leader's own line (FRONT/UNKWN) may end with appended sensor segments
# (see arduino.ino imuAppendTelemetry):
#   ;IMU <accel_x> <accel_y> <accel_z> <gyro_x> <gyro_y> <gyro_z> <temp_c> <valid>
# accel m/s^2, gyro rad/s (body frame, bias-subtracted), temp C, valid 0/1.
#
# Wire contract: append-only. New sensor segments are appended to the line
# under a fresh tag, and parsers ignore segments they do not recognize.
# Consumers reading lines from firmware that lacks a given sensor segment
# simply see that field as None -- no version negotiation on either side.

# Line-start prefixes a host uses to recognize a telemetry line (str.startswith).
# These carry the firmware's exact wire punctuation from roleName() + "; " in
# arduino.ino -- note "LEFT " is padded to five chars, so its prefix is "LEFT ;",
# and the leader's role prints as "UNKWN" not "UNKNOWN". Distinct from
# JointTelemetry.ROLE_PREFIXES, which are the unpunctuated role *tokens*.
TELEMETRY_LINE_PREFIXES = (
    "FRONT;",
    "UNKWN;",
    "LEFT ;",
    "RIGHT;",
)


# Cap on the raw segment text retained in ParseStats.last_segment. A garbled
# line can be arbitrarily long; the stored copy is only for a log message.
_MAX_STORED_SEGMENT = 120


class ImuParseReason(enum.Enum):
    """Why a *recognized* IMU segment was dropped by the parser.

    A segment whose tag is not the IMU tag is a dispatch miss, not corruption,
    and is not recorded here. These reasons cover an IMU-tagged segment whose
    payload is malformed, making the (intentional) None return observable
    instead of information-free.
    """

    BAD_TOKEN_COUNT = "bad-token-count"      # truncated or over-long segment
    NON_NUMERIC_TOKEN = "non-numeric-token"  # garbled bytes, AVR "ovf", bad valid flag
    NON_FINITE_VALUE = "non-finite-value"    # AVR "nan"/"inf" on accel/gyro (wiring/link)
    TEMP_READ_FAILED = "temp-read-failed"    # retained (later task); temp-only NaN now keeps the sample, so no longer emitted here


@dataclass
class ParseStats:
    """Out-of-band aggregate of dropped segments.

    Parsers stay Optional-returning (a malformed segment on the lossy stream
    is expected, not exceptional) but record *why* here so the silence is
    observable. Callers that do not care pass nothing and get the plain
    Optional contract; the SDK passes one instance per connection and owns
    the logging/throttling built on top of it.
    """

    error_count: int = 0
    last_reason: Optional[ImuParseReason] = None
    last_segment: Optional[str] = None

    def record(self, reason: ImuParseReason, segment: str) -> None:
        self.error_count += 1
        self.last_reason = reason
        self.last_segment = segment[:_MAX_STORED_SEGMENT]


@dataclass
class JointTelemetry:
    name: str
    pos: float
    pot: int
    current: int
    en: Tuple[int, int]
    pwm: Tuple[int, int]
    saf: int

    # Role prefix (first segment of a line); not a joint.
    ROLE_PREFIXES = ("JT", "FRONT", "UNKNOWN", "LEFT", "RIGHT")

    @classmethod
    def from_tokens(cls, tokens) -> Optional["JointTelemetry"]:
        if not tokens:
            return None
        if tokens[0] in cls.ROLE_PREFIXES:
            tokens = tokens[1:] if tokens[0] == "JT" else None
        if not tokens or len(tokens) != 9:
            return None
        name, pos, pot, cur, enL, enR, pwmL, pwmR, saf = tokens
        try:
            return cls(
                name=name,
                pos=float(pos),
                pot=int(pot),
                current=int(cur),
                en=(int(enL), int(enR)),
                pwm=(int(pwmL), int(pwmR)),
                saf=int(saf),
            )
        except ValueError:
            return None

    @classmethod
    def parse_line(cls, line: str):
        return parse_telemetry_line(line).joints

    def format_compact(self, target: Optional[float] = None) -> str:
        pos_part = f"{self.pos:.3f}"
        if target is not None:
            pos_part = f"{pos_part}/{target:.3f}"
        return (
            f"{self.name}:{pos_part},{self.pot},{self.current},"
            f"({self.en[0]},{self.en[1]}),({self.pwm[0]},{self.pwm[1]}),{self.saf}"
        )


@dataclass
class ImuTelemetry:
    """Leader-board LSM6DSO sample appended to the telemetry line (see arduino.ino)."""

    accel: Tuple[float, float, float]  # m/s^2, body frame
    gyro: Tuple[float, float, float]   # rad/s, body frame, bias-subtracted
    temp_c: float
    valid: bool                        # False = sensor not responding this tick

    TAG = "IMU"
    # Tag plus eight payload fields (accel x3, gyro x3, temp, valid). A wire
    # change that appends a field must land with a parser update; until then
    # the over-long segment is dropped rather than misparsed.
    TOKEN_COUNT = 9

    @classmethod
    def from_tokens(
        cls, tokens, stats: Optional[ParseStats] = None
    ) -> Optional["ImuTelemetry"]:
        """Parse one whitespace-tokenized IMU segment.

        Returns None on any malformed shape -- the sentinel-return idiom for
        an attempt that may not produce a value, matching the rest of this
        parse layer. A valid=0 segment is *well-formed* (sensor present but
        not responding) and parses to a sample with .valid False; it is not
        a parse failure. When `stats` is provided, drops are recorded with a
        reason so the caller can count/log them.
        """

        def _drop(reason: ImuParseReason) -> None:
            if stats is not None:
                stats.record(reason, " ".join(tokens))
            return None

        # A tag mismatch (or nothing to parse) is a dispatch miss, not
        # corruption: return None without touching stats so error_count stays
        # an alarm-meaningful count of genuinely broken IMU segments. In the
        # production path parse_telemetry_line only calls this on IMU-tagged
        # segments, so this guard fires only for direct/other callers.
        if not tokens or tokens[0] != cls.TAG:
            return None
        if len(tokens) != cls.TOKEN_COUNT:
            return _drop(ImuParseReason.BAD_TOKEN_COUNT)
        try:
            vals = [float(t) for t in tokens[1:8]]
        except ValueError:
            # Garbled bytes, or AVR Print's "ovf" for floats outside its
            # printable range; float() rejects both.
            return _drop(ImuParseReason.NON_NUMERIC_TOKEN)
        # The valid flag is exactly "0" or "1" on the wire; anything else is a
        # corrupt token, not a valid=2/-1 "sample".
        if tokens[8] not in ("0", "1"):
            return _drop(ImuParseReason.NON_NUMERIC_TOKEN)
        valid = tokens[8] == "1"
        # AVR prints non-finite floats as "nan"/"inf", which float() accepts.
        if not all(math.isfinite(v) for v in vals):
            if not all(math.isfinite(v) for v in vals[:6]):
                # accel/gyro (vals[:6]) garbled: a genuine wiring/link fault,
                # so the whole sample is worthless -- drop it and record why.
                return _drop(ImuParseReason.NON_FINITE_VALUE)
            # Only the temp field is non-finite: the firmware NAN-poisons token 7
            # when getTemperature() fails while accel/gyro are good. That sample
            # is still useful, so keep it with temp_c = NaN rather than dropping
            # the tick. This is not a parse error, so stats stay untouched.
            return cls(
                accel=(vals[0], vals[1], vals[2]),
                gyro=(vals[3], vals[4], vals[5]),
                temp_c=float("nan"),
                valid=valid,
            )
        return cls(
            accel=(vals[0], vals[1], vals[2]),
            gyro=(vals[3], vals[4], vals[5]),
            temp_c=vals[6],
            valid=valid,
        )

    @classmethod
    def from_segment(
        cls, segment: str, stats: Optional[ParseStats] = None
    ) -> Optional["ImuTelemetry"]:
        """Parse one raw ';'-delimited segment as it appears on the wire.

        The native transport shape is the whitespace-separated text between
        semicolons; this overload owns the tokenization so callers and tests
        can feed wire-shaped strings directly.
        """
        return cls.from_tokens(segment.split(), stats=stats)

    @property
    def accel_g(self) -> Tuple[float, float, float]:
        """Per-axis acceleration in g (raw dataclass is m/s^2)."""
        return tuple(a / 9.80665 for a in self.accel)

    @property
    def gyro_dps(self) -> Tuple[float, float, float]:
        """Per-axis angular rate in deg/s (raw dataclass is rad/s)."""
        return tuple(g * 180.0 / math.pi for g in self.gyro)

    @property
    def roll_deg(self) -> float:
        """Accel-derived static roll (gravity vector). Valid at/near rest, no
        yaw; units cancel so raw m/s^2 is fine as input."""
        _ax, ay, az = self.accel
        return math.degrees(math.atan2(ay, az))

    @property
    def pitch_deg(self) -> float:
        """Accel-derived static pitch (gravity vector). Valid at/near rest."""
        ax, ay, az = self.accel
        return math.degrees(math.atan2(-ax, math.hypot(ay, az)))

    def format_compact(self) -> str:
        ax, ay, az = self.accel
        gx, gy, gz = self.gyro
        flag = "" if self.valid else " STALE"
        return (
            f"a:({ax:.2f},{ay:.2f},{az:.2f})m/s2 "
            f"g:({gx:.3f},{gy:.3f},{gz:.3f})rad/s {self.temp_c:.1f}C{flag}"
        )


@dataclass
class ParsedTelemetry:
    """One parsed telemetry line. Future sensor segments (Task 3 BATT, ...) are
    appended here as new Optional fields, matching the append-only wire format
    without churning parse_telemetry_line's callers."""

    joints: List[JointTelemetry] = field(default_factory=list)
    imu: Optional[ImuTelemetry] = None


def parse_telemetry_line(
    line: str, stats: Optional[ParseStats] = None
) -> ParsedTelemetry:
    """Parse one telemetry line into joints plus optional sensor fields.

    .imu is None unless the line carries a well-formed IMU segment (the
    leader's own line only).

    Wire contract (append-only): a segment whose tag this parser does not
    recognize is assumed to come from newer firmware and is ignored
    silently -- that silence is what lets the wire grow without breaking
    deployed hosts. A *recognized* tag with a malformed payload is
    corruption, not forward compatibility: the segment is dropped (the last
    good sample wins) and, when `stats` is provided, the drop is recorded.
    A bad sensor segment never costs the joint data on the same line.
    """
    parsed = ParsedTelemetry()
    for seg in line.strip().split(";"):
        tokens = seg.split()
        if not tokens:
            continue
        if tokens[0] == ImuTelemetry.TAG:
            imu = ImuTelemetry.from_tokens(tokens, stats=stats)
            if imu is not None:
                parsed.imu = imu
            continue
        jt = JointTelemetry.from_tokens(tokens)
        if jt:
            parsed.joints.append(jt)
    return parsed
