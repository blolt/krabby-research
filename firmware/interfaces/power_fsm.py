"""Pure battery-protective state machine (M16 Task 4).

This is the *decision core* the leader MCU runs once per telemetry tick to pick
the pack's :class:`PowerState` from its measured voltage. It is deliberately
pure — no serial I/O, no timers, no ``millis()`` — so the exact same transition
rules can be unit-tested on the host and mirrored 1:1 in ``arduino/power_fsm.h``
(``powerFsmStep``). The side-effects the transitions *imply* — parking the
actuators, emitting ``PWR`` messages to the Orin, the 60 s ack-wait, the
force-off timer, the recovery poll — live in the C++ ``PowerController`` layer,
which calls this function and then acts on the returned state.

Design decisions baked into the transition rules (see the grant design critique):

1. **Valid-guard.** The FSM only advances on a trustworthy reading: ``valid``
   (both INA228s up, per ``battAppendTelemetry``) *and* a finite ``pack_v`` in
   ``[0, 40] V``. Any other input holds the current state and the debounce
   counters untouched — a wedged monitor never drives a shutdown.

2. **Debounced downward cuts.** Latching SOFT_CUT or HARD_CUT requires
   ``POWER_CUT_DEBOUNCE_TICKS`` *consecutive* valid ticks below the threshold, so
   a transient sag under a current spike (LiFePO4 sags ~internal_R x I) does not
   trip a protective shutdown. A single tick back above the threshold — or an
   INVALID reading (a dropped tick is not a healthy tick) — resets the counter.
   The counter saturates at ``POWER_CUT_DEBOUNCE_TICKS`` once latched (no unbounded
   growth; matters for the C++ ``uint16_t`` mirror). The SOFT_CUT boundary is
   strict ``<``; the HARD_CUT boundary is inclusive ``<=`` — the single source of
   truth for the SOFT->HARD escalation, consistent with the controller. The upward
   WARN transition is instantaneous.

7. **Debounced, one-way OVER_VOLT.** OVER_VOLT latches only after
   ``POWER_OVER_VOLT_DEBOUNCE_TICKS`` consecutive valid ticks at/above
   ``PACK_OVER_VOLT_V`` (a lone glitch-high sample must not trip it), and one
   INVALID tick resets that run. Once latched it is terminal: every subsequent
   tick returns OVER_VOLT regardless of ``pack_v`` (an early return before any
   other rule). A charger/BMS over-voltage fault must not silently self-clear.

**Recovery hysteresis.** SLEEP is left only when ``pack_v`` climbs strictly above
``PACK_RECOVERY_V`` (a *resting*-voltage gate — SLEEP de-energizes the motors —
set ~1.8 V above the *loaded* SOFT_CUT), routing through a transient RESUMING
beat so the controller can re-power the Orin and emit ``RESUMING`` before running.
SOFT_CUT/HARD_CUT do *not* auto-recover on a voltage rebound — once a graceful
shutdown has begun it commits, and the pack must fully recover past RECOVERY
(via SLEEP) to come back.
"""
from dataclasses import dataclass

from firmware.interfaces.joint_telemetry import PowerState

# --- Pack thresholds (V) — keep in sync with arduino/sensors_config.h ---
# Re-declared here (not imported) for the same reason TELEMETRY_INTERVAL_MS is:
# the firmware #defines are the source of truth on the wire, and these mirrors
# let the host-side FSM be tested without a C toolchain. If sensors_config.h
# changes, change these together (there is no build-time link between them).
PACK_WARN_V = 24.8       # ~20-30% SoC; telemetry-only WARN, no behavior change
PACK_SOFT_CUT_V = 24.0   # ~10% SoC; begin graceful shutdown (park + signal Orin)
PACK_HARD_CUT_V = 22.4   # margin above the ~20V internal-BMS cutoff; immediate stop
PACK_OVER_VOLT_V = 29.6  # charger/BMS fault; one-way protective cutout, no auto-resume
PACK_RECOVERY_V = 25.8   # auto-resume RESTING gate (SLEEP de-energizes motors); ~nominal 8S resting so a half pack wakes, ~1.8V above loaded SOFT_CUT. PROVISIONAL, 4h tunes vs real pack. Was 26.4 (F13/D36).

