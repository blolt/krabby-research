#pragma once
#include "Wire.h"
#include "lsm6dso.h"

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
struct Environment
{
    wire_native::State bus;
    uint64_t microseconds = 0;
    // LSM6DSO fakes answering the real driver on this environment's bus.
    std::map<uint8_t, lsm6dso_native::Device> devices;
    std::deque<int> sda;
    bool sdaHigh = true;
    // Bus lifecycle, clock, GPIO and device events in order. Transfer-level Wire
    // events stay in bus.events only.
    std::vector<Event> events;
    std::vector<std::string> errors;
    void record(const char *name, long a = 0, long b = 0, long c = 0)
    { events.push_back({name, a, b, c}); }
};
extern Environment environment;
void reset();
void bind(Environment &state);
// The environment's device at address, created and attached to its bus on first use.
lsm6dso_native::Device &device(uint8_t address);
}
