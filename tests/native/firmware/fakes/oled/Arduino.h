#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string>
static constexpr uint8_t INPUT = 0, OUTPUT = 1, INPUT_PULLUP = 2;
static constexpr uint8_t LOW = 0, HIGH = 1, SDA = 20, SCL = 21;
unsigned long millis();
void delay(unsigned long);
void delayMicroseconds(unsigned int);
void pinMode(uint8_t, uint8_t);
void digitalWrite(uint8_t, uint8_t);
int digitalRead(uint8_t);

// The Print base and String the SparkFun OLED header declares against; nothing prints.
class Print
{
public:
    virtual ~Print() {}
    virtual size_t write(uint8_t) = 0;
};
class String
{
public:
    String(const char *value = "") : value_(value ? value : "") {}
    const char *c_str() const { return value_.c_str(); }
private:
    std::string value_;
};
