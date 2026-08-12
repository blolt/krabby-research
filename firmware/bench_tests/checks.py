"""Atomic bench checks — one measurement each, no criterion attached.

Every check answers a single question about the hardware and returns both a
machine-readable measurement and a line of human text. Acceptance criteria in
`task1.py` compose these; the CLI can also run any of them on its own.

Supersedes `firmware/scripts/imu_bench.py`:
    imu_bench timing  -> tick_timing
    imu_bench watch   -> stream          (observation only, never a verdict)
    imu_bench flip    -> orientation_flip
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from firmware.bench_tests import mcu

# Orientation gate, kept identical to imu_bench.py's so results stay comparable.
INVERTED_ACCEL_Z = -3.0
UPRIGHT_ACCEL_Z = 3.0


@dataclass
class Measurement:
    """What a check saw. `values` is for composition, `text` for the operator."""

    values: Dict[str, float | int | str | bool] = field(default_factory=dict)
    text: str = ""
    ok: Optional[bool] = None          # only set when the check is self-judging


# ------------------------------------------------------------------ boot
def boot_log(port: str, seconds: float = 14.0) -> Measurement:
    """Reset and report what the firmware said, plus the telemetry that followed."""
    with mcu.open_port(port) as ser:
        boot, samples = mcu.reset_and_collect(ser, seconds=seconds)
    cal_line = boot.matching("IMU CAL") or ""
    return Measurement(
        values={
            "lines": len(samples),
            "ready": boot.says("Krabby Ready"),
            "captured": boot.says("captured"),
            "loaded": boot.says("loaded from EEPROM"),
            "not_detected": boot.says("not detected"),
            "cal_line": cal_line,
        },
        text="\n".join(f"  {l}" for l in boot.lines if "IMU CAL" in l or "Ready" in l),
    )


# ------------------------------------------------------------------ timing
def tick_timing(port: str, lines: int = 400) -> Measurement:
    """Inter-arrival statistics for leader telemetry lines. Keep the board still."""
    with mcu.open_port(port) as ser:
        stats = mcu.interval_stats(mcu.collect(ser, lines))
    if not stats:
        return Measurement(text="too few lines to measure", ok=False)
    return Measurement(
        values=stats,
        text=(f"mean {stats['mean']:.2f} ms  p50 {stats['p50']:.2f}  "
              f"p95 {stats['p95']:.2f}  max {stats['max']:.2f}  min {stats['min']:.2f}  "
              f"({stats['line_bytes']} B/line, n={stats['n']})"),
    )


# ------------------------------------------------------------------ gravity
def gravity_magnitude(port: str, lines: int = 40) -> Measurement:
    """Mean |accel| over a still board. Should be 1 g if scaling is right."""
    with mcu.open_port(port) as ser:
        samples = mcu.collect(ser, lines)
    valid = [i for i in (mcu.imu_of(s) for s in samples) if i is not None and i.valid]
    if not valid:
        parsed = sum(1 for s in samples if mcu.imu_of(s) is not None)
        return Measurement(
            values={"valid": 0, "parsed": parsed, "lines": len(samples)},
            text=(f"{parsed}/{len(samples)} lines carried a ;IMU segment but none were "
                  "valid — sensor absent, or reconnected without a reset"),
            ok=False,
        )
    magnitude = statistics.mean(mcu.accel_magnitude(i) for i in valid)
    return Measurement(
        values={"magnitude_g": magnitude, "valid": len(valid), "lines": len(samples)},
        text=(f"{len(valid)}/{len(samples)} lines carry a valid ;IMU segment; "
              f"mean |accel| = {magnitude:.3f} g"),
    )


# ------------------------------------------------------------------ resting gyro
def resting_gyro(port: str, lines: int = 60) -> Measurement:
    """Per-axis mean and worst magnitude with the board still — the bias residual."""
    with mcu.open_port(port) as ser:
        samples = mcu.collect(ser, lines)
    gyro = mcu.gyro_degrees(samples)
    if not gyro:
        return Measurement(text="no valid IMU samples", ok=False)
    means = [statistics.mean(a[i] for a in gyro) for i in range(3)]
    worst = max(abs(v) for axes in gyro for v in axes)
    return Measurement(
        values={"mean_x": means[0], "mean_y": means[1], "mean_z": means[2],
                "worst_axis_dps": worst, "samples": len(gyro)},
        text=(f"means {means[0]:+.3f} {means[1]:+.3f} {means[2]:+.3f} deg/s, "
              f"worst |axis| = {worst:.3f} (n={len(gyro)})"),
    )


# ------------------------------------------------------------------ motion
def peak_motion(port: str, lines: int = 150) -> Measurement:
    """Largest gyro rate seen — evidence the readings respond to being moved."""
    with mcu.open_port(port) as ser:
        samples = mcu.collect(ser, lines)
    gyro = mcu.gyro_degrees(samples)
    if len(gyro) < 20:
        return Measurement(text=f"only {len(gyro)} valid samples", ok=False)
    peak = max(max(abs(v) for v in axes) for axes in gyro)
    spread = max(max(a[i] for a in gyro) - min(a[i] for a in gyro) for i in range(3))
    return Measurement(
        values={"peak_dps": peak, "widest_span_dps": spread, "samples": len(gyro)},
        text=f"peak |gyro| = {peak:.1f} deg/s, widest axis span = {spread:.1f} deg/s",
    )


# ------------------------------------------------------------------ orientation
def orientation_flip(port: str, seconds: float = 20.0) -> Measurement:
    """Count inverted samples while the operator turns the breakout over.

    Same accel-Z gate as imu_bench.py's `flip`, so counts remain comparable.
    Evidence that accel tracks gravity's direction, not just its magnitude.
    """
    print(f"     turn the BREAKOUT upside down and hold it there — {seconds:.0f}s window")
    inverted = total = 0
    peak = 0.0
    state = "?"
    with mcu.open_port(port) as ser:
        ser.reset_input_buffer()
        started = time.monotonic()
        while time.monotonic() - started < seconds:
            raw = ser.readline().decode("utf-8", errors="replace")
            imu = mcu.parse_line(raw)
            if imu is None or not imu.valid:
                continue
            total += 1
            az = imu.accel[2]
            peak = max(peak, max(abs(v) for v in imu.gyro))
            if az < INVERTED_ACCEL_Z:
                inverted += 1
            now = ("DOWN" if az < INVERTED_ACCEL_Z
                   else "up" if az > UPRIGHT_ACCEL_Z else "sideways")
            if now != state:
                state = now
                print(f"     {time.monotonic() - started:5.1f}s  accel-Z {az:+6.2f} -> {now}")
    return Measurement(
        values={"samples": total, "inverted": inverted, "peak_gyro_rads": peak},
        text=(f"samples {total}, inverted {inverted}, peak |gyro| {peak:.3f} rad/s "
              f"(accel-Z below {INVERTED_ACCEL_Z} counts as inverted)"),
    )


# ------------------------------------------------------------------ observation
def stream(port: str, seconds: float = 20.0) -> Measurement:
    """Print one parsed sample a second. Observation only — never judges."""
    shown = 0
    with mcu.open_port(port) as ser:
        started = last = time.monotonic()
        while time.monotonic() - started < seconds:
            imu = mcu.parse_line(ser.readline().decode("utf-8", errors="replace"))
            if imu and imu.valid and time.monotonic() - last > 1.0:
                last = time.monotonic()
                shown += 1
                print(f"     {imu.format_compact()}")
    return Measurement(values={"shown": shown}, text=f"{shown} samples printed")


CHECKS: Dict[str, Callable[..., Measurement]] = {
    "boot": boot_log,
    "timing": tick_timing,
    "gravity": gravity_magnitude,
    "resting-gyro": resting_gyro,
    "motion": peak_motion,
    "flip": orientation_flip,
    "stream": stream,
}
