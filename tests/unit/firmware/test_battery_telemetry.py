"""Unit tests for the BATT telemetry segment (Task 3 parse layer).

Mirrors test_imu_telemetry.py: the BATT segment follows the same append-only,
Optional-returning, ParseStats-recording contract as IMU (see
docs/M16-ERROR-HANDLING.md). A malformed segment is dropped (never raised) and
never costs the joint/IMU data on the same line.

Wire frame (arduino.ino leader line, spec §4):
  ;BATT <pack_v> <pack_i> <pack_w> <pack_charge> <batt_a_v> <batt_b_v> <divergence> <power_state>
"""
import logging
import time

import pytest

from firmware.interfaces.joint_telemetry import (
    _MAX_STORED_SEGMENT,
    BatteryParseReason,
    BatteryTelemetry,
    ParsedTelemetry,
    ParseStats,
    PowerState,
    parse_telemetry_line,
)
from firmware.krabby_mcu import KrabbyMCUSDK

JOINT_SEG = "FLHY 0.123 512 12 1 0 0 128 3"
IMU_SEG = "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 1"
BATT_SEG = "BATT 24.13 12.5 301.6 1450.0 12.09 12.04 0 0"
DIVERGE_BATT_SEG = "BATT 24.13 -3.2 -77.2 1450 12.6 11.5 1 2"  # charging, diverged, soft-cut
LEADER_LINE = f"FRONT; {JOINT_SEG};{IMU_SEG};{BATT_SEG}"
DIVERGE_LEADER_LINE = f"FRONT; {JOINT_SEG};{DIVERGE_BATT_SEG}"
FOLLOWER_LINE = f"LEFT ; {JOINT_SEG.replace('FLHY', 'RLHY')}"


def _bare_sdk() -> KrabbyMCUSDK:
    """A real SDK with no serial port opened (__init__ is I/O-free with an
    explicit port), so tests exercise the real storage path, not a stand-in."""
    return KrabbyMCUSDK(port="unused")

# Every malformed shape a BATT-tagged segment can take, with the reason recorded.
MALFORMED_SEGMENTS = [
    pytest.param("BATT 24 12 300 1450", BatteryParseReason.BAD_TOKEN_COUNT,
                 id="segment-truncated-mid-line"),
    pytest.param(BATT_SEG + " 42", BatteryParseReason.BAD_TOKEN_COUNT,
                 id="extra-appended-field"),
    pytest.param("BATT a b c d e f 0 0", BatteryParseReason.NON_NUMERIC_TOKEN,
                 id="garbled-alpha-payload"),
    pytest.param("BATT 24 12 300 1450 12 12 2 0", BatteryParseReason.NON_NUMERIC_TOKEN,
                 id="divergence-flag-not-0-or-1"),
    pytest.param("BATT 24 12 300 1450 12 12 0 x", BatteryParseReason.NON_NUMERIC_TOKEN,
                 id="power-state-non-numeric"),
    pytest.param("BATT 24 12 300 1450 12 12 0 -1", BatteryParseReason.NON_NUMERIC_TOKEN,
                 id="power-state-negative"),
    pytest.param("BATT 24 12 300 1450 12 12 0 256", BatteryParseReason.NON_NUMERIC_TOKEN,
                 id="power-state-exceeds-byte"),  # 256 > 255: over the byte ceiling
    pytest.param("BATT nan 12 300 1450 12 12 0 0", BatteryParseReason.NON_FINITE_VALUE,
                 id="avr-nan-on-pack-v"),
    pytest.param("BATT 24 inf 300 1450 12 12 0 0", BatteryParseReason.NON_FINITE_VALUE,
                 id="avr-inf-on-pack-i"),
    # AVR-poison shapes the reason docstrings advertise ("AVR 'ovf'" / "AVR 'nan'"):
    pytest.param("BATT 24 12 300 ovf 12 12 0 0", BatteryParseReason.NON_NUMERIC_TOKEN,
                 id="avr-ovf-on-charge"),
    pytest.param("BATT 24 12 300 1450 nan 12 0 0", BatteryParseReason.NON_FINITE_VALUE,
                 id="avr-nan-on-batt-a"),
]


