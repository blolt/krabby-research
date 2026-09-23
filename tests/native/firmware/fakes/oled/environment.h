#pragma once
#include "Wire.h"
#include "ssd1306.h"
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
    // The SSD1306 fake at the adapter's 0x3D address; bind() attaches it to bus.
    ssd1306_native::Device panel;
    std::deque<int> sda;
    // Bus lifecycle, clock, timeout flag, GPIO and panel events in order. Transfer-level
    // Wire events stay in bus.events only.
    std::vector<Event> events;
    std::vector<std::string> errors;
    void record(const char *name, std::initializer_list<long> args = {}, const char *text = "")
    { events.push_back({name, args, text}); }
};
extern Environment environment;
void reset();
void bind(Environment &state);
}
