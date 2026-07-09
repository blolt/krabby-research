#!/usr/bin/env python3
"""M16 IMU bench tool — timing capture, live watch, and motion verification.

Talks to a leader/bench Mega over USB serial and exercises the ;IMU telemetry
segment end-to-end through the real parser (firmware.interfaces.joint_telemetry).

Usage (from the repo root, venv with pyserial):
    python firmware/scripts/imu_bench.py PORT timing [--lines 400]
    python firmware/scripts/imu_bench.py PORT watch  [--seconds 20]
    python firmware/scripts/imu_bench.py PORT flip   [--seconds 60]

PORT is e.g. /dev/cu.usbmodemXXX (macOS) or /dev/ttyACM0 (Linux/Jetson).

Modes:
  timing  AC 1c evidence: inter-line arrival stats for leader telemetry lines
          (mean/p50/p95/max ms + line length). Keep the board still.
  watch   Stream parsed IMU samples (~1/s) — sanity-check accel = gravity
          (|a| ~= 9.81 m/s^2 at rest) and gyro ~= 0 after boot calibration.
  flip    Motion verification with a human in the loop: reports orientation
          transitions and counts inverted samples. The test passes only if
          accel-Z goes below -3 m/s^2 while the BREAKOUT (not the Mega!) is
          physically held upside down. Binary and timing-proof.

NOTE: opening the port resets the board on macOS (DTR pulses on open no
matter what pyserial is told), so every mode waits ~4 s through role election
before measuring. Boot logs are echoed — expect on a bench leader:
    ROLE: UNKNOWN (front actuators)
    IMU CAL: BMI270 online at 0x69        (0x68 on an uncut ADR jumper)
    IMU CAL: loaded from EEPROM.          (or "gyro bias captured..." on first boot)
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

import serial

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from firmware.interfaces.joint_telemetry import (  # noqa: E402
    TELEMETRY_LINE_PREFIXES,
    parse_telemetry_line,
)

PREFIXES = TELEMETRY_LINE_PREFIXES  # shared wire prefixes (joint_telemetry.py)
DEFAULT_BAUD = 250000  # must match BAUD_RATE in firmware/arduino/arduino.ino


def open_and_boot(port: str, baud: int, boot_timeout: float = 12.0) -> serial.Serial:
    """Open the port (resets the board), echo boot logs, return once telemetry flows."""
    ser = serial.Serial(port, baud, timeout=2.0)
    deadline = time.time() + boot_timeout
    while time.time() < deadline:
        line = ser.readline().decode("utf-8", errors="replace").strip()
        if line.startswith(PREFIXES):
            return ser
        if line:
            print(f"boot: {line}")
    print("warning: telemetry never started; proceeding anyway", file=sys.stderr)
    return ser


def cmd_timing(ser: serial.Serial, args: argparse.Namespace) -> None:
    stamps = [time.monotonic()]
    lens = []
    while len(stamps) < args.lines + 1:
        line = ser.readline().decode("utf-8", errors="replace").strip()
        if line.startswith(PREFIXES):
            stamps.append(time.monotonic())
            lens.append(len(line))
    deltas = sorted((b - a) * 1000 for a, b in zip(stamps, stamps[1:]))
    print(f"lines: {len(deltas)}  line-length: mean {statistics.mean(lens):.0f} B, max {max(lens)} B")
    print(
        f"inter-line ms: mean {statistics.mean(deltas):.2f}  p50 {deltas[len(deltas) // 2]:.2f}  "
        f"p95 {deltas[int(len(deltas) * 0.95)]:.2f}  max {deltas[-1]:.2f}  min {deltas[0]:.2f}"
    )


def cmd_watch(ser: serial.Serial, args: argparse.Namespace) -> None:
    t0 = time.time()
    last = 0.0
    while time.time() - t0 < args.seconds:
        parsed = parse_telemetry_line(ser.readline().decode("utf-8", errors="replace"))
        if parsed.imu and parsed.imu.valid and time.time() - last > 1.0:
            last = time.time()
            print(parsed.imu.format_compact())


def cmd_flip(ser: serial.Serial, args: argparse.Namespace) -> None:
    print(f"=== {args.seconds}s window: flip the BREAKOUT upside down and hold ~10s ===")
    t0 = time.time()
    n = inverted = 0
    peak_gyro = 0.0
    state = "?"
    def orientation(az):
        return "DOWN" if az < -3 else ("up" if az > 3 else "sideways")
    while time.time() - t0 < args.seconds:
        parsed = parse_telemetry_line(ser.readline().decode("utf-8", errors="replace"))
        if not (parsed.imu and parsed.imu.valid):
            continue
        n += 1
        az = parsed.imu.accel[2]
        peak_gyro = max(peak_gyro, max(abs(v) for v in parsed.imu.gyro))
        if az < -3:  # same threshold as the DOWN gate and the docstring's pass criterion
            inverted += 1
        new = orientation(az)
        if new != state:
            state = new
            print(f"{time.time() - t0:5.1f}s  accel-Z {az:+6.2f}  -> {new}")
    verdict = "PASS" if inverted > 20 else "FAIL (sensor never inverted — was the breakout itself flipped?)"
    print(f"samples {n}  inverted {inverted}  peak|gyro| {peak_gyro:.3f} rad/s  -> {verdict}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port")
    ap.add_argument("mode", choices=["timing", "watch", "flip"])
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    ap.add_argument("--lines", type=int, default=400, help="timing mode: lines to sample")
    ap.add_argument("--seconds", type=int, default=20, help="watch/flip mode: window length")
    args = ap.parse_args()

    ser = open_and_boot(args.port, args.baud)
    try:
        {"timing": cmd_timing, "watch": cmd_watch, "flip": cmd_flip}[args.mode](ser, args)
    finally:
        ser.close()


if __name__ == "__main__":
    main()
