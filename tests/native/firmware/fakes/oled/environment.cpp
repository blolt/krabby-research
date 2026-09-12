#include "environment.h"
#include "Arduino.h"
#include "Wire.h"
namespace oled_native {
Environment environment;

namespace {
bool isTransfer(const std::string &name)
{
    return name == "wire.transmit" || name == "wire.write" || name == "wire.endTransmission" ||
           name == "wire.request" || name == "wire.read";
}
}

void reset()
{
    environment = Environment{};
    Wire.reset();
    bind(environment);
}

void bind(Environment &state)
{
    state.bus.observe = [&state](const wire_native::Event &event) {
        if (isTransfer(event.name)) return;
        std::string name = event.name;
        if (name != "wire.begin" && name != "wire.end") name = name.substr(5);
        state.events.push_back({name, event.args, ""});
    };
    state.bus.devices[0x3D] = &state.panel;
    // One event per ping, per setup sequence, and per run of display data, the last
    // carrying the bus clock active when it was sent.
    state.panel.onTransaction = [&state](ssd1306_native::Transaction kind,
                                         const std::vector<uint8_t> &bytes, uint8_t status) {
        using ssd1306_native::Transaction;
        if (kind == Transaction::Ping)
            state.record("ping", {status});
        else if (kind == Transaction::Command && bytes.size() > 1 && bytes[1] == ssd1306_native::DISPLAY_ON)
            state.record("setup");
        else if (kind == Transaction::Data && (state.events.empty() || state.events.back().name != "data"))
            state.record("data", {long(state.bus.clock)});
    };
}

}
using oled_native::environment;
unsigned long millis() { return static_cast<uint32_t>(environment.microseconds / 1000); }
void delay(unsigned long ms) { environment.record("delay", {long(ms)}); environment.microseconds += uint64_t(ms) * 1000; }
void delayMicroseconds(unsigned int us) { environment.record("delayUs", {long(us)}); environment.microseconds += us; }
void pinMode(uint8_t pin, uint8_t mode) { environment.record("pinMode", {pin, mode}); }
void digitalWrite(uint8_t pin, uint8_t value) { environment.record("digitalWrite", {pin, value}); }
int digitalRead(uint8_t pin)
{
    if (pin != SDA) environment.errors.push_back("unexpected GPIO read");
    int value = environment.sdaHigh;
    if (!environment.sda.empty()) { value = environment.sda.front(); environment.sda.pop_front(); }
    environment.record("digitalRead", {pin,value}); return value;
}
