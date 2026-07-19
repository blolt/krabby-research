"""Firmware <-> sim parity for the OLED battery-gauge voltage window.

The volts->bar-fraction clamp is duplicated on purpose: krab.py (the Python sim,
RENDER_SPEC §7) holds BATT_EMPTY_V / BATT_FULL_V, and arduino.ino's OLED port
holds OLED_BATT_EMPTY_V / OLED_BATT_FULL_V, applied by oledBatteryFraction().
Nothing else pins that the two windows agree, so a silent edit to one side would
drift the physical panel away from the sim/goldens. This test reads the firmware
constants straight out of arduino.ino and asserts they equal the Python ones.
"""
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_SIM = _REPO / "firmware" / "oled_sim"
if str(_SIM) not in sys.path:
    sys.path.insert(0, str(_SIM))

import krab  # noqa: E402  (sys.path set above; sim lives outside the package tree)

_ARDUINO_INO = _REPO / "firmware" / "arduino" / "arduino.ino"

# Matches e.g. `static const float OLED_BATT_EMPTY_V = 12.0f, OLED_BATT_FULL_V = 13.4f;`
_WINDOW_RE = re.compile(
    r"OLED_BATT_EMPTY_V\s*=\s*([0-9.]+)f?\s*,\s*OLED_BATT_FULL_V\s*=\s*([0-9.]+)f?"
)


def _firmware_batt_window() -> tuple[float, float]:
    text = _ARDUINO_INO.read_text()
    m = _WINDOW_RE.search(text)
    assert m is not None, "OLED_BATT_EMPTY_V/OLED_BATT_FULL_V not found in arduino.ino"
    return float(m.group(1)), float(m.group(2))


def test_batt_gauge_window_matches_firmware():
    empty_v, full_v = _firmware_batt_window()
    assert empty_v == krab.BATT_EMPTY_V
    assert full_v == krab.BATT_FULL_V
