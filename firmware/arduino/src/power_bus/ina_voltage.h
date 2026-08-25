#pragma once

#include "../units/electrical_units.h"

template <typename InaDevice>
inline Volts readCorrectedInaBusVoltage(
    InaDevice& device,
    Volts offset)
{
    return Volts(device.readBusVoltage() + offset.value());
}
