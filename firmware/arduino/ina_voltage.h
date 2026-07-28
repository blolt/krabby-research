#pragma once

#include "measurement_units.h"

inline Volts correctInaBusVoltage(
    Volts rawVoltage,
    Volts offset)
{
    return Volts(rawVoltage.value() + offset.value());
}

template <typename InaDevice>
inline Volts readCorrectedInaBusVoltage(
    InaDevice& device,
    Volts offset)
{
    return correctInaBusVoltage(Volts(device.readBusVoltage()), offset);
}
