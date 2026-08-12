"""Task 1 acceptance criteria — the LSM6DSO IMU on the leader.

Each criterion composes atomic checks from `checks.py` and adds the threshold that
turns a measurement into a verdict. Criterion text is quoted from the review spec
so the operator sees what is being claimed.

Two entries can share one acceptance criterion: 1g.1 needs a stationary capture
and a moving negative control. They run the same code under different guidance,
which is the whole point of a control, and each keeps its own `key` so results
record separately.
"""
from __future__ import annotations

from firmware.bench_tests import cal, checks
from firmware.bench_tests.harness import BenchTest, Result

# Thresholds. Each traces to a firmware constant or a spec statement.
TELEMETRY_INTERVAL_MS = 50.0     # TELEMETRY_INTERVAL_MS in src/telemetry.h
IMU_CAL_MAX_SPREAD_DPS = 2.0     # firmware rejects a capture wider than this
RESTING_GYRO_DPS = 0.5           # a quarter of the motion-rejection threshold
GRAVITY_TOLERANCE_G = 0.15
TIMING_TOLERANCE_MS = 5.0        # "no measurable change" on a 50 ms tick
STALL_FACTOR = 4                 # a gap this many ticks wide counts as a stall
INVERTED_SAMPLES = 20            # same bar as imu_bench.py's flip verdict


def _confirm(question: str) -> Result:
    answer = input(f"     {question} [y/N] > ").strip().lower()
    ok = answer.startswith("y")
    return Result(ok, "operator confirmed" if ok else "operator did not confirm")


# ------------------------------------------------------------- composed criteria
def _segment_reaches_host(port: str, **_) -> Result:
    m = checks.gravity_magnitude(port)
    if m.ok is False:
        return Result(False, m.text)
    ok = abs(m.values["magnitude_g"] - 1.0) <= GRAVITY_TOLERANCE_G
    return Result(ok, f"{m.text}\n(pass within {GRAVITY_TOLERANCE_G} g of 1.000)")


def _responds_to_motion(port: str, **_) -> Result:
    print("     move and rotate the board continuously for about 8 s...")
    m = checks.peak_motion(port)
    if m.ok is False:
        return Result(False, m.text)
    return Result(m.values["peak_dps"] > 20.0,
                  f"{m.text}\n(pass above 20 deg/s while moving)")


def _accel_tracks_gravity_direction(port: str, **_) -> Result:
    m = checks.orientation_flip(port)
    if m.ok is False:
        return Result(False, m.text)
    return Result(m.values["inverted"] > INVERTED_SAMPLES,
                  f"{m.text}\n(pass above {INVERTED_SAMPLES} inverted samples — a "
                  "failure here usually means the breakout itself was not turned over)")


def _gui_shows_imu(port: str, **_) -> Result:
    print("     in another terminal, from the repo root:")
    print(f"       python3 -m firmware.gui --port {port}")
    print("     check the IMU row: live roll/pitch/accel/gyro/temp, state = fresh (green).")
    print("     tilt the board, confirm the values track it, then close the GUI.")
    return _confirm("did the GUI show live IMU values that responded to motion?")


def _calibration_boot(port: str, moving: bool) -> Result:
    """Clear the stored bias, boot, and report what calibration decided.

    Shared by both 1g.1 entries; only the operator's behaviour differs.
    """
    cal.invalidate(port)
    if moving:
        print("     START MOVING THE BOARD NOW — keep it moving until told to stop.")
        input("     press Enter once you are already moving it > ")
    else:
        print("     put the board down and do not touch it.")
        input("     press Enter when it is settled > ")

    boot = checks.boot_log(port)
    if moving:
        print("     you can stop moving it now.")
        captured = bool(boot.values["captured"])
        return Result(not captured,
                      f"{boot.text}\ncaptured a bias: {captured}  (pass requires False)")

    if not boot.values["captured"]:
        return Result(False, f"{boot.text}\nno capture logged — was a valid bias still "
                             "stored, or is the sensor absent?")
    gyro = checks.resting_gyro(port)
    if gyro.ok is False:
        return Result(False, f"{boot.text}\n{gyro.text}")
    return Result(gyro.values["worst_axis_dps"] < RESTING_GYRO_DPS,
                  f"{boot.text}\n{gyro.text}\n(pass under {RESTING_GYRO_DPS} deg/s)")


