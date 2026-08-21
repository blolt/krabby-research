"""Serial primitives shared by the bench tests.

Nothing here decides pass or fail; it only talks to the board and parses what
comes back, using the same interfaces the production host code uses.
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import serial

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from firmware.interfaces.imu_telemetry import ImuTelemetry  # noqa: E402
from firmware.interfaces.telemetry_constants import TELEMETRY_LINE_PREFIXES  # noqa: E402
from firmware.interfaces.telemetry_parser import parse_telemetry_line  # noqa: E402
from firmware.krabby_mcu import DEFAULT_BAUD  # noqa: E402

RADIANS_TO_DEGREES = 57.29577951308232

# The leader's own emissions. TELEMETRY_LINE_PREFIXES also covers the LEFT/RIGHT
# lines it forwards from followers, which belong to a different board's loop.
LEADER_PREFIXES = ("FRONT;", "UNKWN;")


@dataclass
class Boot:
    """Everything the board said between reset and steady telemetry."""

    lines: List[str] = field(default_factory=list)

    def says(self, needle: str) -> bool:
        return any(needle in l for l in self.lines)

    def matching(self, needle: str) -> Optional[str]:
        return next((l for l in self.lines if needle in l), None)


@dataclass
class Sample:
    at: float
    line: str


def open_port(port: str, baud: int = DEFAULT_BAUD,
              wait_ready: bool = True) -> serial.Serial:
    """Open the port and, by default, wait for the board to come back up.

    Opening asserts DTR, which resets the Mega. Anything written before the
    bootloader hands off is discarded with no error — a jog just silently does
    nothing. Callers that want the reset itself pass wait_ready=False.
    """
    ser = serial.Serial(port, baud, timeout=0.4)
    if wait_ready:
        await_telemetry(ser)
    return ser


def await_telemetry(ser: serial.Serial, seconds: float = 8.0) -> bool:
    """Block until telemetry lines are flowing. False on timeout."""
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        raw = ser.readline().decode("utf-8", errors="replace")
        if raw.startswith(TELEMETRY_LINE_PREFIXES):
            ser.reset_input_buffer()
            return True
    return False


def reset(ser: serial.Serial) -> None:
    """Pulse DTR, which resets the Mega."""
    ser.setDTR(False)
    time.sleep(0.15)
    ser.setDTR(True)


def reset_and_collect(
    ser: serial.Serial, seconds: float = 14.0
) -> Tuple[Boot, List[Sample]]:
    """Reset, then gather boot chatter and timestamped telemetry lines."""
    reset(ser)
    ser.reset_input_buffer()
    boot, samples = Boot(), []
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        raw = ser.readline().decode("utf-8", errors="replace").rstrip()
        if not raw:
            continue
        if raw.startswith(TELEMETRY_LINE_PREFIXES):
            samples.append(Sample(time.monotonic() - started, raw))
        else:
            boot.lines.append(raw)
    return boot, samples


def collect(ser: serial.Serial, count: int, timeout: float = 40.0,
            role: str = LEADER_PREFIXES) -> List[Sample]:
    """Gather `count` telemetry lines without resetting.

    Defaults to the leader's own lines. A leader with followers attached also
    forwards their LEFT/RIGHT lines on the same wire, so admitting every prefix
    would interleave three boards' emissions and make inter-arrival statistics
    measure the mix rather than the leader's tick.

    Returns fewer than `count` on timeout; callers that need the full sample must
    check, since a short capture otherwise looks like a completed one.
    """
    ser.reset_input_buffer()
    out: List[Sample] = []
    started = time.monotonic()
    while len(out) < count and time.monotonic() - started < timeout:
        raw = ser.readline().decode("utf-8", errors="replace").rstrip()
        if raw.startswith(role):
            out.append(Sample(time.monotonic() - started, raw))
    return out


def parse_line(raw: str) -> Optional[ImuTelemetry]:
    """Parse a raw wire line through the production parser."""
    return parse_telemetry_line(raw).imu


def joints_of(sample: Sample) -> list:
    """Parsed joint segments from one telemetry line."""
    return parse_telemetry_line(sample.line).joints


def battery_of(sample: Sample):
    """Parsed BATT segment from one line, or None when the frame was omitted."""
    return parse_telemetry_line(sample.line).battery


def parse_full(raw: str):
    """Everything on one line — joints, IMU, and the bench raw burst."""
    return parse_telemetry_line(raw)


def send(ser: serial.Serial, command: str) -> None:
    """Write one command line and let the firmware pick it up on the next tick."""
    ser.write((command + "\n").encode())
    ser.flush()
    time.sleep(0.15)


def jog(ser: serial.Serial, joint: str, pwm: int) -> None:
    """Drive one actuator directly. `hold_all` stops everything again.

    No space after the J: the firmware consumes one character then reads the name
    up to the next space, so "J FLHY 200" parses the name as empty and silently
    drives nothing.
    """
    send(ser, f"J{joint} {pwm}")


def hold_all(ser: serial.Serial) -> None:
    send(ser, "H")


OLED_OFF, OLED_NORMAL, OLED_FORCED = 0, 1, 2


def oled_mode(ser: serial.Serial, mode: int) -> None:
    """Select panel off / normal / a full transfer on every eligible refresh.

    Only the middle one occurs in normal operation; the other two exist so 2h.1
    can compare the loop against both extremes.
    """
    send(ser, f"O{mode}")


def imu_of(sample: Sample) -> Optional[ImuTelemetry]:
    """Parse through the production parser, so a wire-format change breaks here too."""
    return parse_line(sample.line)


def interval_stats(samples: List[Sample]) -> dict:
    """Inter-arrival statistics in milliseconds."""
    if len(samples) < 3:
        return {}
    gaps = [
        (b.at - a.at) * 1000.0 for a, b in zip(samples, samples[1:])
    ]
    gaps.sort()
    return {
        "n": len(gaps),
        "mean": statistics.mean(gaps),
        "p50": gaps[len(gaps) // 2],
        "p95": gaps[int(len(gaps) * 0.95)],
        "max": gaps[-1],
        "min": gaps[0],
        "line_bytes": max(len(s.line) for s in samples),
    }


def gyro_degrees(samples: List[Sample]) -> List[Tuple[float, float, float]]:
    out = []
    for s in samples:
        imu = imu_of(s)
        if imu is not None and imu.valid:
            out.append(tuple(v for v in imu.gyro_dps))
    return out


def accel_magnitude(imu: ImuTelemetry) -> float:
    ax, ay, az = imu.accel_g
    return (ax * ax + ay * ay + az * az) ** 0.5
