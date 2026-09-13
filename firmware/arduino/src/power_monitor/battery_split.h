#pragma once

#include <math.h>

#include "../units/electrical_units.h"

static constexpr float BATTERY_PACK_V_MIN = 0.0f;
static constexpr float BATTERY_PACK_V_MAX = 40.0f;
static constexpr float BATTERY_CELL_V_MIN = 0.0f;
static constexpr float BATTERY_CELL_V_MAX = 20.0f;

struct BatterySplit
{
    float batteryA;
    float batteryB;
    bool isDiverged;
};

inline bool isBatteryPackVoltageValid(float packVoltage)
{
    return
        isfinite(packVoltage) &&
        packVoltage >= BATTERY_PACK_V_MIN &&
        packVoltage <= BATTERY_PACK_V_MAX;
}

// Whether one battery's measured voltage is plausible on its own terms. Held
// apart from calculateBatterySplit because that function answers a different
// question - whether the *pair* describes two sane batteries - and answers it
// false when the Pack is the wrong one.
inline bool isBatteryCellVoltageValid(float cellVoltage)
{
    return
        isfinite(cellVoltage) &&
        cellVoltage >= BATTERY_CELL_V_MIN &&
        cellVoltage <= BATTERY_CELL_V_MAX;
}

inline bool isPackVoltageDisplayable(
    bool isPackValid, bool isMidpointValid, bool isSplitValid)
{
    return isPackValid && (!isMidpointValid || isSplitValid);
}

inline bool calculateBatterySplit(
    float packVoltage,
    float midpointVoltage,
    Volts divergenceThreshold,
    BatterySplit& result)
{
    const float divergenceThresholdVolts = divergenceThreshold.value();
    if (!isBatteryPackVoltageValid(packVoltage) ||
        !isfinite(midpointVoltage) ||
        midpointVoltage < BATTERY_CELL_V_MIN ||
        midpointVoltage > BATTERY_CELL_V_MAX ||
        !isfinite(divergenceThresholdVolts) ||
        divergenceThresholdVolts < 0.0f)
        return false;

    const float batteryB = packVoltage - midpointVoltage;
    if (!isfinite(batteryB) ||
        batteryB < BATTERY_CELL_V_MIN ||
        batteryB > BATTERY_CELL_V_MAX)
        return false;

    result.batteryA = midpointVoltage;
    result.batteryB = batteryB;
    result.isDiverged =
        fabs(result.batteryA - result.batteryB) >
            divergenceThresholdVolts;
    return true;
}
