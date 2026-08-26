#pragma once

#include <stdint.h>

extern uint8_t fakeWireEndTransmissionResult;
extern uint8_t fakeWireLastAddress;
extern uint8_t fakeWireBeginTransmissionCount;

class TwoWire
{
public:
    void beginTransmission(uint8_t address)
    {
        fakeWireLastAddress = address;
        ++fakeWireBeginTransmissionCount;
    }

    uint8_t endTransmission() { return fakeWireEndTransmissionResult; }
};
