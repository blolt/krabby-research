#include "environment.h"
#include <map>
#include "Arduino.h"
#include "Wire.h"
#include "SparkFun_Qwiic_OLED.h"
#include "res/qw_fnt_5x7.h"
namespace oled_native {
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
        std::string name = event.name;
        if (name == "wire.transmit") name = "probe";
        else if (name != "wire.begin" && name != "wire.end") name = name.substr(5);
        state.events.push_back({name, event.args, ""});
    };
}

}
using oled_native::environment;
const QwiicFont oledStatusFont{};
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
static bool result(oled_native::Environment &environment, std::deque<bool> &script)
{
    if (script.empty()) { environment.errors.push_back("unscripted driver operation"); return false; }
    bool value = script.front(); script.pop_front(); return value;
}
bool Qwiic1in3OLED::begin(TwoWire &wire, uint8_t address)
{ wire_ = &wire; auto &environment = wire_ ? oled_native::environmentFor(*wire_) : oled_native::environment;
    environment.record("begin", {address});
    return result(environment, environment.begins);
}
bool Qwiic1in3OLED::reset(bool clear) { auto &environment = wire_ ? oled_native::environmentFor(*wire_) : oled_native::environment; environment.record("reset", {clear}); return result(environment, environment.resets); }
void Qwiic1in3OLED::display() { auto &environment = wire_ ? oled_native::environmentFor(*wire_) : oled_native::environment; environment.record("display", {long(wire_ ? wire_->state().clock : environment.bus.clock)}); }
void Qwiic1in3OLED::setFont(const QwiicFont *font)
{ auto &environment = wire_ ? oled_native::environmentFor(*wire_) : oled_native::environment;
    environment.record("font", {font == QW_FONT_5X7});
    if (font != QW_FONT_5X7) environment.errors.push_back("wrong font");
}
void Qwiic1in3OLED::erase() { auto &environment = wire_ ? oled_native::environmentFor(*wire_) : oled_native::environment; environment.record("erase"); }
void Qwiic1in3OLED::pixel(uint8_t x,uint8_t y,uint8_t c) { auto &environment = wire_ ? oled_native::environmentFor(*wire_) : oled_native::environment; environment.record("pixel", {x,y,c}); }
void Qwiic1in3OLED::line(uint8_t x,uint8_t y,uint8_t x1,uint8_t y1,uint8_t c) { auto &environment = wire_ ? oled_native::environmentFor(*wire_) : oled_native::environment; environment.record("line", {x,y,x1,y1,c}); }
void Qwiic1in3OLED::rectangle(uint8_t x,uint8_t y,uint8_t w,uint8_t h,uint8_t c) { auto &environment = wire_ ? oled_native::environmentFor(*wire_) : oled_native::environment; environment.record("rectangle", {x,y,w,h,c}); }
void Qwiic1in3OLED::rectangleFill(uint8_t x,uint8_t y,uint8_t w,uint8_t h,uint8_t c) { auto &environment = wire_ ? oled_native::environmentFor(*wire_) : oled_native::environment; environment.record("fill", {x,y,w,h,c}); }
void Qwiic1in3OLED::text(uint8_t x,uint8_t y,const char *t,uint8_t c) { auto &environment = wire_ ? oled_native::environmentFor(*wire_) : oled_native::environment; environment.record("text", {x,y,c},t); }
