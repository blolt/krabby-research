"""Unit tests for the IMU telemetry segment (parse layer + SDK storage).

Naming convention: pytest has no enforced convention beyond the ``test_``
prefix; the Python idiom is a snake_case name that reads as a sentence —
``test_<unit>_<condition>_<expected behavior>`` — with Arrange/Act/Assert as
blank-line-separated *body structure* rather than encoded in the method name
(the AWS-style ``arrange_act_assert`` suffix is not idiomatic here).
Comments are used freely to state author intent.

Error-handling behavior under test:
- Class A (malformed segment on the lossy stream): parser returns None.
- Class B (leader sensor present but valid=0): sample stored, one-shot WARNING
  on the transition, rendered STALE.
- Class C (follower / absent hardware): sdk.imu stays None, zero logging.
"""

import logging
import math
from unittest import mock

import pytest

from firmware.interfaces.imu_telemetry import ImuTelemetry
from firmware.interfaces.joint_telemetry import JointTelemetry
from firmware.interfaces.parsed_telemetry import ParsedTelemetry
from firmware.interfaces.telemetry_parser import parse_telemetry_line
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
        "IMU 1.0 2.0 3.0",
        id="segment-truncated-mid-line",
    ),
    pytest.param(
        # Append-only contract: a firmware that appends a 10th field to the
        # IMU segment must come with a parser update; until then the segment
        # is dropped rather than misparsed.
        IMU_SEG + " 42",
        id="extra-appended-field",
    ),
    pytest.param(
        "IMU a b c d e f g 1",
        id="garbled-alpha-payload",
    ),
    pytest.param(
        # AVR Print emits "ovf" for floats outside +/-4294967040; float()
        # rejects it.
        "IMU ovf 0.0 0.0 0.0 0.0 0.0 24.5 1",
        id="avr-ovf-print",
    ),
    pytest.param(
        "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 x",
        id="non-numeric-valid-flag",
    ),
    pytest.param(
        # The valid flag is exactly "0" or "1"; any other value is a corrupt
        # token, not a "valid=2" sample.
        "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 2",
        id="out-of-range-valid-flag",
    ),
    pytest.param(
        "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 -1",
        id="negative-valid-flag",
    ),
    pytest.param(
        "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 1.0",
        id="float-shaped-valid-flag",
    ),
    pytest.param(
        "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 24.5 true",
        id="textual-valid-flag",
    ),
    pytest.param(
        # AVR prints non-finite floats as "nan"; float() accepts it, so the
        # finiteness check must catch it.
        "IMU nan nan nan 0.0 0.0 0.0 24.5 1",
        id="avr-nan-print",
    ),
    pytest.param(
        "IMU inf 0.0 0.0 0.0 0.0 -inf 24.5 1",
        id="avr-inf-print",
    ),
    # NOTE: a temp-only non-finite value (accel/gyro good) is NOT a malformed
    # segment. Partial motion data remains useful even though the current
    # LSM6DSO path does not intentionally emit NaN for temperature. See
    # TestImuFromTokens.test_temp_only_nonfinite_keeps_sample_with_nan_temp.
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

    @pytest.mark.parametrize("segment", MALFORMED_SEGMENTS)
    def test_from_tokens_malformed_segment_returns_none(self, segment):
        # Malformed segments drop to None; the caller cannot distinguish shapes.
        assert ImuTelemetry.from_tokens(segment.split()) is None

    def test_temp_only_nonfinite_keeps_sample_with_nan_temp(self):
        # Temperature failure alone still leaves usable motion data: keep the
        # sample with temp_c = NaN.
        imu = ImuTelemetry.from_tokens(
            "IMU 0.012 -0.034 9.807 0.0012 -0.0008 0.0003 nan 1".split()
        )

        assert imu is not None
        assert imu.accel == (0.012, -0.034, 9.807)
        assert imu.gyro == (0.0012, -0.0008, 0.0003)
        assert math.isnan(imu.temp_c)
        assert imu.valid is True


class TestImuDerivedProperties:
    # The four derived properties feed the operator GUI (roll/pitch attitude,
    # accel in g, gyro in deg/s). Unit conversions and the accel-gravity
    # attitude math are pinned here with pytest.approx.

    @staticmethod
    def _imu(accel, gyro=(0.0, 0.0, 0.0)):
        # Build through the real parser (from_tokens) as the rest of the file
        # does; str() keeps full float precision through the round-trip.
        tokens = (
            ["IMU"] + [str(v) for v in accel] + [str(v) for v in gyro] + ["24.5", "1"]
        )
        imu = ImuTelemetry.from_tokens(tokens)
        assert imu is not None
        return imu

    def test_accel_g_normalizes_gravity_to_one_g(self):
        imu = self._imu((0.0, 0.0, 9.80665))

        assert imu.accel_g == pytest.approx((0.0, 0.0, 1.0))

    def test_level_orientation_reads_zero_roll_and_pitch(self):
        imu = self._imu((0.0, 0.0, 9.80665))

        assert imu.roll_deg == pytest.approx(0.0)
        assert imu.pitch_deg == pytest.approx(0.0)

    def test_gyro_dps_converts_rad_per_s_to_deg_per_s(self):
        imu = self._imu((0.0, 0.0, 9.80665), gyro=(math.pi, 0.0, -math.pi / 2))

        assert imu.gyro_dps == pytest.approx((180.0, 0.0, -90.0))

    def test_gravity_on_plus_x_reads_pitch_minus_90(self):
        imu = self._imu((9.80665, 0.0, 0.0))

        assert imu.pitch_deg == pytest.approx(-90.0)

    def test_gravity_on_plus_y_reads_roll_plus_90(self):
        imu = self._imu((0.0, 9.80665, 0.0))

        assert imu.roll_deg == pytest.approx(90.0)


