#pragma once
#include "Wire.h"
#include <stdint.h>
#include <deque>
#include <initializer_list>
#include <string>
#include <vector>
namespace oled_native {
struct Event
{
    std::string name;
    std::vector<long> args;
    std::string text;
    bool operator==(const Event &other) const
    { return name == other.name && args == other.args && text == other.text; }
};
struct Environment
{
    wire_native::State bus;
    uint64_t microseconds = 0;
    bool sdaHigh = true;
    std::deque<bool> begins, resets;
    std::deque<int> sda;
    std::vector<Event> events;
    std::vector<std::string> errors;
    void record(const char *name, std::initializer_list<long> args = {}, const char *text = "")
    { events.push_back({name, args, text}); }
};
extern Environment environment;
void reset();
void bind(Environment &state);
Environment &environmentFor(TwoWire &wire);
}
