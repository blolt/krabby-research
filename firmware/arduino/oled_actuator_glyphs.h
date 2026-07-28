#pragma once

#include <math.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

enum OledGlyph { OG_HOLD, OG_EXTEND, OG_RETRACT, OG_DISC };

const size_t OLED_ACTUATORS_PER_CONTROLLER = 6;
const size_t OLED_JOINTS_PER_LEG = 3;
const size_t OLED_TELEMETRY_FIELDS_PER_ACTUATOR = 9;
const size_t OLED_TELEMETRY_POSITION_FIELD = 1;
const size_t OLED_TELEMETRY_RETRACT_PWM_FIELD = 6;
const size_t OLED_TELEMETRY_EXTEND_PWM_FIELD = 7;
const int OLED_TELEMETRY_PWM_MIN = 0;
const int OLED_TELEMETRY_PWM_MAX = 255;

template <typename Display>
static void drawOledActuatorGlyph(
    Display &display,
    int centerX,
    int centerY,
    OledGlyph glyph,
    int glyphSize)
{
    const int radius = glyphSize / 2;
    const int triangleRadius = radius - 1;

    if (glyph == OG_EXTEND || glyph == OG_RETRACT)
    {
        const int diameter = 2 * triangleRadius;
        for (int row = 0; row <= diameter; ++row)
        {
            const int widthRow =
                glyph == OG_EXTEND ? row : diameter - row;
            const int halfWidth = widthRow * triangleRadius / diameter;
            const int y = centerY - triangleRadius + row;
            display.line(
                centerX - halfWidth,
                y,
                centerX + halfWidth,
                y);
        }
        return;
    }

    if (glyph == OG_HOLD)
    {
        for (int dy = -radius; dy <= radius; ++dy)
            for (int dx = -radius; dx <= radius; ++dx)
                if (dx * dx + dy * dy <= radius * radius)
                    display.pixel(centerX + dx, centerY + dy);
        return;
    }

    display.line(
        centerX - triangleRadius,
        centerY - triangleRadius,
        centerX + triangleRadius,
        centerY + triangleRadius);
    display.line(
        centerX - triangleRadius,
        centerY + triangleRadius,
        centerX + triangleRadius,
        centerY - triangleRadius);
}

static OledGlyph actuatorGlyph(bool connected, int pwm, int moveThreshold)
{
    if (!connected)
        return OG_DISC;
    if (pwm >= moveThreshold)
        return OG_EXTEND;
    if (pwm <= -moveThreshold)
        return OG_RETRACT;
    return OG_HOLD;
}

static bool parseIntegerToken(const char *begin, const char *end, int &value)
{
    if (!begin || begin == end)
        return false;

    char *parsedEnd = NULL;
    const long parsed = strtol(begin, &parsedEnd, 10);
    if (parsedEnd != end)
        return false;

    value = (int)parsed;
    return true;
}

static bool parsePositionConnected(
    const char *begin,
    const char *end,
    bool &connected)
{
    if (!begin || begin == end)
        return false;

    char *parsedEnd = NULL;
    const double position = strtod(begin, &parsedEnd);
    if (parsedEnd != end)
        return false;

    connected = isfinite(position);
    return true;
}

