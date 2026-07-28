#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

struct ControllerTelemetryFreshness
{
    bool seen;
    uint32_t lastTelemetryMs;
};

const size_t CONTROLLER_TELEMETRY_JOINT_COUNT = 6;
const size_t CONTROLLER_TELEMETRY_FIELDS_PER_JOINT = 9;

static bool telemetrySegmentHasFieldCount(
    const char *begin,
    const char *end,
    size_t expectedFields)
{
    size_t fields = 0;
    bool inField = false;
    for (const char *cursor = begin; cursor < end; ++cursor)
    {
        const bool whitespace = *cursor == ' ' || *cursor == '\t';
        if (!whitespace && !inField)
        {
            ++fields;
            inField = true;
        }
        else if (whitespace)
        {
            inField = false;
        }
    }
    return fields == expectedFields;
}

static bool isExpectedControllerTelemetry(
    const char *line,
    const char *expectedRoleLabel)
{
    if (!line || !expectedRoleLabel)
        return false;

    const size_t roleLength = strlen(expectedRoleLabel);
    if (strncmp(line, expectedRoleLabel, roleLength) != 0 ||
        line[roleLength] != ';')
        return false;

    const char *cursor = line + roleLength;
    for (size_t joint = 0; joint < CONTROLLER_TELEMETRY_JOINT_COUNT; ++joint)
    {
        if (*cursor != ';')
            return false;
        const char *segmentBegin = cursor + 1;
        const char *segmentEnd = strchr(segmentBegin, ';');
        if (!segmentEnd)
            segmentEnd = segmentBegin + strlen(segmentBegin);
        if (!telemetrySegmentHasFieldCount(
                segmentBegin,
                segmentEnd,
                CONTROLLER_TELEMETRY_FIELDS_PER_JOINT))
            return false;
        cursor = segmentEnd;
    }
    return *cursor == '\0';
}

static void noteControllerTelemetry(
    ControllerTelemetryFreshness &freshness,
    uint32_t now)
{
    freshness.seen = true;
    freshness.lastTelemetryMs = now;
}

static bool controllerTelemetryIsFresh(
    bool slotAssigned,
    const ControllerTelemetryFreshness &freshness,
    uint32_t now,
    uint32_t timeoutMs)
{
    return slotAssigned &&
           freshness.seen &&
           now - freshness.lastTelemetryMs < timeoutMs;
}