def _bias_survives_reboot(port: str, **_) -> Result:
    first = checks.boot_log(port, seconds=12.0)
    if not (first.values["loaded"] or first.values["captured"]):
        return Result(False, f"first boot neither loaded nor captured:\n{first.text}")
    second = checks.boot_log(port, seconds=12.0)
    gyro = checks.resting_gyro(port)
    ok = bool(second.values["loaded"]) and (
        gyro.ok is not False and gyro.values["worst_axis_dps"] < RESTING_GYRO_DPS
    )
    return Result(ok, f"first boot : {first.values['cal_line'] or '(none)'}\n"
                      f"second boot: {second.values['cal_line'] or '(none)'}\n"
                      f"loaded from EEPROM on the second boot: {bool(second.values['loaded'])}\n"
                      f"{gyro.text}")


def _survives_absent_sensor(port: str, **_) -> Result:
    boot = checks.boot_log(port)
    if not boot.values["not_detected"]:
        return Result(False, f"boot logged no initialisation failure — is the sensor "
                             f"still connected?\n{boot.text}")
    timing = checks.tick_timing(port, lines=200)
    if timing.ok is False:
        return Result(False, f"{boot.text}\n{timing.text}")
    stall_limit = STALL_FACTOR * TELEMETRY_INTERVAL_MS
    ok = bool(boot.values["ready"]) and timing.values["max"] <= stall_limit
    return Result(ok, f"{boot.text}\n{timing.text}\n"
                      f"reached 'Krabby Ready': {bool(boot.values['ready'])}; "
                      f"a stall would exceed {stall_limit:.0f} ms")


def _timing_unchanged(port: str, **_) -> Result:
    with_imu = checks.tick_timing(port)
    if with_imu.ok is False:
        return Result(False, f"connected: {with_imu.text}")
    print(f"     with IMU: {with_imu.text}")
    input("     now UNPLUG the IMU, then press Enter > ")
    boot = checks.boot_log(port, seconds=8.0)
    if not boot.values["not_detected"]:
        return Result(False, "sensor still detected after the unplug prompt")
    without = checks.tick_timing(port)
    if without.ok is False:
        return Result(False, f"absent: {without.text}")
    delta = with_imu.values["mean"] - without.values["mean"]
    return Result(abs(delta) < TIMING_TOLERANCE_MS,
                  f"with IMU   : {with_imu.text}\n"
                  f"without IMU: {without.text}\n"
                  f"mean delta : {delta:+.2f} ms on a {TELEMETRY_INTERVAL_MS:.0f} ms tick "
                  f"({abs(delta) / TELEMETRY_INTERVAL_MS * 100:.1f}%) — "
                  f"pass under {TIMING_TOLERANCE_MS:.0f} ms")


# ------------------------------------------------------------- wiring checklist
WIRING = [
    ("1a.1", "Sensor on the leader only",
     "LSM6DSO connected to the primary (leader) Mega only",
     "is the LSM6DSO on the leader Mega and no other board?"),
    ("1a.2", "Powered from 3.3 V",
     "powered from 3.3 V",
     "is its supply the 3.3 V rail, not 5 V?"),
    ("1a.3", "On SDA=D20 / SCL=D21",
     "on SDA=D20 / SCL=D21",
     "are SDA and SCL on D20 and D21?"),
    ("1a.4", "Via a Qwiic to Dupont adapter",
     "via a Qwiic→Dupont adapter",
     "is it connected through the Qwiic to Dupont adapter?"),
    ("1a.5", "Followers untouched",
     "Followers are untouched.",
     "are both follower boards unmodified — no IMU, no rewiring?"),
]


def _wiring_check(question: str):
    def run(**_) -> Result:
        return _confirm(question)
    return run


