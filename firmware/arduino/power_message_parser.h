#pragma once

#include <string.h>

static const char POWER_SHUTDOWN_ACK_LINE[] = "PWR 1 SHUTDOWN_ACK";
static const char POWER_SHUTDOWN_ACK_PAYLOAD[] = "WR 1 SHUTDOWN_ACK";

inline bool powerMatchesExactLine(const char* line, const char* expected)
{
    if (line == nullptr || expected == nullptr)
        return false;

    const size_t expectedLength = strlen(expected);
    const size_t actualLength = strlen(line);
    if (actualLength == expectedLength)
        return memcmp(line, expected, expectedLength) == 0;
    return actualLength == expectedLength + 1 &&
           line[expectedLength] == '\r' &&
           memcmp(line, expected, expectedLength) == 0;
}

inline bool powerIsShutdownAckLine(const char* line)
{
    return powerMatchesExactLine(line, POWER_SHUTDOWN_ACK_LINE);
}

// The normal first-character dispatcher has already consumed the leading 'P'.
// Match the remaining payload directly instead of rebuilding or reinterpreting
// the line as another command family.
inline bool powerIsShutdownAckPayload(const char* payload)
{
    return powerMatchesExactLine(payload, POWER_SHUTDOWN_ACK_PAYLOAD);
}
