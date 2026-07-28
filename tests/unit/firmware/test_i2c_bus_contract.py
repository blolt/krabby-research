"""Source-contract coverage for the Task 1 leader I2C bus setup.

The Arduino Wire calls cannot execute in the host Python suite. These tests pin
the small compile-time contract instead: a named 100 kHz constant, initialization
order, leader gating, and reuse of the production constants by the bench scanner.
"""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ARDUINO = REPO_ROOT / "firmware" / "arduino" / "arduino.ino"
SENSORS_CONFIG = REPO_ROOT / "firmware" / "arduino" / "sensors_config.h"
I2C_SCANNER = (
    REPO_ROOT
    / "firmware"
    / "bench_sketches"
    / "i2c_scanner"
    / "i2c_scanner.ino"
)


def _function_body(source: str, signature: str) -> str:
    """Return one C++ function body using balanced braces."""
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def test_i2c_clock_is_a_named_100_khz_constant():
    config = SENSORS_CONFIG.read_text()

    match = re.search(
        r"^#define\s+I2C_BUS_CLOCK_HZ\s+(\d+)UL\s*$",
        config,
        flags=re.MULTILINE,
    )

    assert match is not None
    assert int(match.group(1)) == 100_000


def test_leader_bus_setup_uses_named_constants_in_required_order():
    source = ARDUINO.read_text()
    body = _function_body(source, "static void imuSetup(bool allowBiasCapture)")

    begin = body.index("Wire.begin();")
    clock = body.index("Wire.setClock(I2C_BUS_CLOCK_HZ);")
    timeout = body.index("Wire.setWireTimeout(I2C_WIRE_TIMEOUT_US, true);")
    sensor_begin = body.index("initializeImu(")

    assert begin < clock < timeout < sensor_begin
    assert body.count("Wire.begin();") == 1
    assert body.count("Wire.setClock(") == 1
    assert "Wire.setClock(100000" not in body


def test_setup_initializes_i2c_only_through_the_sensor_cluster_gate():
    source = ARDUINO.read_text()
    setup = _function_body(source, "void setup()")
    gate = _function_body(source, "static inline bool isI2CClusterBoard()")

    assert re.search(
        r"if\s*\(\s*isI2CClusterBoard\(\)\s*\)\s*"
        r"imuSetup\(true\);",
        setup,
    )
    assert setup.count("imuSetup(") == 1
    assert "currentRole == ROLE_FRONT" in gate
    assert "currentRole == ROLE_UNKNOWN" in gate
    assert "ROLE_LEFT" not in gate
    assert "ROLE_RIGHT" not in gate


def test_i2c_scanner_named_constants_match_production_bus_contract():
    config = SENSORS_CONFIG.read_text()
    scanner = I2C_SCANNER.read_text()

    production_clock = re.search(
        r"^#define\s+I2C_BUS_CLOCK_HZ\s+(\d+)UL\s*$",
        config,
        flags=re.MULTILINE,
    )
    production_timeout = re.search(
        r"^#define\s+I2C_WIRE_TIMEOUT_US\s+(\d+)UL\s*$",
        config,
        flags=re.MULTILINE,
    )
    scanner_clock = re.search(
        r"^static const unsigned long SCANNER_I2C_CLOCK_HZ = (\d+)UL;\s*$",
        scanner,
        flags=re.MULTILINE,
    )
    scanner_timeout = re.search(
        r"^static const unsigned long SCANNER_I2C_TIMEOUT_US = (\d+)UL;\s*$",
        scanner,
        flags=re.MULTILINE,
    )

    assert production_clock is not None
    assert production_timeout is not None
    assert scanner_clock is not None
    assert scanner_timeout is not None
    assert scanner_clock.group(1) == production_clock.group(1)
    assert scanner_timeout.group(1) == production_timeout.group(1)
    assert "Wire.setClock(SCANNER_I2C_CLOCK_HZ);" in scanner
    assert "Wire.setWireTimeout(SCANNER_I2C_TIMEOUT_US, true);" in scanner
    assert "Wire.setClock(100000" not in scanner
    assert "Wire.setWireTimeout(10000" not in scanner


def test_imu_initialization_failures_have_distinct_diagnostics():
    source = ARDUINO.read_text()
    setup = _function_body(source, "static void imuSetup(bool allowBiasCapture)")
    logger = _function_body(source, "static void logImuInitFailure(ImuInitResult result)")

    assert "imuValid = initResult == IMU_INIT_OK;" in setup
    assert "if (!imuValid)" in setup
    assert "logImuInitFailure(initResult);" in setup
    assert "IMU_INIT_NOT_DETECTED" in logger
    assert "not detected at 0x" in logger
    assert "LSM6DSO_I2C_ADDR" in logger
    assert "LSM6DSO_I2C_ADDR_ALT" in logger
    assert "IMU_INIT_CONFIGURATION_FAILED" in logger
    assert "detected but register configuration failed" in logger
    assert "detection or configuration failed" not in logger


def test_imu_init_result_drives_the_emitted_valid_flag():
    source = ARDUINO.read_text()
    setup = _function_body(source, "static void imuSetup(bool allowBiasCapture)")
    telemetry = _function_body(source, "static void imuAppendTelemetry(Print& out)")

    result = setup.index("ImuInitResult initResult = initializeImu(")
    derive_valid = setup.index("imuValid = initResult == IMU_INIT_OK;")
    failure_gate = setup.index("if (!imuValid)")
    failure_return = setup.index("return;", failure_gate)

    assert result < derive_valid < failure_gate < failure_return
    assert setup.count("imuValid =") == 1
    assert "bool fresh = false;" in telemetry
    assert "if (imuValid)" in telemetry
    assert "out.print(fresh ? 1 : 0);" in telemetry
