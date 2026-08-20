"""Interactive calibration for the detector thresholds.

The shipped values are provisional — nobody measured them. These routines gather
the evidence the acceptance criteria ask for and print the constants they imply,
along with the separation margin behind each, so a number can be defended rather
than guessed.

    python3 -m firmware.bench_tests calibrate identify --port PORT
    python3 -m firmware.bench_tests calibrate current --port PORT --joint FRHY
    python3 -m firmware.bench_tests calibrate pot     --port PORT --joints FRHY,FRKL
    python3 -m firmware.bench_tests calibrate debounce --port PORT --joint FRHY
    python3 -m firmware.bench_tests calibrate wiper   --port PORT --joint FLHY

**What this can and cannot see.** The wire carries the smoothed averages, while
the detectors read the raw pins at loop rate — roughly twenty times faster. So
every figure here is the mean behaviour, and per-sample excursions the detector
acts on are invisible. Treat recommended thresholds as a starting point with the
margin stated, not a final answer: a floor that looks generous against smoothed
current can still sit inside the per-sample spread.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Dict, List

from firmware.bench_tests import mcu

PWM_SWEEP = [50, 75, 100, 150, 200, 255]
SAMPLES_PER_STEP = 25
SETTLE_LINES = 6            # discard while the EMA catches up after a PWM change
REST_LINES = 300
JOINTS_PER_BOARD = 6        # two legs; a full robot's 18 span three boards


def _prompt(message: str) -> None:
    input(f"\n  {message}\n  press Enter when ready > ")


def _drive_and_measure(port: str, joint: str, pwm: int) -> Dict[str, float]:
    """Hold one PWM level and report that channel's current and position spread."""
    with mcu.open_port(port) as ser:
        mcu.jog(ser, joint, pwm)
        mcu.collect(ser, SETTLE_LINES)
        samples = mcu.collect(ser, SAMPLES_PER_STEP)
        mcu.hold_all(ser)
    rows = [j for s in samples for j in mcu.joints_of(s) if j.name == joint]
    if not rows:
        return {}
    currents = [j.current for j in rows]
    pots = [j.pot for j in rows]
    return {
        "pwm": pwm,
        "n": len(rows),
        "cur_mean": statistics.mean(currents),
        "cur_min": min(currents),
        "cur_max": max(currents),
        "pot_span": max(pots) - min(pots),
    }


# --------------------------------------------------------------- who is plugged in
IDENT_PWM = 200             # linear actuators need real drive before anything moves
IDENT_LINES = 16            # ~0.8 s at the 50 ms telemetry tick
IDENT_MOVE_COUNTS = 8       # pot displacement that is unambiguously drive, not noise
# ACTUATOR_ATTACHMENT_DEFAULT_LIMITS.currentPresentFloor. The firmware calls a
# channel attached at this reading, so anything stricter here would disagree with
# the detector this routine exists to inform.
IDENT_CURRENT_FLOOR = 1


def _median(values: List[float]) -> float:
    return statistics.median(values) if values else 0.0


def _probe_channel(ser, joint: str, pwm: int) -> Dict[str, float]:
    """Drive one channel briefly and report what the pot and current did."""
    before = [j for s in mcu.collect(ser, 6) for j in mcu.joints_of(s) if j.name == joint]
    mcu.jog(ser, joint, pwm)
    during = [j for s in mcu.collect(ser, IDENT_LINES)
              for j in mcu.joints_of(s) if j.name == joint]
    mcu.hold_all(ser)
    after = [j for s in mcu.collect(ser, 6) for j in mcu.joints_of(s) if j.name == joint]
    if not (before and during and after):
        return {}
    return {
        "pot_before": _median([j.pot for j in before]),
        "pot_after": _median([j.pot for j in after]),
        "pot_travel": max(j.pot for j in during) - min(j.pot for j in during),
        "cur_idle": _median([j.current for j in before]),
        "cur_driven": _median([j.current for j in during]),
    }