class TestBatteryFromTokens:
    def test_parses_fully_valid_wire_segment(self):
        b = BatteryTelemetry.from_segment(BATT_SEG)
        assert b == BatteryTelemetry(
            pack_v=24.13, pack_i=12.5, pack_w=301.6, pack_charge=1450.0,
            batt_a_v=12.09, batt_b_v=12.04, divergence=False, power_state=0,
        )

    def test_negative_current_parses_as_charging(self):
        # pack_i is signed; a charging pack reads negative, not a parse failure.
        b = BatteryTelemetry.from_segment(DIVERGE_BATT_SEG)
        assert b is not None and b.pack_i == -3.2 and b.pack_w == -77.2

    def test_divergence_flag_and_power_state_parse(self):
        b = BatteryTelemetry.from_segment(DIVERGE_BATT_SEG)
        assert b.divergence is True and b.power_state == PowerState.SOFT_CUT

    def test_unknown_power_state_byte_is_kept_as_int(self):
        # Forward-compat: a byte outside the known enum is retained, not dropped.
        b = BatteryTelemetry.from_segment("BATT 24 12 300 1450 12 12 0 99")
        assert b is not None and b.power_state == 99

    def test_power_state_at_byte_ceiling_parses(self):
        # 255 is the top of the valid byte range: it parses and is retained as-is
        # (the reject only starts at 256 — see MALFORMED_SEGMENTS).
        b = BatteryTelemetry.from_segment("BATT 24 12 300 1450 12 12 0 255")
        assert b is not None and b.power_state == 255

    @pytest.mark.parametrize("segment, reason", MALFORMED_SEGMENTS)
    def test_malformed_segment_returns_none_without_stats(self, segment, reason):
        assert BatteryTelemetry.from_segment(segment) is None

    @pytest.mark.parametrize("segment, reason", MALFORMED_SEGMENTS)
    def test_malformed_segment_records_reason_in_stats(self, segment, reason):
        stats = ParseStats()
        assert BatteryTelemetry.from_segment(segment, stats) is None
        assert stats.error_count == 1 and stats.last_reason == reason

    def test_successful_parse_leaves_stats_untouched(self):
        stats = ParseStats()
        assert BatteryTelemetry.from_segment(BATT_SEG, stats) is not None
        assert stats.error_count == 0 and stats.last_reason is None

    def test_stats_preserve_offending_segment_text(self):
        # The offending text rides along (mirror of the IMU suite) so the SDK's
        # throttled warning can echo what actually arrived on the wire.
        stats = ParseStats()
        assert BatteryTelemetry.from_segment("BATT nope", stats) is None
        assert stats.last_segment == "BATT nope"

    def test_stored_offending_segment_is_length_bounded(self):
        # A garbled BATT line can be arbitrarily long; the copy kept for the log
        # message is truncated to the stored-segment cap (assert the symbol, not
        # a magic literal), so a flood can't blow up the log line.
        stats = ParseStats()
        assert BatteryTelemetry.from_segment("BATT " + "9 " * 500, stats) is None
        assert stats.last_segment is not None
        assert len(stats.last_segment) <= _MAX_STORED_SEGMENT


class TestBatteryTagDispatch:
    @pytest.mark.parametrize("segment", ["IMU 1 2 3 4 5 6 7 1", JOINT_SEG, ""])
    def test_non_batt_segment_returns_none_without_recording(self, segment):
        # A tag mismatch is a dispatch miss, not corruption: stats untouched.
        stats = ParseStats()
        assert BatteryTelemetry.from_tokens(segment.split(), stats) is None
        assert stats.error_count == 0


