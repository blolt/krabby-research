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

// No trustworthy reading: the bar draws as a dotted centre line and the header
// voltage as dashes, so "we lost the monitor" is distinct from "the pack is flat".
static constexpr int8_t BATTERY_FILL_NO_SIGNAL = -1;
static constexpr int16_t PACK_DECIVOLTS_NO_SIGNAL = INT16_MIN;

struct StatusDisplayModel
{
    StatusDisplayModel();

    StatusDisplayRole role;
    ActuatorGlyph legs[CONTROLLER_ACTUATOR_COUNT][STATUS_DISPLAY_JOINTS_PER_LEG];
    // Quantized to what the display can actually show: filled pixel count, and
    // the tenths of a volt the header prints. Storing the raw floats made almost
    // every frame differ under statusDisplayModelsEqual's exact !=, forcing a
    // redraw for changes too small to move a pixel (Task 2, 2h.2).
    int8_t batteryFill[2];
    int16_t packDecivolts;
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
    // Latest battery measurement, or defaults when no BATT frame has been read.
    // Passed in rather than sampled so the model stays free of the sketch's
    // globals and testable on the host.
    Volts packVoltage,
    const float (&batteryLevel)[2],
    bool batteryValid,
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
int8_t batteryFillPixels(float level);

bool statusDisplayModelsEqual(const StatusDisplayModel &left, const StatusDisplayModel &right);
const char *statusDisplayRoleLabel(StatusDisplayRole role);