def identify(port: str, only: List[str] = ()) -> int:
    """Say which channels actually have an actuator on them, by driving each one.

    Nothing at rest distinguishes an empty channel from a populated one — that is
    the whole difficulty. Motion does: a pot that tracks an applied drive is
    attached and its wiper works, and no amount of floating-pin coincidence
    reproduces that.

    Three outcomes, and the middle one is the interesting failure. A channel that
    draws current but whose pot does not move has a motor on it and a dead
    position signal — a wiper off its track, or a broken pot lead. That reads
    identically to 'no motor' from telemetry at rest, which is exactly how it
    escapes notice.
    """
    print("\n=== which channels have an actuator ===")
    print("  Each channel is driven briefly, then driven back. Keep clear of them.")
    with mcu.open_port(port) as ser:
        names = sorted({j.name for s in mcu.collect(ser, 4) for j in mcu.joints_of(s)})
    if not names:
        print("  no joint telemetry")
        return 1
    targets = [n.upper() for n in only] or names
    unknown = [n for n in targets if n not in names]
    if unknown:
        print(f"  not present in telemetry: {', '.join(unknown)}")
        return 1

    print(f"\n  {len(names)} channel(s) reporting; probing {len(targets)}")
    _prompt("Confirm nothing is obstructing the actuators.")

    findings = {}
    with mcu.open_port(port) as ser:
        for joint in targets:
            print(f"    {joint:<6} ", end="", flush=True)
            m = _probe_channel(ser, joint, IDENT_PWM)
            # An actuator already against an end stop cannot move further one way,
            # so a still pot is only meaningful once both directions are tried.
            if m and m["pot_travel"] < IDENT_MOVE_COUNTS:
                m = _probe_channel(ser, joint, -IDENT_PWM) or m
            else:
                _probe_channel(ser, joint, -IDENT_PWM)   # return toward the start
            if not m:
                print("no telemetry")
                continue
            findings[joint] = m
            moved = m["pot_travel"] >= IDENT_MOVE_COUNTS
            drew = m["cur_driven"] >= IDENT_CURRENT_FLOOR
            verdict = ("ATTACHED" if moved else
                       "MOTOR, DEAD POT" if drew else "empty")
            print(f"pot travel {m['pot_travel']:>4}   current "
                  f"{m['cur_idle']:.0f}->{m['cur_driven']:.0f}   {verdict}")

    attached = [n for n, m in findings.items() if m["pot_travel"] >= IDENT_MOVE_COUNTS]
    dead_pot = [n for n, m in findings.items()
                if m["pot_travel"] < IDENT_MOVE_COUNTS
                and m["cur_driven"] >= IDENT_CURRENT_FLOOR]
    print(f"\n  attached with a working pot : {', '.join(attached) or '(none)'}")
    if dead_pot:
        print(f"  motor present, pot not moving: {', '.join(dead_pot)}")
        print("    Current says the motor is wired and driven; the pot says it never")
        print("    moved. Check the wiper lead before trusting any position reading")
        print("    or attachment threshold on these channels.")
    if attached:
        print(f"\n  pass this to the other routines:")
        print(f"    --joints {','.join(attached)}")
    return 0 if attached else 1


