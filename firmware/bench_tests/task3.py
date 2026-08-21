"""Power-bus instrumentation criteria — external shunt and two INA228 monitors.

Almost all of this task is high-current assembly, which no script can judge: where
a fuse sits in the loom, whether a Kelvin sense lands on the right terminal, whether
a 15 mOhm resistor was actually removed. Those appear as guided inspections that
state exactly what to look for.

What software can add is the reverse direction — reading back what the firmware
believes about the bus and letting the operator compare it against a meter. A wiring
error that inspection misses often shows up as a sign flip or a factor-of-two in the
reported current.

Safety comes first here and the harness does not enforce it: make and break every
connection with the pack protection open.
"""
from __future__ import annotations

from firmware.bench_tests import checks, mcu
from firmware.bench_tests.harness import BenchTest, Result

# Swapped from spec §3: the desolder landed on the already-A0-bridged board,
# and Pack is whichever board carries the external shunt, not whichever
# address it answers on.
PACK_ADDRESS = "0x41"
MIDPOINT_ADDRESS = "0x40"
SHUNT_RATING = "200 A / 75 mV"
PACK_FUSE = "150 A"
ONBOARD_SHUNT = "15 mOhm"


def _confirm(question: str) -> Result:
    answer = input(f"     {question} [y/N] > ").strip().lower()
    ok = answer.startswith("y")
    return Result(ok, "operator confirmed" if ok else "operator did not confirm")


def _inspect(instructions: list, question: str):
    def run(**_) -> Result:
        for line in instructions:
            print(f"     {line}")
        return _confirm(question)
    return run


def _measured_against_meter(prompt: str, question: str):
    """Show what the firmware reports, then ask the operator to compare a meter.

    The comparison is the point: agreement in magnitude and sign is what catches a
    reversed Kelvin sense or a wrong shunt constant, and neither is visible from
    the wire alone.
    """
    def run(port: str, **_) -> Result:
        print(f"     {prompt}")
        boot = checks.boot_log(port, seconds=10.0)
        print("     firmware boot output:")
        for line in boot.text.splitlines():
            print(f"     {line}")
        report = checks.battery_report(port)
        for line in report.text.splitlines():
            print(f"     {line}")
        return _confirm(question)
    return run


