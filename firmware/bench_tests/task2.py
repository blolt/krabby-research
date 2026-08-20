"""Task 2 acceptance criteria — OLED status display and actuator disconnect handling.

Composed from the atomic checks in `checks.py`. Criterion text is quoted from the
review spec so the operator sees what is being claimed.

Much of this task is a rendered image, which no script can judge. Those criteria
appear as guided visual confirmations: the harness puts the hardware into a known
state, tells the operator exactly what should be on the panel, and records their
answer. The parts that *are* measurable — filtered position on the wire,
diagnostics continuing to update, refresh cost — are measured.
"""
from __future__ import annotations

from firmware.bench_tests import checks, mcu
from firmware.bench_tests.harness import BenchTest, Result


TELEMETRY_INTERVAL_MS = 50.0     # TELEMETRY_INTERVAL_MS in src/telemetry.h
OLED_REDRAW_INTERVAL_MS = 250.0  # OLED_REDRAW_INTERVAL_MILLISECONDS in arduino.ino
STATUS_LED_PIN = 40              # STATUS_LED_PIN in board_pins.h
TIMING_TOLERANCE_MS = 5.0
DEADLINE_SAMPLE_LINES = 520      # 2h.1 asks for at least 500 intervals per condition
# Telemetry fires on elapsed >= 50 ms, so a healthy board sits near 51 and a
# threshold of 50 would call half a passing run late. Past 1.5x the interval an
# entire slot was skipped, which is the failure the criterion is about.
SKIPPED_SLOT_MS = TELEMETRY_INTERVAL_MS * 1.5
STALL_FACTOR = 4
JOG_PWM = 200                    # matches the GUI's jog magnitude
PROBE_PWM = 50                   # ACTUATOR_ATTACHMENT_DEFAULT_LIMITS.probePwm

# Default channel for single-actuator tests. Override with --joint: which joints
# actually have motors attached varies by bench setup, and driving an empty
# channel proves nothing.
TEST_JOINT = "FLHY"


def _confirm(question: str) -> Result:
    answer = input(f"     {question} [y/N] > ").strip().lower()
    ok = answer.startswith("y")
    return Result(ok, "operator confirmed" if ok else "operator did not confirm")


def _visual(instructions: list, question: str):
    """A criterion the panel answers, not the wire. State the setup, then ask."""
    def run(**_) -> Result:
        for line in instructions:
            print(f"     {line}")
        return _confirm(question)
    return run


def _visual_while_jogging(default_joint: str, pwm: int, instructions: list, question: str):
    """Hold an actuator in a known drive state while the operator reads the panel."""
    def run(port: str, joint: str = "", **_) -> Result:
        joint = joint or default_joint
        with mcu.open_port(port) as ser:
            mcu.collect(ser, 2)
            mcu.jog(ser, joint, pwm)
            for line in instructions:
                print(f"     {line}")
            answer = input(f"     {question} [y/N] > ").strip().lower()
            mcu.hold_all(ser)
        ok = answer.startswith("y")
        return Result(ok, f"{joint} driven at pwm {pwm}; "
                          + ("operator confirmed" if ok else "operator did not confirm"))
    return run


# ------------------------------------------------------------- measured criteria
def _display_init_failure_survivable(port: str, **_) -> Result:
    boot = checks.boot_log(port)
    # Without this the test passes on a healthy board with the panel plugged in,
    # which is the one state that proves nothing about surviving a failure.
    if not boot.values["oled_failed"]:
        return Result(False, "boot logged no OLED initialisation failure — the panel is "
                             "still connected, so this run proves nothing about "
                             "surviving one")
    timing = checks.tick_timing(port, lines=200)
    if timing.ok is False:
        return Result(False, f"{boot.text}\n{timing.text}")
    stall_limit = STALL_FACTOR * TELEMETRY_INTERVAL_MS
    ok = bool(boot.values["ready"]) and timing.values["max"] <= stall_limit
    return Result(ok, f"{boot.text}\n{timing.text}\n"
                      f"reached 'Krabby Ready': {bool(boot.values['ready'])}; "
                      f"a stall would exceed {stall_limit:.0f} ms")


