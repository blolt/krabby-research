"""Source-contract coverage for role-election to OLED controller-slot mapping."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ARDUINO_DIR = REPO_ROOT / "firmware" / "arduino"


def test_oled_applies_freshness_after_role_slot_mapping():
    source = (ARDUINO_DIR / "arduino.ino").read_text()
    start = source.index("static void oledRenderLive()")
    end = source.index("\n}", start) + 2
    render = source[start:end]

    mapping = render.index("controllerSlotLinks(")
    front = render.index("s.front = slots.frontLocal;")
    left = render.index("s.left = controllerTelemetryIsFresh(")
    left_slot = render.index("slots.leftAssigned", left)
    right = render.index("s.right = controllerTelemetryIsFresh(")
    right_slot = render.index("slots.rightAssigned", right)

    assert mapping < front < left < left_slot < right < right_slot
    assert "s.front = true;" not in render
    assert "leftSerial  &&" not in render
    assert "rightSerial &&" not in render
