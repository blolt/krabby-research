"""Unit tests for the IMU telemetry segment (parse layer + SDK storage).

Naming convention: pytest has no enforced convention beyond the ``test_``
prefix; the Python idiom is a snake_case name that reads as a sentence —
``test_<unit>_<condition>_<expected behavior>`` — with Arrange/Act/Assert as
blank-line-separated *body structure* rather than encoded in the method name
(the AWS-style ``arrange_act_assert`` suffix is not idiomatic here).
Comments are used freely to state author intent.

Error-handling behavior under test is specified in docs/M16-ERROR-HANDLING.md:
- Class A (malformed segment on the lossy stream): parser returns None,
  drop is recorded in ParseStats, SDK warns throttled.
- Class B (leader sensor present but valid=0): sample stored, one-shot WARNING
  on the transition, rendered STALE.
- Class C (follower / absent hardware): sdk.imu stays None, zero logging.
"""
import logging
import time

import pytest

from firmware.interfaces.joint_telemetry import (
    ImuParseReason,
    ImuTelemetry,
    JointTelemetry,
    ParsedTelemetry,
    ParseStats,
    parse_telemetry_line,
)
from firmware.krabby_mcu import KrabbyMCUSDK

JOINT_SEG = "FLHY 0.123 512 12 1 0 0 128 3"
IMU_SEG = "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 1"
STALE_IMU_SEG = "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 0"
MALFORMED_IMU_SEG = "IMU bad data"
LEADER_LINE = f"FRONT; {JOINT_SEG};{IMU_SEG}"
STALE_LEADER_LINE = f"FRONT; {JOINT_SEG};{STALE_IMU_SEG}"
MALFORMED_IMU_LINE = f"FRONT; {JOINT_SEG};{MALFORMED_IMU_SEG}"
FOLLOWER_LINE = f"LEFT ; {JOINT_SEG.replace('FLHY', 'RLHY')}"

# Every malformed shape a *recognized* (IMU-tagged) segment can take, with the
# reason the parser must record. A tag mismatch is NOT here — that is a dispatch
# miss, not corruption, and records nothing (see TestImuTagDispatch).
# ids name the real-world event that produces each shape.
MALFORMED_SEGMENTS = [
    pytest.param(
        "IMU 1.0 2.0 3.0", ImuParseReason.BAD_TOKEN_COUNT,
        id="segment-truncated-mid-line",
    ),
    pytest.param(
        # Append-only contract: a firmware that appends a 10th field to the
        # IMU segment must come with a parser update; until then the segment
        # is dropped rather than misparsed.
        IMU_SEG + " 42", ImuParseReason.BAD_TOKEN_COUNT,
        id="extra-appended-field",
    ),
    pytest.param(
        "IMU a b c d e f g 1", ImuParseReason.NON_NUMERIC_TOKEN,
        id="garbled-alpha-payload",
    ),
    pytest.param(
        # AVR Print emits "ovf" for floats outside +/-4294967040; float()
        # rejects it.
        "IMU ovf 0.0 0.0 0.0 0.0 0.0 24.5 1", ImuParseReason.NON_NUMERIC_TOKEN,
        id="avr-ovf-print",
    ),
    pytest.param(
        "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 x",
        ImuParseReason.NON_NUMERIC_TOKEN,
        id="non-numeric-valid-flag",
    ),
    pytest.param(
        # The valid flag is exactly "0" or "1"; any other value is a corrupt
        # token, not a "valid=2" sample.
        "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 2",
        ImuParseReason.NON_NUMERIC_TOKEN,
        id="out-of-range-valid-flag",
    ),
    pytest.param(
        # AVR prints non-finite floats as "nan"; float() accepts it, so the
        # finiteness check must catch it.
        "IMU nan nan nan 0.0 0.0 0.0 24.5 1", ImuParseReason.NON_FINITE_VALUE,
        id="avr-nan-print",
    ),
    pytest.param(
        "IMU inf 0.0 0.0 0.0 0.0 -inf 24.5 1", ImuParseReason.NON_FINITE_VALUE,
        id="avr-inf-print",
    ),
    pytest.param(
        # Only the temp field (token 7) non-finite, accel/gyro good: the
        # firmware NAN-poisons temp on a getTemperature() failure, so this is
        # attributed to the temperature read, not a wiring/link fault.
        "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 nan 1",
        ImuParseReason.TEMP_READ_FAILED,
        id="nan-temperature-only",
    ),
]


