#pragma once

#include <Adafruit_INA228.h>
#include <Arduino.h>
#include <Wire.h>

#include "../i2c/i2c_recovery.h"
#include "power_monitor_constants.h"

enum class PowerMonitorRole : uint8_t
{
    Pack,
    Midpoint,
};

class Ina228Adapter
{
public:
    explicit Ina228Adapter(PowerMonitorRole role)
        : address_(addressFor(role)), role_(role), isUp_(false),
          isInitialized_(false)
    {
    }

    bool begin(TwoWire *wire)
    {
        isUp_ = start(wire, false);
        isInitialized_ = isInitialized_ || isUp_;
        return isUp_;
    }

    bool isUp() const { return isUp_; }

    Volts readBusVoltage(Volts offset = Volts())
    {
        return Volts(device_.readBusVoltage() + offset.value());
    }

    Amps readCurrent()
    {
        return MilliAmps(device_.readCurrent()).toAmps();
    }

    Watts readPower()
    {
        return MilliWatts(device_.readPower()).toWatts();
    }

    Coulombs readCharge()
    {
        return Coulombs(device_.readCharge());
    }

    void noteRead(bool didSucceed, TwoWire *wire, uint32_t nowMs)
    {
        const I2cRecoveryLimits limits = {
            POWER_MONITOR_REINIT_AFTER_BAD_TICKS,
            POWER_MONITOR_REINIT_INTERVAL_MILLISECONDS,
        };
        if (didSucceed)
        {
            isUp_ = true;
            recovery_.noteSuccess();
            return;
        }
        isUp_ = false;
        if (recovery_.shouldAttemptRecovery(nowMs, limits))
            isUp_ = recover(wire);
    }

    uint8_t address() const { return address_; }
    uint8_t badTicks() const { return recovery_.badTicks(); }

private:
    static constexpr uint8_t PACK_ADDRESS = 0x40;
    static constexpr uint8_t MIDPOINT_ADDRESS = 0x41;
    static constexpr float PACK_SHUNT_RESISTANCE_OHMS = 0.000375f;
    static constexpr float PACK_SHUNT_MAX_CURRENT_AMPS = 200.0f;

    static uint8_t addressFor(PowerMonitorRole role)
    {
        return role == PowerMonitorRole::Pack
            ? PACK_ADDRESS
            : MIDPOINT_ADDRESS;
    }

    // Avoid repeated begin() calls: Adafruit_INA2xx allocates internal register
    // objects without freeing the old ones.
    bool recover(TwoWire *wire)
    {
        if (isInitialized_)
        {
            if (!isPresent(wire))
                return false;
            reconfigure();
            return true;
        }
        if (!isPresent(wire))
            return false;
        const bool didStart = start(wire, true);
        isInitialized_ = isInitialized_ || didStart;
        return didStart;
    }

    bool isPresent(TwoWire *wire)
    {
        wire->beginTransmission(address_);
        return wire->endTransmission() == 0;
    }

    void reconfigure()
    {
        if (role_ == PowerMonitorRole::Pack)
            configurePack();
    }

    void configurePack()
    {
        device_.setShunt(
            PACK_SHUNT_RESISTANCE_OHMS,
            PACK_SHUNT_MAX_CURRENT_AMPS);
    }

    bool start(TwoWire *wire, bool isRecovery)
    {
        if (role_ == PowerMonitorRole::Midpoint)
            return device_.begin(address_, wire);

        if (!device_.begin(address_, wire, isRecovery))
            return false;
        configurePack();
        if (!isRecovery)
            device_.resetAccumulators();
        return true;
    }

    Adafruit_INA228 device_;
    I2cRecoveryPolicy recovery_;
    uint8_t address_;
    PowerMonitorRole role_;
    bool isUp_;
    bool isInitialized_;
};
