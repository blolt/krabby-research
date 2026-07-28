#pragma once

#include <stdint.h>

#include "measurement_units.h"
#include "telemetry_protocol.h"

struct BatteryTelemetryFrame
{
    Volts packVoltage;
    Amps packCurrent;
    Watts packPower;
    Coulombs packCharge;
    Volts batteryAVoltage;
    Volts batteryBVoltage;
    bool diverged;
    uint8_t powerState;
};

template <typename Output>
inline void appendBatteryTelemetry(
    Output& out,
    const BatteryTelemetryFrame& frame)
{
    out.print(TELEMETRY_SEGMENT_DELIMITER);
    out.print(BATT_TELEMETRY_TAG);
    out.print(TELEMETRY_FIELD_DELIMITER);
    out.print(frame.packVoltage.value(), 2);
    out.print(TELEMETRY_FIELD_DELIMITER);
    out.print(frame.packCurrent.value(), 2);
    out.print(TELEMETRY_FIELD_DELIMITER);
    out.print(frame.packPower.value(), 1);
    out.print(TELEMETRY_FIELD_DELIMITER);
    out.print(frame.packCharge.value(), 1);
    out.print(TELEMETRY_FIELD_DELIMITER);
    out.print(frame.batteryAVoltage.value(), 2);
    out.print(TELEMETRY_FIELD_DELIMITER);
    out.print(frame.batteryBVoltage.value(), 2);
    out.print(TELEMETRY_FIELD_DELIMITER);
    out.print(frame.diverged ? 1 : 0);
    out.print(TELEMETRY_FIELD_DELIMITER);
    out.print(frame.powerState);
}
