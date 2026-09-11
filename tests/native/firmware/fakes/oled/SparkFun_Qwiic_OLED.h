#pragma once
#include "Wire.h"
#define COLOR_BLACK 0
#define COLOR_WHITE 1
struct QwiicFont {};
class Qwiic1in3OLED
{
public:
    bool begin(TwoWire &wire = Wire, uint8_t address = 0);
    bool reset(bool clearDisplay);
    void display();
    void setFont(const QwiicFont *font);
    void erase();
    void pixel(uint8_t x, uint8_t y, uint8_t color = COLOR_WHITE);
    void line(uint8_t x0, uint8_t y0, uint8_t x1, uint8_t y1, uint8_t color = COLOR_WHITE);
    void rectangle(uint8_t x, uint8_t y, uint8_t width, uint8_t height, uint8_t color = COLOR_WHITE);
    void rectangleFill(uint8_t x, uint8_t y, uint8_t width, uint8_t height, uint8_t color = COLOR_WHITE);
    void text(uint8_t x, uint8_t y, const char *text, uint8_t color = COLOR_WHITE);
private:
    TwoWire *wire_ = nullptr;
};
