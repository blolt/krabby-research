#pragma once

#include <math.h>

#include "../../units.h"

struct VoltageOffsets
{
    Volts packVoltageOffset;
    Volts midpointVoltageOffset;
};

struct VoltageCalibrationLimits
{
    Volts maximumPackReference;
    Volts maximumMidpointReference;
    Volts maximumOffsetMagnitude;
};

inline bool calculateVoltageOffset(
    Volts referenceVoltage,
    Volts rawVoltage,
    Volts maximumOffsetMagnitude,
    Volts& result)
{
    const float reference = referenceVoltage.value;
    const float raw = rawVoltage.value;
    const float maximumOffset = maximumOffsetMagnitude.value;

    if (!isfinite(reference) ||
        !isfinite(raw) ||
        !isfinite(maximumOffset) ||
        maximumOffset < 0.0f)
        return false;

    const float offset = reference - raw;
    if (!isfinite(offset) || fabs(offset) > maximumOffset)
        return false;

    result = Volts(offset);
    return true;
}

inline bool voltageReferenceIsValid(Volts reference, Volts maximum)
{
    return isfinite(reference.value) &&
        isfinite(maximum.value) &&
        maximum.value > 0.0f &&
        reference.value > 0.0f &&
        reference.value <= maximum.value;
}

template <typename PackDevice, typename MidpointDevice>
inline bool captureVoltageOffsets(
    PackDevice& packDevice,
    MidpointDevice& midpointDevice,
    Volts packReference,
    Volts midpointReference,
    const VoltageCalibrationLimits& limits,
    VoltageOffsets& result)
{
    if (!voltageReferenceIsValid(
            packReference, limits.maximumPackReference) ||
        !voltageReferenceIsValid(
            midpointReference, limits.maximumMidpointReference))
        return false;

    // Capture both raw values before solving either offset. Each device is read
    // exactly once, and result remains untouched unless both solves succeed.
    const Volts rawPackVoltage(packDevice.readBusVoltage());
    const Volts rawMidpointVoltage(midpointDevice.readBusVoltage());
    Volts packOffset(result.packVoltageOffset);
    Volts midpointOffset(result.midpointVoltageOffset);

    if (!calculateVoltageOffset(
            packReference,
            rawPackVoltage,
            limits.maximumOffsetMagnitude,
            packOffset) ||
        !calculateVoltageOffset(
            midpointReference,
            rawMidpointVoltage,
            limits.maximumOffsetMagnitude,
            midpointOffset))
        return false;

    result.packVoltageOffset = packOffset;
    result.midpointVoltageOffset = midpointOffset;
    return true;
}
