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


def open_port(port: str, baud: int = DEFAULT_BAUD) -> serial.Serial:
    return serial.Serial(port, baud, timeout=0.4)


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


def collect(ser: serial.Serial, count: int, timeout: float = 40.0) -> List[Sample]:
    """Gather `count` telemetry lines without resetting."""
    ser.reset_input_buffer()
    out: List[Sample] = []
    started = time.monotonic()
    while len(out) < count and time.monotonic() - started < timeout:
        raw = ser.readline().decode("utf-8", errors="replace").rstrip()
        if raw.startswith(TELEMETRY_LINE_PREFIXES):
            out.append(Sample(time.monotonic() - started, raw))
    return out


def parse_line(raw: str) -> Optional[ImuTelemetry]:
    """Parse a raw wire line through the production parser."""
    return parse_telemetry_line(raw).imu


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
