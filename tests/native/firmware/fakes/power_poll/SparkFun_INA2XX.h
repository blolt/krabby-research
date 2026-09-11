#pragma once

#include <cstdio>
#include "Wire.h"

// Fake only the vendor/device boundary. Ina228Adapter, recovery scheduling,
// calibration, splitting, telemetry, and rendering remain production code.
static constexpr int ksfTkErrOk = 0;
static constexpr int INA2XX_MODE_CONT_ALL = 15;

class SfeINA228ArdI2C
{
public:
    int setConversionReadyAlert(bool) { return ksfTkErrOk; }
    int setADCMode(int) { return ksfTkErrOk; }
    bool begin(uint8_t address, TwoWire &wire)
    {
        if (&wire != &Wire) throw std::runtime_error("unexpected INA228 Wire instance");
        address_ = address;
        auto &device = powerPollFake::devices[powerPollFake::index(address_)];
        ++device.beginCount;
        powerPollFake::event(address_, "begin");
        return device.present && device.begins;
    }
    int calibrate(float resistance, float maxCurrent)
    {
        ++powerPollFake::devices[powerPollFake::index(address_)].shuntCount;
        char value[80];
        snprintf(value, sizeof(value), "shunt(%.6f,%.1f)", resistance, maxCurrent);
        powerPollFake::event(address_, value);
        return ksfTkErrOk;
    }
    int reset()
    {
        powerPollFake::event(address_, "reset");
        return ksfTkErrOk;
    }
    int resetAccumulators()
    {
        auto &device = powerPollFake::devices[powerPollFake::index(address_)];
        ++device.resetCount;
        device.coulombs = 0.0f;
        powerPollFake::event(address_, "reset-charge");
        return ksfTkErrOk;
    }
    int getBusVoltage_V(float &value) { value = read("voltage", device().volts); return device().present ? device().readStatus[0] : -1; }
    int getCurrent_A(float &value) { value = read("current", device().milliamps) / 1000.0f; return device().present ? device().readStatus[1] : -1; }
    int getPower_W(float &value) { value = read("power", device().milliwatts) / 1000.0f; return device().present ? device().readStatus[2] : -1; }
    int getCharge_C(double &value) { value = read("charge", device().coulombs); return device().present ? device().readStatus[3] : -1; }
private:
    powerPollFake::Device &device() { return powerPollFake::devices[powerPollFake::index(address_)]; }
    float read(const char *name, float value) { return powerPollFake::read(address_, name, value); }
    uint8_t address_ = 0;
};
