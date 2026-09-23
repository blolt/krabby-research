#pragma once

#include "Wire.h"

#include <array>
#include <cstdint>
#include <deque>
#include <functional>
#include <vector>

namespace ssd1306_native {

static constexpr uint8_t WIDTH = 128;
static constexpr uint8_t HEIGHT = 64;
static constexpr uint8_t CONTROL_DATA = 0x40;
static constexpr uint8_t DISPLAY_OFF = 0xAE;
static constexpr uint8_t DISPLAY_ON = 0xAF;

enum class Transaction { Ping, Command, Data };

// An SSD1306 at one address, answering the real SparkFun Qwiic OLED library.
// An empty transaction is a ping; [0x00 cmd args...] is one command; [0x40 bytes...]
// writes display RAM from the current page and column, as in page addressing mode.
// The panel is write-only, so reads return nothing.
class Device : public wire_native::Device
{
public:
    bool present = true; // false NACKs every transaction
    // Status for each ping (0 ACK, 2 NACK, 5 timeout); an empty queue ACKs.
    std::deque<uint8_t> pings;
    // Returning true NACKs that command or data transaction.
    std::function<bool(Transaction kind, const std::vector<uint8_t> &bytes)> nack;
    // Called for every transaction with the status it received.
    std::function<void(Transaction kind, const std::vector<uint8_t> &bytes, uint8_t status)> onTransaction;

    bool isOn() const { return isOn_; }
    bool pixel(uint8_t x, uint8_t y) const;
    const std::array<uint8_t, 1024> &ram() const { return ram_; }

    uint8_t transmit(const std::vector<uint8_t> &bytes) override;
    std::vector<uint8_t> receive(uint8_t) override { return {}; }

private:
    void command(uint8_t value);

    uint8_t page_ = 0;
    uint8_t column_ = 0;
    bool isOn_ = false;
    std::array<uint8_t, 1024> ram_{};
};

}
