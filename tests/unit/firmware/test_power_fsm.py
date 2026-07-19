"""Unit tests for the pure battery-protective state machine (M16 Task 4).

Mirrors the Task 3 BATT test style (test_battery_telemetry.py): exhaustive,
table-driven, no serial I/O. Exercises the pure ``power_fsm_step`` decision core
directly — every threshold crossing, the downward-cut debounce, the recovery
hysteresis, the one-way OVER_VOLT latch, and the valid-guard.

Thresholds under test (mirroring sensors_config.h):
  WARN 24.8  SOFT_CUT 24.0  HARD_CUT 22.4  OVER_VOLT 29.6  RECOVERY 25.8
  cut debounce = POWER_CUT_DEBOUNCE_TICKS consecutive ticks below a cut threshold
  (SOFT strict <, HARD inclusive <=); OVER_VOLT debounce =
  POWER_OVER_VOLT_DEBOUNCE_TICKS consecutive ticks at/above OVER_VOLT. An INVALID
  tick resets any in-progress run; a latched counter saturates at its target.
"""
import math

import pytest

from firmware.interfaces.joint_telemetry import PowerState
from firmware.interfaces.power_fsm import (
    PACK_HARD_CUT_V,
    PACK_OVER_VOLT_V,
    PACK_RECOVERY_V,
    PACK_SOFT_CUT_V,
    PACK_WARN_V,
    POWER_CUT_DEBOUNCE_TICKS,
    POWER_OVER_VOLT_DEBOUNCE_TICKS,
    PowerFsmResult,
    power_fsm_step,
)

N = POWER_CUT_DEBOUNCE_TICKS  # consecutive ticks to latch a cut
OV_N = POWER_OVER_VOLT_DEBOUNCE_TICKS  # consecutive ticks to latch OVER_VOLT


def run(initial_state, readings, below_soft=0, below_hard=0, over_volt=0):
    """Thread a sequence of readings through the FSM from an initial state.

    Each reading is a bare voltage (valid=True) or a (voltage, valid) tuple.
    Returns the list of PowerFsmResult, one per reading, so a test can assert
    both the final state and the per-tick trace (e.g. debounce timing)."""
    res = PowerFsmResult(initial_state, below_soft, below_hard, over_volt)
    trace = []
    for item in readings:
        v, valid = item if isinstance(item, tuple) else (item, True)
        res = power_fsm_step(
            res.state, v, valid,
            res.below_soft_ticks, res.below_hard_ticks, res.over_volt_ticks,
        )
        trace.append(res)
    return trace


def final_state(initial_state, readings, **kw):
    return run(initial_state, readings, **kw)[-1].state


class TestNormalWarnBand:
    """WARN is telemetry-only: instantaneous NORMAL<->WARN, no hysteresis."""

    def test_healthy_pack_is_normal(self):
        assert final_state(PowerState.NORMAL, [25.5]) == PowerState.NORMAL

    def test_normal_to_warn_is_instantaneous(self):
        # A single tick below WARN latches WARN — no debounce on the up-band.
        assert final_state(PowerState.NORMAL, [24.7]) == PowerState.WARN

    def test_warn_threshold_is_inclusive_normal(self):
        # v == WARN_V reads NORMAL (>=), one tick below reads WARN.
        assert final_state(PowerState.NORMAL, [PACK_WARN_V]) == PowerState.NORMAL
        assert final_state(PowerState.NORMAL, [PACK_WARN_V - 0.01]) == PowerState.WARN

    def test_warn_recovers_to_normal_instantly(self):
        # No RECOVERY gate on WARN: rising back above WARN_V returns NORMAL at once.
        assert final_state(PowerState.WARN, [25.0]) == PowerState.NORMAL

    def test_warn_band_holds_between_soft_and_warn(self):
        # 24.0 <= v < 24.8 is the WARN band; soft counter stays 0 (v not < SOFT).
        trace = run(PowerState.NORMAL, [24.2, 24.2, 24.2, 24.2, 24.2])
        assert all(r.state == PowerState.WARN for r in trace)
        assert all(r.below_soft_ticks == 0 for r in trace)


