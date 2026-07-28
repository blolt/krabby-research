#pragma once

#include <stdint.h>

#include "sensors_config.h"

// Unsigned subtraction intentionally preserves the elapsed duration across the
// uint32_t millis() rollover.
inline bool telemetryPollDue(uint32_t now, uint32_t previousPoll)
{
    return static_cast<uint32_t>(now - previousPoll) >=
        TELEMETRY_POLL_INTERVAL.value();
}
