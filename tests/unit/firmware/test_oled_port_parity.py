"""Secondary firmware <-> sim contract for the OLED battery-gauge window.

The direct Unity test executes BatteryLevel, which is the production C++
calculation. This narrower source check only pins the intentionally duplicated
Python simulator endpoints to that C++ rendering contract.
"""
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_SIM = _REPO / "firmware" / "oled_sim"
if str(_SIM) not in sys.path:
    sys.path.insert(0, str(_SIM))

import krab  # noqa: E402  (sys.path set above; sim lives outside the package tree)

_BATTERY_LEVEL_HEADER = _REPO / "firmware" / "arduino" / "battery_level.h"

_EMPTY_RE = re.compile(r"BATTERY_LEVEL_EMPTY_VOLTS\s*=\s*([0-9.]+)f?")
_FULL_RE = re.compile(r"BATTERY_LEVEL_FULL_VOLTS\s*=\s*([0-9.]+)f?")


def _firmware_batt_window() -> tuple[float, float]:
    text = _BATTERY_LEVEL_HEADER.read_text()
    empty = _EMPTY_RE.search(text)
    full = _FULL_RE.search(text)
    assert empty is not None, "BATTERY_LEVEL_EMPTY_VOLTS not found"
    assert full is not None, "BATTERY_LEVEL_FULL_VOLTS not found"
    return float(empty.group(1)), float(full.group(1))


def test_batt_gauge_window_matches_firmware():
    empty_v, full_v = _firmware_batt_window()
    assert empty_v == krab.BATT_EMPTY_V
    assert full_v == krab.BATT_FULL_V