class TestSoftCutDebounce:
    """SOFT_CUT latches only after N consecutive ticks below SOFT_CUT_V."""

    SOFT_LOW = (PACK_SOFT_CUT_V + PACK_HARD_CUT_V) / 2  # below SOFT, above HARD

    def test_n_minus_one_ticks_below_soft_does_not_cut(self):
        trace = run(PowerState.NORMAL, [self.SOFT_LOW] * (N - 1))
        assert trace[-1].state == PowerState.WARN
        assert trace[-1].below_soft_ticks == N - 1

    def test_n_ticks_below_soft_latches_soft_cut(self):
        trace = run(PowerState.NORMAL, [self.SOFT_LOW] * N)
        assert trace[-1].state == PowerState.SOFT_CUT
        # The Nth tick is exactly where it flips.
        assert trace[N - 2].state == PowerState.WARN
        assert trace[N - 1].state == PowerState.SOFT_CUT

    def test_one_tick_above_soft_resets_the_debounce(self):
        # N-1 below, one tick back in the WARN band, then N-1 more below: still
        # no cut, because the run was broken.
        readings = [self.SOFT_LOW] * (N - 1) + [24.5] + [self.SOFT_LOW] * (N - 1)
        trace = run(PowerState.NORMAL, readings)
        assert trace[N - 1].below_soft_ticks == 0  # the WARN-band tick reset it
        assert trace[-1].state == PowerState.WARN

    def test_soft_boundary_is_not_below(self):
        # v == SOFT_CUT_V is NOT below SOFT (strict <), so it never counts down.
        trace = run(PowerState.NORMAL, [PACK_SOFT_CUT_V] * (N + 2))
        assert all(r.below_soft_ticks == 0 for r in trace)
        assert trace[-1].state == PowerState.WARN


class TestHardCutDebounce:
    """HARD_CUT latches after N ticks at/below HARD_CUT_V and wins over SOFT."""

    HARD_LOW = PACK_HARD_CUT_V - 0.5

    def test_n_minus_one_ticks_below_hard_does_not_cut(self):
        trace = run(PowerState.NORMAL, [self.HARD_LOW] * (N - 1))
        assert trace[-1].state == PowerState.WARN

    def test_n_ticks_below_hard_latches_hard_cut_directly(self):
        # Below HARD is also below SOFT, but the Nth tick trips HARD (checked
        # first) — never routing through SOFT_CUT.
        trace = run(PowerState.NORMAL, [self.HARD_LOW] * N)
        assert [r.state for r in trace][:-1].count(PowerState.SOFT_CUT) == 0
        assert trace[-1].state == PowerState.HARD_CUT

    def test_hard_boundary_is_inclusive(self):
        # D15: v == HARD_CUT_V IS at-or-below HARD (inclusive <=), so it counts
        # toward the hard cut — the single source of truth for SOFT->HARD, matching
        # the controller's boundary. N ticks at exactly HARD_CUT_V latch HARD_CUT.
        trace = run(PowerState.NORMAL, [PACK_HARD_CUT_V] * N)
        assert trace[-1].below_hard_ticks == N
        assert trace[-1].state == PowerState.HARD_CUT

    def test_just_above_hard_counts_soft_only(self):
        # A hair above HARD_CUT_V is not <= HARD, so it counts SOFT only.
        v = PACK_HARD_CUT_V + 0.01
        trace = run(PowerState.NORMAL, [v] * N)
        assert trace[-1].below_hard_ticks == 0
        assert trace[-1].state == PowerState.SOFT_CUT  # soft debounce still fires


