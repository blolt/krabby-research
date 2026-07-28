"""Source-contract coverage for firmware telemetry-line construction."""

import re
from dataclasses import fields
from pathlib import Path

from firmware.interfaces.joint_telemetry import (
    ImuTelemetry,
    ParsedTelemetry,
    TELEMETRY_LINE_PREFIXES,
    parse_telemetry_line,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
ARDUINO = REPO_ROOT / "firmware" / "arduino" / "arduino.ino"
ACTUATOR_MANAGER = REPO_ROOT / "firmware" / "arduino" / "actuator_manager.h"
PROTOCOL = REPO_ROOT / "firmware" / "arduino" / "telemetry_protocol.h"


def _function_body(source: str, signature: str, occurrence: int = 0) -> str:
    starts = [match.start() for match in re.finditer(re.escape(signature), source)]
    assert starts, f"missing function: {signature}"
    start = starts[occurrence]
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


def _char_constant(source: str, name: str) -> str:
    match = re.search(
        rf"^static const char {name} = '(.)';$",
        source,
        flags=re.MULTILINE,
    )
    assert match is not None
    return match.group(1)


def _string_constant(source: str, name: str) -> str:
    match = re.search(
        rf'^static const char {name}\[\] = "([^"]+)";$',
        source,
        flags=re.MULTILINE,
    )
    assert match is not None
    return match.group(1)


def test_firmware_protocol_constants_match_the_host_contract():
    protocol = PROTOCOL.read_text()

    assert _char_constant(protocol, "TELEMETRY_SEGMENT_DELIMITER") == ";"
    assert _char_constant(protocol, "TELEMETRY_FIELD_DELIMITER") == " "
    assert _string_constant(protocol, "IMU_TELEMETRY_TAG") == ImuTelemetry.TAG


def test_role_prefix_bytes_remain_the_pre_m16_wire_contract():
    source = ARDUINO.read_text()
    role_name = _function_body(source, "static const char* roleName(BoardRole r)")
    emitted_names = dict(
        re.findall(r'case (ROLE_\w+):\s*return "([^"]+)";', role_name)
    )
    expected_names = {
        "ROLE_UNKNOWN": "UNKWN",
        "ROLE_FRONT": "FRONT",
        "ROLE_LEFT": "LEFT ",
        "ROLE_RIGHT": "RIGHT",
    }
    expected_prefixes = ("FRONT;", "UNKWN;", "LEFT ;", "RIGHT;")

    assert emitted_names == expected_names
    assert TELEMETRY_LINE_PREFIXES == expected_prefixes
    for prefix in expected_prefixes:
        assert parse_telemetry_line(prefix) == ParsedTelemetry()


def test_leader_appends_exactly_one_imu_segment_after_joints_before_newline():
    source = ARDUINO.read_text()
    loop = _function_body(source, "void loop()")

    joints = loop.index("actuatorManager->printTelemetry(*mainSerial);")
    imu = loop.index("imuAppendTelemetry(*mainSerial);")
    newline = loop.index("mainSerial->println();")

    assert joints < imu < newline
    assert loop.count("imuAppendTelemetry(*mainSerial);") == 1
    assert re.search(
        r"if\s*\(\s*isI2CClusterBoard\(\)\s*\)\s*"
        r"imuAppendTelemetry\(\*mainSerial\);",
        loop,
    )


def test_imu_segment_uses_named_delimiters_and_tag():
    source = ARDUINO.read_text()
    telemetry = _function_body(source, "static void imuAppendTelemetry(Print& out)")
    manager = ACTUATOR_MANAGER.read_text()

    segment = telemetry.index("out.print(TELEMETRY_SEGMENT_DELIMITER);")
    tag = telemetry.index("out.print(IMU_TELEMETRY_TAG);")
    field = telemetry.index("out.print(TELEMETRY_FIELD_DELIMITER);")

    assert segment < tag < field
    assert 'out.print(";IMU ")' not in telemetry
    assert "out.print(TELEMETRY_SEGMENT_DELIMITER);" in manager
    assert "out.print(';')" not in manager


def test_m16_does_not_add_controller_role_to_telemetry_payload():
    source = ARDUINO.read_text()
    telemetry = _function_body(source, "static void imuAppendTelemetry(Print& out)")
    parsed = parse_telemetry_line(
        "FRONT; FLHY 0.123 512 12 1 0 0 128 3;"
        "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 1"
    )

    assert "controller_role" not in {item.name for item in fields(ParsedTelemetry)}
    assert "controller_role" not in {item.name for item in fields(ImuTelemetry)}
    assert not hasattr(parsed, "controller_role")
    assert "controller_role" not in telemetry
    assert parsed.imu is not None
    assert len(parsed.joints) == 1


def test_existing_joint_serialization_keeps_field_order_and_no_terminator():
    manager = ACTUATOR_MANAGER.read_text()
    actuator = _function_body(
        manager, "void printTelemetry(Print& out) const", occurrence=0
    )
    aggregate = _function_body(
        manager, "void printTelemetry(Print& out) const", occurrence=-1
    )

    expected_fields = [
        "out.print(name);",
        "out.print(getPos(), 3);",
        "out.print((int)avgPot);",
        "out.print((int)avgIS);",
        "out.print(en);",
        "out.print(en);",
        "out.print(currentPwm < 0 ? abs(currentPwm) : 0);",
        "out.print(currentPwm > 0 ? currentPwm : 0);",
        "out.print(hallHwGetEdgeCount((uint8_t)hallSlot));",
    ]
    positions = [actuator.index(field) for field in expected_fields]

    assert positions == sorted(positions)
    assert actuator.count("out.print(TELEMETRY_FIELD_DELIMITER);") == 8
    assert "out.println" not in actuator
    assert "out.println" not in aggregate
    assert "if (i) out.print(TELEMETRY_SEGMENT_DELIMITER);" in aggregate
    assert aggregate.index("if (i) out.print") < aggregate.index(
        "actuators[i]->printTelemetry(out);"
    )


def test_loop_owns_exactly_one_line_ending_after_optional_imu():
    source = ARDUINO.read_text()
    tick = _function_body(
        source, "if (millis() - lastTelemetry >= TELEMETRY_INTERVAL_MS)"
    )
    expected_order = [
        "mainSerial->print(roleName(currentRole));",
        "mainSerial->print(TELEMETRY_SEGMENT_DELIMITER);",
        "mainSerial->print(TELEMETRY_FIELD_DELIMITER);",
        "actuatorManager->printTelemetry(*mainSerial);",
        "imuAppendTelemetry(*mainSerial);",
        "mainSerial->println();",
    ]
    positions = [tick.index(statement) for statement in expected_order]

    assert positions == sorted(positions)
    assert tick.count("mainSerial->println();") == 1


def test_forwarded_follower_lines_are_reemitted_without_prefix_reconstruction():
    source = ARDUINO.read_text()
    forward = _function_body(source, "void forwardFullLines(")

    assert "to->println(partial);" in forward
    assert "roleName(" not in forward
    assert "imuAppendTelemetry(" not in forward


def test_appending_imu_preserves_every_existing_joint_field():
    joint = "FLHY 0.123 512 12 1 0 0 128 3"
    baseline = parse_telemetry_line(f"FRONT; {joint}").joints
    fresh = parse_telemetry_line(
        f"FRONT; {joint};IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 1"
    ).joints
    stale = parse_telemetry_line(
        f"FRONT; {joint};IMU 0.000 0.000 0.000 0.0000 0.0000 0.0000 0.0 0"
    ).joints

    assert fresh == baseline
    assert stale == baseline


def _pre_m16_parse_joints(line: str):
    """Frozen origin/pr/m16-base JointTelemetry.parse_line behavior.

    Keep this independent of the current parser: its purpose is to execute the
    parser deployed before the IMU type existed and prove the appended segment
    cannot change its joint result or raise.
    """
    joints = []
    role_prefixes = ("JT", "FRONT", "UNKNOWN", "LEFT", "RIGHT")
    for segment in line.strip().split(";"):
        tokens = segment.strip().split()
        if not tokens:
            continue
        if tokens[0] in role_prefixes:
            tokens = tokens[1:] if tokens[0] == "JT" else None
        if not tokens or len(tokens) != 9:
            continue
        name, pos, pot, current, en_left, en_right, pwm_left, pwm_right, saf = tokens
        try:
            joints.append(
                (
                    name,
                    float(pos),
                    int(pot),
                    int(current),
                    (int(en_left), int(en_right)),
                    (int(pwm_left), int(pwm_right)),
                    int(saf),
                )
            )
        except ValueError:
            continue
    return joints


def test_pre_m16_parser_ignores_fresh_and_stale_imu_segments():
    protocol = PROTOCOL.read_text()
    segment_delimiter = _char_constant(protocol, "TELEMETRY_SEGMENT_DELIMITER")
    tag = _string_constant(protocol, "IMU_TELEMETRY_TAG")
    joint = "FLHY 0.123 512 12 1 0 0 128 3"
    baseline = f"FRONT{segment_delimiter} {joint}"
    fresh_imu = f"{tag} 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 1"
    stale_imu = f"{tag} 0.000 0.000 0.000 0.0000 0.0000 0.0000 0.0 0"
    expected = _pre_m16_parse_joints(baseline)

    assert len(expected) == 1
    assert _pre_m16_parse_joints(
        f"{baseline}{segment_delimiter}{fresh_imu}"
    ) == expected
    assert _pre_m16_parse_joints(
        f"{baseline}{segment_delimiter}{stale_imu}"
    ) == expected
