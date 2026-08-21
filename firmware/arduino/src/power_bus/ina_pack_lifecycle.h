#pragma once

#include <stdint.h>

#include "ina_pack_config.h"

enum class PackInaStart
{
    Boot,
    Recovery
};

// Boot deliberately resets the Pack INA228 and its accumulators. Runtime
// recovery skips the device reset so a still-powered INA228 retains charge.
// A physical INA228 brownout resets its hardware accumulator regardless.
template <typename InaDevice, typename WireBus>
inline bool startPackIna(
    InaDevice& device,
    uint8_t address,
    WireBus* wire,
    PackInaStart start)
{
    const bool skipReset = start == PackInaStart::Recovery;
    if (!device.begin(address, wire, skipReset))
        return false;

    configurePackIna(device);
    if (start == PackInaStart::Boot)
        device.resetAccumulators();
    return true;
}
