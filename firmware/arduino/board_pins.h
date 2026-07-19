#pragma once

// Pin revision — select at compile time (or pass -DKRABBY_PIN_REV=N).
//
//  1 = Original breadboard: EN D22,D23,D24,D28,D26,D27; Hall D37,D36,D35,D32,D33,D34 (PCINT1/Port C).
//  2 = Krabby Uno v0.1:    EN FL D22,D23,D24 / FR D28,D26,D27; no Hall.
//  3 = Krabby Uno v0.2:    EN interleaved D22,D24,D26 / D23,D25,D27; Hall D50-D52 (PCINT0) + A12-A14 (PCINT2).
//
// PWM (D2-D13) and analog (IS A6-A11, POT A0-A5) are the same across all revisions.
#ifndef KRABBY_PIN_REV
#define KRABBY_PIN_REV 3
#endif

// --- PWM pins — identical for all revisions ---
#define PIN_S0_PWMR  2
#define PIN_S0_PWML  3
#define PIN_S1_PWMR  4
#define PIN_S1_PWML  5
#define PIN_S2_PWMR  6
#define PIN_S2_PWML  7
#define PIN_S3_PWMR  8
#define PIN_S3_PWML  9
#define PIN_S4_PWMR 10
#define PIN_S4_PWML 11
#define PIN_S5_PWMR 12
#define PIN_S5_PWML 13

// --- EN pins — differ per revision ---
#if KRABBY_PIN_REV == 1

#define PIN_S0_EN 22
#define PIN_S1_EN 23
#define PIN_S2_EN 24
#define PIN_S3_EN 28
#define PIN_S4_EN 26
#define PIN_S5_EN 27

#elif KRABBY_PIN_REV == 2

#define PIN_S0_EN 22   // FL board
#define PIN_S1_EN 23
#define PIN_S2_EN 24
#define PIN_S3_EN 28   // FR board
#define PIN_S4_EN 26
#define PIN_S5_EN 27

#elif KRABBY_PIN_REV == 3

#define PIN_S0_EN 22   // FL
#define PIN_S1_EN 24
#define PIN_S2_EN 26
#define PIN_S3_EN 23   // FR
#define PIN_S4_EN 25
#define PIN_S5_EN 27

#else
#error "KRABBY_PIN_REV must be 1, 2, or 3"
#endif

inline const char* boardPinRevisionLabel()
{
#if KRABBY_PIN_REV == 1
    return "PINS_REV1_ORIGINAL";
#elif KRABBY_PIN_REV == 2
    return "PINS_REV2_UNO_V01";
#else
    return "PINS_REV3_UNO_V02";
#endif
}

// --- M16 status/power GPIO (leader board only) ---
// Two named pins for the leader's hardware indicators/side-effects:
//   STATUS_LED_PIN — a dedicated indicator LED. AC-2g (Task 2) lights it whenever
//                    any of the leader's own actuators reads disconnected; the
//                    protective FSM (Task 4) reuses it for the dead-battery blink
//                    (POWER_LOW_BATT_BLINK_MS) in SLEEP/OVER_VOLT. The two never
//                    fight: the low-power blink lives on the SLEEP path, which
//                    returns before the normal-loop disconnect drive is reached.
//   ORIN_PWR_PIN  — drives the high-side MOSFET / optocoupler that gates the Orin's
//                    supply (spec §4i). HIGH = powered; the FSM drives it LOW on the
//                    force-off timeout, HARD_CUT, SLEEP, and OVER_VOLT.
// Pin 30 is a free digital GPIO on Rev 3 — deliberately NOT a PWM out (D2-D13), an
// EN line (D22-D27), the I2C bus (D20/D21), a follower UART (D14-D19), a Hall input
// (D50-D52), or the Orin gate (D38) — so the indicator never contends with an
// actuator PWM or a bus. (This is why the default is a free pin rather than
// LED_BUILTIN / D13 = PIN_S5_PWML, which is shared with the S5 actuator PWM.)
// ORIN_PWR_PIN targets D38, also free in every KRABBY_PIN_REV (rev1/3 Hall use
// 32-37 / 50-52). Both are placeholders until the MOSFET/optocoupler are wired; the
// FSM's timer + toggle logic is live now. Override either with -DSTATUS_LED_PIN=N /
// -DORIN_PWR_PIN=N at build time if the harness wires them elsewhere.
#ifndef STATUS_LED_PIN
#define STATUS_LED_PIN 30
#endif

#ifndef ORIN_PWR_PIN
#define ORIN_PWR_PIN 38
#endif

constexpr bool boardPinIsReserved(int pin)
{
    return
        // USB serial, actuator PWM, follower UARTs, and I2C occupy D0-D21.
        (pin >= 0 && pin <= 21) ||
        pin == PIN_S0_EN ||
        pin == PIN_S1_EN ||
        pin == PIN_S2_EN ||
        pin == PIN_S3_EN ||
        pin == PIN_S4_EN ||
        pin == PIN_S5_EN ||
        // Reserved for the Orin power-control gate shared with Task 4.
        pin == ORIN_PWR_PIN ||
        // A0-A11 are actuator pot/current inputs (digital aliases D54-D65).
        (pin >= 54 && pin <= 65) ||
#if KRABBY_PIN_REV == 1
        // Original breadboard Hall inputs.
        (pin >= 32 && pin <= 37) ||
#elif KRABBY_PIN_REV == 3
        // v0.2 Hall inputs D50-D52 and A12-A14 (D66-D68).
        (pin >= 50 && pin <= 52) ||
        (pin >= 66 && pin <= 68) ||
#endif
        false;
}

static_assert(
    !boardPinIsReserved(STATUS_LED_PIN),
    "STATUS_LED_PIN conflicts with a reserved Krabby Mega pin");