TESTS = [
    # ---- safety and assembly, in the order the loom is built
    BenchTest(
        ac="3b.2", title="Safety procedure was followed during assembly",
        criterion="Battery-safety section is followed",
        setup="Retrospective: how the loom was actually built.",
        expect="Every connection was made and broken with pack protection open.",
        run=_inspect(["recall how the bus was assembled"],
                     "was pack protection open for every make and break?"),
        manual=True,
    ),
    BenchTest(
        ac="3b.3", title="Pack fuse is the first element on Pack+",
        criterion=f"The {PACK_FUSE} fuse/breaker is the first element on Pack+, closest to "
                  "the battery positive terminal",
        setup="Trace the positive lead from the battery terminal outward.",
        expect=f"The {PACK_FUSE} fuse or breaker is the first thing in that path — "
               "nothing else between it and the terminal.",
        run=_inspect([f"follow Pack+ from the battery post to the first component"],
                     f"is the {PACK_FUSE} protection the very first element?"),
        manual=True,
    ),
    BenchTest(
        ac="3c.1", title="Shunt is inline downstream of the fuse",
        criterion=f"{SHUNT_RATING} external shunt is installed inline downstream of the fuse",
        setup="Trace from the fuse toward the load.",
        expect=f"The {SHUNT_RATING} shunt carries full pack current, after the fuse.",
        run=_inspect(["check the shunt's position relative to the fuse and the load"],
                     "is the shunt inline, downstream of the fuse?"),
        manual=True,
    ),
    BenchTest(
        ac="3c.2", title="Kelvin sense lands on the shunt sense terminals",
        criterion=f"Kelvin sense is connected to the Pack INA228 ({PACK_ADDRESS})",
        setup="Inspect the two small sense screws on the shunt.",
        expect="IN+ and IN- come from the shunt's dedicated sense terminals, not from "
               "the main current-carrying bolts.",
        run=_inspect(["check where the INA228 IN+/IN- leads attach on the shunt"],
                     "are both on the Kelvin sense terminals rather than the main bolts?"),
        manual=True,
    ),
    BenchTest(
        ac="3c.3", title="Pack VBUS senses the load side of the shunt",
        criterion="The Pack INA228 VBUS input is connected to the external shunt's "
                  "octopus/load-side node.",
        setup="Trace the Pack monitor's VBUS lead.",
        expect="VBUS is on the load side, so it reads bus voltage after the shunt drop.",
        run=_inspect(["find which side of the shunt the VBUS lead taps"],
                     "is VBUS on the load-side node?"),
        manual=True,
    ),
    BenchTest(
        ac="3d.1", title="Midpoint monitor answers at its own address",
        criterion=f"Midpoint INA228 is at {MIDPOINT_ADDRESS}",
        setup="Both monitors on the bus, board powered.",
        expect=f"Two distinct devices respond — {PACK_ADDRESS} and {MIDPOINT_ADDRESS}.",
        run=lambda port, **_: (
            lambda m: Result(m.values.get("monitors", 0) >= 2,
                             f"{m.text}\n(pass requires both monitors responding; one "
                             "address answering twice means the A0 jumper is unset)")
        )(checks.battery_report(port)),
    ),
    BenchTest(
        ac="3d.2", title="A0 jumper selects the second address",
        criterion=f"One INA228's A0 solder jumper is bridged so the two answer at "
                  f"distinct addresses. Spec §3 straps the Midpoint to {PACK_ADDRESS}; "
                  f"this build straps the Pack instead, because the onboard-shunt "
                  f"desolder was done on the already-bridged board.",
        setup="Inspect the Pack board's A0 pads.",
        expect=f"A0 is bridged with solder on the Pack board, moving it off the default "
               f"to {PACK_ADDRESS}. The Midpoint is unmodified at the default "
               f"{MIDPOINT_ADDRESS}.",
        run=_inspect([f"look at the A0 solder jumper on the PACK board ({PACK_ADDRESS})",
                      f"the Midpoint ({MIDPOINT_ADDRESS}) should be unbridged — it is the default",
                      "",
                      "Spec §3 has these the other way round. Record the swap as a",
                      "deviation against 3c/3d/3h.1/3h.2, not as a failure."],
                     "is A0 bridged on the Pack board and unbridged on the Midpoint?"),
        manual=True,
    ),
    BenchTest(
        ac="3d.3", title="Midpoint VBUS senses the series junction",
        criterion="The Midpoint INA228 VBUS input senses the junction between the two "
                  "series-connected batteries.",
        setup="Trace the Midpoint VBUS lead. This node is live at battery voltage.",
        expect="VBUS taps the junction between the two packs, so per-battery voltage "
               "can be derived by subtraction.",
        run=_inspect(["find where the Midpoint VBUS lead attaches",
                      "treat that node as a live battery terminal"],
                     "does VBUS sense the series junction?"),
        manual=True,
    ),
    BenchTest(
        ac="3d.4", title="Midpoint current inputs are tied off",
        criterion="The Midpoint INA228's unused IN+ and IN- current-sense inputs are both "
                  "connected to Pack-.",
        setup="Inspect the Midpoint board's IN+/IN- terminals.",
        expect="Both are tied to Pack-, so the unused current channel reads a defined "
               "zero rather than floating.",
        run=_inspect(["check both IN+ and IN- on the Midpoint board"],
                     "are both tied to Pack-?"),
        manual=True,
    ),
    BenchTest(
        ac="3e.1", title="Onboard shunts removed from both monitors",
        criterion=f"Both INA228 onboard {ONBOARD_SHUNT} shunt resistors are desoldered and "
                  "removed, disabling the onboard shunt paths.",
        setup="Inspect the shunt footprint on both boards.",
        expect="Physically absent on the Pack board. The Midpoint's is inert once "
               "3d.4 ties its IN+/IN- to Pack-, so removing it there is defensive "
               "rather than electrical.",
        run=_inspect(
            [f"Pack ({PACK_ADDRESS}): confirm the {ONBOARD_SHUNT} resistor is gone. Its IN+/IN- go",
             "  to the external shunt's Kelvin taps, so an onboard resistor between them",
             "  sits in parallel with the external shunt and conducts ~1 A of the sense",
             "  current at full scale. Removal is mandatory.",
             "",
             f"Midpoint ({MIDPOINT_ADDRESS}): the same {ONBOARD_SHUNT} bridges two pins that 3d.4 ties",
             "  to the same node, so it has zero volts across it and cannot conduct.",
             "  The spec asks for removal anyway, as insurance against a loose tie and",
             "  so the two boards stay interchangeable.",
             "",
             "Answer for BOTH. If only the Pack board is done, that is a deliberate",
             "deviation to record against 3e.1, not a pass."],
            "is the resistor removed on both boards?"),
        manual=True,
    ),

    # ---- calibration, which is where software and the meter meet
    BenchTest(
        ac="3i.1", title="Shunt constant captured against a known current",
        criterion="The Pack shunt calibration constant is captured against a known signed "
                  "current",
        setup="A known load drawing a measured current, with a clamp meter or the "
              "supply's own readout for reference. Try both directions if you can.",
        expect="Reported current agrees with the meter in magnitude and sign. A sign "
               "flip means IN+/IN- are swapped; a constant ratio means the shunt "
               "constant is wrong.",
        run=_measured_against_meter(
            "apply a known load and read your meter",
            "does reported current match the meter in magnitude and sign?"),
    ),
    BenchTest(
        ac="3i.2", title="Pack VBUS offset trimmed",
        criterion=f"Pack INA228 VBUS offset trim is captured",
        setup="Pack at rest, a DMM across the same node the Pack monitor senses.",
        expect="Reported pack voltage matches the DMM once the offset is trimmed.",
        run=_measured_against_meter(
            "measure pack voltage with a DMM at the Pack VBUS node",
            "does reported pack voltage match the DMM?"),
    ),
    BenchTest(
        ac="3i.3", title="Midpoint VBUS offset trimmed",
        criterion="Midpoint INA228 VBUS offset trim is captured",
        setup="DMM across the series junction to Pack-.",
        expect="Reported midpoint voltage matches the DMM, and the derived per-battery "
               "split is plausible for two packs in series.",
        run=_measured_against_meter(
            "measure the series junction with a DMM",
            "does reported midpoint voltage match, and the derived split look right?"),
    ),
]
