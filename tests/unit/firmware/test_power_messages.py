"""Power-state control message protocol (M16 Task 4, firmware/interfaces/power_messages.py).

Naming: test_<unit>_<condition>_<expected>, arrange/act/assert body structure.
"""
import pytest

from firmware.interfaces.power_messages import (
    EmergencyShutdownReason,
    POWER_MSG_SCHEMA,
    PowerMessage,
    PowerMessageType,
    PoweringDownReason,
    ResumingReason,
)


class TestFormatParseRoundTrip:
    @pytest.mark.parametrize(
        "msg",
        [
            PowerMessage(
                PowerMessageType.POWERING_DOWN,
                PoweringDownReason.UNDER_VOLTAGE_SOFT,
            ),
            PowerMessage(
                PowerMessageType.POWERING_DOWN,
                PoweringDownReason.MANUAL,
            ),
            PowerMessage(
                PowerMessageType.EMERGENCY_SHUTDOWN,
                EmergencyShutdownReason.HARD_CUT,
            ),
            PowerMessage(
                PowerMessageType.EMERGENCY_SHUTDOWN,
                EmergencyShutdownReason.OVER_VOLTAGE,
            ),
            PowerMessage(
                PowerMessageType.RESUMING,
                ResumingReason.VOLTAGE_RECOVERED,
            ),
            PowerMessage(PowerMessageType.SHUTDOWN_ACK),  # no reason
        ],
        ids=lambda m: f"{m.type.name}-{m.reason.name if m.reason else 'none'}",
    )
    def test_format_then_parse_recovers_the_message(self, msg):
        assert PowerMessage.parse(msg.format_line()) == msg

    def test_powering_down_line_is_the_expected_wire_shape(self):
        line = PowerMessage(
            PowerMessageType.POWERING_DOWN,
            PoweringDownReason.UNDER_VOLTAGE_SOFT,
        ).format_line()

        assert line == f"PWR {POWER_MSG_SCHEMA} POWERING_DOWN under_voltage_soft"

    def test_ack_line_omits_the_reason(self):
        assert PowerMessage(PowerMessageType.SHUTDOWN_ACK).format_line() == (
            f"PWR {POWER_MSG_SCHEMA} SHUTDOWN_ACK"
        )

    def test_emergency_shutdown_line_carries_its_typed_reason(self):
        assert PowerMessage(
            PowerMessageType.EMERGENCY_SHUTDOWN,
            EmergencyShutdownReason.OVER_VOLTAGE,
        ).format_line() == (
            f"PWR {POWER_MSG_SCHEMA} EMERGENCY_SHUTDOWN over_voltage"
        )


class TestParseRejections:
    @pytest.mark.parametrize(
        "line",
        [
            "FRONT; FLHY 0.1 0 0 0 0 0 0 0",  # a telemetry line
            "VER 1.0 main abc",               # a version line
            "PWR",                            # prefix only
            "PWR 1",                          # no type
            "PWR 1 POWERING_DOWN",             # required reason missing
            "PWR 1 EMERGENCY_SHUTDOWN",        # required reason missing
            "PWR 1 SHUTDOWN_ACK extra",        # reasonless type has extra field
            "PWR 1 POWERING_DOWN manual extra",  # excess field
            "",
        ],
        ids=[
            "telemetry",
            "version",
            "prefix-only",
            "no-type",
            "powering-down-no-reason",
            "emergency-no-reason",
            "ack-extra-field",
            "powering-down-extra-field",
            "empty",
        ],
    )
    def test_non_power_or_incomplete_line_returns_none(self, line):
        assert PowerMessage.parse(line) is None

    def test_unknown_schema_is_dropped_not_guessed(self):
        # A future layout must not be misread under the current field meanings.
        assert PowerMessage.parse("PWR 99 POWERING_DOWN under_voltage_soft") is None

    def test_non_numeric_schema_returns_none(self):
        assert PowerMessage.parse("PWR x POWERING_DOWN") is None

    def test_unknown_message_type_returns_none(self):
        assert PowerMessage.parse(f"PWR {POWER_MSG_SCHEMA} REBOOT_NOW") is None


class TestReasonHierarchy:
    @pytest.mark.parametrize(
        "line",
        [
            "PWR 1 POWERING_DOWN over_voltage",
            "PWR 1 POWERING_DOWN hard_cut",
            "PWR 1 POWERING_DOWN voltage_recovered",
            "PWR 1 EMERGENCY_SHUTDOWN under_voltage_soft",
            "PWR 1 EMERGENCY_SHUTDOWN manual",
            "PWR 1 RESUMING over_voltage",
            "PWR 1 POWERING_DOWN brownout_future",
        ],
    )
    def test_unknown_or_cross_family_reason_is_rejected(self, line):
        assert PowerMessage.parse(line) is None

    @pytest.mark.parametrize(
        ("message_type", "reason"),
        [
            (PowerMessageType.POWERING_DOWN, None),
            (
                PowerMessageType.POWERING_DOWN,
                EmergencyShutdownReason.OVER_VOLTAGE,
            ),
            (
                PowerMessageType.EMERGENCY_SHUTDOWN,
                PoweringDownReason.UNDER_VOLTAGE_SOFT,
            ),
            (PowerMessageType.SHUTDOWN_ACK, PoweringDownReason.MANUAL),
            (PowerMessageType.RESUMING, EmergencyShutdownReason.HARD_CUT),
        ],
    )
    def test_invalid_constructed_message_is_rejected(self, message_type, reason):
        with pytest.raises(ValueError):
            PowerMessage(message_type, reason)
