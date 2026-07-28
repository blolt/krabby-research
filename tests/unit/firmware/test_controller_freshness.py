"""Source-contract coverage for telemetry-qualified follower freshness."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ARDUINO_DIR = REPO_ROOT / "firmware" / "arduino"


def test_left_and_right_forwarders_use_their_own_role_and_tracker():
    source = (ARDUINO_DIR / "arduino.ino").read_text()

    assert source.count(
        "&leftPartialPos, roleName(ROLE_LEFT), &followerLeftFreshness"
    ) == 2
    assert source.count(
        "&rightPartialPos, roleName(ROLE_RIGHT), &followerRightFreshness"
    ) == 2
    assert "followerLeftLastMs" not in source
    assert "followerRightLastMs" not in source
