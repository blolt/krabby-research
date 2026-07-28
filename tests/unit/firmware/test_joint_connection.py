"""Host side of the disconnected-actuator fix (M16 Task 2).

A channel with no motor has a floating pot pin that streams high-variance ADC
noise; the firmware (LinearActuator::updateSensors / isConnected in
actuator_manager.h) detects this and reports pos as NaN instead of noise,
keeping the 9-token joint segment otherwise intact. The host reads NaN as
"disconnected" via JointTelemetry.connected.

The production firmware decision (PotValidityTracker plus current attachment)
has native C++ coverage. These tests pin the resulting *wire contract*:
finite pos <-> connected, "nan" <-> disconnected. In particular, a
driven/jogged joint stays connected while its real position changes quickly.

Naming: test_<unit>_<condition>_<expected>, arrange/act/assert body structure.
"""
import math

from firmware.interfaces.joint_telemetry import JointTelemetry, parse_telemetry_line

CONNECTED_SEG = "FLHY 0.123 512 12 1 0 0 128 3"
# Same channel unplugged: pos = "nan", the rest of the fields unchanged in shape.
DISCONNECTED_SEG = "FLHY nan 517 0 0 0 0 0 3"


class TestJointConnectedFlag:
    def test_finite_pos_segment_is_connected(self):
        jt = JointTelemetry.from_tokens(CONNECTED_SEG.split())

        assert jt is not None
        assert jt.connected is True
        assert jt.pos == 0.123

    def test_nan_pos_segment_is_disconnected(self):
        jt = JointTelemetry.from_tokens(DISCONNECTED_SEG.split())

        assert jt is not None
        assert jt.connected is False
        assert math.isnan(jt.pos)

    def test_inf_pos_segment_is_disconnected(self):
        # AVR Print emits "inf" for an over-range float; float() accepts it.
        # A non-finite pos is not a live position, so it must read disconnected
        # (isfinite, not just isnan) and render the DISC form -- never surface
        # an 'inf' position through format_compact.
        inf_seg = "FLHY inf 517 0 0 0 0 0 3"
        jt = JointTelemetry.from_tokens(inf_seg.split())

        assert jt is not None
        assert jt.connected is False
        assert not math.isfinite(jt.pos)
        assert jt.format_compact() == "FLHY:DISC,517,0"

    def test_disconnected_segment_keeps_its_other_fields(self):
        # The fix must not cost the rest of the channel's telemetry -- pot,
        # current, and the hall count still parse.
        jt = JointTelemetry.from_tokens(DISCONNECTED_SEG.split())

        assert jt.name == "FLHY"
        assert jt.pot == 517
        assert jt.current == 0
        assert jt.saf == 3


class TestDisconnectedJointInLine:
    def test_disconnected_joint_is_kept_not_dropped(self):
        # A disconnected channel is still a channel; it must remain in the
        # parsed joints (as disconnected), not vanish like a malformed segment.
        parsed = parse_telemetry_line(f"FRONT; {DISCONNECTED_SEG}")

        assert [j.name for j in parsed.joints] == ["FLHY"]
        assert parsed.joints[0].connected is False

    def test_line_mixes_connected_and_disconnected_joints(self):
        second = CONNECTED_SEG.replace("FLHY", "FLHL")
        parsed = parse_telemetry_line(f"FRONT; {DISCONNECTED_SEG};{second}")

        by_name = {j.name: j for j in parsed.joints}
        assert by_name["FLHY"].connected is False
        assert by_name["FLHL"].connected is True


class TestFormatCompact:
    def test_connected_joint_shows_position(self):
        jt = JointTelemetry.from_tokens(CONNECTED_SEG.split())

        assert jt.format_compact() == "FLHY:0.123,512,12,(1,0),(0,128),3"

    def test_disconnected_joint_shows_disc_marker_not_a_position(self):
        jt = JointTelemetry.from_tokens(DISCONNECTED_SEG.split())

        assert jt.format_compact() == "FLHY:DISC,517,0"


