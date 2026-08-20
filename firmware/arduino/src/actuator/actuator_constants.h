#pragma once


// TODO: Define and relocate other actuator constants into this file.
static constexpr int ACTUATOR_PWM_MAXIMUM_MAGNITUDE = 255;

// An open position input is a persistent fault, so the probe is rare; the pin is
// pulled up only for the read itself.
static constexpr unsigned long POT_PROBE_INTERVAL_MS = 2000;
// RC of the wiper's output impedance against cable capacitance is sub-microsecond;
// this is slack, not a computed settling time.
static constexpr unsigned int POT_PROBE_SETTLE_US = 200;
