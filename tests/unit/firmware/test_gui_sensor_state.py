"""Headless unit tests for the GUI IMU link-age state machine.

These exercise the two pure, module-level helpers extracted from the GUI so the
three-state readout and the identity-based sample latch can be tested WITHOUT
opening a Tk window (importing the module pulls tkinter, but no window is ever
created and no `tk.Tk()` is instantiated here).
"""
import pytest

from firmware.gui.app import (
    SENSOR_STALE_S,
    STATE_COLOR_OK,
    STATE_COLOR_STALE,
    format_battery_row,
    latch_imu,
    resolve_imu_state,
)
from firmware.interfaces.joint_telemetry import (
    BatteryTelemetry,
    ImuTelemetry,
    PowerState,
)


def _sample(valid=True):
    return ImuTelemetry(
        accel=(0.0, 0.0, 9.80665), gyro=(0.0, 0.0, 0.0), temp_c=24.0, valid=valid
    )


def _battery(
    power_state=PowerState.NORMAL,
    divergence=False,
    current=-3.25,
):
    return BatteryTelemetry(
        pack_volts=26.55,
        pack_current_amperes=current,
        pack_power_watts=86.3,
        pack_charge_coulombs=1450.4,
        battery_a_volts=13.35,
        battery_b_volts=13.20,
        divergence=divergence,
        power_state=power_state,
    )


class TestResolveImuState:
    def test_absent_when_no_sample(self):
        text, col = resolve_imu_state(None, None)
        assert text == "—"
        assert col == ""

    def test_sensor_stale_beats_link_fresh(self):
        # valid=0 (sensor present, not responding) is STALE even at age 0.
        text, col = resolve_imu_state(_sample(valid=False), 0.0)
        assert text == "STALE"
        assert col == STATE_COLOR_STALE

    def test_link_stale_when_age_exceeds_window(self):
        text, col = resolve_imu_state(_sample(valid=True), SENSOR_STALE_S + 0.5)
        assert text == "stale"
        assert col == STATE_COLOR_STALE

    def test_fresh_when_valid_and_recent(self):
        text, col = resolve_imu_state(_sample(valid=True), 0.0)
        assert text == "fresh"
        assert col == STATE_COLOR_OK

    def test_fresh_when_age_unknown(self):
        # Before the first latched sample, age is None -> treated as fresh.
        text, col = resolve_imu_state(_sample(valid=True), None)
        assert text == "fresh"
        assert col == STATE_COLOR_OK


class TestLatchImu:
    def test_new_sample_object_advances_timestamp(self):
        a = object()  # stand-in for a fresh ImuTelemetry; identity is all latch uses
        obj, ts = latch_imu(None, None, a, 100.0)
        assert obj is a
        assert ts == 100.0

    def test_same_instance_does_not_advance_timestamp(self):
        # THE bug catcher: a dead link keeps handing back the SAME object every
        # poll. The timestamp must stay put so the age can grow past the window
        # and the row flips to "stale" — the old code re-latched every poll and
        # the row showed "fresh" forever.
        a = object()
        obj, ts = latch_imu(None, None, a, 100.0)

        obj2, ts2 = latch_imu(obj, ts, a, 200.0)

        assert obj2 is a
        assert ts2 == 100.0  # unchanged

    def test_distinct_object_relatches(self):
        a, b = object(), object()
        obj, ts = latch_imu(None, None, a, 100.0)

        obj2, ts2 = latch_imu(obj, ts, b, 300.0)

        assert obj2 is b
        assert ts2 == 300.0

    def test_none_imu_preserves_prior_latch(self):
        a = object()
        obj, ts = latch_imu(None, None, a, 100.0)

        obj2, ts2 = latch_imu(obj, ts, None, 400.0)

        assert obj2 is a
        assert ts2 == 100.0


class TestFormatBatteryRow:
    def test_absent_sample_uses_placeholders_without_alarm_colors(self):
        presentation = format_battery_row(None, stale=False)

        assert {
            presentation.pack_volts,
            presentation.pack_current_amperes,
            presentation.pack_power_watts,
            presentation.pack_charge_coulombs,
            presentation.battery_a_volts,
            presentation.battery_b_volts,
            presentation.power_state,
            presentation.divergence,
        } == {"—"}
        assert presentation.power_state_color == ""
        assert presentation.divergence_color == ""

    def test_fresh_sample_formats_every_measurement(self):
        presentation = format_battery_row(_battery(), stale=False)

        assert presentation.pack_volts == "26.55"
        assert presentation.pack_current_amperes == "-3.25"
        assert presentation.pack_power_watts == "86.3"
        assert presentation.pack_charge_coulombs == "1450"
        assert presentation.battery_a_volts == "13.35"
        assert presentation.battery_b_volts == "13.20"
        assert presentation.power_state == "NORMAL"
        assert presentation.divergence == "ok"
        assert presentation.power_state_color == STATE_COLOR_OK
        assert presentation.divergence_color == ""

    def test_positive_current_keeps_an_explicit_plus_sign(self):
        presentation = format_battery_row(_battery(current=3.25), stale=False)
        assert presentation.pack_current_amperes == "+3.25"

    @pytest.mark.parametrize(
        ("state", "expected_text", "expected_color"),
        [
            pytest.param(PowerState.NORMAL, "NORMAL", STATE_COLOR_OK, id="normal"),
            pytest.param(PowerState.WARN, "WARN", STATE_COLOR_STALE, id="warn"),
            pytest.param(
                PowerState.SOFT_CUT, "SOFT_CUT", STATE_COLOR_STALE, id="soft-cut"
            ),
            pytest.param(
                PowerState.HARD_CUT, "HARD_CUT", STATE_COLOR_STALE, id="hard-cut"
            ),
            pytest.param(
                PowerState.OVER_VOLT, "OVER_VOLT", STATE_COLOR_STALE, id="over-volt"
            ),
            pytest.param(PowerState.SLEEP, "SLEEP", STATE_COLOR_OK, id="sleep"),
            pytest.param(
                PowerState.RESUMING, "RESUMING", STATE_COLOR_OK, id="resuming"
            ),
        ],
    )
    def test_each_defined_power_state_is_named_and_colored(
        self, state, expected_text, expected_color
    ):
        presentation = format_battery_row(_battery(power_state=state), stale=False)
        assert presentation.power_state == expected_text
        assert presentation.power_state_color == expected_color

    def test_unknown_power_state_remains_visible(self):
        presentation = format_battery_row(_battery(power_state=99), stale=False)
        assert presentation.power_state == "99"
        assert presentation.power_state_color == STATE_COLOR_OK

    def test_stale_link_overrides_state_text_and_color(self):
        presentation = format_battery_row(
            _battery(power_state=PowerState.NORMAL), stale=True
        )
        assert presentation.power_state == "stale"
        assert presentation.power_state_color == STATE_COLOR_STALE

    def test_divergence_has_independent_text_and_alarm_color(self):
        presentation = format_battery_row(_battery(divergence=True), stale=False)
        assert presentation.divergence == "DIVERGE"
        assert presentation.divergence_color == STATE_COLOR_STALE

    def test_later_sample_replaces_the_presented_measurement(self):
        first = format_battery_row(_battery(current=-3.25), stale=False)
        second = format_battery_row(_battery(current=4.75), stale=False)

        assert first.pack_current_amperes == "-3.25"
        assert second.pack_current_amperes == "+4.75"
