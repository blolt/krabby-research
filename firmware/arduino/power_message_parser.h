#pragma once

#include <string.h>

static const char POWER_SHUTDOWN_ACK_LINE[] = "PWR 1 SHUTDOWN_ACK";

inline bool powerIsShutdownAckLine(const char* line)
{
    if (line == nullptr)
        return false;

    const size_t expectedLength = sizeof(POWER_SHUTDOWN_ACK_LINE) - 1;
    if (strncmp(line, POWER_SHUTDOWN_ACK_LINE, expectedLength) != 0)
        return false;

    return line[expectedLength] == '\0' ||
           (line[expectedLength] == '\r' &&
            line[expectedLength + 1] == '\0');
}
