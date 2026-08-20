#include <math.h>

#include "display.h"
#include "display_constants.h"

ControllerDisplayState::ControllerDisplayState()
    : glyphs{}, connected{}, lastTelemetryMilliseconds(0), seen(false)
{
    for (size_t actuator = 0;
         actuator < CONTROLLER_ACTUATOR_COUNT;
         ++actuator)
    {
        glyphs[actuator] = ActuatorGlyph::Disconnected;
        connected[actuator] = false;
    }
}

StatusDisplayModel::StatusDisplayModel()
    : role(StatusDisplayRole::Unknown), legs{}, batteryLevel{0.0f, 0.0f},
      packVoltage(), roll(), pitch(), frontPresent(false),
      leftPresent(false), rightPresent(false)
{
    for (size_t leg = 0; leg < CONTROLLER_ACTUATOR_COUNT; ++leg)
        for (size_t joint = 0; joint < STATUS_DISPLAY_JOINTS_PER_LEG; ++joint)
            legs[leg][joint] = ActuatorGlyph::Disconnected;
}

ActuatorGlyph actuatorGlyphForCommandedDrive(
    bool connected, int pwm, int moveThreshold, bool attachmentVerified)
{
    if (!connected)
        return ActuatorGlyph::Disconnected;
    if (pwm >= moveThreshold)
        return ActuatorGlyph::Extend;
    if (pwm <= -moveThreshold)
        return ActuatorGlyph::Retract;
    return attachmentVerified ? ActuatorGlyph::Hold : ActuatorGlyph::Unverified;
}

// TODO: introduce decay from holding to unverified if the actuator has gone uncommanded for a while.
void updateControllerDisplayState(
    ControllerDisplayState &controller,
    const ActuatorTelemetry (&actuators)[CONTROLLER_ACTUATOR_COUNT],
    int moveThreshold,
    uint32_t nowMilliseconds)
{
    for (size_t actuator = 0; actuator < CONTROLLER_ACTUATOR_COUNT; ++actuator)
    {
        controller.connected[actuator] = actuators[actuator].connected;
        controller.glyphs[actuator] = actuatorGlyphForCommandedDrive(
            actuators[actuator].connected,
            static_cast<int>(actuators[actuator].extendPwm) -
                static_cast<int>(actuators[actuator].retractPwm),
            moveThreshold,
            actuators[actuator].attachmentVerified);
    }
    controller.lastTelemetryMilliseconds = nowMilliseconds;
    controller.seen = true;
}

bool isControllerDisplayStateFresh(
    const ControllerDisplayState &controller,
    bool slotAssigned,
    uint32_t nowMilliseconds,
    uint32_t timeoutMilliseconds)
{
    return slotAssigned && controller.seen &&
            nowMilliseconds - controller.lastTelemetryMilliseconds < timeoutMilliseconds;
}

void setControllerDisplayLegs(
    StatusDisplayModel &model,
    size_t firstLeg,
    size_t secondLeg,
    const ActuatorGlyph (&glyphs)[CONTROLLER_ACTUATOR_COUNT])
{
    for (size_t joint = 0; joint < STATUS_DISPLAY_JOINTS_PER_LEG; ++joint)
    {
        model.legs[firstLeg][joint] = glyphs[joint];
        model.legs[secondLeg][joint] = glyphs[joint + STATUS_DISPLAY_JOINTS_PER_LEG];
    }
}

bool hasDisconnectedActuator(
    const bool (&connected)[CONTROLLER_ACTUATOR_COUNT])
{
    for (size_t actuator = 0; actuator < CONTROLLER_ACTUATOR_COUNT; ++actuator)
        if (!connected[actuator])
            return true;
    return false;
}

bool statusDisplayModelsEqual(const StatusDisplayModel &left, const StatusDisplayModel &right)
{
    if (left.role != right.role ||
        left.packVoltage.value != right.packVoltage.value ||
        left.roll.value != right.roll.value ||
        left.pitch.value != right.pitch.value ||
        left.frontPresent != right.frontPresent ||
        left.leftPresent != right.leftPresent ||
        left.rightPresent != right.rightPresent)
        return false;
    for (size_t battery = 0; battery < 2; ++battery)
        if (left.batteryLevel[battery] != right.batteryLevel[battery])
            return false;
    for (size_t leg = 0; leg < CONTROLLER_ACTUATOR_COUNT; ++leg)
        for (size_t joint = 0; joint < STATUS_DISPLAY_JOINTS_PER_LEG; ++joint)
            if (left.legs[leg][joint] != right.legs[leg][joint])
                return false;
    return true;
}

const char *statusDisplayRoleLabel(StatusDisplayRole role)
{
    switch (role)
    {
        case StatusDisplayRole::Front: return "FRONT";
        case StatusDisplayRole::Left: return "LEFT";
        case StatusDisplayRole::Right: return "RIGHT";
        default: return "UNKWN";
    }
}

Degrees tiltRoll(const ImuMeasurement &measurement)
{
    const float ay = measurement.acceleration[1].value;
    const float az = measurement.acceleration[2].value;

    return Radians(atan2(ay, az)).toDegrees(Rounding::HalfAwayFromZero);
}

Degrees tiltPitch(const ImuMeasurement &measurement)
{
    const float ax = measurement.acceleration[0].value;
    const float ay = measurement.acceleration[1].value;
    const float az = measurement.acceleration[2].value;
    return Radians(atan2(-ax, sqrt(ay * ay + az * az))).toDegrees(Rounding::HalfAwayFromZero);
}

StatusDisplayModel buildStatusDisplayModel(
    StatusDisplayRole role,
    bool frontPresent,
    const ActuatorGlyph (&localGlyphs)[CONTROLLER_ACTUATOR_COUNT],
    const ControllerDisplayState &left,
    bool leftAssigned,
    const ControllerDisplayState &right,
    bool rightAssigned,
    const ImuMeasurement &measurement,
    uint32_t nowMilliseconds)
{
    StatusDisplayModel model;
    model.role = role;
    model.frontPresent = frontPresent;
    model.leftPresent =
        isControllerDisplayStateFresh(left, leftAssigned, nowMilliseconds);
    model.rightPresent =
        isControllerDisplayStateFresh(right, rightAssigned, nowMilliseconds);

    ActuatorGlyph missingGlyphs[CONTROLLER_ACTUATOR_COUNT];
    for (size_t actuator = 0; actuator < CONTROLLER_ACTUATOR_COUNT; ++actuator)
        missingGlyphs[actuator] = ActuatorGlyph::Disconnected;

    setControllerDisplayLegs(model, 0, 1, localGlyphs);
    setControllerDisplayLegs(
        model, 4, 2, model.leftPresent ? left.glyphs : missingGlyphs);
    setControllerDisplayLegs(
        model, 5, 3, model.rightPresent ? right.glyphs : missingGlyphs);

    if (measurement.succeeded())
    {
        model.roll = tiltRoll(measurement);
        model.pitch = tiltPitch(measurement);
    }
    return model;
}

bool anyActuatorDisconnected(
    const bool (&localConnected)[CONTROLLER_ACTUATOR_COUNT],
    const ControllerDisplayState &left,
    bool leftFresh,
    const ControllerDisplayState &right,
    bool rightFresh)
{
    return hasDisconnectedActuator(localConnected) ||
           (leftFresh && hasDisconnectedActuator(left.connected)) ||
           (rightFresh && hasDisconnectedActuator(right.connected));
}
