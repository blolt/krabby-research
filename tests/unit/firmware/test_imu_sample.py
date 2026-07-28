"""Source-contract coverage for the one-transaction LSM6DSO sample boundary."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ARDUINO_DIR = REPO_ROOT / "firmware" / "arduino"


def test_telemetry_uses_one_burst_and_no_per_field_accessors():
    source = (ARDUINO_DIR / "arduino.ino").read_text()
    start = source.index("static void imuAppendTelemetry(Print& out)")
    end = source.index("\n}", start) + 2
    telemetry = source[start:end]

    assert telemetry.count("readLsm6dsoOutputSample(") == 1
    valid_gate = telemetry.index("if (imuValid)")
    burst = telemetry.index("readLsm6dsoOutputSample(")
    assert valid_gate < burst
    assert "readFloatAccel" not in telemetry
    assert "readFloatGyro" not in telemetry
    assert "readTempC" not in telemetry
