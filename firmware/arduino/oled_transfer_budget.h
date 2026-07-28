#pragma once

#include <stdint.h>

// The SparkFun 1.3-inch OLED driver tracks a dirty x-range independently for
// each of the SSD1306's eight pages. display() sends only those ranges, but a
// completely changed 128x64 frame can still require all 1024 payload bytes.
static const uint32_t OLED_FRAMEBUFFER_BYTES = 128UL * 64UL / 8UL;
static const uint32_t OLED_WIRE_BITS_PER_BYTE = 9UL;

// Allow 25% above the framebuffer payload for page-address commands, I2C
// addresses/control bytes, Wire's 32-byte chunking, and integer rounding.
static const uint32_t OLED_WORST_CASE_WIRE_BYTES =
    OLED_FRAMEBUFFER_BYTES + OLED_FRAMEBUFFER_BYTES / 4UL;

constexpr uint32_t oledWorstCaseWireTimeUs(uint32_t busClockHz)
{
    return
        (OLED_WORST_CASE_WIRE_BYTES * OLED_WIRE_BITS_PER_BYTE * 1000000UL
         + busClockHz - 1UL) / busClockHz;
}
