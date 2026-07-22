"""Make the OLED sim package importable to these tests.

The render sim lives in firmware/oled_sim/ (krab.py + ssd1306.py), outside the
normal package tree, so add it to sys.path for the render test modules.
"""
import sys
from pathlib import Path

import pytest

_SIM = Path(__file__).resolve().parents[3] / "firmware" / "oled_sim"
if str(_SIM) not in sys.path:
    sys.path.insert(0, str(_SIM))


def pytest_collection_modifyitems(config, items):
    """Skip the whole oled_sim render suite when the SparkFun font headers can't
    be resolved (no QWIIC_OLED_LIB_DIR, no fetched repo libs, no ~/Documents
    install) -- e.g. Docker `make test` or CI on a clean HOME. Deterministic
    skip, not an import error; materialize the libs with
    firmware/scripts/fetch_arduino_libs.py (or set QWIIC_OLED_LIB_DIR) to run them.
    """
    import ssd1306

    if ssd1306.fonts_available():
        return
    skip = pytest.mark.skip(
        reason="SparkFun OLED font headers not found; run "
        "firmware/scripts/fetch_arduino_libs.py or set QWIIC_OLED_LIB_DIR"
    )
    for item in items:
        item.add_marker(skip)
