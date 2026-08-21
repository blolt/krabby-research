#pragma once

#include <stdint.h>

#include "power_bus_constants.h"

// When to re-initialise a monitor that has stopped answering.
//
// Two independent brakes. A single bad read is not evidence — the I2C bus is
// shared with the IMU and the display, so a transient collision looks the same
// as a dead device. And a device that is genuinely gone would otherwise be
// re-initialised every tick, spending bus time on a monitor that is not there.
struct InaRecoveryLimits
{
    uint8_t badTicksBeforeReinit;   // consecutive failures before trying again
    uint32_t reinitIntervalMs;      // and no more than one attempt this often
};

// Sourced from power_bus_constants.h rather than restated here: 3h makes that
// file the contract for this task's rates, and a second copy is how the two
// drifted to {20, 5000} and {3, 2000} at the same time.
constexpr InaRecoveryLimits INA_RECOVERY_DEFAULT_LIMITS = {
    INA_REINIT_AFTER_BAD_TICKS,
    INA_REINIT_INTERVAL_MILLISECONDS};

// Decides *when* to retry; knows nothing about I2C or the device. Held apart
// from the adapter so the counting and the rollover arithmetic are testable on
// the host, where an off-by-one is visible.
class InaRecoveryPolicy
{
public:
    InaRecoveryPolicy()
        : badTicks_(0), lastAttemptMs_(0), attempted_(false)
    {
    }

    // A read succeeded: the device is answering, so pending failures are stale.
    void noteSuccess()
    {
        badTicks_ = 0;
    }

    // A read failed. True when this failure should trigger a re-initialisation,
    // which also consumes the pending evidence — the caller is expected to act
    // on a true return, so returning true twice for one run would double-retry.
    bool noteFailure(uint32_t nowMs, const InaRecoveryLimits &limits)
    {
        if (badTicks_ < 255)
            ++badTicks_;
        if (badTicks_ < limits.badTicksBeforeReinit)
            return false;
        // Unsigned subtraction carries the elapsed duration across the millis()
        // rollover; comparing timestamps directly would not.
        if (attempted_ &&
            static_cast<uint32_t>(nowMs - lastAttemptMs_) < limits.reinitIntervalMs)
            return false;
        lastAttemptMs_ = nowMs;
        attempted_ = true;
        badTicks_ = 0;
        return true;
    }

    uint8_t badTicks() const { return badTicks_; }

private:
    uint8_t badTicks_;        // saturates at 255
    uint32_t lastAttemptMs_;
    // Distinguishes "never attempted" from "attempted at millis() == 0", which
    // otherwise blocks the first retry for a whole interval after boot.
    bool attempted_;
};
