#include "telemetry.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

static bool parseActuatorPwmField(
    const char *begin,
    const char *end,
    uint8_t &value)
{
    if (!begin || begin == end)
        return false;

    char *parsedEnd = nullptr;
    const long parsed = strtol(begin, &parsedEnd, 10);
    if (parsedEnd != end ||
        parsed < 0 ||
        parsed > ACTUATOR_PWM_MAXIMUM_MAGNITUDE)
    {
        return false;
    }

    value = static_cast<uint8_t>(parsed);
    return true;
}

static bool parseActuatorConnectionFromPosition(
    const char *begin,
    const char *end,
    bool &connected)
{
    if (!begin || begin == end)
        return false;

    char *parsedEnd = nullptr;
    const double position = strtod(begin, &parsedEnd);
    if (parsedEnd != end)
        return false;

    connected = isfinite(position);
    return true;
}

static bool parseActuatorTelemetryFields(
    const char *begin,
    const char *end,
    ActuatorTelemetry &actuator)
{
    const char *fieldBegin[ACTUATOR_TELEMETRY_MAX_FIELD_COUNT];
    const char *fieldEnd[ACTUATOR_TELEMETRY_MAX_FIELD_COUNT];
    size_t fieldCount = 0;
    const char *cursor = begin;
    while (cursor < end)
    {
        while (cursor < end && (*cursor == ' ' || *cursor == '\t'))
            ++cursor;
        if (cursor == end)
            break;
        if (fieldCount == ACTUATOR_TELEMETRY_MAX_FIELD_COUNT)
            return false;
        fieldBegin[fieldCount] = cursor;
        while (cursor < end && *cursor != ' ' && *cursor != '\t')
            ++cursor;
        fieldEnd[fieldCount++] = cursor;
    }

    if (fieldCount != ACTUATOR_TELEMETRY_FIELD_COUNT &&
        fieldCount != ACTUATOR_TELEMETRY_MAX_FIELD_COUNT)
        return false;

    // A sender that omits the field is one that cannot measure it, so claiming
    // "unverified" would render a hollow glyph forever on an older follower.
    actuator.attachmentVerified = true;
    if (fieldCount == ACTUATOR_TELEMETRY_MAX_FIELD_COUNT)
    {
        const char *attach = fieldBegin[ACTUATOR_TELEMETRY_ATTACHMENT_FIELD_INDEX];
        if (attach + 1 != fieldEnd[ACTUATOR_TELEMETRY_ATTACHMENT_FIELD_INDEX])
            return false;
        actuator.attachmentVerified = *attach != '0';
    }

    if (!parseActuatorConnectionFromPosition(
            fieldBegin[ACTUATOR_TELEMETRY_POSITION_FIELD_INDEX],
            fieldEnd[ACTUATOR_TELEMETRY_POSITION_FIELD_INDEX],
            actuator.connected) ||
        !parseActuatorPwmField(
            fieldBegin[ACTUATOR_TELEMETRY_RETRACT_PWM_FIELD_INDEX],
            fieldEnd[ACTUATOR_TELEMETRY_RETRACT_PWM_FIELD_INDEX],
            actuator.retractPwm) ||
        !parseActuatorPwmField(
            fieldBegin[ACTUATOR_TELEMETRY_EXTEND_PWM_FIELD_INDEX],
            fieldEnd[ACTUATOR_TELEMETRY_EXTEND_PWM_FIELD_INDEX],
            actuator.extendPwm))
    {
        return false;
    }

    return actuator.retractPwm == 0 || actuator.extendPwm == 0;
}

bool parseActuatorTelemetry(
    const char *line,
    const char *expectedRole,
    ActuatorTelemetry (&actuators)[CONTROLLER_ACTUATOR_COUNT])
{
    if (!line || !expectedRole)
        return false;

    const size_t roleLength = strlen(expectedRole);
    if (strncmp(line, expectedRole, roleLength) != 0 || line[roleLength] != ';')
        return false;

    ActuatorTelemetry parsedActuators[CONTROLLER_ACTUATOR_COUNT] = {};
    const char *cursor = line + roleLength;
    for (size_t actuator = 0;
         actuator < CONTROLLER_ACTUATOR_COUNT;
         ++actuator)
    {
        if (*cursor != ';')
            return false;
        const char *begin = cursor + 1;
        const char *end = strchr(begin, ';');
        if (!end)
            end = begin + strlen(begin);
        if (!parseActuatorTelemetryFields(
                begin, end, parsedActuators[actuator]))
        {
            return false;
        }
        cursor = end;
    }

    if (*cursor != '\0')
        return false;

    for (size_t actuator = 0;
         actuator < CONTROLLER_ACTUATOR_COUNT;
         ++actuator)
        actuators[actuator] = parsedActuators[actuator];
    return true;
}