class TestDebounceSaturation:
    """D16b: counters increment but SATURATE at their debounce target once latched,
    so the C++ uint16_t mirror can't wrap under a long sustained low/high pack."""

    def test_below_soft_counter_saturates_at_n(self):
        low = (PACK_SOFT_CUT_V + PACK_HARD_CUT_V) / 2  # below SOFT, above HARD
        trace = run(PowerState.NORMAL, [low] * (N + 5))
        assert max(r.below_soft_ticks for r in trace) == N
        assert trace[-1].below_soft_ticks == N          # pinned, not still climbing
        assert trace[-1].state == PowerState.SOFT_CUT

    def test_below_hard_counter_saturates_at_n(self):
        low = PACK_HARD_CUT_V - 0.5
        trace = run(PowerState.NORMAL, [low] * (N + 5))
        assert max(r.below_hard_ticks for r in trace) == N
        assert trace[-1].below_hard_ticks == N
        assert trace[-1].state == PowerState.HARD_CUT


class TestOverVoltDebouncedAndOneWay:
    """D16c: OVER_VOLT latches after OV_N consecutive valid ticks at/above
    OVER_VOLT_V, then is terminal/one-way."""

    def test_over_volt_needs_debounce_from_normal(self):
        # OV_N-1 high ticks do NOT latch; the OV_N-th does.
        assert final_state(PowerState.NORMAL, [PACK_OVER_VOLT_V] * (OV_N - 1)) == PowerState.NORMAL
        trace = run(PowerState.NORMAL, [PACK_OVER_VOLT_V] * OV_N)
        assert trace[OV_N - 2].state == PowerState.NORMAL  # still holding one tick before
        assert trace[-1].state == PowerState.OVER_VOLT

    def test_over_volt_counter_counts_up_then_latches(self):
        trace = run(PowerState.NORMAL, [PACK_OVER_VOLT_V] * (OV_N - 1))
        assert [r.over_volt_ticks for r in trace] == list(range(1, OV_N))

    def test_over_volt_debounce_resets_on_a_non_high_tick(self):
        # A single tick below the threshold breaks the run — no latch.
        readings = [PACK_OVER_VOLT_V] * (OV_N - 1) + [25.0] + [PACK_OVER_VOLT_V] * (OV_N - 1)
        trace = run(PowerState.NORMAL, readings)
        assert trace[OV_N - 1].over_volt_ticks == 0  # the normal tick reset it
        assert trace[-1].state == PowerState.NORMAL

    def test_over_volt_debounce_resets_on_invalid_tick(self):
        # An INVALID reading mid-run also breaks it (D16a): dropped ticks aren't
        # trustworthy over-voltage confirmations.
        readings = [PACK_OVER_VOLT_V] * (OV_N - 1) + [(float("nan"), True)] + [PACK_OVER_VOLT_V] * (OV_N - 1)
        trace = run(PowerState.NORMAL, readings)
        assert trace[-1].state == PowerState.NORMAL

    def test_over_volt_threshold_inclusive(self):
        # At/above OVER_VOLT_V counts toward the latch; just under never does.
        assert final_state(PowerState.NORMAL, [PACK_OVER_VOLT_V + 0.5] * OV_N) == PowerState.OVER_VOLT
        assert final_state(PowerState.NORMAL, [PACK_OVER_VOLT_V - 0.01] * (OV_N + 3)) == PowerState.NORMAL

    def test_over_volt_trips_from_warn_or_soft_cut_after_debounce(self):
        assert final_state(PowerState.WARN, [PACK_OVER_VOLT_V] * OV_N) == PowerState.OVER_VOLT
        assert final_state(PowerState.SOFT_CUT, [PACK_OVER_VOLT_V] * OV_N) == PowerState.OVER_VOLT
        # SOFT_CUT holds until the OV debounce completes, then latches OVER_VOLT.
        soft_trace = run(PowerState.SOFT_CUT, [PACK_OVER_VOLT_V] * OV_N)
        assert soft_trace[OV_N - 2].state == PowerState.SOFT_CUT

    def test_over_volt_is_one_way_through_a_normal_reading(self):
        # Once latched, a perfectly healthy reading does NOT clear it.
        assert final_state(PowerState.OVER_VOLT, [25.0]) == PowerState.OVER_VOLT

    def test_over_volt_stays_latched_through_low_and_recovery_readings(self):
        readings = [25.0, PACK_RECOVERY_V + 1.0, 23.0, 27.0]
        assert all(r.state == PowerState.OVER_VOLT for r in run(PowerState.OVER_VOLT, readings))

    def test_over_volt_latch_ignores_even_invalid_readings(self):
        assert final_state(PowerState.OVER_VOLT, [(float("nan"), True), (25.0, False)]) == PowerState.OVER_VOLT

    def test_over_volt_latches_from_sleep_via_no_resuming(self):
        # An over-voltage charger fault DURING SLEEP must hold SLEEP while the
        # over_volt debounce accumulates and then latch OVER_VOLT — it must NOT take
        # a spurious RESUMING beat (which would re-power the Orin mid-fault). The
        # SLEEP-recovery gate is PACK_RECOVERY_V < pack_v < PACK_OVER_VOLT_V, so an
        # at/above-OVER_VOLT reading never opens the resume path.
        readings = [PACK_OVER_VOLT_V + 0.5] * (OV_N + 2)
        trace = run(PowerState.SLEEP, readings)
        assert all(r.state is not PowerState.RESUMING for r in trace)
        assert trace[-1].state == PowerState.OVER_VOLT


