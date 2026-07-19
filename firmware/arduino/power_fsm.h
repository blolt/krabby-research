#pragma once

// Battery-protective state machine (M16 Task 4) — firmware side.
//
// 1:1 C++ mirror of firmware/interfaces/power_fsm.py. The pure decision core
// (powerFsmStep) is byte-for-byte the same transition table as the Python; the
// host unit tests (tests/unit/firmware/test_power_fsm.py) pin the behavior and
// this header must not diverge from them. Keep the two files edited together.
//
// Split of concerns (identical to the Python doc):
//   powerFsmStep()  — PURE. state + measured pack voltage + validity -> next
//                     state. No millis(), no Serial, no actuator calls. Trivially
//                     unit-testable and matches the host FSM exactly.
//   PowerController — the STATEFUL wrapper the .ino owns: it holds the FSM state
//                     and debounce counters, calls powerFsmStep once per tick,
//                     and runs the *side-effects and timers* a pure function
//                     cannot — parking the actuators, emitting PWR messages, the
//                     60 s Orin ack-wait, the force-off GPIO toggle, the recovery
//                     poll / dead-battery blink. The action hooks here are thin;
//                     the .ino integration phase wires holdAll() / the MOSFET.

#include <stdint.h>
#include <math.h>          // isfinite
#include "sensors_config.h"
#include "board_pins.h"    // ORIN_PWR_PIN, STATUS_LED_PIN

// PowerState codes — MUST equal the PowerState IntEnum in joint_telemetry.py and
// the powerState byte battAppendTelemetry() ships in the BATT frame.
enum PowerFsmState : uint8_t
{
    PWR_NORMAL    = 0,
    PWR_WARN      = 1,
    PWR_SOFT_CUT  = 2,
    PWR_HARD_CUT  = 3,
    PWR_OVER_VOLT = 4,
    PWR_SLEEP     = 5,
    PWR_RESUMING  = 6,
};

// Plausibility window for pack_v, mirroring battAppendTelemetry()'s own bounds
// (arduino.ino) and PACK_V_MIN/PACK_V_MAX in power_fsm.py.
#ifndef PACK_V_MIN
#define PACK_V_MIN 0.0f
#endif
#ifndef PACK_V_MAX
#define PACK_V_MAX 40.0f
#endif

// Result of one pure step: next state + carried-forward debounce counters.
struct PowerFsmResult
{
    uint8_t  state;
    uint16_t belowSoftTicks;
    uint16_t belowHardTicks;
    uint16_t overVoltTicks;
};

// The valid-guard predicate (fix 1): a trustworthy reading is a live monitor
// reporting a finite voltage inside the plausibility window.
static inline bool powerReadingValid(float packV, bool valid)
{
    return valid && isfinite(packV) && packV >= PACK_V_MIN && packV <= PACK_V_MAX;
}

