#pragma once

#include <stdint.h>

#include "../../units.h"
#include "imu_constants.h"

struct ImuMeasurement
{
    explicit ImuMeasurement(bool isValid = false)
        : acceleration{},
          angularRate{},
          temperature{},
          valid(isValid)
    {
    }

    MetersPerSecondSquared acceleration[3];
    RadiansPerSecond angularRate[3];
    Celsius temperature;
    // Telemetry carries one validity bit (TASK-1 section 4).
    bool valid;

    bool succeeded() const { return valid; }
};

inline ImuMeasurement transformImuMeasurementToBodyFrame(
    const ImuMeasurement &sensorMeasurement)
{
    if (!sensorMeasurement.succeeded())
        return sensorMeasurement;

    ImuMeasurement bodyMeasurement{true};
    for (uint8_t axis = 0; axis < 3; ++axis)
    {
        const uint8_t source = IMU_AXIS_SRC[axis];
        const float direction = static_cast<float>(IMU_AXIS_SIGN[axis]);

        bodyMeasurement.acceleration[axis] =
            MetersPerSecondSquared(
                direction * sensorMeasurement.acceleration[source].value);
        bodyMeasurement.angularRate[axis] =
            RadiansPerSecond(
                direction * sensorMeasurement.angularRate[source].value);
    }

    bodyMeasurement.temperature = sensorMeasurement.temperature;
    return bodyMeasurement;
}

