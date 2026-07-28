#pragma once

#include <stdint.h>
// Arduino -> host telemetry wire tokens. Keep these separate from sensor
// configuration: punctuation and tags are protocol, not I2C settings.
static const char TELEMETRY_SEGMENT_DELIMITER = ';';
static const char TELEMETRY_FIELD_DELIMITER = ' ';
static const char IMU_TELEMETRY_TAG[] = "IMU";
static const char BATT_TELEMETRY_TAG[] = "BATT";

enum BatteryPowerStateCode : uint8_t
{
    BATTERY_POWER_NORMAL = 0,
    BATTERY_POWER_WARN = 1,
    BATTERY_POWER_SOFT_CUT = 2,
    BATTERY_POWER_HARD_CUT = 3,
    BATTERY_POWER_OVER_VOLT = 4,
    BATTERY_POWER_SLEEP = 5,
    BATTERY_POWER_RESUMING = 6
};
