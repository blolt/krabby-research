#include "lsm6dso.h"

#include <algorithm>

namespace lsm6dso_native {

// Power-on values from the LSM6DSO datasheet; every other register resets to zero.
Device::Device()
{
    registers_[WHO_AM_I] = WHO_AM_I_VALUE;
    registers_[CTRL3_C] = CTRL3_C_IF_INC;
}

size_t Device::readCount(uint8_t reg) const
{
    return size_t(std::count_if(operations.begin(), operations.end(),
        [reg](const Operation &operation) { return !operation.isWrite && operation.reg == reg; }));
}

void Device::log(const Operation &operation)
{
    operations.push_back(operation);
    if (onOperation) onOperation(operation);
}

uint8_t Device::transmit(const std::vector<uint8_t> &bytes)
{
    if (bytes.empty()) return present ? 0 : 2;
    const uint8_t reg = bytes[0];
    const bool isWrite = bytes.size() > 1;
    const bool refused = !present || (nack && nack(reg, isWrite, isWrite ? bytes[1] : 0));
    if (!isWrite)
        log({reg, false, 0, !refused});
    for (size_t index = 1; index < bytes.size(); ++index)
        log({uint8_t(reg + index - 1), true, bytes[index], !refused});
    if (!present) return 2;
    if (refused) return 3;
    pointer_ = reg;
    for (size_t index = 1; index < bytes.size(); ++index)
        registers_[uint8_t(reg + index - 1)] = bytes[index];
    return 0;
}

std::vector<uint8_t> Device::receive(uint8_t count)
{
    std::vector<uint8_t> bytes;
    if (!present) return bytes;
    if (pointer_ == OUT_TEMP_L)
    {
        current_ = samples.empty() ? sample : samples.front();
        if (!samples.empty()) samples.pop_front();
    }
    const bool increments = (registers_[CTRL3_C] & CTRL3_C_IF_INC) != 0;
    const size_t length = std::min<size_t>(count, maxReadBytes);
    for (size_t index = 0; index < length; ++index)
        bytes.push_back(read(uint8_t(pointer_ + (increments ? index : 0))));
    if (increments) pointer_ = uint8_t(pointer_ + length);
    return bytes;
}

uint8_t Device::read(uint8_t reg) const
{
    if (reg < OUT_TEMP_L || reg > OUTZ_H_A) return registers_[reg];
    const size_t offset = reg - OUT_TEMP_L;
    const uint16_t word = uint16_t(current_[offset / 2]);
    return offset % 2 == 0 ? uint8_t(word & 0xFF) : uint8_t(word >> 8);
}

}