class TestRecoveryHysteresis:
    """SLEEP is left only when the pack climbs STRICTLY above RECOVERY."""

    def test_sleep_holds_below_recovery(self):
        assert final_state(PowerState.SLEEP, [PACK_RECOVERY_V - 1.0]) == PowerState.SLEEP

    def test_recovery_gate_is_strict(self):
        # v == RECOVERY_V does not resume (strict >).
        assert final_state(PowerState.SLEEP, [PACK_RECOVERY_V]) == PowerState.SLEEP
        assert final_state(PowerState.SLEEP, [PACK_RECOVERY_V + 0.01]) == PowerState.RESUMING

    def test_sleep_does_not_resume_in_the_warn_band(self):
        # A pack sitting at WARN-level (below RECOVERY) must stay asleep — this is
        # the whole point of the RECOVERY hysteresis being above WARN.
        assert final_state(PowerState.SLEEP, [PACK_WARN_V]) == PowerState.SLEEP

    def test_resuming_settles_to_normal_when_healthy(self):
        assert final_state(PowerState.RESUMING, [27.0]) == PowerState.NORMAL

    def test_full_sleep_to_normal_path(self):
        # SLEEP --(v>RECOVERY)--> RESUMING --(healthy)--> NORMAL.
        trace = run(PowerState.SLEEP, [PACK_RECOVERY_V + 0.5, 27.5])
        assert [r.state for r in trace] == [PowerState.RESUMING, PowerState.NORMAL]


class TestCommittedShutdownStickiness:
    """A started shutdown commits: SOFT_CUT/HARD_CUT do not auto-recover on a
    voltage rebound. Recovery only comes back through SLEEP + RECOVERY."""

    def test_soft_cut_does_not_recover_on_voltage_rebound(self):
        assert final_state(PowerState.SOFT_CUT, [25.5, 26.0]) == PowerState.SOFT_CUT

    def test_soft_cut_escalates_to_hard_cut_on_debounced_collapse(self):
        # Fix 4 spirit at the FSM layer: SOFT_CUT + N ticks below HARD -> HARD_CUT.
        trace = run(PowerState.SOFT_CUT, [PACK_HARD_CUT_V - 0.5] * N)
        assert trace[-1].state == PowerState.HARD_CUT
        assert trace[N - 2].state == PowerState.SOFT_CUT

    def test_hard_cut_is_sticky(self):
        assert final_state(PowerState.HARD_CUT, [25.0, 27.0]) == PowerState.HARD_CUT