# --------------------------------------------------------------- current floor
def current(port: str, joint: str) -> int:
    """Sweep PWM with the motor attached, then unplugged, and compare.

    The floor has to separate two distributions. If they overlap at every PWM the
    current-sense path is not discriminating, and no threshold will fix it — that
    is a wiring or sense-resistor finding, not a tuning one.
    """
    print(f"\n=== current floor and probe PWM — {joint} ===")
    print("  Each step drives the actuator briefly. Keep clear of it.")

    _prompt(f"Connect {joint}'s motor normally (ATTACHED).")
    attached = [r for pwm in PWM_SWEEP if (r := _drive_and_measure(port, joint, pwm))]
    for r in attached:
        print(f"    pwm {r['pwm']:>3}  current mean {r['cur_mean']:6.1f}  "
              f"range {r['cur_min']:>4}-{r['cur_max']:<4}  pot span {r['pot_span']:>4}")

    _prompt(f"Now UNPLUG {joint}'s motor, leaving everything else as it is.")
    absent = [r for pwm in PWM_SWEEP if (r := _drive_and_measure(port, joint, pwm))]
    for r in absent:
        print(f"    pwm {r['pwm']:>3}  current mean {r['cur_mean']:6.1f}  "
              f"range {r['cur_min']:>4}-{r['cur_max']:<4}")

    print("\n  separation by PWM (attached low vs absent high):")
    usable = []
    for a, b in zip(attached, absent):
        margin = a["cur_min"] - b["cur_max"]
        verdict = "clear" if margin > 0 else "OVERLAP"
        if margin > 0:
            usable.append((a["pwm"], b["cur_max"], a["cur_min"], margin))
        print(f"    pwm {a['pwm']:>3}  attached>={a['cur_min']:>4}  "
              f"absent<={b['cur_max']:<4}  margin {margin:+5.0f}   {verdict}")

    if not usable:
        print("\n  NO PWM SEPARATES THE TWO STATES.")
        print("  Attached and unplugged draw indistinguishable current at every level,")
        print("  so no floor can work. Check the current-sense wiring and the sense")
        print("  resistor value before touching thresholds.")
        return 1

    probe_pwm, absent_max, attached_min, best = min(usable, key=lambda u: u[0])
    widest = max(usable, key=lambda u: u[3])
    floor = int((absent_max + attached_min) / 2)
    print(f"\n  lowest PWM with clear separation : {probe_pwm}")
    print(f"  widest separation at PWM         : {widest[0]} (margin {widest[3]:.0f})")
    print(f"  suggested currentPresentFloor    : {floor}")
    print(f"    sits between absent max {absent_max} and attached min {attached_min}")
    print(f"  suggested probePwm               : {probe_pwm}")
    print("\n  Set these in ACTUATOR_ATTACHMENT_DEFAULT_LIMITS, reflash, then re-run 2e.2.")
    print("  Remember these are smoothed means; leave margin for per-sample spread.")
    return 0


# --------------------------------------------------------------- pot jitter
def _ask_attached(names: List[str]) -> List[str]:
    """Have the operator name the channels that actually have a pot on them.

    This cannot be inferred from telemetry. Whether a channel reads a real wiper
    or a floating pin is the very thing the validity detector is judging, so
    asking the firmware would be circular.
    """
    print(f"\n  {len(names)} channel(s) reporting: {', '.join(names)}")
    if len(names) == JOINTS_PER_BOARD:
        print(f"  ({JOINTS_PER_BOARD} is one board's two legs — a full robot's 18 span "
              "three boards)")
    answer = input("  which have an actuator attached? (comma-separated, or 'all') > ")
    answer = answer.strip()
    if not answer or answer.lower() == "all":
        return list(names)
    return [a.strip().upper() for a in answer.split(",") if a.strip()]