TESTS = [
    *[
        BenchTest(ac=ac, title=title, criterion=criterion,
                  setup="Visual and multimeter inspection — nothing is flashed.",
                  expect="You can confirm it by inspection.",
                  run=_wiring_check(question), manual=True)
        for ac, title, criterion, question in WIRING
    ],
    BenchTest(
        ac="e2e.1", title="IMU segment reaches the host and parses",
        criterion="Leader on USB -> ;IMU appears and parses (sheet row, not a Patina A/C)",
        setup="IMU connected, and the board booted with it attached. Keep it still.",
        expect="Most lines carry a valid ;IMU segment and |accel| is about 1 g.",
        run=_segment_reaches_host,
    ),
    BenchTest(
        ac="e2e.2", title="Readings respond to real motion",
        criterion="Move the robot -> accel/gyro visibly change (sheet row)",
        setup="IMU connected. Be ready to move the board for about 8 s.",
        expect="Peak gyro above 20 deg/s while you move it.",
        run=_responds_to_motion,
    ),
    BenchTest(
        ac="1i.2", key="1i.2-orientation",
        title="Accel tracks gravity's direction, not just magnitude",
        criterion="Firmware README documents the axis convention "
                  "(bench evidence that the reported axes behave as documented)",
        setup="IMU connected. You will turn the breakout upside down and hold it.",
        expect=f"More than {INVERTED_SAMPLES} samples read accel-Z below -3 while inverted.",
        run=_accel_tracks_gravity_direction,
    ),
    BenchTest(
        ac="1e.4", title="GUI displays the IMU",
        criterion="joint_telemetry.py parses the IMU segment ... the GUI shows it",
        setup="IMU connected and the board booted with it attached.",
        expect="Live values, state = fresh, and they track board motion.",
        run=_gui_shows_imu,
    ),
    BenchTest(
        ac="1g.1", key="1g.1-stationary",
        title="Bias captured on a stationary boot",
        criterion="Gyro zero-rate bias captured at boot while stationary",
        setup="IMU connected. The board must sit still through the boot.",
        expect=f"Boot logs a capture and resting gyro stays under {RESTING_GYRO_DPS} deg/s.",
        run=lambda port, **_: _calibration_boot(port, moving=False),
        needs_cal_reset=True,
    ),
    BenchTest(
        ac="1g.1", key="1g.1-moving",
        title="Moving boot is not saved as bias (negative control)",
        criterion="the moving-boot control does not persist motion as calibration bias",
        setup="IMU connected. Move the board continuously through the whole boot — "
              "the capture window is about one second and rejection is on max-min.",
        expect=f"No capture is stored: spread exceeds {IMU_CAL_MAX_SPREAD_DPS} deg/s "
               "so the firmware refuses it.",
        run=lambda port, **_: _calibration_boot(port, moving=True),
        needs_cal_reset=True,
    ),
    BenchTest(
        ac="1g.4", title="Stored bias is reused across reboots",
        criterion="a valid stored gyro bias is loaded and applied on subsequent boots "
                  "without performing another calibration capture",
        setup="IMU connected, board stationary. Run the stationary 1g.1 first so a "
              "bias exists.",
        expect="Second boot logs 'loaded from EEPROM' and resting gyro stays near zero.",
        run=_bias_survives_reboot,
    ),
    BenchTest(
        ac="1b.5", title="Absent sensor does not crash or stall the loop",
        criterion="After logging the LSM6DSO initialisation failure and setting "
                  "imu_valid=0, gait control and telemetry continue without a crash or stall",
        setup="UNPLUG the IMU before running this one.",
        expect="Boot logs the failure, reaches 'Krabby Ready', and telemetry holds its "
               "50 ms cadence.",
        run=_survives_absent_sensor,
    ),
    BenchTest(
        ac="1c.4", title="Acquisition does not change loop timing",
        criterion="The LSM6DSO acquisition causes no measurable change to gait-loop timing",
        setup="Start with the IMU CONNECTED; you will be asked to unplug it midway.",
        expect=f"Mean tick interval differs by under {TIMING_TOLERANCE_MS:.0f} ms "
               "between the two cases.",
        run=_timing_unchanged,
    ),
]
