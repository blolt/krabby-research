#pragma once

#include <stdint.h>

#include "Wire.h"

extern float fakeInaBusVoltage;
extern float fakeInaCurrent;
extern float fakeInaPower;
extern float fakeInaCharge;
extern bool shouldInaBeginSucceed;
extern uint8_t fakeInaBeginAddress;
extern bool didInaBeginSkipReset;
extern uint8_t fakeInaBeginCount;
extern uint8_t fakeInaSetShuntCount;
extern float fakeInaShuntResistance;
extern float fakeInaShuntMaxCurrent;
extern uint8_t fakeInaResetAccumulatorsCount;

class Adafruit_INA228
{
public:
    bool begin(uint8_t address, TwoWire *, bool shouldSkipReset = false)
    {
        ++fakeInaBeginCount;
        fakeInaBeginAddress = address;
        didInaBeginSkipReset = shouldSkipReset;
        return shouldInaBeginSucceed;
    }

    void setShunt(float resistance, float maxCurrent)
    {
        ++fakeInaSetShuntCount;
        fakeInaShuntResistance = resistance;
        fakeInaShuntMaxCurrent = maxCurrent;
    }

    void resetAccumulators()
    {
        ++fakeInaResetAccumulatorsCount;
    }
    float readBusVoltage() { return fakeInaBusVoltage; }
    float readCurrent() { return fakeInaCurrent; }
    float readPower() { return fakeInaPower; }
    float readCharge() { return fakeInaCharge; }
};
