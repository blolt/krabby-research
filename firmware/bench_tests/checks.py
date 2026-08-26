"""Atomic measurements used by the Task 3 power-monitor bench suite."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from firmware.bench_tests import mcu


@dataclass
class Measurement:
    """What a check saw. `values` is for composition, `text` for the operator."""

    values: Dict[str, float | int | str | bool] = field(default_factory=dict)
    text: str = ""
    ok: Optional[bool] = None


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


def battery_report(port: str, lines: int = 40) -> Measurement:
    """Latest BATT frame, and how many monitors are answering.

    The frame is emitted every tick regardless of whether the monitors answered,
    so its presence says nothing about them: pack_valid and midpoint_valid do.
    Reporting a count rather than a boolean is what makes 3d.1 checkable — two
    devices must answer at two distinct addresses, and one address answering
    twice looks identical on the wire unless you count them.

    When a validity byte is 0 that monitor's fields carry its last trustworthy
    reading, which looks entirely plausible. Do not calibrate against them.
    """
    with mcu.open_port(port) as ser:
        samples = mcu.collect(ser, lines)
    if not samples:
        return Measurement(text="no telemetry", ok=False)

    frames = [b for b in (mcu.battery_of(s) for s in samples) if b is not None]
    if not frames:
        return Measurement(
            values={"monitors": 0, "frames": 0, "lines": len(samples)},
            text=(f"no BATT segment in {len(samples)} lines — the leader is not "
                  "emitting one at all (wrong board, or telemetry stopped)"),
            ok=False,
        )

    latest = frames[-1]
    # Straight from the frame's own validity bytes rather than inferred from the
    # frame's presence, which no longer carries that information.
    monitors = int(latest.pack_valid) + int(latest.midpoint_valid)
    down = [n for n, ok in (("pack", latest.pack_valid),
                            ("midpoint", latest.midpoint_valid)) if not ok]
    return Measurement(
        ok=(monitors == 2),
        values={
            "monitors": monitors,
            "pack_valid": latest.pack_valid,
            "midpoint_valid": latest.midpoint_valid,
            "frames": len(frames),
            "lines": len(samples),
            "pack_volts": latest.pack_volts,
            "pack_amps": latest.pack_current_amperes,
            "pack_watts": latest.pack_power_watts,
            "pack_coulombs": latest.pack_charge_coulombs,
            "battery_a": latest.battery_a_volts,
            "battery_b": latest.battery_b_volts,
            "diverged": latest.divergence,
        },
        text=(f"{len(frames)}/{len(samples)} lines carry BATT   "
              f"monitors up: {monitors}/2"
              + (f"   DOWN: {', '.join(down)}  (fields below are last-good, "
                 "do not calibrate against them)" if down else "") + "\n"
              f"  pack   {latest.pack_volts:.3f} V  {latest.pack_current_amperes:+.3f} A  "
              f"{latest.pack_power_watts:.2f} W  {latest.pack_charge_coulombs:.1f} C\n"
              f"  batt A {latest.battery_a_volts:.3f} V   batt B {latest.battery_b_volts:.3f} V"
              f"   diverged={latest.divergence}\n"
              f"  derived: A+B = {latest.battery_a_volts + latest.battery_b_volts:.3f} V "
              f"against pack {latest.pack_volts:.3f} V"),
    )


def _battery_state_count(samples, pack_valid: bool, midpoint_valid: bool):
    frames = [b for b in (mcu.battery_of(s) for s in samples) if b is not None]
    matching = sum(
        1 for frame in frames
        if frame.pack_valid is pack_valid and
        frame.midpoint_valid is midpoint_valid
    )
    return matching, len(frames)


def ina_reconnect(port: str) -> Measurement:
    """Disconnect and recover each INA228 without reopening serial."""
    with mcu.open_port(port) as ser:
        print("     waiting for both INA228 monitors...")
        baseline = mcu.collect(ser, 40)

        input("     UNPLUG only Pack INA228 Qwiic (0x41), then press Enter > ")
        pack_absent = mcu.collect(ser, 80)
        input("     RECONNECT Pack INA228 Qwiic, then press Enter > ")
        pack_recovered = mcu.collect(ser, 120)
        pack_visual = input(
            "     did the OLED lose and restore power data without a Mega reset? [y/N] > "
        ).strip().lower().startswith("y")

        input("     UNPLUG only Midpoint INA228 Qwiic (0x40), then press Enter > ")
        midpoint_absent = mcu.collect(ser, 80)
        input("     RECONNECT Midpoint INA228 Qwiic, then press Enter > ")
        midpoint_recovered = mcu.collect(ser, 120)
        midpoint_visual = input(
            "     did the OLED lose and restore power data without a Mega reset? [y/N] > "
        ).strip().lower().startswith("y")

    phases = {
        "baseline": _battery_state_count(baseline, True, True),
        "pack_absent": _battery_state_count(pack_absent, False, True),
        "pack_recovered": _battery_state_count(pack_recovered, True, True),
        "midpoint_absent": _battery_state_count(midpoint_absent, True, False),
        "midpoint_recovered": _battery_state_count(midpoint_recovered, True, True),
    }
    minimums = {
        "baseline": 20,
        "pack_absent": 40,
        "pack_recovered": 40,
        "midpoint_absent": 40,
        "midpoint_recovered": 40,
    }
    telemetry_ok = all(phases[name][0] >= minimums[name] for name in phases)
    detail = "; ".join(
        f"{name.replace('_', ' ')} {matching}/{frames}"
        for name, (matching, frames) in phases.items()
    )
    return Measurement(
        values={
            **{f"{name}_matching": value[0] for name, value in phases.items()},
            "pack_oled_recovered": pack_visual,
            "midpoint_oled_recovered": midpoint_visual,
        },
        text=(f"{detail}; OLED pack={pack_visual}, midpoint={midpoint_visual}"),
        ok=telemetry_ok and pack_visual and midpoint_visual,
    )


CHECKS: Dict[str, Callable[..., Measurement]] = {
    "boot": boot_log,
    "battery": battery_report,
    "ina-reconnect": ina_reconnect,
}