# Consecutive valid ticks below a cut threshold required to latch that cut.
# Keep in sync with POWER_CUT_DEBOUNCE_TICKS in sensors_config.h / power_fsm.h.
POWER_CUT_DEBOUNCE_TICKS = 4

# Consecutive valid ticks at/above PACK_OVER_VOLT_V required to latch OVER_VOLT.
# Keep in sync with POWER_OVER_VOLT_DEBOUNCE_TICKS in sensors_config.h / power_fsm.h.
POWER_OVER_VOLT_DEBOUNCE_TICKS = 3

# The plausibility window the valid-guard enforces on pack_v, mirroring the
# firmware's own bounds in battAppendTelemetry (arduino.ino): outside this a
# reading is treated as a wedged/browned-out monitor, not a real pack voltage.
PACK_V_MIN = 0.0
PACK_V_MAX = 40.0

# Running (monitoring) states from which the FSM freely re-evaluates the voltage
# band each tick. RESUMING is included so the transient resume beat settles into
# NORMAL/WARN once the pack reads healthy again. The cut/sleep states are NOT
# here: they are latched and only the listed rules (or the controller's
# ack/timer events) move them forward.
_RUNNING_STATES = (PowerState.NORMAL, PowerState.WARN, PowerState.RESUMING)


@dataclass(frozen=True)
class PowerFsmResult:
    """Return of :func:`power_fsm_step`: the next state plus the carried-forward
    debounce counters. Frozen so a step's output is a value, not mutable state —
    the caller threads it into the next call."""

    state: PowerState
    below_soft_ticks: int
    below_hard_ticks: int
    over_volt_ticks: int = 0


def _is_valid_reading(pack_v: float, valid: bool) -> bool:
    """The valid-guard predicate (fix 1): a trustworthy pack reading is a live
    monitor (`valid`) reporting a finite voltage inside the plausibility window.
    ``pack_v != pack_v`` is the NaN test (NaN is the only value unequal to
    itself), so a NAN-poisoned reading fails the guard without importing math."""
    return (
        valid
        and pack_v == pack_v  # not NaN
        and PACK_V_MIN <= pack_v <= PACK_V_MAX
    )


