"""Raw current/position capture across a PWM sweep, to CSV.

Collects the two distributions the attachment floor has to separate: a channel
with a motor on it, and a channel on the same H-bridge board with none. Both are
driven identically, so the only difference is the motor.

Channels whose IS pin runs to no H-bridge at all are a third case and must not be
pooled with either — an unconnected ADC input floats at a few hundred counts and
would read as the strongest "attached" signal on the bench.

Resolution is one smoothed sample per 50 ms frame — the shipped firmware carries
no raw pin values. That separates the two populations, but it cannot show the
per-sample excursions the detector actually thresholds, so a threshold read off
this data wants margin for spread it cannot see. The raw-burst build that could
show them lives on bench/raw-scope.

    python3 -m firmware.bench_tests capture --port PORT \
        --motor FLHY --empty FLHL,FLKL --out ~/Downloads/attach.csv
"""
from __future__ import annotations

import csv
import os
from typing import List

from firmware.bench_tests import mcu

# Both signs: the BTS7960 senses only through the active high-side switch, so a
# direction asymmetry would show up here and nowhere else.
PWM_SWEEP = [50, 75, 100, 150, 200, 255]
FRAMES_PER_STEP = 8
SETTLE_FRAMES = 2


def _step(ser, joint: str, pwm: int) -> List[dict]:
    """Drive one level and return every per-loop sample the board bursted."""
    mcu.jog(ser, joint, pwm)
    mcu.collect(ser, SETTLE_FRAMES)
    frames = mcu.collect(ser, FRAMES_PER_STEP)
    mcu.hold_all(ser)

    rows = []
    for frame in frames:
        parsed = mcu.parse_full(frame.line)
        joints = {j.name: j for j in parsed.joints}
        if joint not in joints:
            continue
        smoothed = joints[joint]
        burst = getattr(parsed, "raw_burst", None)
        if burst is not None and burst.joint == joint:
            # Bench build: every per-loop sample the detector saw.
            samples = list(enumerate(burst.samples))
            dropped = burst.dropped
        else:
            # Shipped build: one smoothed sample per frame. Enough to compare the
            # two populations, but it cannot show per-sample excursions, and the
            # detector thresholds the raw pin — say so in the file rather than
            # letting a later reader assume the columns mean the same thing.
            samples = [(0, (smoothed.pot, smoothed.current))]
            dropped = ""
        for index, (pot, current) in samples:
            rows.append({
                "joint": joint,
                "pwm": pwm,
                "seq": index,
                "raw_pot": pot,
                "raw_current": current,
                "dropped": dropped,
                "avg_pot": smoothed.pot,
                "avg_is": smoothed.current,
            })
    return rows


def sweep(port: str, motor: List[str], empty: List[str], out: str) -> int:
    out = os.path.expanduser(out)
    rows: List[dict] = []

    for joint, has_motor in [(j, 1) for j in motor] + [(j, 0) for j in empty]:
        label = "MOTOR ATTACHED" if has_motor else "no motor"
        print(f"\n=== {joint} ({label}) ===")
        if has_motor:
            input(f"  {joint} will be driven both directions. Keep clear, Enter > ")
        with mcu.open_port(port) as ser:
            for pwm in PWM_SWEEP:
                for signed in (pwm, -pwm):
                    got = _step(ser, joint, signed)
                    for r in got:
                        r["has_motor"] = has_motor
                    rows.extend(got)
                    currents = [r["raw_current"] for r in got]
                    if currents:
                        print(f"    pwm {signed:>+4}  n={len(got):<4} "
                              f"rawIS {min(currents):>4}-{max(currents):<4} "
                              f"dropped={got[0]['dropped']}")
                    else:
                        print(f"    pwm {signed:>+4}  no telemetry for {joint}")

    if not rows:
        print("\nno samples captured — did the jog reach the board?")
        return 1
    fields = ["joint", "has_motor", "pwm", "seq", "raw_pot", "raw_current",
              "avg_pot", "avg_is", "dropped"]
    with open(out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} samples -> {out}")
    return 0
