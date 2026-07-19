"""C++/Python parity guard for the power FSM (M16 Task 4).

The pure FSM lives twice — firmware/arduino/power_fsm.h (+ its thresholds in
sensors_config.h) on the AVR, and firmware/interfaces/power_fsm.py as the
host-testable mirror — with no build-time link between them: today they agree only
because comments say "keep in sync". These tests give that invariant teeth by
reading the C++ headers as text and asserting the numbers/enums/wire-tokens match
the Python. A one-sided edit now fails a test instead of silently drifting.

Deliberately text/regex, not a compile: the point is to catch a divergence a
Python-only test never sees. (From the m16-critique-sweep test-gap + cross-cut
findings.)
"""
import re
from pathlib import Path

from firmware.interfaces import power_fsm as pf
from firmware.interfaces.joint_telemetry import PowerState
from firmware.interfaces.power_messages import (
    POWER_MSG_PREFIX,
    POWER_MSG_SCHEMA,
    PowerMessageType,
    PowerReason,
)

_REPO = Path(__file__).resolve().parents[3]
_SENSORS_H = (_REPO / "firmware/arduino/sensors_config.h").read_text()
_FSM_H = (_REPO / "firmware/arduino/power_fsm.h").read_text()


def _define_float(name: str, text: str) -> float:
    m = re.search(rf"#define\s+{name}\s+([0-9.]+)f?\b", text)
    assert m, f"{name} not found in header"
    return float(m.group(1))


def _define_int(name: str, text: str) -> int:
    m = re.search(rf"#define\s+{name}\s+(\d+)", text)
    assert m, f"{name} not found in header"
    return int(m.group(1))


# --- thresholds: sensors_config.h #defines == power_fsm.py constants ----------
def test_pack_thresholds_match_python():
    assert _define_float("PACK_WARN_V", _SENSORS_H) == pf.PACK_WARN_V
    assert _define_float("PACK_SOFT_CUT_V", _SENSORS_H) == pf.PACK_SOFT_CUT_V
    assert _define_float("PACK_HARD_CUT_V", _SENSORS_H) == pf.PACK_HARD_CUT_V
    assert _define_float("PACK_OVER_VOLT_V", _SENSORS_H) == pf.PACK_OVER_VOLT_V
    assert _define_float("PACK_RECOVERY_V", _SENSORS_H) == pf.PACK_RECOVERY_V


def test_debounce_tick_counts_match_python():
    assert _define_int("POWER_CUT_DEBOUNCE_TICKS", _SENSORS_H) == pf.POWER_CUT_DEBOUNCE_TICKS
    assert _define_int("POWER_OVER_VOLT_DEBOUNCE_TICKS", _SENSORS_H) == pf.POWER_OVER_VOLT_DEBOUNCE_TICKS


# --- PowerState enum: power_fsm.h enum == joint_telemetry.PowerState ----------
def test_powerstate_enum_values_match():
    # C++ names are PWR_<NAME>; strip the prefix to compare with the Python enum.
    pairs = re.findall(r"PWR_(\w+)\s*=\s*(\d+)", _FSM_H)
    cpp = {name: int(val) for name, val in pairs}
    py = {s.name: int(s.value) for s in PowerState}
    assert cpp == py, f"C++ {cpp} != Python {py}"


# --- PWR wire lines: power_fsm.h literals == power_messages schema/type/reason -
def test_pwr_line_literals_match_python_protocol():
    lines = re.findall(r'#define\s+PWR_LINE_\w+\s+"([^"]+)"', _FSM_H)
    assert lines, "no PWR_LINE_* literals found in power_fsm.h"
    types = {t.value for t in PowerMessageType}
    reasons = {r.value for r in PowerReason}
    for line in lines:
        tok = line.split()
        assert tok[0] == POWER_MSG_PREFIX
        assert int(tok[1]) == POWER_MSG_SCHEMA, f"schema token drifted: {line!r}"
        assert tok[2] in types, f"unknown PWR type in {line!r}"
        assert len(tok) < 4 or tok[3] in reasons, f"unknown PWR reason in {line!r}"
