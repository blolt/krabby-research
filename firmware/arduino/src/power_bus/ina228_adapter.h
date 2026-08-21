#pragma once

#include <Adafruit_INA228.h>
#include <Arduino.h>
#include <Wire.h>

#include "ina_pack_config.h"
#include "ina_pack_lifecycle.h"
#include "ina_recovery.h"
#include "power_bus_constants.h"

// One INA228 on the shared I2C bus, with its own liveness.
//
// Two monitors run the same lifecycle at different addresses, so this exists
// once and is instantiated twice rather than duplicated as parallel globals and
// two copies of the recovery function.
//
// The retry arithmetic lives in InaRecoveryPolicy, which has no driver and is
// tested on the host; this class holds only what needs the hardware.
class Ina228Monitor
{
public:
    // configuresShunt distinguishes the two roles. The Pack monitor measures
    // current through the external shunt and must be told its value; the
    // Midpoint monitor senses only bus voltage, with its current inputs tied
    // off, so calibrating a shunt it does not use would be meaningless.
    Ina228Monitor(uint8_t address, bool configuresShunt)
        : address_(address), configuresShunt_(configuresShunt), up_(false),
          initialised_(false)
    {
    }

    // Boot brings the device up and clears its accumulators; a later recovery
    // deliberately does not, so charge and energy survive a transient dropout.
    // A physical brownout resets them regardless of what we ask for.
    bool begin(TwoWire *wire)
    {
        up_ = start(wire, PackInaStart::Boot);
        initialised_ = initialised_ || up_;
        return up_;
    }

    bool isUp() const { return up_; }

    // Call once per poll with the outcome of reading this device. Handles its
    // own re-initialisation when the failures justify one, so the caller does
    // not carry per-monitor counters or timestamps.
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
    // Adafruit_INA2xx::begin() allocates seven objects and the library has no
    // destructor (Adafruit_INA260 issue #5, open since 2019). Its contract is
    // "call once at startup", so a retry loop that calls it is the caller's bug,
    // not the library's. On an 8 KB AVR it exhausts the heap in about a minute
    // at a 2 s retry.
    //
    // Two recovery cases, and only the second needs it:
    //
    //   already initialised - the device browned out and cleared its registers,
    //     but i2c_dev and the Config registers are still valid members. Writing
    //     the configuration again goes through them and allocates nothing.
    //
    //   never initialised - there is nothing to talk through, so begin() is
    //     unavoidable. Gated behind a bare-Wire probe that allocates nothing, so
    //     an absent monitor costs no memory at all and begin() is spent only when
    //     a device has actually appeared.
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
        const bool started = start(wire, PackInaStart::Recovery);
        initialised_ = initialised_ || started;
        return started;
    }

    // Address probe only: no allocation, and it does not disturb a device that
    // is answering.
    bool isPresent(TwoWire *wire)
    {
        wire->beginTransmission(address_);
        return wire->endTransmission() == 0;
    }

    // Re-apply what a device reset would have cleared, through the objects the
    // first begin() already created. The Midpoint has no shunt to calibrate, but
    // both lose their sampling configuration.
    void reconfigure()
    {
        if (configuresShunt_)
            configurePackIna(device_);
        configureSampling();
    }

    // Average in hardware before we read. One conversion is 1.05 ms against the
    // actuators' 2.04 ms PWM period, so an unaveraged value samples an arbitrary
    // point on the chop rather than its mean - which is what a clamp meter reads,
    // and what 3i.1 compares against.
    //
    // The conversion cycle is (VBUS + VSHUNT + VTEMP) x count, and all three
    // default to 1052 us, so 16 samples would be 50.5 ms and the 50 ms telemetry
    // tick would read the same conversion twice. We never read the die
    // temperature, so dropping that channel to its 50 us minimum brings the
    // window to 34.5 ms - about 17 PWM periods, comfortably inside the tick.
    //
    // Applied to both monitors: it also steadies the Midpoint's bus voltage,
    // which the divergence flag is computed from.
    void configureSampling()
    {
        device_.setTemperatureConversionTime(INA2XX_TIME_50_us);
        device_.setAveragingCount(INA2XX_COUNT_16);
    }

    bool start(TwoWire *wire, PackInaStart mode)
    {
        // The Midpoint's IN+/IN- are tied to Pack-, so it has no shunt to
        // calibrate and no accumulators worth preserving across a recovery.
        const bool started = configuresShunt_
            ? startPackIna(device_, address_, wire, mode)
            : device_.begin(address_, wire);
        if (started)
            configureSampling();
        return started;
    }

    Adafruit_INA228 device_;
    InaRecoveryPolicy recovery_;
    uint8_t address_;
    bool configuresShunt_;
    bool up_;
    // Whether begin() has ever succeeded, i.e. whether the library's objects
    // exist. Distinct from up_, which is whether the device is answering now.
    bool initialised_;
};