def _channel_stats(values: List[tuple]) -> Dict[str, float]:
    nan_rate = sum(1 for c, _ in values if not c) / len(values)
    pots = [p for _, p in values]
    deltas = sorted(abs(b - a) for a, b in zip(pots, pots[1:])) or [0]
    return {
        "nan_rate": nan_rate,
        "p50": deltas[len(deltas) // 2],
        "p95": deltas[int(len(deltas) * 0.95)],
        "p99": deltas[min(len(deltas) - 1, int(len(deltas) * 0.99))],
        "max": deltas[-1],
    }


def pot(port: str, attached: List[str] = ()) -> int:
    """Measure resting pot movement and derive the idle-jitter threshold.

    Only channels with an actuator on them inform the threshold. An unconnected
    ADC pin floats, and the sample-and-hold carries charge between conversions,
    so it reports large stable-looking excursions that have nothing to do with
    wiper noise. Pooling those in would fit the threshold to phantom data.

    The unconnected channels are still worth watching, with the verdict inverted:
    a floating pin *should* read invalid, so one that never does means the
    detector is missing a disconnected pot.
    """
    print("\n=== idle pot jitter ===")
    _prompt("Leave every attached actuator connected and completely still.")
    with mcu.open_port(port) as ser:
        samples = mcu.collect(ser, REST_LINES)
    series = defaultdict(list)
    for s in samples:
        for j in mcu.joints_of(s):
            series[j.name].append((j.connected, j.pot))
    if not series:
        print("  no joint telemetry")
        return 1

    names = sorted(series)
    wanted = [a.upper() for a in attached] or _ask_attached(names)
    unknown = [a for a in wanted if a not in series]
    if unknown:
        print(f"  not present in telemetry: {', '.join(unknown)}")
        return 1
    connected = [n for n in names if n in wanted]
    floating = [n for n in names if n not in wanted]

    print(f"\n  {len(samples)} lines at rest\n")
    print(f"  {'joint':<6} {'':<9} {'nan%':>6} {'|dpot| p50':>11} {'p95':>5} {'p99':>5} "
          f"{'max':>5}   verdict")
    stats = {n: _channel_stats(series[n]) for n in names}
    for name in names:
        s = stats[name]
        if name in connected:
            role, verdict = "attached", "flicker" if s["nan_rate"] else "clean"
        else:
            role = "no motor"
            verdict = "invalid, as expected" if s["nan_rate"] else "NEVER INVALID"
        print(f"  {name:<6} {role:<9} {s['nan_rate'] * 100:5.1f}% {s['p50']:11} "
              f"{s['p95']:5} {s['p99']:5} {s['max']:5}   {verdict}")

    if not connected:
        print("\n  No attached channel named, so there is nothing to derive a threshold")
        print("  from. Re-run with --joints listing the channels that have motors.")
        return 1

    worst_p99 = max(stats[n]["p99"] for n in connected)
    suggested = int(worst_p99) * 2 + 1
    print(f"\n  derived from {len(connected)} attached channel(s): {', '.join(connected)}")
    print(f"  worst p99 delta among those     : {worst_p99}")
    print(f"  suggested idleJitterMax         : {suggested}  (2x p99, rounded up)")
    if floating:
        print(f"  ignored {len(floating)} unconnected channel(s): {', '.join(floating)}")
        print("    a floating ADC pin reports spread that is not wiper noise")

    flickering = [n for n in connected if stats[n]["nan_rate"]]
    if flickering:
        print(f"\n  {len(flickering)} attached channel(s) report nan while connected and")
        print(f"  still: {', '.join(flickering)}")
        print("  That is a false invalid — the threshold is below the real noise floor.")
    silent = [n for n in floating if not stats[n]["nan_rate"]]
    if silent:
        print(f"\n  {len(silent)} unconnected channel(s) never went invalid: "
              f"{', '.join(silent)}")
        print("  A floating pin read as a healthy pot is a miss, not a pass. Raising")
        print("  the threshold makes this worse — check the range limits instead.")
    print("\n  Set in POT_VALIDITY_DEFAULT_LIMITS, reflash, then re-run this to confirm")
    print("  the flicker is gone. These are smoothed values, so the raw spread the")
    print("  detector sees is wider — prefer the generous end.")
    return 0


# --------------------------------------------------------------- debounce
def debounce(port: str, joint: str, floor: int) -> int:
    """Find the longest run of below-floor samples a healthy driven motor produces.

    Debounce must exceed that run, or ordinary gaps in current draw latch a
    connected motor as absent.
    """
    print(f"\n=== debounce depth — {joint}, floor {floor} ===")
    _prompt(f"Connect {joint}'s motor. It will be driven continuously.")
    with mcu.open_port(port) as ser:
        mcu.jog(ser, joint, PWM_SWEEP[-1])
        mcu.collect(ser, SETTLE_LINES)
        samples = mcu.collect(ser, 200)
        mcu.hold_all(ser)
    rows = [j for s in samples for j in mcu.joints_of(s) if j.name == joint]
    if not rows:
        print(f"  {joint} never appeared in telemetry")
        return 1

    longest = run = 0
    for j in rows:
        run = run + 1 if j.current < floor else 0
        longest = max(longest, run)
    below = sum(1 for j in rows if j.current < floor)
    print(f"\n  {len(rows)} driven samples, {below} below the floor "
          f"({below / len(rows) * 100:.1f}%)")
    print(f"  longest consecutive run below floor : {longest}")
    print(f"  suggested debounceSamples           : {longest + 2}")
    if longest == 0:
        print("  A healthy motor never dropped below the floor — the current default is safe.")
    else:
        print("  Anything at or below the observed run would latch a working motor as absent.")
    return 0


# --------------------------------------------------------------- open wiper
WIPER_LINES = 200


def _channel_summary(samples, name: str) -> Dict[str, float]:
    values = [(j.pot, j.connected) for s in samples
              for j in mcu.joints_of(s) if j.name == name]
    if not values:
        return {}
    pots = [p for p, _ in values]
    deltas = sorted(abs(b - a) for a, b in zip(pots, pots[1:])) or [0]
    return {
        "n": len(values),
        "min": min(pots),
        "max": max(pots),
        "p99": deltas[min(len(deltas) - 1, int(len(deltas) * 0.99))],
        "worst": deltas[-1],
        "nan_rate": sum(1 for _, c in values if not c) / len(values),
    }


def wiper(port: str, joint: str, limits=(5, 1018)) -> int:
    """Decide whether an open position wiper is detectable in software at all.

    2f.1 names three signatures for a bad position input — rail-pinned, noisy,
    and quiet in-range — and the band and slew checks only cover the first two.
    A pin that floats quietly inside the sane band is indistinguishable from a
    healthy mid-stroke pot, and the spec's answer to that case is a bias
    resistor, not a threshold. This measures which case the present hardware
    actually produces.

    Only the wiper is lifted: leaving the motor connected keeps attachment
    evidence intact, so anything that changes here is the position path alone.

    Detection is now expected rather than in question — the position-input probe
    pulls the pin up periodically and an open input rails on its own. What this
    run still tells you is the *signature*, which differs by channel: a wiper
    lifted from a live cable is noisy, while a channel that has never had a pot
    attached settles to a quiet in-band ghost value that band and slew cannot
    separate from a real reading.
    """
    minimum, maximum = limits
    print(f"\n=== open position wiper — {joint} ===")
    print("  The wire carries the smoothed pot, so brief raw excursions are not")
    print("  visible here. The verdict that matters is behavioural: whether the")
    print("  firmware reports the channel invalid.")

    _prompt("Everything connected and completely still.")
    with mcu.open_port(port) as ser:
        base = mcu.collect(ser, WIPER_LINES)
    before = _channel_summary(base, joint)
    if not before:
        print(f"  {joint} never appeared in telemetry")
        return 1
    print(f"  connected : pot {before['min']}-{before['max']}  |dpot| p99 "
          f"{before['p99']}  worst {before['worst']}  nan {before['nan_rate']*100:.1f}%")

    _prompt(f"De-energize, then lift ONLY {joint}'s pot wiper. Leave its motor connected.")
    with mcu.open_port(port) as ser:
        opened = mcu.collect(ser, WIPER_LINES)
    after = _channel_summary(opened, joint)
    if not after:
        print(f"  {joint} stopped reporting entirely")
        return 1
    print(f"  wiper open: pot {after['min']}-{after['max']}  |dpot| p99 "
          f"{after['p99']}  worst {after['worst']}  nan {after['nan_rate']*100:.1f}%")

    railed = after["min"] <= minimum or after["max"] >= maximum
    noisier = after["p99"] > max(before["p99"] * 3, before["p99"] + 3)
    detected = after["nan_rate"] > 0.5

    print()
    print(f"  firmware reported {joint} invalid: {detected} "
          f"({after['nan_rate']*100:.1f}% of lines)")
    if detected:
        # The pull-up probe forces an open input to the rail on its own, so a
        # detection here says nothing about whether band or slew would have
        # caught it. Recommending a threshold from this capture would tune a
        # check that may not be the one that fired.
        print("  The open input is detected. Nothing to calibrate from this run:")
        print("  the position-input probe forces an open pin to the rail by itself,")
        print("  so it is not evidence about idleJitterMax either way.")
        signature = ("rail-pinned" if railed else
                     "noisy" if noisier else "quiet and in-band")
        print(f"  Signature of the open input, for the record: {signature} "
              f"(pot {after['min']}-{after['max']}, |dpot| p99 {after['p99']}).")
        return 0

    print("  NOT DETECTED — the firmware treated an open input as a live one.")
    if railed:
        print(f"  It sits at a rail, so the band check ({minimum}..{maximum}) should")
        print("  have caught it; the limits are too permissive.")
    elif noisier:
        print("  It slews far beyond the connected channel, so the idle-slew check")
        print(f"  should have caught it: set idleJitterMax above {before['worst']} "
              f"and below {after['p99']}.")
    else:
        print("  It is quiet and in-band, which neither the band nor the slew check")
        print("  can separate from a healthy pot. That is the case the position-input")
        print("  probe exists for — check it is running and that openProbeMinimum is")
        print("  below what the pin reads with the pull-up enabled.")
    return 1