def _bare_sdk() -> KrabbyMCUSDK:
    """A real SDK with no serial port opened.

    __init__ is I/O-free when given an explicit port (it opens nothing until
    connect()), so constructing normally exercises the real object and its
    invariants instead of a hand-copied stand-in that silently drifts when a
    field is renamed.
    """
    return KrabbyMCUSDK(port="unused")


class TestImuFromTokens:
    def test_from_tokens_parses_fully_valid_wire_segment(self):
        imu = ImuTelemetry.from_tokens(IMU_SEG.split())

        assert imu is not None
        assert imu.accel == (0.012, -0.034, 9.807)
        assert imu.gyro == (0.0012, -0.0008, 0.0003)
        assert imu.temp_c == 24.5
        assert imu.valid is True

    def test_from_tokens_valid_flag_zero_yields_stale_sample_not_none(self):
        # valid=0 is a *well-formed* segment (sensor present but not
        # responding); it must parse into a sample, not be dropped like
        # corruption — the valid flag is information the wire gives us.
        imu = ImuTelemetry.from_tokens(
            "IMU 0.000 0.000 0.000 0.0000 0.0000 0.0000 0.0 0".split()
        )

        assert imu is not None
        assert imu.valid is False

    @pytest.mark.parametrize("segment, expected_reason", MALFORMED_SEGMENTS)
    def test_from_tokens_malformed_segment_returns_none_without_stats(
        self, segment, expected_reason
    ):
        # The stats hook is optional: callers that do not pass one get the
        # plain Optional-returning contract (drop the sample, no side effects).
        assert ImuTelemetry.from_tokens(segment.split()) is None

    @pytest.mark.parametrize("segment, expected_reason", MALFORMED_SEGMENTS)
    def test_from_tokens_malformed_segment_records_reason_in_stats(
        self, segment, expected_reason
    ):
        # The None return stays, but with a stats aggregate the drop is no
        # longer information-free: reason + count are recorded out-of-band.
        stats = ParseStats()

        result = ImuTelemetry.from_tokens(segment.split(), stats=stats)

        assert result is None
        assert stats.last_reason is expected_reason
        assert stats.error_count == 1

    def test_from_tokens_successful_parse_leaves_stats_untouched(self):
        stats = ParseStats()

        imu = ImuTelemetry.from_tokens(IMU_SEG.split(), stats=stats)

        assert imu is not None
        assert stats.error_count == 0
        assert stats.last_reason is None
        assert stats.last_segment is None

    def test_parse_stats_error_count_is_monotonic_across_failures(self):
        stats = ParseStats()

        ImuTelemetry.from_tokens("IMU 1.0".split(), stats=stats)
        ImuTelemetry.from_tokens(
            "IMU nan 0.0 0.0 0.0 0.0 0.0 24.5 1".split(), stats=stats
        )

        assert stats.error_count == 2
        assert stats.last_reason is ImuParseReason.NON_FINITE_VALUE  # last wins

    def test_parse_stats_preserves_offending_segment_text(self):
        # The offending text rides along so the SDK's throttled warning can
        # echo what actually arrived on the wire.
        stats = ParseStats()

        ImuTelemetry.from_tokens(MALFORMED_IMU_SEG.split(), stats=stats)

        assert stats.last_segment == "IMU bad data"


class TestImuTagDispatch:
    # A segment whose first token is not the IMU tag is a dispatch miss, not
    # corruption: from_tokens returns None and must NOT touch stats, so
    # error_count stays an alarm-meaningful count of broken IMU segments only.

    @pytest.mark.parametrize(
        "segment",
        [JOINT_SEG, "", "BATT 12.6 1.2"],
        ids=["joint-segment", "empty-segment", "other-sensor-tag"],
    )
    def test_from_tokens_non_imu_segment_returns_none_without_recording(self, segment):
        stats = ParseStats()

        result = ImuTelemetry.from_tokens(segment.split(), stats=stats)

        assert result is None
        assert stats.error_count == 0
        assert stats.last_reason is None


class TestImuFromSegment:
    # The native transport shape is the whitespace-separated text between
    # semicolons on the serial line; from_segment owns the tokenization so
    # callers and tests can exercise wire-shaped strings directly.

    def test_from_segment_parses_raw_wire_segment_string(self):
        assert ImuTelemetry.from_segment(IMU_SEG) == ImuTelemetry.from_tokens(
            IMU_SEG.split()
        )

    def test_from_segment_tolerates_surrounding_whitespace(self):
        # Segments arrive with padding after the ';' separator on real lines.
        imu = ImuTelemetry.from_segment(f"  {IMU_SEG} ")

        assert imu is not None
        assert imu.valid is True

    def test_from_segment_records_reason_for_malformed_segment(self):
        stats = ParseStats()

        result = ImuTelemetry.from_segment(MALFORMED_IMU_SEG, stats=stats)

        assert result is None
        assert stats.last_reason is ImuParseReason.BAD_TOKEN_COUNT
        assert stats.error_count == 1


