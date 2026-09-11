#pragma once
#include <stdint.h>
static constexpr uint8_t INPUT = 0, OUTPUT = 1, INPUT_PULLUP = 2;
static constexpr uint8_t LOW = 0, HIGH = 1, SDA = 20, SCL = 21;
unsigned long millis();
void delay(unsigned long);
void delayMicroseconds(unsigned int);
void pinMode(uint8_t, uint8_t);
void digitalWrite(uint8_t, uint8_t);
int digitalRead(uint8_t);
