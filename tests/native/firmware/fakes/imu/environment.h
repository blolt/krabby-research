#pragma once
#include "Wire.h"

#include <stdint.h>
#include <deque>
#include <map>
#include <string>
#include <vector>

namespace imu_native {
struct Event
{
    std::string name;
    long a, b, c;
    bool operator==(const Event &other) const
    { return name == other.name && a == other.a && b == other.b && c == other.c; }
};
using Transfer = wire_native::Transfer;
struct Register
{
    int status = 0;
    uint8_t value = 0;
};
struct Device
{
    bool present = false;
    bool configuration[6] = {true, true, true, true, true, true};
    std::map<uint8_t, Register> registers;
};
struct Environment
{
    wire_native::State bus;
    uint64_t microseconds = 0;
    std::map<uint8_t, Device> devices;
    std::deque<int> sda;
    bool sdaHigh = true;
    std::vector<Event> events;
    std::vector<std::string> errors;
    void record(const char *name, long a = 0, long b = 0, long c = 0)
    { events.push_back({name, a, b, c}); }
};
extern Environment environment;
void reset();
void bind(Environment &state);
Environment &environmentFor(TwoWire &wire);
}