# A pot wiper shorted to a rail reads a STABLE 1023 with real stall current
# (driven, EN high). Firmware rejects it via the sane-band validity state and
# emits pos = "nan" -- so on the wire it is indistinguishable from a float and
# the host must read it disconnected, current draw notwithstanding (AC 2f, and
# the closed OR-leak: a drawing motor no longer vouches for a dead pot).
RAIL_SHORTED_SEG = "FLHY nan 1023 45 1 1 0 200 3"
# Same channel actively moving under drive (EN high on both, firmware prints en
# twice): a real, changing, in-band position.
MOVING_SEG = "FLHY 0.742 760 30 1 1 0 200 5"
# Two consecutive ticks of a fast full-PWM jog: the pot leaps ~250 counts
# between ticks (well past any idle slew budget), but EN is high so the MCU
# suppresses the slew test and emits a finite pos both ticks. Neither may read
# disconnected -- this is the moving/jogged false-disconnect the prior fix hit.
JOG_TICK_A = "FLHY 0.300 300 210 1 1 0 255 7"
JOG_TICK_B = "FLHY 0.550 555 205 1 1 0 255 9"
# Attached but idle and never driven: EN low, no current, but a valid pot -> a
# finite position. Must stay attached (AC 2d); the current-based attachment FSM
# remains unknown until driven evidence exists, so idle current is never used.
IDLE_ATTACHED_SEG = "FLHY 0.500 512 0 0 0 0 0 3"


class TestRailShortedPot:
    def test_rail_shorted_pot_is_disconnected(self):
        jt = JointTelemetry.from_tokens(RAIL_SHORTED_SEG.split())

        assert jt is not None
        assert jt.connected is False
        assert math.isnan(jt.pos)

    def test_rail_shorted_pot_shows_disc_despite_current(self):
        # The rail value (pot=1023) and stall current (45) must not leak through
        # as a live position.
        jt = JointTelemetry.from_tokens(RAIL_SHORTED_SEG.split())

        assert jt.format_compact() == "FLHY:DISC,1023,45"


class TestMovingJointNotFalselyDisconnected:
    def test_moving_joint_stays_connected(self):
        # Real motion produces a finite pos; the host must not read a moving
        # joint as disconnected (the per-tick slew metric does not inflate under
        # genuine motion).
        jt = JointTelemetry.from_tokens(MOVING_SEG.split())

        assert jt is not None
        assert jt.connected is True
        assert jt.pos == 0.742

    def test_fast_jog_stays_connected_across_ticks(self):
        # EN-gated slew: a full-PWM jog leaps ~250 counts/tick, far past the
        # idle slew budget, yet both ticks stay connected because the MCU
        # suppresses the slew test while EN is high. Guards the prior fix's
        # HIGH regression (a moving joint false-disconnecting) at the wire.
        a = JointTelemetry.from_tokens(JOG_TICK_A.split())
        b = JointTelemetry.from_tokens(JOG_TICK_B.split())

        assert a.connected is True and b.connected is True
        assert abs(b.pot - a.pot) > 200  # slew far exceeds the idle budget

    def test_idle_attached_joint_stays_connected(self):
        # Attached, idle, never driven (EN low, zero current) but a valid pot:
        # still attached (AC 2d) -- attachment remains unknown/allowed until
        # usable driven-current evidence exists.
        jt = JointTelemetry.from_tokens(IDLE_ATTACHED_SEG.split())

        assert jt is not None
        assert jt.connected is True
        assert jt.pos == 0.500


class TestJointNameGrammarGuard:
    def test_unknown_9_token_name_is_not_a_phantom_joint(self):
        # A garbled/unknown name that still has the joint's 9-token shape must
        # not be misparsed as a joint.
        garbled = CONNECTED_SEG.replace("FLHY", "XZQW")

        assert JointTelemetry.from_tokens(garbled.split()) is None

    def test_unknown_9_token_segment_dropped_from_line(self):
        # An unknown appended segment that happens to be 9 tokens is ignored
        # (append-only wire contract), not surfaced as a phantom joint.
        line = f"FRONT; {CONNECTED_SEG};WAT0 1 2 3 4 5 6 7 8"
        parsed = parse_telemetry_line(line)

        assert [j.name for j in parsed.joints] == ["FLHY"]

    def test_every_real_joint_name_is_accepted(self):
        # All 18 firmware joint names ({F,R,M}{L,R}{HY,HL,KL}) parse.
        names = [
            b + s + j
            for b in "FRM"
            for s in "LR"
            for j in ("HY", "HL", "KL")
        ]
        for name in names:
            seg = CONNECTED_SEG.replace("FLHY", name)
            jt = JointTelemetry.from_tokens(seg.split())
            assert jt is not None and jt.name == name
