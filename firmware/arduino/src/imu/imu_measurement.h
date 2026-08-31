#pragma once

#include <stdint.h>

#include "../units/angular_units.h"
#include "../units/inertial_units.h"
#include "../units/temperature_units.h"
#include "imu_constants.h"

struct ImuMeasurement
{
    explicit ImuMeasurement(bool isValid = false)
        : acceleration{},
          angularRate{},
          temperature{},
          isValid(isValid)
    {
    }

    MetersPerSecondSquared acceleration[3];
    RadiansPerSecond angularRate[3];
    Celsius temperature;
    // Telemetry carries one validity bit (TASK-1 section 4).
    bool isValid;

    bool didSucceed() const { return isValid; }
};

inline ImuMeasurement transformImuMeasurementToBodyFrame(
    const ImuMeasurement &sensorMeasurement)
{
    if (!sensorMeasurement.didSucceed())
        return sensorMeasurement;

    ImuMeasurement bodyMeasurement{true};
    for (uint8_t axis = 0; axis < 3; ++axis)
    {
        const uint8_t source = IMU_AXIS_SRC[axis];
        const float direction = static_cast<float>(IMU_AXIS_SIGN[axis]);

        bodyMeasurement.acceleration[axis] =
            sensorMeasurement.acceleration[source].scalarMultiply(direction);
        bodyMeasurement.angularRate[axis] =
            sensorMeasurement.angularRate[source].scalarMultiply(direction);
    }

    bodyMeasurement.temperature = sensorMeasurement.temperature;
    return bodyMeasurement;
}
