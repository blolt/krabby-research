"""Spec-parity guard for the Task 4 low-power timing constants (M16 Task 4).

The low-power cadences are pure *numbers* in sensors_config.h — nothing in the
Python suite ever reads them, and nothing on the AVR fails to compile if one is
mistyped. A fat-fingered zero (30000 -> 3000, 60000 -> 6000) silently turns the
SLEEP recovery poll into a bus-hammering loop, or cuts the Orin's rail 6 s into a
`shutdown -h now` that needed 60 s. The only way anyone would notice today is the
bench test (GAP 3.C / docs/M16-POWER-BENCH-TEST.md), which is a human running a
lab PSU. This file makes that class of typo cost nothing to catch: it pins each
constant to the number the grant spec asks for, and cites the spec section per
value.

This is a parity guard, NOT behavioral coverage. Whether the firmware actually
blinks every 10 s or force-cuts at 60 s is a bench item; all this proves is that
the numbers the firmware was written against have not drifted. (A couple of cheap
"the constant is still wired to the behavior it names" source assertions are
included, because a pinned constant nobody reads is worthless.)

    RECOVERY follows the Appendix-C starting value of 26.4 V. AC 4h explicitly
    requires validation against the real M12 battery pair and an update if the
    resting-versus-loaded measurements justify a different threshold.

Text/regex against the C++ source rather than a compile, matching the repo's
source-guard pattern — no C/C++ is built in this
suite.

Deliberately NOT covered here: the FSM transition rules and typed WARN boundary
(covered by the direct native C++ suite), and the SLEEP-branch
recovery-poll wiring in loop() (test_sleep_recovery_parity.py).
"""
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_SENSORS_H = (_REPO / "firmware/arduino/sensors_config.h").read_text()
_INO = (_REPO / "firmware/arduino/arduino.ino").read_text()


def _define_int(name: str, text: str = None) -> int:
    """First integer of a #define, ignoring any U/L/UL suffix."""
    text = _SENSORS_H if text is None else text
    m = re.search(rf"#define\s+{name}\s+(\d+)", text)
    assert m, f"#define {name} not found in sensors_config.h"
    return int(m.group(1))


def _define_float(name: str, text: str = None) -> float:
    text = _SENSORS_H if text is None else text
    m = re.search(rf"#define\s+{name}\s+([0-9.]+)f?\b", text)
    assert m, f"#define {name} not found in sensors_config.h"
    return float(m.group(1))

def _typed_volts(name: str, text: str = None) -> float:
    text = _SENSORS_H if text is None else text
    m = re.search(
        rf"static\s+constexpr\s+Volts\s+{name}\s*\(\s*([0-9.]+)f?\s*\)",
        text,
    )
    assert m, f"typed Volts constant {name} not found in sensors_config.h"
    return float(m.group(1))


def _const_int(name: str, text: str = None) -> int:
    """`const int NAME = 50;` — the tick constants are consts, not #defines."""
    text = _SENSORS_H if text is None else text
    m = re.search(rf"const\s+\w+\s+{name}\s*=\s*(\d+)", text)
    assert m, f"const {name} not found in sensors_config.h"
    return int(m.group(1))


# --- low-power cadences (spec §3, AC 4f/4g) ----------------------------------
def test_recovery_poll_is_30s():
    # Spec §3 "Recovery check (~30 s)" / AC 4f "recovery checked ~every 30 s".
    ms = _define_int("POWER_RECOVERY_POLL_MS")
    assert ms == 30_000, (
        f"POWER_RECOVERY_POLL_MS={ms} ms; spec §3 / AC 4f call for ~30 s (30000). "
        "Shortening it hammers the Pack INA228 on an already-critical pack; "
        "lengthening it strands a recovered robot asleep. Retune deliberately, "
        "with the bench measurement (§8) to back it."
    )


def test_low_batt_blink_is_10s():
    # Spec §3 "Low-battery indication (~10 s)" / AC 4g "Every ~10 s ... splashes a
    # dead-battery icon on the OLED and blinks the Task 2 red LED".
    ms = _define_int("POWER_LOW_BATT_BLINK_MS")
    assert ms == 10_000, (
        f"POWER_LOW_BATT_BLINK_MS={ms} ms; spec §3 / AC 4g call for ~10 s (10000). "
        "This is the sleep-indicator cadence, deliberately NOT the 250 ms krab-UI "
        "rate — a fast blink drains a pack that is already below SOFT_CUT."
    )


def test_blink_cadence_gates_both_indicators():
    # AC 4g pairs the LED blink and the OLED splash on the SAME cadence; a pinned
    # constant nobody reads would be worthless, so prove both still use it.
    uses = _INO.count("POWER_LOW_BATT_BLINK_MS")
    assert uses >= 2, (
        f"POWER_LOW_BATT_BLINK_MS is referenced {uses}x in arduino.ino; AC 4g needs "
        "it gating BOTH the STATUS-LED blink and the OLED dead-battery splash in "
        "PowerController::lowPowerServices"
    )


