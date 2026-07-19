import os
import sys
import serial
import time
import threading
import logging
from typing import Dict, Optional
from firmware.interfaces.joint_telemetry import (
    BatteryTelemetry,
    ImuParseReason,
    ImuTelemetry,
    JointTelemetry,
    ParseStats,
    TELEMETRY_LINE_PREFIXES,
    parse_telemetry_line,
)
from firmware.interfaces.power_messages import POWER_MSG_PREFIX, PowerMessage
from firmware.mcu_port import default_port

# Single source of truth for the MCU serial rate. MUST equal BAUD_RATE in
# firmware/arduino/arduino.ino (test_default_baud_matches_firmware pins it);
# every host that opens the MCU port imports this rather than repeating 250000.
DEFAULT_BAUD = 250000

# --- LOGGING SETUP ---
# When run as `python -m firmware --debug`, __main__.py calls basicConfig(DEBUG) before this import.
# If krabby_mcu is imported alone, ensure a default handler exists.
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
logger = logging.getLogger("KrabbySDK")


def parse_ver_reply(line: str) -> Optional[list[tuple[str, str, str]]]:
    """Parse a VER reply line. Returns None if not a VER line."""
    if not line.startswith("VER "):
        return None
    parts = line[4:].split()
    if not parts:
        return None
    versions = parts[0].split("|")
    branches = parts[1].split("|") if len(parts) > 1 else []
    commits  = parts[2].split("|") if len(parts) > 2 else []
    result = []
    for i, v in enumerate(versions):
        b = branches[i] if i < len(branches) else "-"
        c = commits[i]  if i < len(commits)  else "-"
        result.append((v, b, c))
    return result


def _raw_rx_to_stderr() -> bool:
    """When True, every non-empty decoded line is printed to stderr (see __main__.py --debug)."""
    v = os.environ.get("KRABBY_MCU_RAW_RX", "").strip().lower()
    return v in ("1", "true", "yes", "on")


# Line-start prefixes (TELEMETRY_LINE_PREFIXES) are imported from
# joint_telemetry so the wire punctuation, including the "LEFT " padding, has
# one definition shared by the SDK and the bench tools.

# Malformed recognized segments are expected steady-state on the lossy serial
# link, so warnings are throttled with a timestamp gate (same idiom as the
# DEBUG joint dump below): at most one WARNING per interval, first occurrence
# never suppressed, every drop still counted in parse_stats.
_PARSE_WARN_INTERVAL_S = 1.0
# Cap how much of an offending segment is echoed into a log record.
_SEGMENT_LOG_MAX_CHARS = 80

# Joint names by board for readable debug output (FRONT / LEFT / RIGHT)
JOINT_GROUP_NAMES = (
    ("FRONT", ["FLHY", "FLHL", "FLKL", "FRHY", "FRHL", "FRKL"]),
    ("LEFT", ["RLHY", "RLHL", "RLKL", "MLHY", "MLHL", "MLKL"]),
    ("RIGHT", ["RRHY", "RRHL", "RRKL", "MRHY", "MRHL", "MRKL"]),
)


