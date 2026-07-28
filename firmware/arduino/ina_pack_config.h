#pragma once

#include <stdint.h>

#include "sensors_config.h"

// Keep Pack INA228 hardware calibration at one boundary. Both boot setup and
// runtime recovery call this helper so their shunt arguments cannot drift.
template <typename InaDevice>
inline void configurePackIna(InaDevice& device)
{
    device.setShunt(
        INA228_SHUNT_RESISTANCE.value(),
        INA228_SHUNT_MAX_CURRENT.value());
}