# --- Orin power-down windows (spec §2 step 3, §4 force-off rule, AC 4c/4i) ----
def test_orin_force_off_is_60s():
    # Spec §2 SOFT_CUT step 3 "Wait up to 60 s for SHUTDOWN_ACK"; §4 force-off rule
    # + AC 4i "if the Orin doesn't ack or stop telemetry within 60 s ... force-cuts".
    ms = _define_int("ORIN_FORCE_OFF_MS")
    assert ms == 60_000, (
        f"ORIN_FORCE_OFF_MS={ms} ms; spec §2/§4 and AC 4c/4i fix the no-response "
        "window at 60 s (60000). Cutting the rail early can corrupt the Jetson's "
        "filesystem mid-poweroff; cutting late drains a pack in shutdown."
    )


def test_acked_off_window_is_15s_and_shorter_than_force_off():
    # NOT a spec number: the spec only bounds the wait at <=60 s (§2 step 3). The
    # 15 s post-SHUTDOWN_ACK grace is a repo refinement (M16 review D19) — once the
    # Orin has ACKed it is already running `poweroff`, so only a flush window is
    # needed. Pinned here because it is exactly the kind of number nobody re-derives.
    acked = _define_int("ORIN_ACKED_OFF_MS")
    force = _define_int("ORIN_FORCE_OFF_MS")
    assert acked == 15_000, (
        f"ORIN_ACKED_OFF_MS={acked} ms; D19 sets the post-ACK grace at 15 s (15000), "
        "enough for a clean Jetson poweroff + filesystem flush."
    )
    assert acked < force, (
        f"ORIN_ACKED_OFF_MS ({acked}) must stay strictly below ORIN_FORCE_OFF_MS "
        f"({force}) — the whole point of D19 is that an ACK *shortens* the wait. "
        "If it is not shorter, SHUTDOWN_ACK buys nothing."
    )
    # Both windows are measured from the same softCutEnteredMs stamp; the ACK only
    # selects which deadline applies. Prove that selection still exists.
    assert re.search(
        r"shutdownAcked\s*\?\s*ORIN_ACKED_OFF_MS\s*:\s*ORIN_FORCE_OFF_MS", _INO
    ), (
        "arduino.ino no longer picks the force-off deadline with "
        "`shutdownAcked ? ORIN_ACKED_OFF_MS : ORIN_FORCE_OFF_MS`; one of the two "
        "windows has been orphaned"
    )


# --- cut debounce counts (no spec number; repo-chosen, tick-derived) ---------
def test_cut_debounce_is_4_ticks():
    # The spec specifies no debounce (it assumes an instantaneous threshold
    # compare); the debounce is a repo addition against LiFePO4 sag under current
    # spikes. 4 ticks at the 20 Hz telemetry tick ~= 200 ms sustained.
    ticks = _define_int("POWER_CUT_DEBOUNCE_TICKS")
    assert ticks == 4, (
        f"POWER_CUT_DEBOUNCE_TICKS={ticks}; the sag filter is sized at 4 ticks "
        "(~200 ms at 20 Hz). Lower it and a current spike trips a shutdown; raise "
        "it and a real collapse is ridden out for longer than the pack can afford."
    )


def test_debounce_windows_are_sane_in_wall_clock():
    # The tick counts only mean anything relative to the telemetry period; if
    # TELEMETRY_INTERVAL_MS is ever retuned, these windows move with it silently.
    period = _const_int("TELEMETRY_INTERVAL_MS")
    cut_ms = period * _define_int("POWER_CUT_DEBOUNCE_TICKS")
    assert 100 <= cut_ms <= 1_000, (
        f"cut debounce is {cut_ms} ms ({period} ms tick x ticks) — outside the "
        "100 ms..1 s band a protective shutdown filter can live in"
    )


# --- Appendix-C thresholds: pin the divergence set to exactly {RECOVERY} -----
def test_appendix_c_thresholds_still_match_the_spec_table():
    """The protective cut thresholds are unchanged from Appendix C (§7).

    Only RECOVERY diverges (see the module docstring and the test below). If one
    of these four starts failing, either the pack was bench-validated (AC 4h —
    update the number here AND the spec table) or something drifted by accident.
    """
    assert _typed_volts("PACK_HARD_CUT_THRESHOLD") == 22.4
    assert _typed_volts("PACK_OVER_VOLT_THRESHOLD") == 29.6


def test_recovery_threshold_matches_appendix_c_until_bench_validation():
    """Appendix C starts RECOVERY at 26.4 V; AC 4h may update it after measurement."""
    v = _typed_volts("PACK_RECOVERY_THRESHOLD")
    assert v == 26.4
    # The spec's real invariant behind the number (AC 4f, §1): RECOVERY must sit at
    # least 0.4 V above SOFT_CUT so a pack hovering at the knee cannot chatter
    # sleep/resume, so assert it independently of the starting value.
    soft = _typed_volts("PACK_SOFT_CUT_THRESHOLD")
    assert v - soft >= 0.4, (
        f"RECOVERY ({v} V) is only {v - soft:.2f} V above SOFT_CUT ({soft} V); "
        "AC 4f requires >= 0.4 V hysteresis to stop sleep/resume chatter"
    )
    # ...and it must stay below the one-way over-voltage cutout, or a resuming pack
    # would have to pass through the fault region to wake.
    assert v < _typed_volts("PACK_OVER_VOLT_THRESHOLD"), (
        "PACK_RECOVERY_THRESHOLD must sit below PACK_OVER_VOLT_THRESHOLD"
    )
