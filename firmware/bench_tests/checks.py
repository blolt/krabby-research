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
# High enough that the actuator is genuinely working during the active timing
# condition, rather than idling inside the deadband.
ACTIVE_PROBE_PWM = 200
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
            "oled_failed": boot.says("OLED: initialization failed"),
            "cal_line": cal_line,
        },
        text="\n".join(f"  {l}" for l in boot.lines
                        if "IMU CAL" in l or "Ready" in l or "OLED" in l),
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


def deadline_timing(
    port: str,
    lines: int = 520,
    oled: int = mcu.OLED_NORMAL,
    joint: str = "",
    # Telemetry fires on `millis() - last >= 50`, so the period is 50 ms plus
    # whatever the loop overruns, and host-side arrival adds more. A healthy
    # board sits near 51 ms, which means counting gaps over 50 would call half of
    # a passing run late. Past 1.5x the interval an entire slot was skipped, and
    # that is the failure the criterion is about.
    deadline_ms: float = 75.0,
) -> Measurement:
    """Tick statistics under one OLED and drive condition, counting late ticks.

    A mean shift says the loop got slower on average; a missed deadline says a
    single tick blew the budget. 2h.1 fails on either, and only the second is
    visible in the maximum, so both are reported.
    """
    with mcu.open_port(port) as ser:
        mcu.oled_mode(ser, oled)
        if joint:
            mcu.jog(ser, joint, ACTIVE_PROBE_PWM)
        mcu.collect(ser, 6)                      # discard the transition
        samples = mcu.collect(ser, lines, timeout=90.0)
        if joint:
            mcu.hold_all(ser)
        mcu.oled_mode(ser, mcu.OLED_NORMAL)

    stats = mcu.interval_stats(samples)
    if not stats:
        return Measurement(text="too few lines to measure", ok=False)
    gaps = [(b.at - a.at) * 1000.0 for a, b in zip(samples, samples[1:])]
    late = sum(1 for g in gaps if g > deadline_ms)
    stats["late"] = late
    stats["deadline_ms"] = deadline_ms
    return Measurement(
        values=stats,
        text=(f"mean {stats['mean']:.2f} ms  p95 {stats['p95']:.2f}  "
              f"max {stats['max']:.2f}  late(>{deadline_ms:.0f}ms) {late}/{len(gaps)}"),
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
    "deadline": deadline_timing,
    "gravity": gravity_magnitude,
    "resting-gyro": resting_gyro,
    "motion": peak_motion,
    "flip": orientation_flip,
    "stream": stream,
}


# ------------------------------------------------------------------ joints
def joint_report(port: str, lines: int = 20) -> Measurement:
    """Per-joint connected flag, position and raw channels, from the last line seen."""
    with mcu.open_port(port) as ser:
        samples = mcu.collect(ser, lines)
    if not samples:
        return Measurement(text="no telemetry lines arrived", ok=False)
    joints = mcu.joints_of(samples[-1])
    if not joints:
        return Measurement(text="lines arrived but no joint segments parsed", ok=False)
    rows = [
        f"  {j.name}  pos {'nan' if not j.connected else f'{j.pos:.3f}'}"
        f"  pot {j.pot:>4}  cur {j.current:>4}  pwm {j.pwm}"
        for j in joints
    ]
    return Measurement(
        values={
            "count": len(joints),
            "connected": sum(1 for j in joints if j.connected),
            "disconnected": ",".join(j.name for j in joints if not j.connected),
            "names": ",".join(j.name for j in joints),
        },
        text="\n".join(rows),
    )


def diagnostics_survive_disconnect(port: str, lines: int = 40) -> Measurement:
    """For channels reporting nan position, check the raw fields still update.

    A filtered channel must keep streaming its diagnostics; a frozen pot or
    current field would mean the whole segment stopped rather than just position.
    """
    with mcu.open_port(port) as ser:
        samples = mcu.collect(ser, lines)
    series: dict = {}
    for s in samples:
        for j in mcu.joints_of(s):
            series.setdefault(j.name, []).append((j.connected, j.pot, j.current))
    filtered = {n: v for n, v in series.items() if any(not c for c, _, _ in v)}
    if not filtered:
        return Measurement(
            values={"filtered": 0},
            text="no channel is reporting a filtered (nan) position",
        )
    rows, all_live = [], True
    for name, values in sorted(filtered.items()):
        pots = {p for _, p, _ in values}
        currents = {c for _, _, c in values}
        live = len(pots) > 1 or len(currents) > 1
        all_live = all_live and live
        rows.append(f"  {name}: {len(values)} samples, "
                    f"{len(pots)} distinct pot, {len(currents)} distinct current"
                    f"{'' if live else '   <-- frozen'}")
    return Measurement(
        values={"filtered": len(filtered), "all_diagnostics_live": all_live},
        text="\n".join(rows),
        ok=all_live,
    )