def _position_is_filtered(port: str, joint: str = "", **_) -> Result:
    """A pass needs a channel latched nan, not one flickering.

    Intermittent nan on a connected channel is the validity detector tripping on
    ordinary pot noise, which is a calibration problem rather than evidence that
    filtering works. Accepting flicker here would let a miscalibrated threshold
    masquerade as a working filter.
    """
    joint = joint or TEST_JOINT
    m = checks.filtering_rate(port)
    if m.ok is False:
        return Result(False, m.text)
    # A bench with empty actuator slots always has *some* latched channel, so
    # accepting any of them would pass without the operator touching anything.
    latched = m.values["latched"]
    if joint not in str(latched):
        return Result(False, f"{m.text}\n\n{joint} is not among the latched channels "
                             f"({latched or 'none'}). The criterion is about the channel "
                             "under test, not about any channel on the board.")
    flickering = m.values["flickering"]
    if not latched:
        detail = f"{m.text}\n\nno channel is latched disconnected."
        if flickering:
            detail += (f"\n{m.values['flickering_count']} channel(s) flicker "
                       f"({flickering}) — that is the idle-jitter threshold tripping on "
                       "noise, not a disconnect. Unplug a motor and jog it above the "
                       f"probe PWM ({PROBE_PWM}) so current evidence can latch.")
        return Result(False, detail)
    return Result(True, f"{m.text}\n\nlatched disconnected: {latched}"
                        + (f"\nalso flickering (worth calibrating): {flickering}"
                           if flickering else ""))


def _diagnostics_keep_streaming(port: str, **_) -> Result:
    m = checks.diagnostics_survive_disconnect(port)
    if m.values.get("filtered", 0) == 0:
        return Result(False, f"{m.text}\n(needs at least one filtered channel — see 2f.1)")
    return Result(bool(m.values["all_diagnostics_live"]),
                  f"{m.text}\n(pass requires pot and current to keep changing on a "
                  "filtered channel — position is filtered, diagnostics are not)")


def _disconnect_latches(port: str, joint: str = "", **_) -> Result:
    """Latch the channel and watch it stay latched, without reconnecting.

    Attachment state is RAM-only and init() resets it, so opening a second serial
    session re-asserts DTR, reboots the board and erases the latch. A criterion
    about state that "persists while idle" cannot be read across a reconnect, so
    the drive and the idle observation share one session.
    """
    joint = joint or TEST_JOINT
    print(f"     unplug {joint}'s motor, then this will jog it above the probe PWM")
    input("     press Enter once the motor is disconnected > ")
    m = checks.jog_then_observe_idle(port, joint, JOG_PWM)
    if m.ok is False:
        return Result(False, m.text)

    if not m.values["commanded_samples"]:
        return Result(False, f"{m.text}\n\nthe jog never reached {joint} — no line "
                             "reported the drive, so nothing was measured")
    latched = bool(m.values["latched_while_driven"])
    retained = bool(m.values["retained_while_idle"])
    return Result(latched and retained,
                  f"{m.text}\n\n"
                  f"latched under drive : {latched}\n"
                  f"retained while idle : {retained}\n"
                  "(both are required: below-floor driven current must latch, and the "
                  "verdict must survive idle samples that carry no evidence)")


