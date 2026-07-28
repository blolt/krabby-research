#pragma once

// Battery-protective state machine (M16 Task 4) — firmware side.
//
// powerFsmStep is the sole production transition implementation. Native Unity
// tests execute this header directly; there is no second behavioral model to
// synchronize.
//
// Split of concerns (identical to the Python doc):
//   powerFsmStep()  — PURE. state + measured pack voltage + validity -> next
//                     state. No millis(), no Serial, no actuator calls. Trivially
//                     unit-testable and matches the host FSM exactly.
//   PowerController — the STATEFUL wrapper the .ino owns: it holds the FSM state
//                     and under-voltage debounce counters, calls powerFsmStep once per tick,
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
enum class PowerState : uint8_t
{
    Normal    = 0,
    Warn      = 1,
    SoftCut   = 2,
    HardCut   = 3,
    OverVolt  = 4,
    Sleep     = 5,
    Resuming  = 6,
};

// Plausibility window for pack_v, mirroring battAppendTelemetry()'s own bounds
// (arduino.ino).
#ifndef PACK_V_MIN
#define PACK_V_MIN 0.0f
#endif
#ifndef PACK_V_MAX
#define PACK_V_MAX 40.0f
#endif

// Result of one pure step: next state + carried-forward under-voltage counters.
struct PowerFsmResult
{
    PowerState state;
    uint16_t belowSoftTicks;
    uint16_t belowHardTicks;
};

// The valid-guard predicate (fix 1): a trustworthy reading is a live monitor
// reporting a finite voltage inside the plausibility window.
static inline bool powerReadingValid(float packV, bool valid)
{
    return valid && isfinite(packV) && packV >= PACK_V_MIN && packV <= PACK_V_MAX;
}

// PURE decision core. No side effects; safe to call directly from native tests.
static inline PowerFsmResult powerFsmStep(
    PowerState state, float packV, bool valid,
    uint16_t belowSoftTicks, uint16_t belowHardTicks)
{
    PowerFsmResult r;

    // Fix 7 — one-way OVER_VOLT latch: terminal, before all else (even the
    // valid-guard). Counters are meaningless once latched, so zero them.
    if (state == PowerState::OverVolt)
    {
        r.state = PowerState::OverVolt; r.belowSoftTicks = 0; r.belowHardTicks = 0;
        return r;
    }

    // Fix 1 / D16a — valid-guard: an untrustworthy reading holds state and RESETS
    // both counters (a dropped tick is not a below-threshold tick, so it breaks
    // any in-progress consecutive run).
    if (!powerReadingValid(packV, valid))
    {
        r.state = state; r.belowSoftTicks = 0; r.belowHardTicks = 0;
        return r;
    }

    // The spec defines OVER_VOLT as a one-way protective cutout. Do not delay it
    // behind an invented debounce: the first valid reading at or above the named
    // threshold latches the terminal state.
    if (packV >= PACK_OVER_VOLT_THRESHOLD.value())
    {
        r.state = PowerState::OverVolt; r.belowSoftTicks = 0; r.belowHardTicks = 0;
        return r;
    }

    // Consecutive-run counters (fix 2 / D16b). Reset when outside the band;
    // increment but SATURATE at the debounce target when inside (D16b — stops the
    // uint16_t wrapping once a cut has latched). SOFT strict `<`; HARD inclusive
    // `<=` (D15 — single source of truth for SOFT->HARD, matches the controller).
    uint16_t belowSoft = (packV < PACK_SOFT_CUT_THRESHOLD.value())
        ? (uint16_t)((belowSoftTicks < POWER_CUT_DEBOUNCE_TICKS) ? belowSoftTicks + 1 : POWER_CUT_DEBOUNCE_TICKS)
        : 0;
    uint16_t belowHard = (packV <= PACK_HARD_CUT_THRESHOLD.value())
        ? (uint16_t)((belowHardTicks < POWER_CUT_DEBOUNCE_TICKS) ? belowHardTicks + 1 : POWER_CUT_DEBOUNCE_TICKS)
        : 0;
    r.belowSoftTicks = belowSoft;
    r.belowHardTicks = belowHard;

    bool softLatched = belowSoft >= POWER_CUT_DEBOUNCE_TICKS;
    bool hardLatched = belowHard >= POWER_CUT_DEBOUNCE_TICKS;

    // Running (monitoring) states: NORMAL, WARN, RESUMING freely re-evaluate.
    if (state == PowerState::Normal || state == PowerState::Warn || state == PowerState::Resuming)
    {
        if (hardLatched)      r.state = PowerState::HardCut;   // fast collapse wins over soft
        else if (softLatched) r.state = PowerState::SoftCut;
        else if (packV >= PACK_WARNING_THRESHOLD.value()) r.state = PowerState::Normal;
        else                  r.state = PowerState::Warn;       // below WARN, cut not yet latched
        return r;
    }

    if (state == PowerState::SoftCut)
    {
        // Graceful shutdown underway. Escalate to HARD_CUT on a further debounced
        // collapse (fix 4); a voltage rebound does NOT abort a started shutdown.
        r.state = hardLatched ? PowerState::HardCut : PowerState::SoftCut;
        return r;
    }

    if (state == PowerState::HardCut)
    {
        // Immediate-stop latch; controller routes to SLEEP on its own beat.
        r.state = PowerState::HardCut;
        return r;
    }

    if (state == PowerState::Sleep)
    {
        // Recovery hysteresis: leave SLEEP only strictly above RECOVERY, via a
        // transient RESUMING beat. Reset counters on the way up. The OVER_VOLT
        // check above takes priority, so a charger fault cannot spuriously resume
        // and re-power the Orin.
        if (packV > PACK_RECOVERY_THRESHOLD.value() &&
            packV < PACK_OVER_VOLT_THRESHOLD.value())
        {
            r.state = PowerState::Resuming; r.belowSoftTicks = 0; r.belowHardTicks = 0;
        }
        else
        {
            r.state = PowerState::Sleep;
        }
        return r;
    }

    // Unknown state: hold it (fail safe) rather than guess a band.
    r.state = state;
    return r;
}

