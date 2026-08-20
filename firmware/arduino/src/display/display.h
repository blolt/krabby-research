#pragma once

#include <stddef.h>
#include <stdint.h>

#include "display_constants.h"
#include "../../units.h"
#include "../telemetry.h"
#include "../imu/imu_measurement.h"

enum class StatusDisplayRole : uint8_t
{
    Unknown,
    Front,
    Left,
    Right,
};

enum class ActuatorGlyph : uint8_t
{
    Hold,
    Extend,
    Retract,
    Disconnected,
    Unverified,
};

struct ControllerDisplayState
{
    ControllerDisplayState();

    ActuatorGlyph glyphs[CONTROLLER_ACTUATOR_COUNT];
    bool connected[CONTROLLER_ACTUATOR_COUNT];
    uint32_t lastTelemetryMilliseconds;
    bool seen;
};

struct StatusDisplayModel
{
    StatusDisplayModel();

    StatusDisplayRole role;
    ActuatorGlyph legs[CONTROLLER_ACTUATOR_COUNT][STATUS_DISPLAY_JOINTS_PER_LEG];
    float batteryLevel[2];
    Volts packVoltage;
    Degrees roll;
    Degrees pitch;
    bool frontPresent;
    bool leftPresent;
    bool rightPresent;
};

ActuatorGlyph actuatorGlyphForCommandedDrive(
    bool connected, int pwm, int moveThreshold, bool attachmentVerified);
void updateControllerDisplayState(
    ControllerDisplayState &controller,
    const ActuatorTelemetry (&actuators)[CONTROLLER_ACTUATOR_COUNT],
    int moveThreshold,
    uint32_t nowMilliseconds);

bool isControllerDisplayStateFresh(
    const ControllerDisplayState &controller,
    bool slotAssigned,
    uint32_t nowMilliseconds,
    uint32_t timeoutMilliseconds = CONTROLLER_DISPLAY_TIMEOUT_MILLISECONDS);

void setControllerDisplayLegs(
    StatusDisplayModel &model,
    size_t firstLeg,
    size_t secondLeg,
    const ActuatorGlyph (&glyphs)[CONTROLLER_ACTUATOR_COUNT]);

Degrees tiltRoll(const ImuMeasurement &measurement);
Degrees tiltPitch(const ImuMeasurement &measurement);

StatusDisplayModel buildStatusDisplayModel(
    StatusDisplayRole role,
    bool frontPresent,
    const ActuatorGlyph (&localGlyphs)[CONTROLLER_ACTUATOR_COUNT],
    const ControllerDisplayState &left,
    bool leftAssigned,
    const ControllerDisplayState &right,
    bool rightAssigned,
    const ImuMeasurement &measurement,
    uint32_t nowMilliseconds);

// True when any actuator this board can see is disconnected. The caller owns
// the pin write.
bool anyActuatorDisconnected(
    const bool (&localConnected)[CONTROLLER_ACTUATOR_COUNT],
    const ControllerDisplayState &left,
    bool leftFresh,
    const ControllerDisplayState &right,
    bool rightFresh);

bool hasDisconnectedActuator(
    const bool (&connected)[CONTROLLER_ACTUATOR_COUNT]);
bool statusDisplayModelsEqual(const StatusDisplayModel &left, const StatusDisplayModel &right);
const char *statusDisplayRoleLabel(StatusDisplayRole role);