class TestParseTelemetryLine:
    def test_leader_line_yields_both_joints_and_imu(self):
        parsed = parse_telemetry_line(LEADER_LINE)

        assert [j.name for j in parsed.joints] == ["FLHY"]
        assert parsed.imu is not None and parsed.imu.valid

    def test_follower_line_yields_joints_and_no_imu(self):
        parsed = parse_telemetry_line(FOLLOWER_LINE)

        assert [j.name for j in parsed.joints] == ["RLHY"]
        assert parsed.imu is None

    def test_line_without_imu_segment_still_parses_joints(self):
        parsed = parse_telemetry_line(f"FRONT; {JOINT_SEG}")

        assert len(parsed.joints) == 1
        assert parsed.imu is None

    def test_imu_segment_never_parses_as_a_joint(self):
        assert parse_telemetry_line(f"FRONT; {IMU_SEG}").joints == []

    def test_joints_only_entry_point_ignores_imu_segment(self):
        # JointTelemetry.parse_line predates sensor segments and returns
        # joints only; sensor segments on the line must stay invisible to
        # its callers (the append-only contract seen from the consumer side).
        joints = JointTelemetry.parse_line(LEADER_LINE)

        assert [j.name for j in joints] == ["FLHY"]

    def test_malformed_imu_segment_never_costs_joints_on_the_same_line(self):
        parsed = parse_telemetry_line(MALFORMED_IMU_LINE)

        assert [j.name for j in parsed.joints] == ["FLHY"]
        assert parsed.imu is None

    def test_nonfinite_imu_segment_never_costs_joints_on_the_same_line(self):
        nan_seg = "IMU nan nan nan 0.0 0.0 0.0 24.5 1"

        parsed = parse_telemetry_line(f"FRONT; {JOINT_SEG};{nan_seg}")

        assert [j.name for j in parsed.joints] == ["FLHY"]
        assert parsed.imu is None

    def test_malformed_imu_segment_is_counted_when_stats_provided(self):
        stats = ParseStats()

        parse_telemetry_line(MALFORMED_IMU_LINE, stats=stats)

        assert stats.error_count == 1
        assert stats.last_reason is ImuParseReason.BAD_TOKEN_COUNT

    def test_unknown_future_segment_is_ignored_and_not_counted_as_error(self):
        # Append-only wire contract: a tag this parser does not recognize is
        # assumed to be newer firmware, not corruption — dropped silently and
        # never counted. Only *recognized* tags with bad payloads count.
        stats = ParseStats()

        parsed = parse_telemetry_line(
            f"FRONT; {JOINT_SEG};BATT 12.6 1.2", stats=stats
        )

        assert [j.name for j in parsed.joints] == ["FLHY"]
        assert parsed.imu is None
        assert stats.error_count == 0

    @pytest.mark.parametrize(
        "line",
        ["FRONT; ", "LEFT ;", "RIGHT;"],
        ids=["front-leader", "left-follower", "right-follower"],
    )
    def test_role_prefix_only_line_parses_to_empty_frame(self, line):
        # A board that has booted but not enumerated joints yet emits just
        # its role prefix. All three wire prefixes must parse to an empty
        # result, not raise. (Prefixes match roleName() in arduino.ino, which
        # pads "LEFT" with a trailing space — hence "LEFT ;" — while "RIGHT;"
        # has no padding.)
        assert parse_telemetry_line(line) == ParsedTelemetry([], None)