// ===========================================================================
// PWR wire-message model. Scoped enums represent the concepts in C++; the
// functions below are the single mapping to the exact Python interface tokens.
// Wire shape: "PWR <schema> <TYPE> [reason]".
// ===========================================================================

#define POWER_MSG_PREFIX "PWR"
#define POWER_TYPE_POWERING_DOWN_TOKEN "POWERING_DOWN"
#define POWER_TYPE_SHUTDOWN_ACK_TOKEN "SHUTDOWN_ACK"
#define POWER_TYPE_RESUMING_TOKEN "RESUMING"
#define POWER_TYPE_EMERGENCY_SHUTDOWN_TOKEN "EMERGENCY_SHUTDOWN"
#define POWER_REASON_UNDER_VOLTAGE_SOFT_TOKEN "under_voltage_soft"
#define POWER_REASON_HARD_CUT_TOKEN "hard_cut"
#define POWER_REASON_OVER_VOLTAGE_TOKEN "over_voltage"
#define POWER_REASON_MANUAL_TOKEN "manual"
#define POWER_REASON_VOLTAGE_RECOVERED_TOKEN "voltage_recovered"

static constexpr uint8_t POWER_MSG_SCHEMA = 1;

enum class PowerMessageType : uint8_t
{
    PoweringDown,
    ShutdownAck,
    Resuming,
    EmergencyShutdown,
};

enum class PoweringDownReason : uint8_t
{
    UnderVoltageSoft,
    Manual,
};

enum class EmergencyShutdownReason : uint8_t
{
    HardCut,
    OverVoltage,
};

enum class ResumingReason : uint8_t
{
    VoltageRecovered,
};

#if !defined(ARDUINO)
static constexpr const char* powerMessageTypeToken(PowerMessageType type)
{
    return type == PowerMessageType::PoweringDown
             ? POWER_TYPE_POWERING_DOWN_TOKEN
         : type == PowerMessageType::ShutdownAck
             ? POWER_TYPE_SHUTDOWN_ACK_TOKEN
         : type == PowerMessageType::Resuming
             ? POWER_TYPE_RESUMING_TOKEN
         : type == PowerMessageType::EmergencyShutdown
             ? POWER_TYPE_EMERGENCY_SHUTDOWN_TOKEN
             : "";
}

static constexpr const char* powerReasonToken(PoweringDownReason reason)
{
    return reason == PoweringDownReason::UnderVoltageSoft
             ? POWER_REASON_UNDER_VOLTAGE_SOFT_TOKEN
         : reason == PoweringDownReason::Manual
             ? POWER_REASON_MANUAL_TOKEN
             : "";
}

static constexpr const char* powerReasonToken(EmergencyShutdownReason reason)
{
    return reason == EmergencyShutdownReason::HardCut
             ? POWER_REASON_HARD_CUT_TOKEN
         : reason == EmergencyShutdownReason::OverVoltage
             ? POWER_REASON_OVER_VOLTAGE_TOKEN
             : "";
}

static constexpr const char* powerReasonToken(ResumingReason reason)
{
    return reason == ResumingReason::VoltageRecovered
             ? POWER_REASON_VOLTAGE_RECOVERED_TOKEN
             : "";
}
#endif

#if defined(ARDUINO)
#include <Arduino.h>