def jog_and_watch(port: str, joint: str, pwm: int, lines: int = 30) -> Measurement:
    """Drive one actuator, report what its segment did, then stop it.

    Leaves the actuator held. Used to put a channel into a known drive state so a
    rendered glyph or an indicator can be judged against it.
    """
    with mcu.open_port(port) as ser:
        mcu.collect(ser, 2)
        mcu.jog(ser, joint, pwm)
        samples = mcu.collect(ser, lines)
        mcu.hold_all(ser)
    rows = [j for s in samples for j in mcu.joints_of(s) if j.name == joint]
    if not rows:
        return Measurement(text=f"{joint} never appeared in telemetry", ok=False)
    driven = [j for j in rows if any(j.pwm)]
    pots = {j.pot for j in rows}
    return Measurement(
        values={"samples": len(rows), "driven_samples": len(driven),
                "distinct_pot": len(pots), "commanded_pwm": pwm,
                "connected": all(j.connected for j in rows)},
        text=(f"{joint} at pwm {pwm}: {len(driven)}/{len(rows)} samples show drive, "
              f"{len(pots)} distinct pot values, "
              f"connected={all(j.connected for j in rows)}"),
    )


CHECKS.update({
    "joints": joint_report,
    "diagnostics": diagnostics_survive_disconnect,
})


def filtering_rate(port: str, lines: int = 200) -> Measurement:
    """How often each channel reports a filtered (nan) position, and its pot jitter.

    Distinguishes a latched disconnect from intermittent flicker. A channel that is
    genuinely unplugged reports nan on essentially every line, because the latched
    state persists while idle. A few percent means the validity detector is
    tripping on healthy hardware — its idle-jitter threshold is too tight for this
    harness, not that the channel is disconnected.

    Note the jitter figures are computed from the smoothed pot at the telemetry
    rate, while the detector reads the raw pin at loop rate. Loop-rate excursions
    the detector acts on are invisible here, so treat these as a lower bound.
    """
    from collections import defaultdict

    with mcu.open_port(port) as ser:
        samples = mcu.collect(ser, lines)
    if not samples:
        return Measurement(text="no telemetry lines arrived", ok=False)
    series = defaultdict(list)
    for s in samples:
        for j in mcu.joints_of(s):
            series[j.name].append((j.connected, j.pot))

    rows, rates = [], {}
    for name in sorted(series):
        values = series[name]
        nan = sum(1 for connected, _ in values if not connected)
        rate = nan / len(values)
        rates[name] = rate
        pots = [p for _, p in values]
        deltas = sorted(abs(b - a) for a, b in zip(pots, pots[1:])) or [0]
        verdict = ("latched" if rate > 0.9 else
                   "flicker" if rate > 0.0 else "clean")
        rows.append(f"  {name}  nan {rate * 100:5.1f}%  pot {min(pots)}-{max(pots)}  "
                    f"|dpot| p50 {deltas[len(deltas) // 2]} max {deltas[-1]}   {verdict}")
    latched = [n for n, r in rates.items() if r > 0.9]
    flickering = [n for n, r in rates.items() if 0.0 < r <= 0.9]
    return Measurement(
        values={"lines": len(samples), "latched": ",".join(latched),
                "flickering": ",".join(flickering),
                "latched_count": len(latched), "flickering_count": len(flickering)},
        text="\n".join(rows),
    )


CHECKS["filtering"] = filtering_rate


def jog_then_observe_idle(port: str, joint: str, pwm: int,
                          drive_lines: int = 30, idle_lines: int = 20) -> Measurement:
    """Drive a channel, stop, and keep watching — all on one serial connection.

    Attachment state lives in RAM and `init()` resets it, so re-opening the port
    re-asserts DTR, reboots the board and erases the very latch a disconnect test
    is trying to observe. The drive and the idle observation therefore have to
    share one session; a criterion phrased as "persists while idle" cannot be
    checked across a reconnect.
    """
    with mcu.open_port(port) as ser:
        mcu.collect(ser, 2)
        mcu.jog(ser, joint, pwm)
        driven = mcu.collect(ser, drive_lines)
        mcu.hold_all(ser)
        idle = mcu.collect(ser, idle_lines)

    driven_rows = [j for s in driven for j in mcu.joints_of(s) if j.name == joint]
    idle_rows = [j for s in idle for j in mcu.joints_of(s) if j.name == joint]
    if not driven_rows or not idle_rows:
        return Measurement(text=f"{joint} never appeared in telemetry", ok=False)

    commanded = [j for j in driven_rows if any(j.pwm)]
    disconnected_driven = sum(1 for j in driven_rows if not j.connected)
    disconnected_idle = sum(1 for j in idle_rows if not j.connected)
    return Measurement(
        values={
            "commanded_samples": len(commanded),
            "driven_lines": len(driven_rows),
            "idle_lines": len(idle_rows),
            "disconnected_driven": disconnected_driven,
            "disconnected_idle": disconnected_idle,
            "latched_while_driven": disconnected_driven > 0,
            "retained_while_idle": disconnected_idle == len(idle_rows),
            "pot_span": max(j.pot for j in driven_rows) - min(j.pot for j in driven_rows),
        },
        text=(f"{joint} at pwm {pwm}: {len(commanded)}/{len(driven_rows)} lines show the "
              f"drive command\n"
              f"  while driven: disconnected on {disconnected_driven}/{len(driven_rows)}\n"
              f"  after stop  : disconnected on {disconnected_idle}/{len(idle_rows)}"),
    )


CHECKS["latch"] = jog_then_observe_idle