// PURE decision core. 1:1 with power_fsm_step() in power_fsm.py — see that file's
// docstring for the rule rationale. No side effects; safe to call from tests.
static inline PowerFsmResult powerFsmStep(
    uint8_t state, float packV, bool valid,
    uint16_t belowSoftTicks, uint16_t belowHardTicks, uint16_t overVoltTicks)
{
    PowerFsmResult r;

    // Fix 7 — one-way OVER_VOLT latch: terminal, before all else (even the
    // valid-guard). Counters are meaningless once latched, so zero them.
    if (state == PWR_OVER_VOLT)
    {
        r.state = PWR_OVER_VOLT; r.belowSoftTicks = 0; r.belowHardTicks = 0; r.overVoltTicks = 0;
        return r;
    }

    // Fix 1 / D16a — valid-guard: an untrustworthy reading holds state and RESETS
    // every counter (a dropped tick is neither a below-threshold tick nor an
    // above-threshold one, so it breaks any in-progress consecutive run).
    if (!powerReadingValid(packV, valid))
    {
        r.state = state; r.belowSoftTicks = 0; r.belowHardTicks = 0; r.overVoltTicks = 0;
        return r;
    }

    // Consecutive-run counters (fix 2 / D16b/D16c). Reset when outside the band;
    // increment but SATURATE at the debounce target when inside (D16b — stops the
    // uint16_t wrapping once a cut has latched). SOFT strict `<`; HARD inclusive
    // `<=` (D15 — single source of truth for SOFT->HARD, matches the controller).
    uint16_t belowSoft = (packV < PACK_SOFT_CUT_V)
        ? (uint16_t)((belowSoftTicks < POWER_CUT_DEBOUNCE_TICKS) ? belowSoftTicks + 1 : POWER_CUT_DEBOUNCE_TICKS)
        : 0;
    uint16_t belowHard = (packV <= PACK_HARD_CUT_V)
        ? (uint16_t)((belowHardTicks < POWER_CUT_DEBOUNCE_TICKS) ? belowHardTicks + 1 : POWER_CUT_DEBOUNCE_TICKS)
        : 0;
    uint16_t overVolt = (packV >= PACK_OVER_VOLT_V)
        ? (uint16_t)((overVoltTicks < POWER_OVER_VOLT_DEBOUNCE_TICKS) ? overVoltTicks + 1 : POWER_OVER_VOLT_DEBOUNCE_TICKS)
        : 0;

    // Fix 7 / D16c — debounced over-voltage cutout: latch only after
    // POWER_OVER_VOLT_DEBOUNCE_TICKS consecutive valid ticks at/above threshold,
    // so a lone glitch-high sample can't trip the terminal cutout.
    if (overVolt >= POWER_OVER_VOLT_DEBOUNCE_TICKS)
    {
        r.state = PWR_OVER_VOLT; r.belowSoftTicks = 0; r.belowHardTicks = 0; r.overVoltTicks = 0;
        return r;
    }

    r.belowSoftTicks = belowSoft;
    r.belowHardTicks = belowHard;
    r.overVoltTicks  = overVolt;

    bool softLatched = belowSoft >= POWER_CUT_DEBOUNCE_TICKS;
    bool hardLatched = belowHard >= POWER_CUT_DEBOUNCE_TICKS;

    // Running (monitoring) states: NORMAL, WARN, RESUMING freely re-evaluate.
    if (state == PWR_NORMAL || state == PWR_WARN || state == PWR_RESUMING)
    {
        if (hardLatched)      r.state = PWR_HARD_CUT;   // fast collapse wins over soft
        else if (softLatched) r.state = PWR_SOFT_CUT;
        else if (packV >= PACK_WARN_V) r.state = PWR_NORMAL;
        else                  r.state = PWR_WARN;       // below WARN, cut not yet latched
        return r;
    }

    if (state == PWR_SOFT_CUT)
    {
        // Graceful shutdown underway. Escalate to HARD_CUT on a further debounced
        // collapse (fix 4); a voltage rebound does NOT abort a started shutdown.
        r.state = hardLatched ? PWR_HARD_CUT : PWR_SOFT_CUT;
        return r;
    }

    if (state == PWR_HARD_CUT)
    {
        // Immediate-stop latch; controller routes to SLEEP on its own beat.
        r.state = PWR_HARD_CUT;
        return r;
    }

    if (state == PWR_SLEEP)
    {
        // Recovery hysteresis: leave SLEEP only strictly above RECOVERY, via a
        // transient RESUMING beat. Reset counters on the way up. NOT at/above the
        // over-volt threshold: an over-voltage-during-SLEEP charger fault must hold
        // SLEEP so the over_volt debounce (above) latches OVER_VOLT, not spuriously
        // RESUME and re-power the Orin mid-fault.
        if (packV > PACK_RECOVERY_V && packV < PACK_OVER_VOLT_V)
        {
            r.state = PWR_RESUMING; r.belowSoftTicks = 0; r.belowHardTicks = 0; r.overVoltTicks = 0;
        }
        else
        {
            r.state = PWR_SLEEP;
        }
        return r;
    }

    // Unknown state: hold it (fail safe) rather than guess a band.
    r.state = state;
    return r;
}

// ===========================================================================
// PWR wire-message emitters — EXACT strings from firmware/interfaces/
// power_messages.py (PowerMessage.format_line): "PWR <schema> <TYPE> [reason]".
// Kept as string literals so a grep pins parity with the Python. Guarded for the
// Arduino toolchain (need Print/Serial); the pure FSM above stays host-buildable.
// ===========================================================================

// Line prefix marking a power-control message — MUST equal POWER_MSG_PREFIX in
// power_messages.py. Used to recognize the Orin's inbound SHUTDOWN_ACK.
#define POWER_MSG_PREFIX "PWR"

// Full wire lines (no trailing newline), one per Mega->Orin message type. The
// leading "1" is the wire schema — MUST equal POWER_MSG_SCHEMA in power_messages.py
// (the parity test asserts this so it can't drift).
#define PWR_LINE_POWERING_DOWN "PWR 1 POWERING_DOWN under_voltage_soft"
#define PWR_LINE_OVER_VOLTAGE  "PWR 1 OVER_VOLTAGE_SHUTDOWN over_voltage"
#define PWR_LINE_RESUMING      "PWR 1 RESUMING voltage_recovered"

#if defined(ARDUINO)
#include <Arduino.h>

// Emit one PWR line on its own, terminated — never appended to a telemetry line
// (the host demuxes PWR vs. telemetry by line prefix). Callers must invoke these
// OUTSIDE the telemetry line-assembly window (fix 3).
static inline void powerEmitPoweringDown(Print& out) { out.println(F(PWR_LINE_POWERING_DOWN)); }
static inline void powerEmitOverVoltage(Print& out)  { out.println(F(PWR_LINE_OVER_VOLTAGE)); }
static inline void powerEmitResuming(Print& out)     { out.println(F(PWR_LINE_RESUMING)); }
#endif  // ARDUINO