static inline void powerPrintTypeToken(Print& out, PowerMessageType type)
{
    switch (type)
    {
        case PowerMessageType::PoweringDown:
            out.print(F(POWER_TYPE_POWERING_DOWN_TOKEN));
            break;
        case PowerMessageType::ShutdownAck:
            out.print(F(POWER_TYPE_SHUTDOWN_ACK_TOKEN));
            break;
        case PowerMessageType::Resuming:
            out.print(F(POWER_TYPE_RESUMING_TOKEN));
            break;
        case PowerMessageType::EmergencyShutdown:
            out.print(F(POWER_TYPE_EMERGENCY_SHUTDOWN_TOKEN));
            break;
    }
}

static inline void powerPrintReasonToken(Print& out, PoweringDownReason reason)
{
    switch (reason)
    {
        case PoweringDownReason::UnderVoltageSoft:
            out.print(F(POWER_REASON_UNDER_VOLTAGE_SOFT_TOKEN));
            break;
        case PoweringDownReason::Manual:
            out.print(F(POWER_REASON_MANUAL_TOKEN));
            break;
    }
}

static inline void powerPrintReasonToken(
    Print& out, EmergencyShutdownReason reason)
{
    switch (reason)
    {
        case EmergencyShutdownReason::HardCut:
            out.print(F(POWER_REASON_HARD_CUT_TOKEN));
            break;
        case EmergencyShutdownReason::OverVoltage:
            out.print(F(POWER_REASON_OVER_VOLTAGE_TOKEN));
            break;
    }
}

static inline void powerPrintReasonToken(Print& out, ResumingReason reason)
{
    switch (reason)
    {
        case ResumingReason::VoltageRecovered:
            out.print(F(POWER_REASON_VOLTAGE_RECOVERED_TOKEN));
            break;
    }
}

// Emit one PWR line on its own, terminated — never appended to a telemetry line
// (the host demuxes PWR vs. telemetry by line prefix). Callers must invoke these
// OUTSIDE the telemetry line-assembly window (fix 3).
static inline void powerEmitHeader(Print& out, PowerMessageType type)
{
    out.print(F(POWER_MSG_PREFIX));
    out.print(' ');
    out.print(POWER_MSG_SCHEMA);
    out.print(' ');
    powerPrintTypeToken(out, type);
}

static inline void emitPowerMessage(Print& out, PoweringDownReason reason)
{
    powerEmitHeader(out, PowerMessageType::PoweringDown);
    out.print(' ');
    powerPrintReasonToken(out, reason);
    out.println();
}

static inline void emitPowerMessage(
    Print& out, EmergencyShutdownReason reason)
{
    powerEmitHeader(out, PowerMessageType::EmergencyShutdown);
    out.print(' ');
    powerPrintReasonToken(out, reason);
    out.println();
}

static inline void emitPowerMessage(Print& out, ResumingReason reason)
{
    powerEmitHeader(out, PowerMessageType::Resuming);
    out.print(' ');
    powerPrintReasonToken(out, reason);
    out.println();
}
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
    PowerState state          = PowerState::Normal;
    uint16_t belowSoftTicks = 0;
    uint16_t belowHardTicks = 0;

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
    PowerState step(float packV, bool valid)
    {
        PowerFsmResult r = powerFsmStep(state, packV, valid, belowSoftTicks, belowHardTicks);
        state          = r.state;
        belowSoftTicks = r.belowSoftTicks;
        belowHardTicks = r.belowHardTicks;
        return state;
    }

    // Accept SHUTDOWN_ACK only while a graceful POWERING_DOWN transaction is
    // actively waiting on the still-powered Orin. Emergency, stale, and early
    // ACKs cannot shorten a later or unrelated rail-cut deadline.
    bool acceptShutdownAckIfExpected()
    {
        if (state != PowerState::SoftCut || !orinCutArmed || !orinPowered)
            return false;
        shutdownAcked = true;
        return true;
    }

    // True in any state where the leader has parked its actuators — motor
    // commands (T/B/J/C) are gated to no-ops here (fix 5). SHUTDOWN_ACK / version
    // / sync handling stay live (they are not motor commands).
    bool actuatorsParked() const
    {
        return state == PowerState::SoftCut || state == PowerState::HardCut ||
               state == PowerState::Sleep    || state == PowerState::OverVolt;
    }

#if defined(ARDUINO)
    // Full per-tick side-effect orchestration: advance the pure FSM, then run the
    // transition's actuator/serial/GPIO/OLED effects and the timers the pure core
    // cannot. Defined in arduino.ino (needs actuatorManager / mainSerial / oled /
    // inaPack). Declared ARDUINO-only so the header stays host-buildable.
    void update(float packV, bool valid);
    // Immediate shutdown hierarchy. HARD_CUT is silent and recoverable;
    // OVER_VOLT emits an emergency notification and is terminal. Neither path
    // parks, waits for an ACK, or delays motor de-energization.
    void beginEmergencyShutdown(
        EmergencyShutdownReason reason, unsigned long now);
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
