"""Headless unit tests for the GUI IMU link-age state machine.

These exercise the ImuRow state helpers without opening a Tk window.
"""

from firmware.gui.app import (
    SENSOR_STALE_S,
    STATE_COLOR_OK,
    STATE_COLOR_STALE,
    ImuRow,
)
from firmware.interfaces.imu_telemetry import ImuTelemetry


def _sample(valid=True):
    return ImuTelemetry(
        accel=(0.0, 0.0, 9.80665), gyro=(0.0, 0.0, 0.0), temp_c=24.0, valid=valid
    )


class TestResolveImuState:
    def test_absent_when_no_sample(self):
        text, col = ImuRow.resolve_state(None, None)
        assert text == "—"
        assert col == ""

    def test_sensor_down_beats_link_fresh(self):
        # valid=0 (sensor present, not responding) reads "down" even at age 0,
        # and is a different word from "stale" rather than a different case.
        text, col = ImuRow.resolve_state(_sample(valid=False), 0.0)
        assert text == "down"
        assert col == STATE_COLOR_STALE

    def test_link_stale_when_age_exceeds_window(self):
        text, col = ImuRow.resolve_state(_sample(valid=True), SENSOR_STALE_S + 0.5)
        assert text == "stale"
        assert col == STATE_COLOR_STALE

    def test_fresh_when_valid_and_recent(self):
        text, col = ImuRow.resolve_state(_sample(valid=True), 0.0)
        assert text == "fresh"
        assert col == STATE_COLOR_OK

    def test_fresh_when_age_unknown(self):
        # Before the first latched sample, age is None -> treated as fresh.
        text, col = ImuRow.resolve_state(_sample(valid=True), None)
        assert text == "fresh"
        assert col == STATE_COLOR_OK


class TestLatchImu:
    def test_new_sample_object_advances_timestamp(self):
        a = object()  # stand-in for a fresh ImuTelemetry; identity is all latch uses
        obj, ts = ImuRow.latch_sample(None, None, a, 100.0)
        assert obj is a
        assert ts == 100.0

    def test_same_instance_does_not_advance_timestamp(self):
        # THE bug catcher: a dead link keeps handing back the SAME object every
        # poll. The timestamp must stay put so the age can grow past the window
        # and the row flips to "stale" — the old code re-latched every poll and
        # the row showed "fresh" forever.
        a = object()
        obj, ts = ImuRow.latch_sample(None, None, a, 100.0)

        obj2, ts2 = ImuRow.latch_sample(obj, ts, a, 200.0)

        assert obj2 is a
        assert ts2 == 100.0  # unchanged

    def test_distinct_object_relatches(self):
        a, b = object(), object()
        obj, ts = ImuRow.latch_sample(None, None, a, 100.0)

        obj2, ts2 = ImuRow.latch_sample(obj, ts, b, 300.0)

        assert obj2 is b
        assert ts2 == 300.0

    def test_none_imu_preserves_prior_latch(self):
        a = object()
        obj, ts = ImuRow.latch_sample(None, None, a, 100.0)

        obj2, ts2 = ImuRow.latch_sample(obj, ts, None, 400.0)

        assert obj2 is a
        assert ts2 == 100.0
