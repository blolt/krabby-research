#pragma once

#include "Wire.h"

#include <array>
#include <cstdint>
#include <deque>
#include <functional>
#include <limits>
#include <vector>

namespace lsm6dso_native {

enum Register : uint8_t
{
    WHO_AM_I = 0x0F,
    CTRL1_XL = 0x10,
    CTRL2_G = 0x11,
    CTRL3_C = 0x12,
    CTRL6_C = 0x15,
    CTRL8_XL = 0x17,
    OUT_TEMP_L = 0x20,
    OUTZ_H_A = 0x2D,
};

static constexpr uint8_t CTRL3_C_IF_INC = 0x04;
static constexpr uint8_t WHO_AM_I_VALUE = 0x6C;

// Raw output words in register order: temperature, gyro x/y/z, accel x/y/z.
using Sample = std::array<int16_t, 7>;

struct Operation
{
    uint8_t reg;
    bool isWrite;
    uint8_t value;
    bool acknowledged;
};

// An LSM6DSO at one address, answering the real SparkFun driver and the adapter's
// burst read register by register. A one-byte transaction sets the register
// pointer; longer ones write registers in sequence. Reads start at the pointer and
// advance while CTRL3_C IF_INC is set.
class Device : public wire_native::Device
{
public:
    Device();

    bool present = true; // false NACKs the address; attempts are still logged
    // Returning true NACKs that register read (isWrite false) or write.
    std::function<bool(uint8_t reg, bool isWrite, uint8_t value)> nack;
    // Bytes returned per read; fewer than requested is a short read.
    size_t maxReadBytes = std::numeric_limits<size_t>::max();
    Sample sample{};            // output registers once queued samples run out
    std::deque<Sample> samples; // one consumed by each read starting at OUT_TEMP_L

    // Called for each logged operation, NACKed ones included.
    std::function<void(const Operation &)> onOperation;
    std::vector<Operation> operations; // register-pointer reads and each written byte

    uint8_t registerValue(uint8_t reg) const { return registers_[reg]; }
    void setRegister(uint8_t reg, uint8_t value) { registers_[reg] = value; }
    size_t readCount(uint8_t reg) const;
    void clearLog() { operations.clear(); }

    uint8_t transmit(const std::vector<uint8_t> &bytes) override;
    std::vector<uint8_t> receive(uint8_t count) override;

private:
    void log(const Operation &operation);
    uint8_t read(uint8_t reg) const;

    uint8_t pointer_ = 0;
    Sample current_{};
    std::array<uint8_t, 256> registers_{};
};

}
