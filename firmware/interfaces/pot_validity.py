"""Pure-Python mirror of the firmware posValid FSM (M16 Task 2, AC 2f).

The disconnected-actuator detection lives in LinearActuator::updateSensors /
init in firmware/arduino/actuator_manager.h and runs only on the MCU, so it has
no direct host harness. This module re-implements the exact decision -- POT_BAND
sane-band + EN-gated per-tick slew test + POS_DEBOUNCE debounce with immediate
re-validation -- as executable Python so the behavior is unit-testable off
hardware, following the repo's parity-mirror pattern (cf. power_fsm.py).

The module constants below MUST equal the firmware's; tests/unit/firmware/
test_pot_validity.py pins the parity against actuator_manager.h.
"""
from __future__ import annotations

# Sane-band for the raw pot ADC (actuator_manager.h POT_BAND_LO/HI). A wiper
# shorted/open to a rail reads a STABLE 0 or 1023, which no slew test can catch,
# so a reading pinned at either rail is rejected regardless of EN.
POT_BAND_LO = 5      # raw ADC at/below this = wiper shorted low / open
POT_BAND_HI = 1018   # raw ADC at/above this = wiper shorted high

# Consecutive bad ticks before posValid flips True->False (POS_DEBOUNCE). Drops
# slow (debounced), recovers fast (immediate on the first good tick).
POS_DEBOUNCE = 3

# Idle-only per-tick slew budget (ControlConfig.potJitterMax). Only enforced
# while EN is LOW; a driven joint is expected to move, so the slew test is
# suppressed while EN is HIGH.
POT_JITTER_MAX = 6.0


class PotValidityModel:
    """Mirror of LinearActuator's posValid state.

    Construct with the boot pot seed (firmware seeds prevRawPot from the first
    analogRead(pinPot) in init(), with posValid True). Call step() once per
    sensor tick with the raw pot reading and whether EN is currently HIGH.
    """

    def __init__(self, seed_pot: int):
        # Matches init(): prevRawPot seeded, badPotTicks=0, posValid=True.
        self.prev_raw = int(seed_pot)
        self.bad_ticks = 0
        self.pos_valid = True

    def step(self, raw_pot: int, en_high: bool) -> bool:
        """Advance one tick; returns the debounced posValid.

        Mirrors updateSensors() exactly:
          band_ok = POT_BAND_LO < raw < POT_BAND_HI          (always enforced)
          slew    = |raw - prev_raw|
          slew_ok = en_high or slew <= POT_JITTER_MAX        (EN-gated)
          good tick -> bad_ticks = 0; bad tick -> bad_ticks++ (capped at DEBOUNCE)
          pos_valid = bad_ticks < POS_DEBOUNCE
        """
        band_ok = POT_BAND_LO < raw_pot < POT_BAND_HI
        slew = abs(raw_pot - self.prev_raw)
        self.prev_raw = raw_pot
        slew_ok = en_high or (slew <= POT_JITTER_MAX)
        if band_ok and slew_ok:
            self.bad_ticks = 0
        elif self.bad_ticks < POS_DEBOUNCE:
            self.bad_ticks += 1
        self.pos_valid = self.bad_ticks < POS_DEBOUNCE
        return self.pos_valid
