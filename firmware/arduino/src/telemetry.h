#pragma once

#include <stdint.h>

#include "imu/imu_measurement.h"

static constexpr uint16_t TELEMETRY_INTERVAL_MS = 50;
static constexpr char TELEMETRY_SEGMENT_DELIMITER = ';';
static constexpr char TELEMETRY_FIELD_SEPARATOR = ' ';
static constexpr char IMU_TELEMETRY_TAG[] = "IMU";

template <typename Output>
void appendImuMeasurement(
    Output &output,
    const ImuMeasurement &measurement)
{
    output.print(TELEMETRY_SEGMENT_DELIMITER);
    output.print(IMU_TELEMETRY_TAG);
    output.print(TELEMETRY_FIELD_SEPARATOR);

    for (uint8_t axis = 0; axis < 3; ++axis)
    {
        output.print(measurement.acceleration[axis].value, 3);
        output.print(TELEMETRY_FIELD_SEPARATOR);
    }

    for (uint8_t axis = 0; axis < 3; ++axis)
    {
        output.print(measurement.angularRate[axis].value, 4);
        output.print(TELEMETRY_FIELD_SEPARATOR);
    }

    output.print(measurement.temperature.value, 1);
    output.print(TELEMETRY_FIELD_SEPARATOR);
    output.print(measurement.succeeded() ? 1 : 0);
}