class TestLossyStreamResilience:
    # The parser is the first thing a garbled serial line hits; it must never
    # raise, and its "last wins" / bounded-storage behaviors must hold.

    def test_two_imu_segments_on_one_line_keep_the_last(self):
        # A merged line (dropped newline between two ticks) carries two IMU
        # segments; the later one is the fresher sample and wins.
        stale = "IMU 0.0 0.0 9.8 0.0 0.0 0.0 20.0 0"
        parsed = parse_telemetry_line(f"FRONT; {JOINT_SEG};{stale};{IMU_SEG}")

        assert parsed.imu is not None
        assert parsed.imu.valid is True
        assert parsed.imu.temp_c == 24.5

    def test_good_then_malformed_imu_segment_keeps_the_good_sample(self):
        # last-*valid* wins: a malformed later segment does not clobber a good
        # earlier one on the same line.
        parsed = parse_telemetry_line(f"FRONT; {JOINT_SEG};{IMU_SEG};{MALFORMED_IMU_SEG}")

        assert parsed.imu is not None
        assert parsed.imu.valid is True

    def test_stored_offending_segment_is_length_bounded(self):
        # A garbled line can be arbitrarily long; the copy kept for the log
        # message must not grow without bound.
        stats = ParseStats()

        parse_telemetry_line("FRONT; IMU " + "9" * 5000, stats=stats)

        assert stats.last_segment is not None
        assert len(stats.last_segment) <= 200

    def test_arbitrary_garbage_lines_never_raise(self):
        # Binary noise, partial lines, and control characters all reach here on
        # a real link; parsing must degrade to empty/None, never throw.
        garbage = [
            "",
            ";",
            ";;;;;",
            "FRONT;",
            "\x00\xff\x01 garbage \r",
            "IMU",
            "IMU " + "nan " * 50,
            "FRONT; " + "IMU 1 2 3;" * 40,
            "\t\t  ;  \t",
            "RIGHT; FLHY not a number here at all 9 9",
        ]
        for i in range(200):
            line = garbage[i % len(garbage)] + (";x" * (i % 7))
            parsed = parse_telemetry_line(line)  # must not raise
            assert isinstance(parsed, ParsedTelemetry)


class TestFormatCompact:
    # These strings feed the debug log and GUI label verbatim; the exact-match
    # assertions pin the rounding widths (.3f joints, .2f/.3f/.1f IMU) so an
    # accidental format change surfaces in review.

    def test_joint_format_compact_pins_exact_debug_string(self):
        jt = JointTelemetry.from_tokens(JOINT_SEG.split())

        assert jt.format_compact() == "FLHY:0.123,512,12,(1,0),(0,128),3"

    def test_joint_format_compact_with_target_shows_pos_slash_target(self):
        jt = JointTelemetry.from_tokens(JOINT_SEG.split())

        assert jt.format_compact(target=0.5) == "FLHY:0.123/0.500,512,12,(1,0),(0,128),3"

    def test_imu_format_compact_pins_exact_debug_string(self):
        imu = ImuTelemetry.from_tokens(IMU_SEG.split())

        assert imu.format_compact() == (
            "a:(0.01,-0.03,9.81)m/s2 g:(0.001,-0.001,0.000)rad/s 24.5C"
        )

    def test_imu_format_compact_appends_stale_flag_when_not_valid(self):
        # valid=0 -> sensor not responding this tick; the GUI/debug log must
        # visibly distinguish this from a fresh sample.
        imu = ImuTelemetry.from_segment(STALE_IMU_SEG)

        assert imu.valid is False
        assert imu.format_compact() == (
            "a:(0.01,-0.03,9.81)m/s2 g:(0.001,-0.001,0.000)rad/s 24.5C STALE"
        )


class TestSdkImuStorage:
    def test_leader_line_populates_imu_and_joints(self):
        sdk = _bare_sdk()

        sdk._parse_joint_line(LEADER_LINE)

        assert sdk.imu is not None
        assert sdk.imu.temp_c == 24.5
        assert sdk.joints["FLHY"].pos == 0.123

    def test_follower_line_preserves_last_leader_imu_sample(self):
        # Followers never carry an IMU segment; their lines must not clobber
        # the last sample the leader delivered.
        sdk = _bare_sdk()
        sdk._parse_joint_line(LEADER_LINE)

        sdk._parse_joint_line(FOLLOWER_LINE)

        assert sdk.imu is not None
        assert "RLHY" in sdk.joints

    def test_malformed_imu_segment_preserves_last_good_sample(self):
        # One corrupt tick must not erase the newest good data; the last
        # good sample wins until a well-formed segment replaces it.
        sdk = _bare_sdk()
        sdk._parse_joint_line(LEADER_LINE)

        sdk._parse_joint_line(MALFORMED_IMU_LINE)

        assert sdk.imu is not None
        assert sdk.imu.valid is True

    @pytest.mark.parametrize(
        "line",
        ["FRONT; ", "LEFT ;", "RIGHT;"],
        ids=["front-leader", "left-follower", "right-follower"],
    )
    def test_role_prefix_only_line_is_a_noop(self, line):
        # Plausible on the wire (board booted, no joints enumerated yet):
        # must not raise and must leave joints/imu untouched.
        sdk = _bare_sdk()

        sdk._parse_joint_line(line)

        assert sdk.joints == {}
        assert sdk.imu is None

    def test_role_prefix_only_line_preserves_prior_state(self):
        sdk = _bare_sdk()
        sdk._parse_joint_line(LEADER_LINE)

        sdk._parse_joint_line("FRONT; ")

        assert sdk.imu is not None
        assert "FLHY" in sdk.joints


