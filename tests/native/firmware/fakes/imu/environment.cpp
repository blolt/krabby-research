#include "environment.h"
#include "Arduino.h"
#include "Wire.h"
#include "SparkFunLSM6DSO.h"

namespace imu_native {
Environment environment;
static std::map<const wire_native::State *, Environment *> environments;
void reset()
{
    environment = Environment{};
    Wire.reset();
    environments.clear();
    bind(environment);
}
Environment &environmentFor(TwoWire &wire)
{
    const auto found = environments.find(&wire.state());
    if (found != environments.end()) return *found->second;
    wire.state().errors.push_back("unbound driver bus");
    static Environment unbound;
    unbound = Environment{};
    return unbound;
}
void bind(Environment &state)
{
    environments[&state.bus] = &state;
    state.bus.observe = [&state](const wire_native::Event &event) {
        state.record(event.name.c_str(),
            event.args.size() > 0 ? event.args[0] : 0,
            event.args.size() > 1 ? event.args[1] : 0,
            event.args.size() > 2 ? event.args[2] : 0);
    };
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
bool LSM6DSO::begin(uint8_t address, TwoWire &wire)
{ wire_ = &wire; auto &environment = imu_native::environmentFor(*wire_);
    environment.record("sensor.begin", address);
    address_ = address;
    if (!environment.devices.count(address))
    {
        environment.errors.push_back("unscripted device discovery");
        return false;
    }
    return environment.devices.at(address).present;
}
bool LSM6DSO::configure(unsigned index, const char *name, long value)
{ auto &environment = imu_native::environmentFor(*wire_);
    environment.record(name, value);
    return environment.devices.at(address_).configuration[index];
}
bool LSM6DSO::setIncrement(bool value) { return configure(0, "increment", value); }
bool LSM6DSO::setAccelRange(uint8_t value) { return configure(1, "accelRange", value); }
bool LSM6DSO::setAccelDataRate(uint16_t value) { return configure(2, "accelRate", value); }
bool LSM6DSO::setGyroRange(uint16_t value) { return configure(3, "gyroRange", value); }
bool LSM6DSO::setGyroDataRate(uint16_t value) { return configure(4, "gyroRate", value); }
bool LSM6DSO::setBlockDataUpdate(bool value) { return configure(5, "blockUpdate", value); }
status_t LSM6DSO::readRegister(uint8_t *value, uint8_t address)
{ auto &environment = imu_native::environmentFor(*wire_);
    environment.record("sensor.register", address);
    auto &registers = environment.devices.at(address_).registers;
    if (!registers.count(address))
    {
        environment.errors.push_back("unscripted configuration register");
        return IMU_HW_ERROR;
    }
    const auto &reg = registers.at(address);
    if (reg.status == 0) *value = reg.value;
    return static_cast<status_t>(reg.status);
}
