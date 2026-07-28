#pragma once

#include <math.h>

#include "measurement_units.h"

// Solve the dimensionless correction applied to every Pack measurement derived
// from shunt current. The caller owns command parsing and persistence; this
// function only validates the measurement pair and computes the scale.
inline bool calculateShuntTrim(
    Amps knownCurrent,
    Amps measuredCurrent,
    Amps minimumCurrentMagnitude,
    float minimumTrim,
    float maximumTrim,
    float& result)
{
    const float knownAmps = knownCurrent.value();
    const float measuredAmps = measuredCurrent.value();
    const float minimumAmps = minimumCurrentMagnitude.value();

    if (!isfinite(knownAmps) ||
        !isfinite(measuredAmps) ||
        !isfinite(minimumAmps) ||
        minimumAmps < 0.0f ||
        fabs(knownAmps) < minimumAmps ||
        fabs(measuredAmps) < minimumAmps ||
        !isfinite(minimumTrim) ||
        !isfinite(maximumTrim) ||
        minimumTrim <= 0.0f ||
        maximumTrim < minimumTrim)
        return false;

    const float trim = knownAmps / measuredAmps;
    if (!isfinite(trim) || trim < minimumTrim || trim > maximumTrim)
        return false;

    result = trim;
    return true;
}