def _refresh_does_not_disturb_timing(port: str, joint: str = "", **_) -> Result:
    """Four conditions: panel off vs forced full transfer, each idle and driving.

    Normal operation shows neither extreme — an unchanged model transfers nothing,
    so a still robot exercises almost no OLED work. The forced mode makes every
    eligible refresh do a full transfer, which is the worst case partial-page
    updates exist to survive.

    Two failures are distinct and both disqualify: a repeatable rise in the mean,
    and any single tick past the deadline. A loop can hold its average and still
    miss a deadline, and only the second matters to a gait.
    """
    driven = joint or TEST_JOINT
    conditions = [
        ("panel off,  idle   ", mcu.OLED_OFF, ""),
        ("panel off,  driving", mcu.OLED_OFF, driven),
        ("forced,     idle   ", mcu.OLED_FORCED, ""),
        ("forced,     driving", mcu.OLED_FORCED, driven),
    ]
    print(f"     driving {driven}; four conditions of "
          f"{DEADLINE_SAMPLE_LINES} ticks each")

    measured = {}
    for label, oled, drive in conditions:
        m = checks.deadline_timing(port, lines=DEADLINE_SAMPLE_LINES,
                                   oled=oled, joint=drive,
                                   deadline_ms=SKIPPED_SLOT_MS)
        if m.ok is False:
            return Result(False, f"{label}: {m.text}")
        measured[label] = m
        print(f"       {label}  {m.text}")

    late = sum(m.values["late"] for m in measured.values())
    off_idle = measured["panel off,  idle   "].values["mean"]
    worst_rise = max(m.values["mean"] - off_idle for m in measured.values())
    detail = "\n".join(f"{label}  {m.text}" for label, m in measured.items())
    detail += (f"\n\nworst mean rise vs panel-off idle: {worst_rise:+.2f} ms "
               f"(pass under {TIMING_TOLERANCE_MS:.0f} ms)"
               f"\nticks that skipped a {TELEMETRY_INTERVAL_MS:.0f} ms slot entirely "
               f"(gap over {SKIPPED_SLOT_MS:.0f} ms): {late} "
               "(pass requires 0)")
    return Result(late == 0 and abs(worst_rise) < TIMING_TOLERANCE_MS, detail)


