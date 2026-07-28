#pragma once

#include <math.h>
#include <stdint.h>

const int POT_BAND_LO = 5;
const int POT_BAND_HI = 1018;
const uint8_t POS_DEBOUNCE = 3;

struct PotValidityTracker
{
    int previousRawPot;
    uint8_t badSampleCount;
    bool valid;

    PotValidityTracker()
        : previousRawPot(0), badSampleCount(0), valid(true)
    {
    }

    void reset(int seedRawPot)
    {
        previousRawPot = seedRawPot;
        badSampleCount = 0;
        valid = true;
    }

    bool update(int rawPot, bool driving, float idleJitterMax)
    {
        const bool inSaneBand =
            rawPot > POT_BAND_LO && rawPot < POT_BAND_HI;
        int delta = rawPot - previousRawPot;
        if (delta < 0)
            delta = -delta;
        previousRawPot = rawPot;

        const bool slewValid = driving || delta <= idleJitterMax;
        if (inSaneBand && slewValid)
            badSampleCount = 0;
        else if (badSampleCount < POS_DEBOUNCE)
            ++badSampleCount;

        valid = badSampleCount < POS_DEBOUNCE;
        return valid;
    }
};

static float filteredActuatorPosition(
    bool connected,
    float normalizedPosition)
{
    return connected ? normalizedPosition : (float)NAN;
}
