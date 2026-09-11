#pragma once

#include <stdint.h>
#include <string>
#include <stdexcept>
#include <vector>

namespace powerPollFake
{
struct Device
{
    bool present = true;
    bool begins = true;
    int readStatus[4] = {};
    float volts = 0.0f;
    float milliamps = 0.0f;
    float milliwatts = 0.0f;
    float coulombs = 0.0f;
    uint32_t voltageReadDuration = 0;
    unsigned beginCount = 0;
    unsigned shuntCount = 0;
    unsigned resetCount = 0;
};
extern Device devices[2];
extern uint32_t now;
extern std::vector<std::string> events;
inline size_t index(uint8_t address)
{
    if (address == 0x40) return 0;
    if (address == 0x41) return 1;
    throw std::runtime_error("unexpected INA228 address: " + std::to_string(address));
}
inline void event(uint8_t address, const std::string &operation)
{
    events.push_back(std::string(index(address) == 0 ? "pack." : "mid.") + operation);
}
inline float read(uint8_t address, const char *name, float value)
{
    event(address, name);
    if (std::string(name) == "voltage") now += devices[index(address)].voltageReadDuration;
    return value;
}
}
