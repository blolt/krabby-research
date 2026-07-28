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
import re
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Union

# Wire format: must match firmware (actuator_manager.h + arduino.ino).
# Line starts with a role prefix "FRONT; ", "UNKWN; ", "LEFT ;", or "RIGHT; "
# then semicolon-separated segments. LEFT is padded before the semicolon.
# Forwarded lines from left/right already include their role (LEFT ; / RIGHT;).
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


# A dropped segment's reason comes from whichever sensor parser rejected it;
# ParseStats records both (BatteryParseReason is defined with BatteryTelemetry).
ParseReason = Union[ImuParseReason, "BatteryParseReason"]


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
    last_reason: Optional[ParseReason] = None
    last_segment: Optional[str] = None

    def record(self, reason: ParseReason, segment: str) -> None:
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

    # Grammar of the 18 firmware joint names (arduino.ino): board {F,R,M} x side
    # {L,R} x joint {HY hip-yaw, HL hip-lift, KL knee-lift}. A name outside this
    # set is a garbled joint or an unknown appended segment that happens to be 9
    # tokens; either way it must NOT be misparsed as a phantom joint.
    NAME_RE = re.compile(r"^[FRM][LR](?:HY|HL|KL)$")

    @classmethod
    def from_tokens(cls, tokens) -> Optional["JointTelemetry"]:
        if not tokens:
            return None
        if tokens[0] in cls.ROLE_PREFIXES:
            tokens = tokens[1:] if tokens[0] == "JT" else None
        if not tokens or len(tokens) != 9:
            return None
        name, pos, pot, cur, enL, enR, pwmL, pwmR, saf = tokens
        # Grammar guard: reject anything whose first token is not a known joint
        # name before we treat the segment as joint telemetry.
        if not cls.NAME_RE.match(name):
            return None
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

    @property
    def connected(self) -> bool:
        """False when no actuator is attached to this channel.

        The firmware reports pos as NaN for a channel whose motor is unplugged
        (its pot pin floats and would otherwise stream noise as a live
        position); a finite pos means an actuator is present. See
        LinearActuator::isConnected in actuator_manager.h.

        Guards on isfinite, not just isnan: an AVR-printed non-finite 'inf'
        (over-range float) is also "not a live position" and must read
        disconnected, never surface as an 'inf' through format_compact.
        """
        return math.isfinite(self.pos)

    def format_compact(self, target: Optional[float] = None) -> str:
        if not self.connected:
            return f"{self.name}:DISC,{self.pot},{self.current}"
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
    VALID_BY_TOKEN = {"0": False, "1": True}
    ACCEL_LABEL = "a"
    ACCEL_UNIT = "m/s2"
    ACCEL_DECIMALS = 2
    GYRO_LABEL = "g"
    GYRO_UNIT = "rad/s"
    GYRO_DECIMALS = 3
    TEMP_UNIT = "C"
    TEMP_DECIMALS = 1
    STALE_SUFFIX = " STALE"

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

        (
            _tag,
            accel_x_token,
            accel_y_token,
            accel_z_token,
            gyro_x_token,
            gyro_y_token,
            gyro_z_token,
            temp_c_token,
            valid_token,
        ) = tokens
        try:
            accel = (
                float(accel_x_token),
                float(accel_y_token),
                float(accel_z_token),
            )
            gyro = (
                float(gyro_x_token),
                float(gyro_y_token),
                float(gyro_z_token),
            )
            temp_c = float(temp_c_token)
        except ValueError:
            # Garbled bytes, or AVR Print's "ovf" for floats outside its
            # printable range; float() rejects both.
            return _drop(ImuParseReason.NON_NUMERIC_TOKEN)

        # The valid flag is exactly "0" or "1" on the wire; anything else is a
        # corrupt token, not a valid=2/-1 "sample".
        if valid_token not in cls.VALID_BY_TOKEN:
            return _drop(ImuParseReason.NON_NUMERIC_TOKEN)
        valid = cls.VALID_BY_TOKEN[valid_token]

        # AVR prints non-finite floats as "nan"/"inf", which float() accepts.
        if not all(math.isfinite(value) for value in accel + gyro):
            return _drop(ImuParseReason.NON_FINITE_VALUE)

        # A non-finite temperature does not invalidate otherwise useful motion
        # data. The LSM6DSO path does not intentionally emit NaN today, but
        # retaining the partial sample is safer if a future driver can report
        # temperature failure independently. This is not a parse error.
        if not math.isfinite(temp_c):
            temp_c = float("nan")

        return cls(
            accel=accel,
            gyro=gyro,
            temp_c=temp_c,
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
        flag = "" if self.valid else self.STALE_SUFFIX
        return (
            f"{self.ACCEL_LABEL}:"
            f"({ax:.{self.ACCEL_DECIMALS}f},"
            f"{ay:.{self.ACCEL_DECIMALS}f},"
            f"{az:.{self.ACCEL_DECIMALS}f}){self.ACCEL_UNIT} "
            f"{self.GYRO_LABEL}:"
            f"({gx:.{self.GYRO_DECIMALS}f},"
            f"{gy:.{self.GYRO_DECIMALS}f},"
            f"{gz:.{self.GYRO_DECIMALS}f}){self.GYRO_UNIT} "
            f"{self.temp_c:.{self.TEMP_DECIMALS}f}{self.TEMP_UNIT}{flag}"
        )


class PowerState(enum.IntEnum):
    """The BATT frame's power_state byte, driven by Task 4's protective FSM.
    IntEnum because it rides the wire as a small integer and consumers compare
    it numerically."""

    NORMAL = 0
    WARN = 1
    SOFT_CUT = 2
    HARD_CUT = 3
    OVER_VOLT = 4
    SLEEP = 5
    RESUMING = 6


class BatteryParseReason(enum.Enum):
    """Why a *recognized* BATT segment was dropped (mirror of ImuParseReason)."""

    BAD_TOKEN_COUNT = "bad-token-count"      # truncated or over-long segment
    NON_NUMERIC_TOKEN = "non-numeric-token"  # garbled bytes, AVR "ovf", bad flag/state
    NON_FINITE_VALUE = "non-finite-value"    # AVR "nan"/"inf" on a pack/battery value


@dataclass
class BatteryTelemetry:
    """Leader-board INA228 pack + per-battery sample appended to the telemetry
    line (Task 3; see arduino.ino). Pack values come from the Pack INA228 across
    the external shunt; battery A is the Midpoint INA228 VBUS and battery B is
    derived as pack volts minus battery-A volts."""

    pack_volts: float               # V, total pack
    pack_current_amperes: float     # A, signed (firmware sign convention: + discharge)
    pack_power_watts: float         # W
    pack_charge_coulombs: float     # C, accumulated (INA228 charge register)
    battery_a_volts: float          # V, lower battery (Midpoint INA228 VBUS)
    battery_b_volts: float          # V, upper battery (pack_volts - battery_a_volts)
    divergence: bool       # |Va - Vb| > INA228_DIVERGENCE_THRESHOLD
    power_state: Union[PowerState, int]  # known enum, or unknown byte retained

    TAG = "BATT"
    # Tag plus eight payload fields (pack V/I/P/charge, batt A/B V, divergence,
    # power_state). Appending a field must land with a parser update; until then
    # the over-long segment is dropped rather than misparsed.
    TOKEN_COUNT = 9

    @classmethod
    def from_tokens(
        cls, tokens, stats: Optional[ParseStats] = None
    ) -> Optional["BatteryTelemetry"]:
        """Parse one whitespace-tokenized BATT segment.

        Mirrors ImuTelemetry.from_tokens: Optional-returning, None on any
        malformed shape, drops recorded to `stats` when provided. A tag mismatch
        is a dispatch miss and does not touch stats. divergence is exactly "0"/
        "1" on the wire; power_state is a small non-negative byte.
        """

        def _drop(reason: BatteryParseReason) -> None:
            if stats is not None:
                stats.record(reason, " ".join(tokens))
            return None

        if not tokens or tokens[0] != cls.TAG:
            return None
        if len(tokens) != cls.TOKEN_COUNT:
            return _drop(BatteryParseReason.BAD_TOKEN_COUNT)
        try:
            (
                pack_volts,
                pack_current_amperes,
                pack_power_watts,
                pack_charge_coulombs,
                battery_a_volts,
                battery_b_volts,
            ) = (float(token) for token in tokens[1:7])
        except ValueError:
            return _drop(BatteryParseReason.NON_NUMERIC_TOKEN)
        divergence_token = tokens[7]
        power_state_token = tokens[8]
        # divergence flag is exactly "0"/"1"; anything else is corruption.
        if divergence_token not in ("0", "1"):
            return _drop(BatteryParseReason.NON_NUMERIC_TOKEN)
        # power_state is a byte enum on the wire; accept any 0..255, map later.
        try:
            power_state_byte = int(power_state_token)
        except ValueError:
            return _drop(BatteryParseReason.NON_NUMERIC_TOKEN)
        if not (0 <= power_state_byte <= 255):
            return _drop(BatteryParseReason.NON_NUMERIC_TOKEN)
        # AVR prints non-finite floats as "nan"/"inf", which float() accepts; a
        # wedged INA228 read would poison a pack/battery value, so reject those.
        measurements = (
            pack_volts,
            pack_current_amperes,
            pack_power_watts,
            pack_charge_coulombs,
            battery_a_volts,
            battery_b_volts,
        )
        if not all(math.isfinite(measurement) for measurement in measurements):
            return _drop(BatteryParseReason.NON_FINITE_VALUE)
        try:
            power_state: Union[PowerState, int] = PowerState(power_state_byte)
        except ValueError:
            power_state = power_state_byte
        return cls(
            pack_volts=pack_volts,
            pack_current_amperes=pack_current_amperes,
            pack_power_watts=pack_power_watts,
            pack_charge_coulombs=pack_charge_coulombs,
            battery_a_volts=battery_a_volts,
            battery_b_volts=battery_b_volts,
            divergence=divergence_token == "1",
            power_state=power_state,
        )

    @classmethod
    def from_segment(
        cls, segment: str, stats: Optional[ParseStats] = None
    ) -> Optional["BatteryTelemetry"]:
        """Parse one raw ';'-delimited segment as it appears on the wire."""
        return cls.from_tokens(segment.split(), stats=stats)

    def format_compact(self) -> str:
        flag = " DIVERGE" if self.divergence else ""
        state = (
            self.power_state.name
            if isinstance(self.power_state, PowerState)
            else str(self.power_state)
        )
        return (
            f"pack:{self.pack_volts:.2f}V {self.pack_current_amperes:+.2f}A "
            f"{self.pack_power_watts:.1f}W A:{self.battery_a_volts:.2f}V "
            f"B:{self.battery_b_volts:.2f}V "
            f"q:{self.pack_charge_coulombs:.0f}C {state}{flag}"
        )


@dataclass
class ParsedTelemetry:
    """One parsed telemetry line. Sensor segments (IMU, Task 3 BATT, ...) are
    Optional fields here, matching the append-only wire format without churning
    parse_telemetry_line's callers."""

    joints: List[JointTelemetry] = field(default_factory=list)
    imu: Optional[ImuTelemetry] = None
    battery: Optional[BatteryTelemetry] = None


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
        if tokens[0] == BatteryTelemetry.TAG:
            batt = BatteryTelemetry.from_tokens(tokens, stats=stats)
            if batt is not None:
                parsed.battery = batt
            continue
        jt = JointTelemetry.from_tokens(tokens)
        if jt:
            parsed.joints.append(jt)
    return parsed
