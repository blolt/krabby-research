#pragma once

#include <stddef.h>
#include <stdint.h>

#include "actuator/actuator_constants.h"
#include "imu/imu_measurement.h"
#include "../units.h"

static constexpr uint16_t TELEMETRY_INTERVAL_MS = 50;

// The one scheduler gate for the telemetry tick. Everything the leader appends
// to a line - actuators, IMU, power - rides this, so there is a single period
// and a single timestamp rather than per-subsystem gates that drift apart.
//
// Unsigned subtraction intentionally preserves the elapsed duration across the
// uint32_t millis() rollover.
inline bool telemetryPollDue(uint32_t now, uint32_t previousPoll)
{
    return static_cast<uint32_t>(now - previousPoll) >= TELEMETRY_INTERVAL_MS;
}
static constexpr char TELEMETRY_SEGMENT_DELIMITER = ';';
static constexpr char TELEMETRY_FIELD_SEPARATOR = ' ';
static constexpr char IMU_TELEMETRY_TAG[] = "IMU";
// Appended by the leader alongside IMU, under its own tag, so a parser that does
// not know it skips one segment rather than mis-reading the line.
static constexpr char BATT_TELEMETRY_TAG[] = "BATT";
static constexpr size_t CONTROLLER_ACTUATOR_COUNT = 6;
static constexpr size_t ACTUATOR_TELEMETRY_FIELD_COUNT = 9;
static constexpr size_t ACTUATOR_TELEMETRY_MAX_FIELD_COUNT = 10;
static constexpr size_t ACTUATOR_TELEMETRY_POSITION_FIELD_INDEX = 1;
static constexpr size_t ACTUATOR_TELEMETRY_RETRACT_PWM_FIELD_INDEX = 6;
static constexpr size_t ACTUATOR_TELEMETRY_EXTEND_PWM_FIELD_INDEX = 7;
static constexpr size_t ACTUATOR_TELEMETRY_ATTACHMENT_FIELD_INDEX = 9;

struct ActuatorTelemetry
{
    bool connected;
    uint8_t retractPwm;
    uint8_t extendPwm;
    // False only before no driven-current evidence has been seen for the channel.
    // Presently, no decay, so once true it stays true until controller reset.
    bool attachmentVerified;
};

bool parseActuatorTelemetry(
    const char *line,
    const char *expectedRole,
    ActuatorTelemetry (&actuators)[CONTROLLER_ACTUATOR_COUNT]);

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

// ---- Battery segment (Task 3) ----
// Lives beside appendImuMeasurement: both are wire-format appends under their
// own tag, and a reader looking for the line's shape should find them together.

// §4's power_state field, carrying only the measurement half of it: which band
// pack_v falls in. Task 3 emits a constant NORMAL; Task 4 owns the thresholds
// that decide it (4a).
//
// §4's enum also lists 5=sleep and 6=resuming, which are controller states
// rather than voltage regions. They are deliberately absent here: Task 4 adds
// the controller axis as its own field when it has a state machine to report
// and knows where 4b's reason code belongs. One byte cannot hold both anyway -
// 4a names a RECOVERY threshold that §4's enum has no value for, because a pack
// back above RECOVERY while the controller is still asleep is region NORMAL
// with the controller asleep, a pair a single byte has nowhere to put.
enum PackVoltageRegion : uint8_t
{
    PACK_REGION_NORMAL = 0,
    PACK_REGION_WARN = 1,
    PACK_REGION_SOFT_CUT = 2,
    PACK_REGION_HARD_CUT = 3,
    PACK_REGION_OVER_VOLT = 4
};

struct BatteryTelemetryFrame
{
    Volts packVoltage;
    Amps packCurrent;
    Watts packPower;
    Coulombs packCharge;
    Volts batteryAVoltage;
    Volts batteryBVoltage;
    bool diverged;
    uint8_t packRegion;
    // Per-monitor liveness, the same convention as the IMU segment's valid byte
    // (TASK-1 §4). One byte each because the two monitors fail and recover
    // independently. When a byte is 0 its fields carry the last trustworthy
    // reading, not the library's failure sentinel.
    bool packValid;
    bool midpointValid;
};

template <typename Output>
inline void appendBatteryTelemetry(
    Output& out,
    const BatteryTelemetryFrame& frame)
{
    out.print(TELEMETRY_SEGMENT_DELIMITER);
    out.print(BATT_TELEMETRY_TAG);
    out.print(TELEMETRY_FIELD_SEPARATOR);
    out.print(frame.packVoltage.value, 2);
    out.print(TELEMETRY_FIELD_SEPARATOR);
    out.print(frame.packCurrent.value, 2);
    out.print(TELEMETRY_FIELD_SEPARATOR);
    out.print(frame.packPower.value, 1);
    out.print(TELEMETRY_FIELD_SEPARATOR);
    out.print(frame.packCharge.value, 1);
    out.print(TELEMETRY_FIELD_SEPARATOR);
    out.print(frame.batteryAVoltage.value, 2);
    out.print(TELEMETRY_FIELD_SEPARATOR);
    out.print(frame.batteryBVoltage.value, 2);
    out.print(TELEMETRY_FIELD_SEPARATOR);
    out.print(frame.diverged ? 1 : 0);
    out.print(TELEMETRY_FIELD_SEPARATOR);
    out.print(frame.packRegion);
    out.print(TELEMETRY_FIELD_SEPARATOR);
    out.print(frame.packValid ? 1 : 0);
    out.print(TELEMETRY_FIELD_SEPARATOR);
    out.print(frame.midpointValid ? 1 : 0);
}