static bool parseActuatorGlyphSegment(
    const char *begin,
    const char *end,
    int moveThreshold,
    OledGlyph &glyph,
    bool &connected)
{
    const char *fieldBegin[OLED_TELEMETRY_FIELDS_PER_ACTUATOR];
    const char *fieldEnd[OLED_TELEMETRY_FIELDS_PER_ACTUATOR];
    size_t fieldCount = 0;
    const char *cursor = begin;

    while (cursor < end)
    {
        while (cursor < end && (*cursor == ' ' || *cursor == '\t'))
            ++cursor;
        if (cursor == end)
            break;
        if (fieldCount == OLED_TELEMETRY_FIELDS_PER_ACTUATOR)
            return false;

        fieldBegin[fieldCount] = cursor;
        while (cursor < end && *cursor != ' ' && *cursor != '\t')
            ++cursor;
        fieldEnd[fieldCount] = cursor;
        ++fieldCount;
    }

    if (fieldCount != OLED_TELEMETRY_FIELDS_PER_ACTUATOR)
        return false;

    bool parsedConnected = false;
    int retractPwm = 0;
    int extendPwm = 0;
    if (!parsePositionConnected(
            fieldBegin[OLED_TELEMETRY_POSITION_FIELD],
            fieldEnd[OLED_TELEMETRY_POSITION_FIELD],
            parsedConnected) ||
        !parseIntegerToken(
            fieldBegin[OLED_TELEMETRY_RETRACT_PWM_FIELD],
            fieldEnd[OLED_TELEMETRY_RETRACT_PWM_FIELD],
            retractPwm) ||
        !parseIntegerToken(
            fieldBegin[OLED_TELEMETRY_EXTEND_PWM_FIELD],
            fieldEnd[OLED_TELEMETRY_EXTEND_PWM_FIELD],
            extendPwm))
        return false;
    if (retractPwm < OLED_TELEMETRY_PWM_MIN ||
        retractPwm > OLED_TELEMETRY_PWM_MAX ||
        extendPwm < OLED_TELEMETRY_PWM_MIN ||
        extendPwm > OLED_TELEMETRY_PWM_MAX ||
        (retractPwm != 0 && extendPwm != 0))
        return false;

    glyph = actuatorGlyph(
        parsedConnected,
        extendPwm - retractPwm,
        moveThreshold);
    connected = parsedConnected;
    return true;
}

static bool parseControllerActuatorStates(
    const char *line,
    const char *expectedRoleLabel,
    int moveThreshold,
    OledGlyph (&glyphs)[OLED_ACTUATORS_PER_CONTROLLER],
    bool (&connected)[OLED_ACTUATORS_PER_CONTROLLER])
{
    if (!line || !expectedRoleLabel)
        return false;

    const size_t roleLength = strlen(expectedRoleLabel);
    if (strncmp(line, expectedRoleLabel, roleLength) != 0 ||
        line[roleLength] != ';')
        return false;

    OledGlyph parsed[OLED_ACTUATORS_PER_CONTROLLER];
    bool parsedConnected[OLED_ACTUATORS_PER_CONTROLLER];
    const char *cursor = line + roleLength;
    for (size_t actuator = 0;
         actuator < OLED_ACTUATORS_PER_CONTROLLER;
         ++actuator)
    {
        if (*cursor != ';')
            return false;
        const char *segmentBegin = cursor + 1;
        const char *segmentEnd = strchr(segmentBegin, ';');
        if (!segmentEnd)
            segmentEnd = segmentBegin + strlen(segmentBegin);
        if (!parseActuatorGlyphSegment(
                segmentBegin,
                segmentEnd,
                moveThreshold,
                parsed[actuator],
                parsedConnected[actuator]))
            return false;
        cursor = segmentEnd;
    }
    if (*cursor != '\0')
        return false;

    for (size_t actuator = 0;
         actuator < OLED_ACTUATORS_PER_CONTROLLER;
         ++actuator)
    {
        glyphs[actuator] = parsed[actuator];
        connected[actuator] = parsedConnected[actuator];
    }
    return true;
}

static void setControllerLegGlyphs(
    OledGlyph (&legs)[OLED_ACTUATORS_PER_CONTROLLER][OLED_JOINTS_PER_LEG],
    size_t firstLeg,
    size_t secondLeg,
    const OledGlyph (&glyphs)[OLED_ACTUATORS_PER_CONTROLLER])
{
    for (size_t joint = 0; joint < OLED_JOINTS_PER_LEG; ++joint)
    {
        legs[firstLeg][joint] = glyphs[joint];
        legs[secondLeg][joint] = glyphs[joint + OLED_JOINTS_PER_LEG];
    }
}