class TestParseTelemetryLine:
    def test_leader_line_yields_joints_imu_and_battery(self):
        parsed = parse_telemetry_line(LEADER_LINE)
        assert len(parsed.joints) == 1
        assert parsed.imu is not None
        assert parsed.battery is not None and parsed.battery.pack_v == 24.13

    def test_follower_line_has_no_battery(self):
        parsed = parse_telemetry_line(FOLLOWER_LINE)
        assert parsed.joints and parsed.battery is None

    def test_line_without_battery_segment_still_parses_joints(self):
        parsed = parse_telemetry_line(f"FRONT; {JOINT_SEG};{IMU_SEG}")
        assert parsed.joints and parsed.battery is None

    def test_malformed_battery_segment_never_costs_joints_on_the_same_line(self):
        parsed = parse_telemetry_line(f"FRONT; {JOINT_SEG};BATT nope")
        assert len(parsed.joints) == 1 and parsed.battery is None

    def test_malformed_battery_segment_is_counted_when_stats_provided(self):
        stats = ParseStats()
        parse_telemetry_line(f"FRONT; {JOINT_SEG};BATT nope", stats)
        assert stats.error_count == 1

    def test_battery_segment_never_parses_as_a_joint(self):
        parsed = parse_telemetry_line(f"FRONT; {BATT_SEG}")
        assert parsed.joints == [] and parsed.battery is not None

    def test_two_battery_segments_on_one_line_keep_the_last(self):
        line = f"FRONT; {JOINT_SEG};{BATT_SEG};{DIVERGE_BATT_SEG}"
        parsed = parse_telemetry_line(line)
        assert parsed.battery is not None and parsed.battery.divergence is True

    def test_good_then_malformed_battery_keeps_the_good_sample(self):
        line = f"FRONT; {JOINT_SEG};{BATT_SEG};BATT nope"
        parsed = parse_telemetry_line(line)
        assert parsed.battery is not None and parsed.battery.pack_v == 24.13


class TestFormatCompact:
    def test_pins_exact_debug_string(self):
        assert BatteryTelemetry.from_segment(BATT_SEG).format_compact() == (
            "pack:24.13V +12.50A 301.6W A:12.09V B:12.04V q:1450C NORMAL"
        )

    def test_diverged_and_named_state(self):
        assert BatteryTelemetry.from_segment(DIVERGE_BATT_SEG).format_compact() == (
            "pack:24.13V -3.20A -77.2W A:12.60V B:11.50V q:1450C SOFT_CUT DIVERGE"
        )

    def test_unknown_power_state_falls_back_to_number(self):
        compact = BatteryTelemetry.from_segment(
            "BATT 24 12 300 1450 12 12 0 99").format_compact()
        assert compact.endswith("99")


class TestSdkBatteryStorage:
    def test_leader_line_populates_battery_and_joints(self):
        sdk = _bare_sdk()
        sdk._parse_joint_line(LEADER_LINE)
        assert sdk.battery is not None and sdk.battery.pack_v == 24.13
        assert sdk.joints["FLHY"].pos == 0.123

    def test_battery_is_none_until_first_leader_sample(self):
        sdk = _bare_sdk()
        sdk._parse_joint_line(FOLLOWER_LINE)
        assert sdk.battery is None  # absence by design (follower), not a failure

    def test_follower_line_preserves_last_battery_sample(self):
        sdk = _bare_sdk()
        sdk._parse_joint_line(LEADER_LINE)
        sdk._parse_joint_line(FOLLOWER_LINE)
        assert sdk.battery is not None and "RLHY" in sdk.joints

    def test_malformed_battery_segment_preserves_last_good_sample(self):
        sdk = _bare_sdk()
        sdk._parse_joint_line(LEADER_LINE)
        sdk._parse_joint_line(f"FRONT; {JOINT_SEG};BATT nope")
        assert sdk.battery is not None and sdk.battery.pack_v == 24.13


class TestSdkBatteryDivergence:
    # A tripped divergence flag is logged once per transition (one-shot), not
    # per tick, and re-armed when the pack rebalances.
    def test_divergence_trips_a_single_warning(self, caplog):
        sdk = _bare_sdk()
        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_joint_line(DIVERGE_LEADER_LINE)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1 and "divergence" in warnings[0].getMessage().lower()

    def test_persistent_divergence_is_not_relogged_every_tick(self, caplog):
        sdk = _bare_sdk()
        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            for _ in range(5):
                sdk._parse_joint_line(DIVERGE_LEADER_LINE)
        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1

    def test_warning_rearms_after_pack_rebalances(self, caplog):
        sdk = _bare_sdk()
        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_joint_line(DIVERGE_LEADER_LINE)   # trip
            sdk._parse_joint_line(LEADER_LINE)           # clear (divergence=0)
            sdk._parse_joint_line(DIVERGE_LEADER_LINE)   # trip again
        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2

    def test_balanced_pack_logs_no_divergence_warning(self, caplog):
        sdk = _bare_sdk()
        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_joint_line(LEADER_LINE)
        assert [r for r in caplog.records if r.levelno == logging.WARNING] == []
