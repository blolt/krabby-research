#pragma once

#include <Adafruit_INA228.h>
#include <Arduino.h>
#include <Wire.h>

#include "ina_recovery.h"
#include "power_bus_constants.h"

enum class Ina228Role : uint8_t
{
    Pack,
    Midpoint,
};

class Ina228Adapter
{
public:
    Ina228Adapter(uint8_t address, Ina228Role role)
        : address_(address), role_(role), up_(false),
          initialised_(false)
    {
    }

    bool begin(TwoWire *wire)
    {
        up_ = start(wire, false);
        initialised_ = initialised_ || up_;
        return up_;
    }

    bool isUp() const { return up_; }

    void noteRead(bool succeeded, TwoWire *wire, uint32_t nowMs,
                  const InaRecoveryLimits &limits = INA_RECOVERY_DEFAULT_LIMITS)
    {
        if (succeeded)
        {
            up_ = true;
            recovery_.noteSuccess();
            return;
        }
        up_ = false;
        if (recovery_.noteFailure(nowMs, limits))
            up_ = recover(wire);
    }

    Adafruit_INA228 &device() { return device_; }
    uint8_t address() const { return address_; }
    uint8_t badTicks() const { return recovery_.badTicks(); }

private:
    // Avoid repeated begin() calls: Adafruit_INA2xx allocates internal register
    // objects without freeing the old ones.
    bool recover(TwoWire *wire)
    {
        if (initialised_)
        {
            if (!isPresent(wire))
                return false;
            reconfigure();
            return true;
        }
        if (!isPresent(wire))
            return false;
        const bool started = start(wire, true);
        initialised_ = initialised_ || started;
        return started;
    }

    bool isPresent(TwoWire *wire)
    {
        wire->beginTransmission(address_);
        return wire->endTransmission() == 0;
    }

    void reconfigure()
    {
        if (role_ == Ina228Role::Pack)
            configurePack();
    }

    void configurePack()
    {
        device_.setShunt(
            INA228_SHUNT_RESISTANCE.value(),
            INA228_SHUNT_MAX_CURRENT.value());
    }

    bool start(TwoWire *wire, bool recovery)
    {
        if (role_ == Ina228Role::Midpoint)
            return device_.begin(address_, wire);

        if (!device_.begin(address_, wire, recovery))
            return false;
        configurePack();
        if (!recovery)
            device_.resetAccumulators();
        return true;
    }

    Adafruit_INA228 device_;
    InaRecoveryPolicy recovery_;
    uint8_t address_;
    Ina228Role role_;
    bool up_;
    bool initialised_;
};
