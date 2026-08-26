"""Serial primitives for the Task 3 power-monitor bench suite."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import serial

from firmware.interfaces.telemetry_frame import TelemetryFrame
from firmware.krabby_mcu import DEFAULT_BAUD

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
        if TelemetryFrame.is_telemetry_line(raw):
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
        if TelemetryFrame.is_telemetry_line(raw):
            samples.append(Sample(time.monotonic() - started, raw))
        else:
            boot.lines.append(raw)
    return boot, samples


def collect(ser: serial.Serial, count: int, timeout: float = 40.0,
            role: Tuple[str, ...] = LEADER_PREFIXES) -> List[Sample]:
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


def battery_of(sample: Sample):
    """Parsed BATT segment from one line, or None when none was received."""
    return TelemetryFrame.parse_line(sample.line).battery