class TestValidGuard:
    """An untrustworthy reading holds state AND resets the debounce counters (D16a):
    a dropped tick is neither below nor above a threshold, so it breaks the run."""

    @pytest.mark.parametrize("bad", [
        pytest.param((23.0, False), id="valid-flag-false"),
        pytest.param((float("nan"), True), id="nan-pack-v"),
        pytest.param((float("inf"), True), id="inf-pack-v"),
        pytest.param((50.0, True), id="above-plausible-range"),
        pytest.param((-1.0, True), id="below-plausible-range"),
    ])
    def test_invalid_reading_holds_state(self, bad):
        for state in (PowerState.NORMAL, PowerState.WARN, PowerState.SOFT_CUT,
                      PowerState.HARD_CUT, PowerState.SLEEP):
            assert final_state(state, [bad]) == state

    def test_invalid_reading_resets_debounce_counters(self):
        # D16a: an invalid tick zeroes the carried counters (does not freeze them).
        res = power_fsm_step(PowerState.WARN, float("nan"), True,
                             below_soft_ticks=2, below_hard_ticks=1, over_volt_ticks=1)
        assert res.state == PowerState.WARN
        assert res.below_soft_ticks == 0 and res.below_hard_ticks == 0
        assert res.over_volt_ticks == 0

    def test_dropout_resets_a_cut_debounce_run(self):
        # D16a NEW behavior: N-1 ticks below soft, then an INVALID dropout, then one
        # more below. The dropout RESETS the run (a ~200 ms contiguous INA228 outage
        # is not a trustworthy below-threshold confirmation), so the trailing tick
        # restarts the count at 1 and NO cut latches.
        low = PACK_SOFT_CUT_V - 0.2
        readings = [low] * (N - 1) + [(float("nan"), True)] + [low]
        trace = run(PowerState.NORMAL, readings)
        assert trace[N - 2].below_soft_ticks == N - 1   # climbed to N-1 before the drop
        assert trace[N - 1].below_soft_ticks == 0       # dropout reset it
        assert trace[-1].below_soft_ticks == 1          # restarted at 1
        assert trace[-1].state == PowerState.WARN        # no cut

    def test_full_run_survives_only_without_a_dropout(self):
        # Contrast: an UNBROKEN run of N below-soft ticks does latch — proving the
        # reset above is specifically the dropout's doing, not an off-by-one.
        low = PACK_SOFT_CUT_V - 0.2
        assert final_state(PowerState.NORMAL, [low] * N) == PowerState.SOFT_CUT


class TestPurity:
    def test_step_is_pure_no_shared_mutation(self):
        # Calling twice with the same args yields equal results (frozen dataclass).
        a = power_fsm_step(PowerState.NORMAL, 23.5, True, 1, 0)
        b = power_fsm_step(PowerState.NORMAL, 23.5, True, 1, 0)
        assert a == b

    def test_result_is_frozen(self):
        r = power_fsm_step(PowerState.NORMAL, 25.0, True)
        with pytest.raises(Exception):
            r.state = PowerState.WARN  # frozen dataclass rejects assignment


class TestFullDescentIntegration:
    def test_normal_to_soft_cut_full_descent(self):
        # Healthy -> WARN band -> sustained below SOFT -> SOFT_CUT, threading the
        # real carried counters the whole way.
        low = PACK_SOFT_CUT_V - 0.3
        readings = [25.0, 24.5] + [low] * N
        states = [r.state for r in run(PowerState.NORMAL, readings)]
        assert states[0] == PowerState.NORMAL
        assert states[1] == PowerState.WARN
        assert states[-1] == PowerState.SOFT_CUT

    def test_isfinite_matches_math(self):
        # Guard-rail: the guard's NaN test agrees with math.isfinite on the edge.
        assert not math.isfinite(float("nan"))
        assert final_state(PowerState.NORMAL, [(float("nan"), True)]) == PowerState.NORMAL