class TestImuTagDispatch:
    # A segment whose first token is not the IMU tag is a dispatch miss, not
    # corruption: from_tokens returns None, so
    # error_count stays an alarm-meaningful count of broken IMU segments only.

    @pytest.mark.parametrize(
        "segment",
        [JOINT_SEG, "", "BATT 12.6 1.2"],
        ids=["joint-segment", "empty-segment", "other-sensor-tag"],
    )
    def test_from_tokens_non_imu_segment_returns_none(self, segment):
        assert ImuTelemetry.from_tokens(segment.split()) is None


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

    def test_unknown_future_segment_is_ignored_and_not_counted_as_error(self):
        # Append-only wire contract: a tag this parser does not recognize is
        # assumed to be newer firmware, not corruption — dropped silently.
        # MAG is a hypothetical future magnetometer segment.
        parsed = parse_telemetry_line(f"FRONT; {JOINT_SEG};MAG 12.6 1.2 0.3")

        assert [j.name for j in parsed.joints] == ["FLHY"]
        assert parsed.imu is None

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
        parsed = parse_telemetry_line(
            f"FRONT; {JOINT_SEG};{IMU_SEG};{MALFORMED_IMU_SEG}"
        )

        assert parsed.imu is not None
        assert parsed.imu.valid is True

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

        assert (
            jt.format_compact(target=0.5) == "FLHY:0.123/0.500,512,12,(1,0),(0,128),3"
        )

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

    def test_imu_format_compact_pins_zero_negative_and_rounding(self):
        imu = ImuTelemetry(
            accel=(0.0, -1.234, 9.876),
            gyro=(0.0, -0.1236, 1.2346),
            temp_c=-2.36,
            valid=True,
        )

        assert imu.format_compact() == (
            "a:(0.00,-1.23,9.88)m/s2 g:(0.000,-0.124,1.235)rad/s -2.4C"
        )

    def test_imu_format_compact_keeps_motion_when_temperature_is_nan(self):
        imu = ImuTelemetry(
            accel=(1.0, 2.0, 3.0),
            gyro=(4.0, 5.0, 6.0),
            temp_c=float("nan"),
            valid=True,
        )

        assert imu.format_compact() == (
            "a:(1.00,2.00,3.00)m/s2 g:(4.000,5.000,6.000)rad/s nanC"
        )