def power_fsm_step(
    state: PowerState,
    pack_v: float,
    valid: bool,
    below_soft_ticks: int = 0,
    below_hard_ticks: int = 0,
    over_volt_ticks: int = 0,
) -> PowerFsmResult:
    """Advance the protective FSM by one telemetry tick.

    Pure: the result depends only on the arguments. Thread the returned counters
    (and state) into the next call.

    Args:
        state: the current :class:`PowerState`.
        pack_v: measured pack voltage this tick (V).
        valid: True when the reading is trustworthy (both INA228s up).
        below_soft_ticks: consecutive prior ticks below SOFT_CUT (debounce carry).
        below_hard_ticks: consecutive prior ticks below HARD_CUT (debounce carry).
        over_volt_ticks: consecutive prior ticks at/above OVER_VOLT (debounce carry).
    """
    # Fix 7 — one-way OVER_VOLT latch. Terminal, checked before everything else
    # (even the valid-guard): once tripped the state never leaves OVER_VOLT, and
    # the counters are meaningless here, so zero them.
    if state == PowerState.OVER_VOLT:
        return PowerFsmResult(PowerState.OVER_VOLT, 0, 0, 0)

    # Fix 1 / D16a — valid-guard. An untrustworthy reading advances nothing AND
    # RESETS every debounce counter: a dropped reading (~a contiguous INA228
    # outage) is not "a tick below threshold" and is not "a tick above" either, so
    # it breaks any in-progress consecutive run rather than freezing it. Real cuts
    # require an UNBROKEN run of *trustworthy* readings, so a dropout must reset.
    if not _is_valid_reading(pack_v, valid):
        return PowerFsmResult(state, 0, 0, 0)

    # Update the consecutive-run counters (fix 2 / D16b/D16c). A reading outside a
    # counter's band resets it; a reading inside increments but SATURATES at the
    # debounce target (no unbounded growth — this is what keeps the C++ uint16_t
    # mirror from wrapping once a cut has latched). SOFT is strict `<`; HARD is
    # inclusive `<=` (D15 — the single source of truth for SOFT->HARD escalation,
    # consistent with the controller's boundary).
    below_soft = (
        min(below_soft_ticks + 1, POWER_CUT_DEBOUNCE_TICKS)
        if pack_v < PACK_SOFT_CUT_V else 0
    )
    below_hard = (
        min(below_hard_ticks + 1, POWER_CUT_DEBOUNCE_TICKS)
        if pack_v <= PACK_HARD_CUT_V else 0
    )
    over_volt = (
        min(over_volt_ticks + 1, POWER_OVER_VOLT_DEBOUNCE_TICKS)
        if pack_v >= PACK_OVER_VOLT_V else 0
    )

    # Fix 7 / D16c — debounced over-voltage cutout. A charger/BMS fault is an
    # emergency, but a single glitch-high sample must not latch the terminal
    # cutout, so require POWER_OVER_VOLT_DEBOUNCE_TICKS consecutive valid ticks
    # at/above the threshold. Checked from any live state, before the band logic.
    if over_volt >= POWER_OVER_VOLT_DEBOUNCE_TICKS:
        return PowerFsmResult(PowerState.OVER_VOLT, 0, 0, 0)

    soft_latched = below_soft >= POWER_CUT_DEBOUNCE_TICKS
    hard_latched = below_hard >= POWER_CUT_DEBOUNCE_TICKS

    if state in _RUNNING_STATES:
        # Hard cut wins over soft (checked first): a fast collapse past HARD_CUT
        # skips straight to the immediate-stop state even though below_soft also
        # crossed. Otherwise the telemetry-only WARN/NORMAL band, instantaneous
        # both ways (no hysteresis — WARN changes nothing but the reported byte).
        if hard_latched:
            return PowerFsmResult(PowerState.HARD_CUT, below_soft, below_hard, over_volt)
        if soft_latched:
            return PowerFsmResult(PowerState.SOFT_CUT, below_soft, below_hard, over_volt)
        if pack_v >= PACK_WARN_V:
            return PowerFsmResult(PowerState.NORMAL, below_soft, below_hard, over_volt)
        # Below WARN but not yet a latched cut: reported as WARN while the soft
        # debounce counts up.
        return PowerFsmResult(PowerState.WARN, below_soft, below_hard, over_volt)

    if state == PowerState.SOFT_CUT:
        # Graceful shutdown is in progress (controller is running the 60 s
        # ack-wait). Escalate to HARD_CUT if the pack collapses further past
        # HARD_CUT (debounced) — fix 4's spirit at the FSM layer; the controller's
        # HARD_CUT/ack path then drops to SLEEP. Otherwise stay: a voltage rebound
        # does NOT abort a started shutdown.
        if hard_latched:
            return PowerFsmResult(PowerState.HARD_CUT, below_soft, below_hard, over_volt)
        return PowerFsmResult(PowerState.SOFT_CUT, below_soft, below_hard, over_volt)

    if state == PowerState.HARD_CUT:
        # Immediate-stop latch. The controller parks the actuators and routes to
        # SLEEP on its own beat; the pure FSM just holds so voltage noise can't
        # bounce it back to a running state.
        return PowerFsmResult(PowerState.HARD_CUT, below_soft, below_hard, over_volt)

    if state == PowerState.SLEEP:
        # Recovery hysteresis: leave SLEEP only when the pack climbs STRICTLY
        # above RECOVERY (well above SOFT_CUT), via a transient RESUMING beat — but
        # NOT at/above the over-volt threshold: an over-voltage-during-SLEEP charger
        # fault must hold SLEEP so the over_volt debounce (above) can latch OVER_VOLT,
        # instead of a spurious RESUMING beat that re-powers the Orin mid-fault.
        if PACK_RECOVERY_V < pack_v < PACK_OVER_VOLT_V:
            return PowerFsmResult(PowerState.RESUMING, 0, 0, 0)
        return PowerFsmResult(PowerState.SLEEP, below_soft, below_hard, over_volt)

    # Unknown/unmapped state: fail safe by holding it rather than guessing a band.
    return PowerFsmResult(state, below_soft, below_hard, over_volt)