class TestSdkThreeStateImuModel:
    # docs/M16-ERROR-HANDLING.md: sdk.imu is None (never seen) is a distinct
    # state from sdk.imu.valid False (sensor present but not responding),
    # which is distinct from a fresh sample.

    def test_imu_is_none_until_first_leader_sample(self):
        sdk = _bare_sdk()

        sdk._parse_joint_line(FOLLOWER_LINE)

        assert sdk.imu is None  # absence by design, not a failure

    def test_imu_is_stale_when_sensor_present_but_not_valid(self):
        sdk = _bare_sdk()

        sdk._parse_joint_line(STALE_LEADER_LINE)

        assert sdk.imu is not None  # the sample is kept, not discarded
        assert sdk.imu.valid is False

    def test_imu_is_fresh_after_recovery_from_stale(self):
        sdk = _bare_sdk()
        sdk._parse_joint_line(STALE_LEADER_LINE)

        sdk._parse_joint_line(LEADER_LINE)

        assert sdk.imu is not None
        assert sdk.imu.valid is True


class TestSdkParseErrorObservability:
    def test_parse_error_count_and_reason_are_queryable_on_the_sdk(self):
        # Mirrors the existing last_error attribute: the drop is silent at
        # the parse layer but the SDK exposes count + reason to callers.
        sdk = _bare_sdk()

        sdk._parse_joint_line(MALFORMED_IMU_LINE)

        assert sdk.parse_error_count == 1
        assert sdk.last_parse_reason is ImuParseReason.BAD_TOKEN_COUNT

    def test_first_malformed_segment_always_logs_a_warning(self, caplog):
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_joint_line(MALFORMED_IMU_LINE)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        message = warnings[0].getMessage()
        assert "BAD_TOKEN_COUNT" in message   # the reason, grep-able
        assert "IMU bad data" in message      # what actually arrived

    def test_repeated_malformed_segments_are_throttled_to_one_warning(self, caplog):
        # Corruption is expected steady-state on the lossy link; a noisy
        # cable must not flood the log. The counter still counts every drop.
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            for _ in range(5):
                sdk._parse_joint_line(MALFORMED_IMU_LINE)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert sdk.parse_error_count == 5

    def test_warning_is_reemitted_after_throttle_window_expires(self, caplog):
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_joint_line(MALFORMED_IMU_LINE)
            # Simulate the ~1 s throttle window having elapsed. The gate uses a
            # monotonic clock, so rewind the monotonic timestamp, not wall time.
            sdk._last_parse_warn_ts = time.monotonic() - 2.0
            sdk._parse_joint_line(MALFORMED_IMU_LINE)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2

    def test_well_formed_lines_log_no_parse_warnings(self, caplog):
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_joint_line(LEADER_LINE)
            sdk._parse_joint_line(FOLLOWER_LINE)

        assert [r for r in caplog.records if r.levelno == logging.WARNING] == []
        assert sdk.parse_error_count == 0


class TestSdkImuValidityTransitions:
    # Class B: a persistent valid=0 condition arrives on every tick, so the
    # warning is one-shot per transition into the invalid state — actionable
    # once, noise thereafter.

    def test_transition_to_invalid_logs_exactly_one_warning(self, caplog):
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_joint_line(STALE_LEADER_LINE)
            sdk._parse_joint_line(STALE_LEADER_LINE)  # still invalid: no repeat

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "valid=0" in warnings[0].getMessage()

    def test_recovery_then_reentry_into_invalid_warns_again(self, caplog):
        # A valid sample re-arms the one-shot so the *next* failure episode
        # is surfaced too.
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_joint_line(STALE_LEADER_LINE)  # episode 1
            sdk._parse_joint_line(LEADER_LINE)        # recovery
            sdk._parse_joint_line(STALE_LEADER_LINE)  # episode 2

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2

    def test_valid_samples_log_nothing(self, caplog):
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_joint_line(LEADER_LINE)

        assert [r for r in caplog.records if r.levelno == logging.WARNING] == []

    def test_follower_absence_logs_nothing(self, caplog):
        # Class C: a follower never carrying an IMU segment is the normal
        # state of a healthy system — by design it produces zero log output.
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_joint_line(FOLLOWER_LINE)

        assert caplog.records == []