TESTS = [
    # ---- display comes up, and survives not coming up
    BenchTest(
        ac="2a.1", title="Panel is on the shared Qwiic bus",
        criterion='SparkFun Qwiic OLED 1.3" (default I2C 0x3D) daisy-chained onto the '
                  "primary Mega's Qwiic->Dupont bus",
        setup="Visual inspection of the harness.",
        expect="The panel is chained onto the same bus as the IMU, not a separate one.",
        run=_visual(["trace the panel's Qwiic lead back to the bus the IMU shares"],
                    "is the OLED daisy-chained onto that same bus?"),
        manual=True,
    ),
    BenchTest(
        ac="2a.2", title="Display init failure does not crash or hang",
        criterion="When OLED initialization fails, the firmware does not crash or hang",
        setup="UNPLUG the OLED, leaving the IMU connected.",
        expect="Boot reaches 'Krabby Ready' and telemetry holds its 50 ms cadence.",
        run=_display_init_failure_survivable,
    ),
    BenchTest(
        ac="2a.3", title="Control continues without the display",
        criterion="After OLED initialization fails, firmware control continues without "
                  "the display",
        setup="OLED still unplugged.",
        expect="Jogging still drives the actuator and its telemetry still changes.",
        run=lambda port, joint="", **_: (
            lambda m: Result(m.values.get("distinct_pot", 0) > 1 or m.values.get("driven_samples", 0) > 0,
                             f"{m.text}\n(pass requires the jog to take effect with no panel present)")
        )(checks.jog_and_watch(port, joint or TEST_JOINT, JOG_PWM)),
    ),

    # ---- what is drawn
    BenchTest(
        ac="2b.1", title="Body split into three controller thirds",
        criterion="A stylized krab is rendered with the body split into three "
                  "controller thirds (front/left/right)",
        setup="OLED reconnected and the board rebooted.",
        expect="Three distinguishable body regions, each filling independently.",
        run=_visual(["look at the krab body on the panel"],
                    "are three separate controller thirds visible?"),
        manual=True,
    ),
    BenchTest(
        ac="2b.2", title="Six legs with three joints each",
        criterion="A stylized krab is rendered with six legs/hips",
        setup="OLED connected.",
        expect="Six legs, three glyphs each, symmetric about the body.",
        run=_visual(["count the legs and the glyphs per leg"],
                    "are there six legs with three glyphs each?"),
        manual=True,
    ),
    BenchTest(
        ac="2b.3", title="Two battery bars on the rear",
        criterion="A stylized krab is rendered with battery as two stacked bars on the "
                  "rear (placeholder until Task 3)",
        setup="OLED connected.",
        expect="Two outlined bars. Empty is correct until battery data exists.",
        run=_visual(["look at the rear of the krab"],
                    "are two battery bar outlines visible?"),
        manual=True,
    ),
    BenchTest(
        ac="2c.1", title="Each controller shown present or missing independently",
        criterion="With the display-owning controller remaining FRONT, independently show "
                  "FRONT, LEFT, and RIGHT as active or missing according to each "
                  "controller's own presence.",
        setup="Whatever controllers are actually present. A single leader with no "
              "followers is a valid case and exercises the criterion directly.",
        expect="Each third reflects its own controller's presence: the leader's third "
               "reads active, and a controller that is absent reads missing. With "
               "followers attached, powering one off flips only its third.",
        run=_visual(["look at the three body thirds on the panel",
                     "the leader's own third should read active",
                     "any controller not present should read missing",
                     "if you have followers attached, power one off and watch only "
                     "that third change"],
                    "does each third reflect its own controller's presence?"),
        manual=True,
    ),

    # ---- glyphs, each with the channel held in the matching drive state
    BenchTest(
        ac="2d.2", title="Extending renders an upward triangle",
        criterion="When an actuator is extending, render a filled upward-pointing "
                  "triangle at its corresponding glyph position.",
        setup=f"OLED connected. {TEST_JOINT} will be driven to extend while you look.",
        expect=f"{TEST_JOINT}'s glyph is a filled upward triangle.",
        run=_visual_while_jogging(TEST_JOINT, JOG_PWM,
                                 [f"{TEST_JOINT} is now extending — find its glyph"],
                                 "is it a filled upward triangle?"),
    ),
    BenchTest(
        ac="2d.3", title="Retracting renders a downward triangle",
        criterion="When an actuator is retracting, render a filled downward-pointing "
                  "triangle at its corresponding glyph position.",
        setup=f"OLED connected. {TEST_JOINT} will be driven to retract.",
        expect=f"{TEST_JOINT}'s glyph is a filled downward triangle.",
        run=_visual_while_jogging(TEST_JOINT, -JOG_PWM,
                                 [f"{TEST_JOINT} is now retracting — find its glyph"],
                                 "is it a filled downward triangle?"),
    ),
    BenchTest(
        ac="2d.4", title="Holding renders a filled dot",
        criterion="When a connected actuator's applied PWM is within the holding range "
                  "(-deadband < PWM < deadband), render a filled dot at its "
                  "corresponding glyph position.",
        setup="OLED connected, nothing being jogged.",
        expect="Connected idle actuators show filled dots.",
        run=_visual(["nothing is being driven; look at a connected actuator's glyph"],
                    "is it a filled dot?"),
    ),
    BenchTest(
        ac="2d.5", title="Disconnected renders a diagonal cross",
        criterion="When an actuator is disconnected, render a diagonal cross at its "
                  "corresponding glyph position.",
        setup="OLED connected and at least one actuator unplugged and latched "
              "disconnected (run 2e.2 first).",
        expect="The unplugged channel's glyph is a diagonal cross.",
        run=_visual(["find the glyph for the channel you unplugged"],
                    "is it a diagonal cross?"),
    ),
    BenchTest(
        ac="2d.6", title="All four glyphs are visually distinct",
        criterion="Render extend, retract, holding, and disconnected as four visually "
                  "distinct glyphs on the 1-bit panel.",
        setup="Having seen all four states across the previous tests.",
        expect="Each of the four is identifiable without reference to the others.",
        run=_visual(["recall the four glyph shapes you have just seen"],
                    "were all four clearly distinguishable?"),
        manual=True,
    ),

    # ---- disconnect detection and filtering
    BenchTest(
        ac="2e.2", title="Driven-current evidence latches a channel disconnected",
        criterion="When driven-current evidence latches a channel as disconnected, report "
                  "that channel as disconnected through isConnected(), telemetry, and the "
                  "OLED; retain that state while idle until new driven-current evidence "
                  "confirms attachment.",
        setup=f"Unplug {TEST_JOINT}'s motor. Leave the pot connected if you can — that "
              "isolates the current-sense path.",
        expect=f"After jogging above PWM {PROBE_PWM}, {TEST_JOINT} reports nan position.",
        run=_disconnect_latches,
    ),
    BenchTest(
        ac="2f.1", title="Filtered position replaces raw ADC noise",
        criterion="Filter each actuator's position through attachment and "
                  "position-validity state so a disconnected or floating channel reports "
                  "invalid, or retains its last valid position, instead of reporting raw "
                  "ADC noise.",
        setup="At least one channel latched disconnected (run 2e.2 first).",
        expect="That channel's normalized position reads nan, not a drifting number.",
        run=_position_is_filtered,
    ),
    BenchTest(
        ac="2f.2", title="Disconnection wins over motion on the panel",
        criterion="When position or attachment filtering marks an actuator disconnected, "
                  "render a cross at its corresponding OLED position instead of a holding "
                  "or motion glyph.",
        setup="A latched-disconnected channel, OLED connected.",
        expect="Jogging the disconnected channel still shows a cross, never a triangle.",
        run=_visual_while_jogging(TEST_JOINT, JOG_PWM,
                                 [f"{TEST_JOINT} is disconnected and now being driven"],
                                 "does its glyph stay a cross rather than a triangle?"),
    ),
    BenchTest(
        ac="2f.3", title="Diagnostics keep updating while position is filtered",
        criterion="When filtering marks an actuator disconnected, report its normalized "
                  "position as nan rather than as a changing valid position, while "
                  "preserving the channel's diagnostic telemetry fields.",
        setup="At least one channel latched disconnected.",
        expect="Position is nan while pot and current keep changing on that channel.",
        run=_diagnostics_keep_streaming,
    ),

    # ---- status LED
    BenchTest(
        ac="2g.1", title="Status LED on a free GPIO",
        criterion="A discrete status LED is wired to a free GPIO.",
        setup=f"LED wired to D{STATUS_LED_PIN} with a series resistor.",
        expect=f"The LED is on D{STATUS_LED_PIN}; the pin-collision test already proves "
               "that pin is free across pin revisions.",
        run=_visual([f"check which pin the LED's anode lead goes to"],
                    f"is the status LED on D{STATUS_LED_PIN}?"),
        manual=True,
    ),
    BenchTest(
        ac="2g.2", title="LED lights on a disconnected motor",
        criterion="The status LED lights or blinks when a motor is disconnected.",
        setup="A latched-disconnected channel, LED wired.",
        expect="LED lit while a channel is disconnected, clear after reconnecting "
               "and re-latching attached.",
        run=_visual(["look at the status LED with a channel latched disconnected",
                     "then reconnect the motor, jog it, and watch the LED"],
                    "did the LED light on disconnect and clear on reconnect?"),
    ),
    BenchTest(
        ac="2g.3", title="Same LED and GPIO available to the power task",
        criterion="The same physical status LED and GPIO are reused by Task 4 for "
                  "low-battery indication.",
        setup="No hardware change — this is a shared-pin claim.",
        expect=f"One LED on D{STATUS_LED_PIN}, with no second indicator wired for the "
               "power task to use.",
        run=_visual([f"confirm there is a single status LED on D{STATUS_LED_PIN}"],
                    "is this the only status LED, so the power task reuses it?"),
        manual=True,
    ),

    # ---- refresh cost
    BenchTest(
        ac="2h.1", title="Refresh does not disturb loop timing",
        criterion="OLED refresh does not measurably impact gait-loop timing",
        setup="OLED and IMU both connected, on the assembled 400 kHz bus. The test "
              "drives the panel itself; do not touch the board while it runs.",
        expect=f"No tick past the {TELEMETRY_INTERVAL_MS:.0f} ms deadline in any of the "
               f"four conditions, and no mean rise beyond {TIMING_TOLERANCE_MS:.0f} ms.",
        run=_refresh_does_not_disturb_timing,
    ),
]
