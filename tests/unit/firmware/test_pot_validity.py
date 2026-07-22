"""Executable coverage for the posValid FSM (M16 Task 2, AC 2f).

The firmware detection (LinearActuator::updateSensors/init in
actuator_manager.h) runs only on the MCU. firmware/interfaces/pot_validity.py
mirrors it in pure Python; these tests exercise the mirror's decision table AND
pin its constants to the firmware header (the parity guard), following the
repo's parity-mirror pattern (cf. test_power_fsm_parity.py).

Naming: test_<condition>_<expected>, arrange/act/assert body structure.
"""
import re
from pathlib import Path

from firmware.interfaces import pot_validity as pv

_ACT_H = (
    Path(__file__).resolve().parents[3]
    / "firmware" / "arduino" / "actuator_manager.h"
).read_text()


def _define_int(name: str) -> int:
    m = re.search(rf"#define\s+{name}\s+(\d+)", _ACT_H)
    assert m, f"#define {name} not found in actuator_manager.h"
    return int(m.group(1))


# --- FSM behavior (table-driven where natural) -------------------------------
class TestPotValidityFsm:
    def test_boot_seed_is_valid(self):
        m = pv.PotValidityModel(seed_pot=512)
        assert m.pos_valid is True

    def test_two_bad_ticks_stay_valid_third_flips_invalid(self):
        # Idle high-slew ticks (EN low): slew far exceeds POT_JITTER_MAX so each
        # is a bad tick. Debounced: valid through 2, invalid on the 3rd.
        m = pv.PotValidityModel(seed_pot=500)
        assert m.step(600, en_high=False) is True    # bad tick 1
        assert m.step(500, en_high=False) is True    # bad tick 2
        assert m.step(600, en_high=False) is False   # bad tick 3 -> invalid

    def test_good_tick_revalidates_immediately(self):
        # After dropping invalid, a single in-band low-slew idle tick recovers it
        # on the very next tick (asymmetric: slow to drop, fast to recover).
        m = pv.PotValidityModel(seed_pot=500)
        m.step(600, en_high=False)
        m.step(500, en_high=False)
        assert m.step(600, en_high=False) is False   # invalid
        assert m.step(602, en_high=False) is True    # slew 2 <= budget -> valid

    def test_rail_pinned_is_invalid_even_while_driving(self):
        # A stable rail value (>= POT_BAND_HI) fails the sane band regardless of
        # EN, so even a driven joint (slew test suppressed) drops invalid.
        m = pv.PotValidityModel(seed_pot=500)
        assert m.step(1023, en_high=True) is True
        assert m.step(1023, en_high=True) is True
        assert m.step(1023, en_high=True) is False

    def test_large_slew_is_valid_while_en_high(self):
        # Driven joint moving fast: the slew test is suppressed while EN is HIGH,
        # so a big in-band jump stays valid (the anti-false-disconnect guard).
        m = pv.PotValidityModel(seed_pot=300)
        assert m.step(560, en_high=True) is True
        assert m.step(300, en_high=True) is True

    def test_same_large_slew_is_invalid_after_three_idle_ticks(self):
        # The identical jumps while EN is LOW are treated as a floating pin and
        # drop invalid after POS_DEBOUNCE ticks.
        m = pv.PotValidityModel(seed_pot=300)
        assert m.step(560, en_high=False) is True
        assert m.step(300, en_high=False) is True
        assert m.step(560, en_high=False) is False

    def test_slew_equal_to_jitter_max_is_a_good_tick(self):
        # Boundary: slew == POT_JITTER_MAX uses <= , so it is in-budget (good).
        m = pv.PotValidityModel(seed_pot=500)
        raw = 500 + int(pv.POT_JITTER_MAX)           # slew exactly the budget
        assert m.step(raw, en_high=False) is True
        assert m.bad_ticks == 0


# --- firmware <-> Python constant parity -------------------------------------
class TestPotValidityParity:
    def test_pot_band_constants_match_firmware(self):
        assert pv.POT_BAND_LO == _define_int("POT_BAND_LO")
        assert pv.POT_BAND_HI == _define_int("POT_BAND_HI")

    def test_pos_debounce_matches_firmware(self):
        assert pv.POS_DEBOUNCE == _define_int("POS_DEBOUNCE")

    def test_pot_jitter_max_matches_firmware(self):
        m = re.search(r"float\s+potJitterMax\s*=\s*([\d.]+)", _ACT_H)
        assert m, "potJitterMax default not found in actuator_manager.h"
        assert pv.POT_JITTER_MAX == float(m.group(1))
