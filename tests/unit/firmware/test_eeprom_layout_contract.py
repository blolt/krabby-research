"""Persistent AVR EEPROM-map contract for the M16 IMU allocation."""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ARDUINO = REPO_ROOT / "firmware" / "arduino" / "arduino.ino"
ACTUATOR_MANAGER = REPO_ROOT / "firmware" / "arduino" / "actuator_manager.h"
SENSORS_CONFIG = REPO_ROOT / "firmware" / "arduino" / "sensors_config.h"

AVR_INT_BYTES = 2
AVR_FLOAT_BYTES = 4
UINT8_BYTES = 1


def _integer_define(source: str, name: str) -> int:
    match = re.search(
        rf"^#define\s+{name}\s+(0x[0-9A-Fa-f]+|\d+)\s*$",
        source,
        flags=re.MULTILINE,
    )
    assert match is not None, f"missing integer define: {name}"
    return int(match.group(1), 0)


def _range(start: int, size: int) -> range:
    return range(start, start + size)


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    raise AssertionError(f"unterminated function: {signature}")


def test_m16_imu_eeprom_region_is_explicit_and_non_colliding():
    arduino = ARDUINO.read_text()
    actuator_manager = ACTUATOR_MANAGER.read_text()
    sensors = SENSORS_CONFIG.read_text()

    joint_start = 0
    joint_size = (6 + 6 + 1) * AVR_INT_BYTES
    role_start = _integer_define(arduino, "EEPROM_ROLE_ADDR")
    role_size = 2  # sentinel byte followed by the uint8_t BoardRole value
    imu_start = _integer_define(sensors, "EEPROM_IMU_CAL_ADDR")
    imu_size = _integer_define(sensors, "EEPROM_IMU_CAL_SIZE")
    imu_struct_size = (
        2 * UINT8_BYTES  # magic + schema
        + 3 * AVR_FLOAT_BYTES  # gyroBiasDps
        + 3 * AVR_FLOAT_BYTES  # accelBiasG
    )

    assert "int minVals[6];" in actuator_manager
    assert "int maxVals[6];" in actuator_manager
    assert "int magic;" in actuator_manager
    assert "uint8_t magic;" in arduino
    assert "uint8_t schema;" in arduino
    assert "float gyroBiasDps[3];" in arduino
    assert "float accelBiasG[3];" in arduino
    assert imu_size == imu_struct_size

    regions = {
        "joint": _range(joint_start, joint_size),
        "role": _range(role_start, role_size),
        "imu": _range(imu_start, imu_size),
    }
    assert (regions["joint"].start, regions["joint"].stop - 1) == (0, 25)
    assert (regions["role"].start, regions["role"].stop - 1) == (32, 33)
    assert (regions["imu"].start, regions["imu"].stop - 1) == (40, 65)

    names = tuple(regions)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1 :]:
            assert set(regions[left_name]).isdisjoint(regions[right_name])

    assert "#define EEPROM_SENSOR_CAL_NEXT_ADDR " \
           "(EEPROM_IMU_CAL_ADDR + EEPROM_IMU_CAL_SIZE)" in sensors
    assert imu_start + imu_size == 66


def test_imu_calibration_write_is_invalid_first_valid_last_and_verified():
    arduino = ARDUINO.read_text()
    capture = _function_body(arduino, "static void imuCaptureGyroBias()")
    ordered_steps = [
        "imuCal.magic = EEPROM_IMU_CAL_INVALID_MAGIC;",
        "imuCal.schema = EEPROM_IMU_CAL_SCHEMA;",
        "EEPROM.put(EEPROM_IMU_CAL_ADDR, imuCal);",
        "imuCal.magic = EEPROM_IMU_CAL_MAGIC;",
        "EEPROM.update(EEPROM_IMU_CAL_ADDR, EEPROM_IMU_CAL_MAGIC);",
        "EEPROM.get(EEPROM_IMU_CAL_ADDR, imuCal);",
        "if (!imuCalPlausible())",
        'Serial.println("IMU CAL: gyro bias captured and saved to EEPROM.");',
    ]
    positions = [capture.index(step) for step in ordered_steps]

    assert positions == sorted(positions)
    assert "imuCal = ImuCalData{};" in capture
    assert 'Serial.println(F("IMU CAL: EEPROM verification failed;' in capture
    assert _integer_define(
        SENSORS_CONFIG.read_text(), "EEPROM_IMU_CAL_INVALID_MAGIC"
    ) != _integer_define(SENSORS_CONFIG.read_text(), "EEPROM_IMU_CAL_MAGIC")


def test_imu_calibration_rejects_every_persisted_failure_class():
    arduino = ARDUINO.read_text()
    plausible = _function_body(arduino, "static bool imuCalPlausible()\n{")
    setup = _function_body(arduino, "static void imuSetup(bool allowBiasCapture)")

    assert "imuCal.magic != EEPROM_IMU_CAL_MAGIC" in plausible
    assert "imuCal.schema != EEPROM_IMU_CAL_SCHEMA" in plausible
    assert "!isfinite(imuCal.gyroBiasDps[a])" in plausible
    assert "fabs(imuCal.gyroBiasDps[a]) > IMU_CAL_MAX_BIAS_DPS" in plausible
    assert "!isfinite(imuCal.accelBiasG[a])" in plausible
    assert "EEPROM.get(EEPROM_IMU_CAL_ADDR, imuCal);" in setup
    assert "if (imuCalPlausible())" in setup
    assert "imuCal = ImuCalData{};" in setup
    assert "if (allowBiasCapture)" in setup
    assert "imuCaptureGyroBias();" in setup
