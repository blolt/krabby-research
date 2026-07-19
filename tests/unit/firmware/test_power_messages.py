"""Power-state control message protocol (M16 Task 4, firmware/interfaces/power_messages.py).

Naming: test_<unit>_<condition>_<expected>, arrange/act/assert body structure.
"""
import pytest

from firmware.interfaces.power_messages import (
    POWER_MSG_SCHEMA,
    PowerMessage,
    PowerMessageType,
    PowerReason,
)


class TestFormatParseRoundTrip:
    @pytest.mark.parametrize(
        "msg",
        [
            PowerMessage(PowerMessageType.POWERING_DOWN, PowerReason.UNDER_VOLTAGE_SOFT),
            PowerMessage(PowerMessageType.POWERING_DOWN, PowerReason.MANUAL),
            PowerMessage(PowerMessageType.RESUMING, PowerReason.VOLTAGE_RECOVERED),
            PowerMessage(PowerMessageType.OVER_VOLTAGE_SHUTDOWN, PowerReason.OVER_VOLTAGE),
            PowerMessage(PowerMessageType.SHUTDOWN_ACK),  # no reason
        ],
        ids=lambda m: f"{m.type.name}-{m.reason.name if m.reason else 'none'}",
    )
    def test_format_then_parse_recovers_the_message(self, msg):
        assert PowerMessage.parse(msg.format_line()) == msg

    def test_powering_down_line_is_the_expected_wire_shape(self):
        line = PowerMessage(
            PowerMessageType.POWERING_DOWN, PowerReason.UNDER_VOLTAGE_SOFT
        ).format_line()

        assert line == f"PWR {POWER_MSG_SCHEMA} POWERING_DOWN under_voltage_soft"

    def test_ack_line_omits_the_reason(self):
        assert PowerMessage(PowerMessageType.SHUTDOWN_ACK).format_line() == (
            f"PWR {POWER_MSG_SCHEMA} SHUTDOWN_ACK"
        )


class TestParseRejections:
    @pytest.mark.parametrize(
        "line",
        [
            "FRONT; FLHY 0.1 0 0 0 0 0 0 0",  # a telemetry line
            "VER 1.0 main abc",               # a version line
            "PWR",                            # prefix only
            "PWR 1",                          # no type
            "",
        ],
        ids=["telemetry", "version", "prefix-only", "no-type", "empty"],
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


class TestReasonTolerance:
    def test_unknown_reason_on_known_type_keeps_the_typed_message(self):
        # Reason codes may grow without a schema bump; a known type with a
        # reason this parser doesn't know is still actionable (reason=None).
        msg = PowerMessage.parse(f"PWR {POWER_MSG_SCHEMA} POWERING_DOWN brownout_future")

        assert msg is not None
        assert msg.type is PowerMessageType.POWERING_DOWN
        assert msg.reason is None