class TestSdkImuStorage:
    def test_leader_line_populates_imu_and_joints(self):
        sdk = _bare_sdk()

        sdk._parse_telemetry_line(LEADER_LINE)

        assert sdk.imu is not None
        assert sdk.imu.temp_c == 24.5
        assert sdk.joints["FLHY"].pos == 0.123

    def test_follower_line_preserves_last_leader_imu_sample(self):
        # Followers never carry an IMU segment; their lines must not clobber
        # the last sample the leader delivered.
        sdk = _bare_sdk()
        sdk._parse_telemetry_line(LEADER_LINE)

        sdk._parse_telemetry_line(FOLLOWER_LINE)

        assert sdk.imu is not None
        assert "RLHY" in sdk.joints

    def test_malformed_imu_segment_preserves_last_good_sample(self):
        # One corrupt tick must not erase the newest good data; the last
        # good sample wins until a well-formed segment replaces it.
        sdk = _bare_sdk()
        sdk._parse_telemetry_line(LEADER_LINE)

        sdk._parse_telemetry_line(MALFORMED_IMU_LINE)

        assert sdk.imu is not None
        assert sdk.imu.valid is True

    def test_second_fresh_sample_replaces_every_stored_imu_field(self):
        sdk = _bare_sdk()
        sdk._parse_telemetry_line(LEADER_LINE)
        first = sdk.imu
        replacement_segment = "IMU -1.25 2.5 8.75 -0.4 0.5 -0.6 31.2 1"

        sdk._parse_telemetry_line(f"FRONT; {JOINT_SEG};{replacement_segment}")

        assert sdk.imu is not None
        assert sdk.imu is not first
        assert sdk.imu.accel == (-1.25, 2.5, 8.75)
        assert sdk.imu.gyro == (-0.4, 0.5, -0.6)
        assert sdk.imu.temp_c == 31.2
        assert sdk.imu.valid is True

    def test_imu_only_leader_line_stores_sample_without_joints(self):
        sdk = _bare_sdk()

        sdk._parse_telemetry_line(f"FRONT; {IMU_SEG}")

        assert sdk.imu is not None
        assert sdk.imu.valid is True
        assert sdk.joints == {}

    def test_first_malformed_imu_leaves_storage_empty(self):
        sdk = _bare_sdk()

        sdk._parse_telemetry_line(MALFORMED_IMU_LINE)

        assert sdk.imu is None

    @pytest.mark.parametrize(
        "line",
        ["FRONT; ", "LEFT ;", "RIGHT;"],
        ids=["front-leader", "left-follower", "right-follower"],
    )
    def test_role_prefix_only_line_is_a_noop(self, line):
        # Plausible on the wire (board booted, no joints enumerated yet):
        # must not raise and must leave joints/imu untouched.
        sdk = _bare_sdk()

        sdk._parse_telemetry_line(line)

        assert sdk.joints == {}
        assert sdk.imu is None

    def test_role_prefix_only_line_preserves_prior_state(self):
        sdk = _bare_sdk()
        sdk._parse_telemetry_line(LEADER_LINE)

        sdk._parse_telemetry_line("FRONT; ")

        assert sdk.imu is not None
        assert "FLHY" in sdk.joints

    def test_connect_resets_the_imu_cache(self):
        # connect() gives every connection a clean slate: cleared IMU cache and
        # a re-armed one-shot stale warning. Seed both with pre-connect traffic,
        # then prove connect() wipes them.
        sdk = _bare_sdk()
        sdk._parse_telemetry_line(STALE_LEADER_LINE)  # imu cached + stale-warn armed

        assert sdk.imu is not None
        assert sdk._imu_stale_warned is True

        # Patch serial + sleep + Thread INSIDE the module namespace so connect()
        # opens no port, waits no 5 s, and starts no background reader thread.
        with (
            mock.patch("firmware.krabby_mcu.serial.Serial"),
            mock.patch("firmware.krabby_mcu.time.sleep"),
            mock.patch("firmware.krabby_mcu.threading.Thread"),
        ):
            assert sdk.connect() is True
        sdk.running = False  # no reader was started, but keep state deterministic

        assert sdk.imu is None
        assert sdk._imu_stale_warned is False


class TestSdkThreeStateImuModel:
    # docs/M16-ERROR-HANDLING.md: sdk.imu is None (never seen) is a distinct
    # state from sdk.imu.valid False (sensor present but not responding),
    # which is distinct from a fresh sample.

    def test_imu_is_none_until_first_leader_sample(self):
        sdk = _bare_sdk()

        sdk._parse_telemetry_line(FOLLOWER_LINE)

        assert sdk.imu is None  # absence by design, not a failure

    def test_imu_is_stale_when_sensor_present_but_not_valid(self):
        sdk = _bare_sdk()

        sdk._parse_telemetry_line(STALE_LEADER_LINE)

        assert sdk.imu is not None  # the sample is kept, not discarded
        assert sdk.imu.valid is False

    def test_imu_is_fresh_after_recovery_from_stale(self):
        sdk = _bare_sdk()
        sdk._parse_telemetry_line(STALE_LEADER_LINE)

        sdk._parse_telemetry_line(LEADER_LINE)

        assert sdk.imu is not None
        assert sdk.imu.valid is True


class TestSdkImuValidityTransitions:
    # Class B: a persistent valid=0 condition arrives on every tick, so the
    # warning is one-shot per transition into the invalid state — actionable
    # once, noise thereafter.

    def test_transition_to_invalid_logs_exactly_one_warning(self, caplog):
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_telemetry_line(STALE_LEADER_LINE)
            sdk._parse_telemetry_line(STALE_LEADER_LINE)  # still invalid: no repeat

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "valid=0" in warnings[0].getMessage()

    def test_recovery_then_reentry_into_invalid_warns_again(self, caplog):
        # A valid sample re-arms the one-shot so the *next* failure episode
        # is surfaced too.
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_telemetry_line(STALE_LEADER_LINE)  # episode 1
            sdk._parse_telemetry_line(LEADER_LINE)  # recovery
            sdk._parse_telemetry_line(STALE_LEADER_LINE)  # episode 2

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2

    def test_valid_samples_log_nothing(self, caplog):
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_telemetry_line(LEADER_LINE)

        assert [r for r in caplog.records if r.levelno == logging.WARNING] == []

    def test_follower_absence_logs_nothing(self, caplog):
        # Class C: a follower never carrying an IMU segment is the normal
        # state of a healthy system — by design it produces zero log output.
        sdk = _bare_sdk()

        with caplog.at_level(logging.WARNING, logger="KrabbySDK"):
            sdk._parse_telemetry_line(FOLLOWER_LINE)

        assert caplog.records == []
