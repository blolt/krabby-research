#include "environment.h"
#include "Arduino.h"
#include "Wire.h"

namespace imu_native {
Environment environment;

namespace {
bool isTransfer(const std::string &name)
{
    return name == "wire.transmit" || name == "wire.write" || name == "wire.endTransmission" ||
           name == "wire.request" || name == "wire.read";
}

// One event per driver call: an identification read or a register write.
void attach(Environment &state, uint8_t address, lsm6dso_native::Device &device)
{
    state.bus.devices[address] = &device;
    device.onOperation = [&state, address](const lsm6dso_native::Operation &operation) {
        if (operation.isWrite) state.record("sensor.write", operation.reg, operation.value);
        else if (operation.reg == lsm6dso_native::WHO_AM_I) state.record("sensor.identify", address);
    };
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
        state.record(event.name.c_str(),
            event.args.size() > 0 ? event.args[0] : 0,
            event.args.size() > 1 ? event.args[1] : 0,
            event.args.size() > 2 ? event.args[2] : 0);
    };
    for (auto &entry : state.devices) attach(state, entry.first, entry.second);
}

lsm6dso_native::Device &device(uint8_t address)
{
    const auto found = environment.devices.find(address);
    if (found != environment.devices.end()) return found->second;
    lsm6dso_native::Device &created = environment.devices[address];
    attach(environment, address, created);
    return created;
}

}
using imu_native::environment;

unsigned long millis() { return static_cast<uint32_t>(environment.microseconds / 1000); }
void delay(unsigned long ms)
{
    environment.record("delay", ms);
    environment.microseconds += uint64_t(ms) * 1000;
}
void delayMicroseconds(unsigned int us)
{
    environment.record("delayUs", us);
    environment.microseconds += us;
}
void pinMode(uint8_t pin, uint8_t mode) { environment.record("pinMode", pin, mode); }
void digitalWrite(uint8_t pin, uint8_t value) { environment.record("digitalWrite", pin, value); }
int digitalRead(uint8_t pin)
{
    if (pin != SDA) environment.errors.push_back("unexpected GPIO read");
    int value = environment.sdaHigh;
    if (!environment.sda.empty())
    {
        value = environment.sda.front();
        environment.sda.pop_front();
    }
    environment.record("digitalRead", pin, value);
    return value;
}
