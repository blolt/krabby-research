#pragma once

#include "Wire.h"
#include <map>

struct FakeInaDevice
{
    bool beginSucceeds = true;
    int resetStatus = 0;
    int alertStatus = 0;
    int modeStatus = 0;
    int calibrationStatus = 0;
    int accumulatorStatus = 0;
    int readStatus[4] = {};
    bool writesOutput[4] = {true, true, true, true};
    float voltage = 26.25f;
    float current = -2.5f;
    float power = -65.625f;
    double charge = -12345.125;
    float shuntResistance = -1;
    float maxCurrent = -1;
    bool alertEnabled = false;
    int mode = -1;
    std::vector<std::string> calls;
};

class FakeInaDevices
{
public:
    explicit FakeInaDevices(TwoWire &wire) : wire_(wire) { registry()[&wire_] = this; }
    ~FakeInaDevices() { registry().erase(&wire_); }
    FakeInaDevices(const FakeInaDevices &) = delete;
    FakeInaDevices &operator=(const FakeInaDevices &) = delete;
    std::map<uint8_t, FakeInaDevice> devices;
    static std::map<TwoWire *, FakeInaDevices *> &registry()
    {
        static std::map<TwoWire *, FakeInaDevices *> value;
        return value;
    }
private:
    TwoWire &wire_;
};

inline std::map<uint8_t, FakeInaDevice> &inaDevices(TwoWire &wire)
{
    return FakeInaDevices::registry().at(&wire)->devices;
}


// Surface used from SparkFun INA2XX 1.0.0; values are already in SI units.
using sfTkError_t = int32_t;
static constexpr sfTkError_t ksfTkErrOk = 0;
enum sfe_ina2xx_mode_t { INA2XX_MODE_CONT_ALL = 15 };

class SfeINA228ArdI2C
{
public:
    bool begin(uint8_t address, TwoWire &wire)
    {
        const auto found = FakeInaDevices::registry().find(&wire);
        if (found == FakeInaDevices::registry().end()) return false;
        device_ = &found->second->devices[address];
        device_->calls.push_back("begin");
        return device_->beginSucceeds;
    }
    sfTkError_t reset()
    {
        device_->calls.push_back("reset");
        return device_->resetStatus;
    }
    sfTkError_t setConversionReadyAlert(bool enabled)
    {
        device_->calls.push_back("alert");
        device_->alertEnabled = enabled;
        return device_->alertStatus;
    }
    sfTkError_t setADCMode(sfe_ina2xx_mode_t mode)
    {
        device_->calls.push_back("mode");
        device_->mode = mode;
        return device_->modeStatus;
    }
    sfTkError_t calibrate(float resistance, float maxCurrent)
    {
        device_->calls.push_back("calibrate");
        device_->shuntResistance = resistance;
        device_->maxCurrent = maxCurrent;
        return device_->calibrationStatus;
    }
    sfTkError_t resetAccumulators()
    {
        device_->calls.push_back("accumulators");
        return device_->accumulatorStatus;
    }
    sfTkError_t getBusVoltage_V(float &value)
    {
        device_->calls.push_back("voltage");
        if (device_->writesOutput[0]) value = device_->voltage;
        return device_->readStatus[0];
    }
    sfTkError_t getCurrent_A(float &value)
    {
        device_->calls.push_back("current");
        if (device_->writesOutput[1]) value = device_->current;
        return device_->readStatus[1];
    }
    sfTkError_t getPower_W(float &value)
    {
        device_->calls.push_back("power");
        if (device_->writesOutput[2]) value = device_->power;
        return device_->readStatus[2];
    }
    sfTkError_t getCharge_C(double &value)
    {
        device_->calls.push_back("charge");
        if (device_->writesOutput[3]) value = device_->charge;
        return device_->readStatus[3];
    }

private:
    FakeInaDevice *device_ = nullptr;
};
