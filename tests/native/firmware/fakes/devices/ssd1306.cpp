#include "ssd1306.h"

namespace ssd1306_native {

bool Device::pixel(uint8_t x, uint8_t y) const
{
    if (x >= WIDTH || y >= HEIGHT) return false;
    return (ram_[(y / 8) * WIDTH + x] & (1 << (y & 7))) != 0;
}

uint8_t Device::transmit(const std::vector<uint8_t> &bytes)
{
    const Transaction kind = bytes.empty() ? Transaction::Ping
        : (bytes[0] == CONTROL_DATA ? Transaction::Data : Transaction::Command);
    uint8_t status = 0;
    if (!present)
        status = 2;
    else if (kind == Transaction::Ping)
    {
        if (!pings.empty())
        {
            status = pings.front();
            pings.pop_front();
        }
    }
    else if (nack && nack(kind, bytes))
        status = 3;
    if (onTransaction) onTransaction(kind, bytes, status);
    if (status != 0) return status;
    if (kind == Transaction::Command && bytes.size() > 1)
        command(bytes[1]);
    if (kind == Transaction::Data)
        for (size_t index = 1; index < bytes.size(); ++index, ++column_)
            if (column_ < WIDTH) ram_[page_ * WIDTH + column_] = bytes[index];
    return status;
}

// Arguments of two-byte commands follow the command byte and change nothing here.
void Device::command(uint8_t value)
{
    if (value == DISPLAY_OFF) isOn_ = false;
    else if (value == DISPLAY_ON) isOn_ = true;
    else if (value >= 0xB0 && value <= 0xB7) page_ = uint8_t(value - 0xB0);
    else if (value <= 0x0F) column_ = uint8_t((column_ & 0xF0) | value);
    else if (value <= 0x1F) column_ = uint8_t(((value & 0x0F) << 4) | (column_ & 0x0F));
}

}
