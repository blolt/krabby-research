#pragma once

#include <stddef.h>

const size_t ACTUATORS_PER_CONTROLLER = 6;

static bool controllerHasDisconnectedActuator(
    const bool (&connected)[ACTUATORS_PER_CONTROLLER])
{
    for (size_t actuator = 0;
         actuator < ACTUATORS_PER_CONTROLLER;
         ++actuator)
        if (!connected[actuator])
            return true;
    return false;
}

static bool disconnectStatusLedActive(
    const bool (&localConnected)[ACTUATORS_PER_CONTROLLER],
    bool leftTelemetryFresh,
    const bool (&leftConnected)[ACTUATORS_PER_CONTROLLER],
    bool rightTelemetryFresh,
    const bool (&rightConnected)[ACTUATORS_PER_CONTROLLER])
{
    return
        controllerHasDisconnectedActuator(localConnected) ||
        (leftTelemetryFresh &&
         controllerHasDisconnectedActuator(leftConnected)) ||
        (rightTelemetryFresh &&
         controllerHasDisconnectedActuator(rightConnected));
}