class KrabbyMCUSDK:
    def __init__(self, port=None, baud=DEFAULT_BAUD):
        self.port = port or default_port()
        self.baud = baud
        self.ser = None
        self.running = False

        # Serializes writes to self.ser. send_power_message runs on the reader
        # thread (invoked inline from _handle_power_line), while the motor/version
        # commands run on the app/HAL thread — two writers on one port. Guard only
        # the write()+flush() body of each writer so their bytes never interleave.
        self._write_lock = threading.Lock()

        # Structured telemetry per joint
        self.joints: Dict[str, Optional[JointTelemetry]] = {}

        # Latest IMU sample from the leader's telemetry line. Three states
        # (see docs/M16-ERROR-HANDLING.md):
        #   imu is None          — no IMU segment ever seen. Normal for
        #                          followers and for firmware that predates
        #                          the IMU segment: absence by design, never
        #                          logged. Distinct from the next state.
        #   imu.valid is False   — sensor present but not responding (leader
        #                          init/read failure). Surfaced once at
        #                          WARNING on the transition; rendered STALE.
        #   imu.valid is True    — fresh sample.
        self.imu: Optional[ImuTelemetry] = None

        # Latest battery/power sample from the leader's telemetry line (Task 3).
        # Same three-state contract as imu: None = no BATT segment seen (follower,
        # or leader firmware without INA228s); otherwise the last parsed sample.
        self.battery: Optional[BatteryTelemetry] = None

        # Malformed-segment accounting. The parse layer returns None on a bad
        # segment (lossy-stream idiom); the SDK owns the observability:
        # a monotonic counter + last reason (queryable, like last_error) and
        # a throttled WARNING (see _warn_parse_errors_throttled).
        self.parse_stats = ParseStats()
        self._last_parse_warn_ts = 0.0
        # One-shot gate for the valid->invalid IMU transition (Class B); re-armed
        # when a valid sample arrives so a later re-failure warns again.
        self._imu_stale_warned = False
        # One-shot gate for the battery divergence transition; re-armed when the
        # two battery voltages come back within threshold.
        self._batt_diverge_warned = False

        # Power-state control (M16 Task 4). The leader emits POWERING_DOWN /
        # RESUMING / OVER_VOLTAGE_SHUTDOWN on the same serial link; the Orin
        # power daemon hangs a callback here rather than opening a second reader
        # on the same device (two readers on one port drop each other's bytes).
        self.last_power_message: Optional[PowerMessage] = None
        self.on_power_message = None  # Optional[Callable[[PowerMessage], None]]

        self.last_feedback_ts = None
        self.thread = None
        self._last_debug_log_ts = 0.0
        self.last_error = None
        self.last_cmd: Dict[str, Optional[float]] = {}
        self._last_ver_line: Optional[str] = None

    @property
    def parse_error_count(self) -> int:
        """Total recognized-but-malformed segments dropped since connect."""
        return self.parse_stats.error_count

    @property
    def last_parse_reason(self) -> Optional[ImuParseReason]:
        """Why the most recent segment was dropped (None if none dropped)."""
        return self.parse_stats.last_reason

    def connect(self):
        try:
            # Open without toggling DTR so the leader board is not reset on connect.
            # A DTR reset would break three-board role election (followers stay in
            # their assigned roles and stop broadcasting SYNC, so a newly-reset
            # leader can never hear from them).
            ser = serial.Serial()
            ser.port = self.port
            ser.baudrate = self.baud
            ser.timeout = 0.5
            ser.dtr = False
            ser.open()
            self.ser = ser
            time.sleep(5.0)  # wait for boot + 3-board role election before starting reader
            self.running = True
            self.last_error = None
            # Fresh accounting per connection ("dropped since connect").
            self.parse_stats = ParseStats()
            self._last_parse_warn_ts = 0.0
            self._imu_stale_warned = False
            self._batt_diverge_warned = False
            self.imu = None  # drop any sample cached from a prior connection
            self.battery = None
            self.thread = threading.Thread(
                target=self._reader_loop, daemon=True)
            self.thread.start()
            logger.info(f"Connected to {self.port}")

            # On startup, immediately command the MCU to hold all joints
            # at their current positions so the legs don't drift or move
            # unexpectedly before the user issues a command.
            self.send_command_joints_hold()

            return True
        except Exception:
            logger.exception("Connection Failed")
            return False

    def _reader_loop(self):
        while self.running and self.ser.is_open:
            try:
                raw = self.ser.readline()
                try:
                    line = raw.decode('utf-8').strip()
                except UnicodeDecodeError as e:
                    logger.warning(
                        "Decode error on serial line (port=%s, len=%d): %s raw=%s",
                        self.port,
                        len(raw),
                        e,
                        raw.hex(),
                    )
                    line = raw.decode('utf-8', errors='ignore').strip()
                except Exception:
                    logger.exception("Decode error")
                    continue
                if not line:
                    continue
                if _raw_rx_to_stderr():
                    print(f"[serial rx] {line}", file=sys.stderr, flush=True)
                elif logger.isEnabledFor(logging.DEBUG):
                    logger.debug("serial rx: %s", line)
                if line.startswith(TELEMETRY_LINE_PREFIXES):
                    self._parse_joint_line(line)
                    self.last_feedback_ts = time.time()
                elif line.startswith(POWER_MSG_PREFIX + " "):
                    self._handle_power_line(line)
                elif line.startswith("VER "):
                    self._last_ver_line = line
                elif "Krabby" in line or "CAL" in line or "Saved" in line:
                    logger.info(f"[MCU] {line}")

            except (serial.SerialException, AttributeError) as e:
                if self.running:
                    logger.exception("Reader loop error")
                else:
                    logger.debug("Reader loop stopped: %s", e)
                self.last_error = e
                self.running = False
                break
            except Exception as exc:
                logger.exception("Reader loop error")
                self.last_error = exc
                self.running = False
                break

    def _warn_parse_errors_throttled(self):
        """WARN about a dropped malformed segment, gated to ~1/s.

        Timestamp gate (the DEBUG joint dump idiom below): the first
        occurrence always logs; while gated, per-drop detail stays at DEBUG.
        parse_stats keeps counting every drop regardless.
        """
        reason = self.parse_stats.last_reason
        reason_name = reason.name if reason is not None else "UNKNOWN"
        segment = (self.parse_stats.last_segment or "")[:_SEGMENT_LOG_MAX_CHARS]
        # Monotonic clock: an NTP step on the RTC-less Jetson must not silently
        # widen or collapse the throttle window.
        now = time.monotonic()
        if (now - self._last_parse_warn_ts) >= _PARSE_WARN_INTERVAL_S:
            logger.warning(
                "Dropped malformed telemetry segment (%s): %r — %d dropped since connect",
                reason_name, segment, self.parse_stats.error_count,
            )
            self._last_parse_warn_ts = now
        else:
            logger.debug(
                "Dropped malformed telemetry segment (%s): %r",
                reason_name, segment,
            )

    def _store_imu(self, imu: ImuTelemetry):
        """Store the latest IMU sample; surface the valid->invalid transition.

        valid=0 means the sensor is present but not responding (leader-side
        init or read failure — actionable: Qwiic wiring, I2C address, 3.3V
        rail). It arrives every tick while the condition persists, so it is
        logged once per transition (one-shot flag), never per tick, and never
        raised: an unhappy optional sensor is not a transport failure. The
        sample itself is stored either way — the host preserves everything
        the wire carries.
        """
        self.imu = imu
        if imu.valid:
            self._imu_stale_warned = False  # re-arm for the next transition
        elif not self._imu_stale_warned:
            logger.warning(
                "IMU reports valid=0 (sensor present but not responding); "
                "readout is STALE. Check Qwiic wiring / I2C address / 3.3V rail."
            )
            self._imu_stale_warned = True

    def _store_battery(self, battery: BatteryTelemetry):
        """Store the latest battery sample; surface the divergence transition.

        A tripped divergence flag means the two series batteries differ by more
        than the configured threshold (a cell imbalance / a failing battery) —
        actionable, and it persists every tick, so it is logged once per
        transition (one-shot flag) and re-armed when the pack rebalances. The
        sample is stored either way. Protective action on divergence / power
        state is Task 4; here the host only records and surfaces it.
        """
        self.battery = battery
        if not battery.divergence:
            self._batt_diverge_warned = False  # re-arm for the next transition
        elif not self._batt_diverge_warned:
            logger.warning(
                "Battery divergence: A=%.2fV B=%.2fV differ beyond threshold "
                "(possible cell imbalance / failing battery).",
                battery.battery_a_volts, battery.battery_b_volts,
            )
            self._batt_diverge_warned = True

    def _parse_joint_line(self, line: str):
        errors_before = self.parse_stats.error_count
        parsed = parse_telemetry_line(line, stats=self.parse_stats)
        if self.parse_stats.error_count != errors_before:
            self._warn_parse_errors_throttled()
        if parsed.imu is not None:
            self._store_imu(parsed.imu)
        if parsed.battery is not None:
            self._store_battery(parsed.battery)
        if not parsed.joints:
            return
        for jt in parsed.joints:
            self.joints[jt.name] = jt

        # Debug Log: FRONT / LEFT / RIGHT each on its own line
        now = time.time()
        if logger.isEnabledFor(logging.DEBUG) and (now - self._last_debug_log_ts) >= 0.25:
            for group_name, names in JOINT_GROUP_NAMES:
                parts = []
                for name in names:
                    jt = self.joints.get(name)
                    if jt:
                        parts.append(jt.format_compact(self.last_cmd.get(name)))
                if parts:
                    logger.debug("JOINTS %s %s", group_name, "; ".join(parts))
            if self.imu is not None:
                logger.debug("IMU %s", self.imu.format_compact())
            if self.battery is not None:
                logger.debug("BATT %s", self.battery.format_compact())
            self._last_debug_log_ts = now

    def send_command_joints(self, cmds_by_joint: Dict[str, float]):
        """
        Send commands keyed by joint name.
        """
        if not self.ser or not self.ser.is_open:
            return

        seq = []
        for key, raw_val in cmds_by_joint.items():
            val = max(0.0, min(1.0, raw_val))
            seq.append((key, val))
            self.last_cmd[key] = val

        parts = ["T"]
        for name, val in seq:
            parts.append(name)
            parts.append(f"{val:.3f}")

        cmd = " ".join(parts) + "\n"
        with self._write_lock:
            self.ser.write(cmd.encode('utf-8'))
            self.ser.flush()

        logger.info("CMD -> %s", " ".join(parts))

    def send_commands_jog(self, cmds_by_joint: Dict[str, int]):
        """
        Send all jog commands in one batch (B name pwm name pwm ...) so the leader
        can forward one line to followers instead of 18 separate J lines.
        """
        if not self.ser or not self.ser.is_open:
            return
        parts = ["B"]
        for name, raw_pwm in cmds_by_joint.items():
            pwm = max(-255, min(255, int(raw_pwm)))
            parts.append(name)
            parts.append(str(pwm))
        cmd = " ".join(parts) + " \n"
        with self._write_lock:
            self.ser.write(cmd.encode('utf-8'))
            self.ser.flush()

    def send_command_jog(self, joint_name: str, pwm: int):
        """ Send J<name> <pwm> (-255 to 255) """
        if not self.ser or not self.ser.is_open:
            return
        pwm = max(-255, min(255, int(pwm)))
        cmd = f"J{joint_name} {pwm}\n"
        with self._write_lock:
            self.ser.write(cmd.encode('utf-8'))
            self.ser.flush()

    def read_version(self, timeout: float = 1.0) -> Optional[str]:
        if not self.ser or not self.ser.is_open:
            return None
        self._last_ver_line = None
        with self._write_lock:                 # lock the write only, NOT the poll loop
            self.ser.write(b"V\n")
            self.ser.flush()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._last_ver_line is not None:
                return self._last_ver_line
            time.sleep(0.02)
        return None

    def send_command_calibrate(self):
        if not self.ser or not self.ser.is_open:
            return
        with self._write_lock:
            self.ser.write(b"C\n")
            self.ser.flush()
        logger.info("CMD -> AUTO-CALIBRATE (C)")

    def send_command_joints_hold(self):
        """
        Send the 'H' command to hold all joints at their current positions.
        """
        if not self.ser or not self.ser.is_open:
            return
        with self._write_lock:
            self.ser.write(b"H\n")
            self.ser.flush()
        logger.info("CMD -> H")

    def _handle_power_line(self, line: str):
        """Dispatch a recognized PWR line to the registered power callback.

        Runs on the reader thread. An unparseable/unknown-schema PWR line is
        dropped (PowerMessage.parse returns None). The callback is invoked
        inline; a slow or raising callback is the daemon's problem, so it is
        guarded so one bad handler can't kill the reader loop.
        """
        msg = PowerMessage.parse(line)
        if msg is None:
            logger.debug("Unrecognized power line dropped: %r", line)
            return
        self.last_power_message = msg
        cb = self.on_power_message
        if cb is not None:
            try:
                cb(msg)
            except Exception:
                logger.exception("on_power_message callback raised")

    def send_power_message(self, msg: PowerMessage):
        """Write a power-control message on the serial link (e.g. the Orin's
        SHUTDOWN_ACK back to the leader). Same port as telemetry."""
        if not self.ser or not self.ser.is_open:
            return
        with self._write_lock:                 # runs on the reader thread — see __init__
            self.ser.write((msg.format_line() + "\n").encode("utf-8"))
            self.ser.flush()
        logger.info("PWR -> %s", msg.format_line())

    def wait_for_move(self, seconds):
        time.sleep(seconds)

    def close(self):
        self.running = False
        if self.ser:
            try:
                # Interrupt any blocking read so the reader thread can exit cleanly
                cancel_read = getattr(self.ser, "cancel_read", None)
                if callable(cancel_read):
                    cancel_read()
            except Exception:
                logger.debug("cancel_read failed during close", exc_info=True)
            try:
                self.ser.close()
            except Exception:
                logger.debug("Serial close failed", exc_info=True)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
