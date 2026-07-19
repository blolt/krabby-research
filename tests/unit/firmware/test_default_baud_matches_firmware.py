"""The host serial rate must equal the firmware's, from a single source.

M16 raised the MCU link from 115200 to 250000 baud. Firmware defines it once
(BAUD_RATE in arduino.ino); every host that opens the port imports
firmware.krabby_mcu.DEFAULT_BAUD. A drift between the two produces a fleet that
talks past itself with no compile error, so pin the equality here and forbid a
bare 250000 literal creeping back into the host modules that changed.
"""
import re
from pathlib import Path

from firmware.krabby_mcu import DEFAULT_BAUD
from firmware.interfaces.joint_telemetry import TELEMETRY_LINE_PREFIXES

FIRMWARE_DIR = Path(__file__).resolve().parents[3] / "firmware"
REPO = FIRMWARE_DIR.parent


def test_default_baud_matches_firmware_baud_rate():
    ino = (FIRMWARE_DIR / "arduino" / "arduino.ino").read_text()
    m = re.search(r"#define\s+BAUD_RATE\s+(\d+)", ino)
    assert m, "BAUD_RATE #define not found in arduino.ino"
    assert int(m.group(1)) == DEFAULT_BAUD


def test_telemetry_prefixes_match_firmware_role_names():
    # TELEMETRY_LINE_PREFIXES is the host's copy of the leader's line-start
    # punctuation; it must equal roleName()'s returned tokens with the trailing
    # ';' the firmware prints after them. The returned strings carry the exact
    # wire punctuation, including the "LEFT " padding (hence "LEFT ;").
    ino = (FIRMWARE_DIR / "arduino" / "arduino.ino").read_text()
    returns = re.findall(r'case\s+ROLE_\w+:\s*return\s+"([^"]+)"', ino)
    assert returns, "roleName() case returns not found in arduino.ino"
    assert {name + ";" for name in returns} == set(TELEMETRY_LINE_PREFIXES)


def test_host_modules_do_not_hardcode_the_baud_literal():
    # These modules open the MCU port; they must reference DEFAULT_BAUD, not a
    # bare 250000. (arduino.ino owns the firmware #define; krabby_mcu.py owns
    # the DEFAULT_BAUD definition; standalone bench tools are exempt.)
    literal = str(DEFAULT_BAUD)
    for rel in [
        "cli.py",
        "gui/app.py",
        "gui/__main__.py",
        "../hal/server/jetson/krabby_mcusdk.py",
        "../hal/server/jetson/hal_server.py",
    ]:
        text = (FIRMWARE_DIR / rel).read_text()
        assert literal not in text, f"{rel} hardcodes {literal}; import DEFAULT_BAUD"