// ===========================================================================
// PowerController — stateful wrapper owned by the .ino. Holds the FSM state +
// debounce counters + the timers/GPIO the pure core cannot. The action methods
// are declared thin here; the .ino integration phase fills holdAll()/MOSFET and
// the ack-wait/force-off timers against millis(). Kept in the header so the pure
// core and its consumer live together and stay in lockstep.
// ===========================================================================
struct PowerController
{
    uint8_t  state          = PWR_NORMAL;
    uint16_t belowSoftTicks = 0;
    uint16_t belowHardTicks = 0;
    uint16_t overVoltTicks  = 0;

    // Timers (millis timestamps; 0 = inactive). Driven by the .ino integration.
    unsigned long softCutEnteredMs = 0;   // start of the 60 s Orin ack-wait / force-off deadline
    bool          shutdownAcked    = false; // Orin replied SHUTDOWN_ACK (poweroff underway)
    unsigned long lastRecoveryPollMs = 0; // SLEEP recovery-poll cadence gate
    unsigned long lastBlinkMs        = 0; // dead-battery blink cadence gate
    unsigned long lastSplashMs       = 0; // dead-battery OLED splash cadence gate
    bool          statusLedOn        = false; // current STATUS_LED level in the SLEEP blink
    bool          orinPowered      = true;
    // F5 / D19: the Orin force-off window. Opened on a SOFT_CUT (graceful) or
    // HARD_CUT (F5 — routed through the window, NOT instant-yanked) entry using
    // softCutEnteredMs as the start; serviceOrinForceOff() cuts the rail once the
    // (ack-shortened) deadline elapses, and it stays open across the drop to SLEEP.
    bool          orinCutArmed     = false;
    // D17/D13: the last Pack VBUS read (value + validity), cached so the low-power
    // loop's LED/OLED indicators can run every iteration while the actual INA228
    // read is throttled to POWER_RECOVERY_POLL_MS.
    float         lastPackV        = 0.0f;
    bool          lastPackValid    = false;
    // D13/4g: true once the low-power OLED has been cleared under the HARD_CUT floor,
    // so the panel is cleared exactly ONCE and then left untouched (no repeated draw
    // draining an already-critical pack).
    bool          panelCleared     = false;

    // Advance the pure FSM one tick and adopt the result. Returns the (possibly
    // unchanged) new state so the caller can drive edge-triggered side-effects
    // (emit a PWR message / park actuators only on the transition).
    uint8_t step(float packV, bool valid)
    {
        PowerFsmResult r = powerFsmStep(state, packV, valid, belowSoftTicks, belowHardTicks, overVoltTicks);
        state          = r.state;
        belowSoftTicks = r.belowSoftTicks;
        belowHardTicks = r.belowHardTicks;
        overVoltTicks  = r.overVoltTicks;
        return state;
    }

    // Orin -> Mega SHUTDOWN_ACK arrived during the ack-wait. Pure bookkeeping
    // (no I/O), so it stays host-buildable: the rail cut still waits the
    // ORIN_FORCE_OFF_MS deadline so the Orin can finish `shutdown -h now`.
    void onShutdownAck()
    {
        shutdownAcked = true;
    }

    // True in any state where the leader has parked its actuators — motor
    // commands (T/B/J/C) are gated to no-ops here (fix 5). SHUTDOWN_ACK / version
    // / sync handling stay live (they are not motor commands).
    bool actuatorsParked() const
    {
        return state == PWR_SOFT_CUT || state == PWR_HARD_CUT ||
               state == PWR_SLEEP    || state == PWR_OVER_VOLT;
    }

#if defined(ARDUINO)
    // Full per-tick side-effect orchestration: advance the pure FSM, then run the
    // transition's actuator/serial/GPIO/OLED effects and the timers the pure core
    // cannot. Defined in arduino.ino (needs actuatorManager / mainSerial / oled /
    // inaPack). Declared ARDUINO-only so the header stays host-buildable.
    void update(float packV, bool valid);
    // Route into the SLEEP low-power loop (park + reset counters + arm the blink).
    void enterSleep(unsigned long now);
    // SLEEP per-tick services: STATUS-LED dead-battery blink + OLED splash (dark
    // below HARD_CUT). Recovery out of SLEEP is the pure FSM's job (packV>RECOVERY).
    void lowPowerServices(float packV, bool valid, unsigned long now);
    // D13: the FSM step + recovery/RESUMING edge run from the dedicated low-power
    // loop (loop() branches here in SLEEP/OVER_VOLT). Caches the reading for the
    // indicators. OVER_VOLT is terminal, so the step is a no-op there.
    void lowPowerStep(float packV, bool valid);
    // F5/D19: cut the Orin rail once the force-off window (opened on SOFT/HARD entry)
    // elapses — the ack-shortened deadline. Called every tick (normal + low-power),
    // so a HARD_CUT-opened window still fires after the drop to SLEEP.
    void serviceOrinForceOff(unsigned long now);
#endif
};
