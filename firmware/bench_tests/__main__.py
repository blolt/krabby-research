"""Bench procedures for the acceptance criteria that need hardware.

Two ways in — atomic checks, or a composed suite:

    # list what exists
    python3 -m firmware.bench_tests list

    # one atomic check, no verdict attached
    python3 -m firmware.bench_tests check timing --port /dev/cu.usbmodem2101
    python3 -m firmware.bench_tests check flip   --port /dev/cu.usbmodem2101

    # the composed suite, interactive, resumable
    python3 -m firmware.bench_tests run --port /dev/cu.usbmodem2101
    python3 -m firmware.bench_tests run --port /dev/cu.usbmodem2101 --only 1g.1 1g.4

Results persist to a JSON file after every test, so a session can be stopped and
picked up later. On resume the selector defaults to the first test that has not
yet passed.

Supersedes firmware/scripts/imu_bench.py:
    imu_bench PORT timing -> check timing
    imu_bench PORT watch  -> check stream
    imu_bench PORT flip   -> check flip
"""
from __future__ import annotations

import argparse
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from firmware.bench_tests import calibrate, capture, checks, task1, task2, task3  # noqa: E402
from firmware.bench_tests.harness import choose_start, load_results, run_suite  # noqa: E402

SUITES = {"task1": task1.TESTS, "task2": task2.TESTS, "task3": task3.TESTS}
# Names as the firmware spells them (arduino.ino ACT_LIST_FRONT and the follower
# lists); handleJog compares case-sensitively.
def _joint(value: str) -> str:
    """Normalise a joint name at the parser, so no command has to remember to.

    handleJog compares names case-sensitively and silently does nothing on a
    miss, so a lowercase name drives nothing and the criterion reports on an
    actuator that never moved.
    """
    return value.strip().upper()


def _joint_list(value: str) -> list:
    return [j.strip().upper() for j in value.split(",") if j.strip()]


KNOWN_JOINTS = {
    "FLHY", "FLHL", "FLKL", "FRHY", "FRHL", "FRKL",
    "RLHY", "RLHL", "RLKL", "MLHY", "MLHL", "MLKL",
    "RRHY", "RRHL", "RRKL", "MRHY", "MRHL", "MRKL",
}
DEFAULT_RESULTS = "bench-results-{suite}.json"


def _cmd_list(args: argparse.Namespace) -> int:
    print("atomic checks (python3 -m firmware.bench_tests check NAME --port ...)")
    for name, fn in sorted(checks.CHECKS.items()):
        first = (fn.__doc__ or "").strip().splitlines()[0]
        print(f"  {name:<13} {first}")
    print(f"\nsuite '{args.suite}' (python3 -m firmware.bench_tests run --port ...)")
    for test in SUITES[args.suite]:
        tags = []
        if test.needs_cal_reset:
            tags.append("clears stored cal")
        if test.manual:
            tags.append("inspection only")
        suffix = f"  [{', '.join(tags)}]" if tags else ""
        print(f"  {test.ac:<7} {test.title}{suffix}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    fn = checks.CHECKS[args.name]
    print(f"check: {args.name}   port: {args.port}")
    measurement = fn(port=args.port)
    for line in measurement.text.splitlines():
        print(f"  {line}")
    if measurement.ok is False:
        return 1
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    tests = SUITES[args.suite]
    if args.only:
        wanted = {a.lower() for a in args.only}
        selected = [t for t in tests if t.ac.lower() in wanted or t.key.lower() in wanted]
        missing = wanted - {t.ac.lower() for t in tests} - {t.key.lower() for t in tests}
        if missing:
            print(f"unknown criteria: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
        tests = selected

    results_path = args.results or DEFAULT_RESULTS.format(suite=args.suite)
    print(f"suite: {args.suite}   port: {args.port}   tests: {len(tests)}")
    print(f"results: {results_path}")
    print("The GUI holds the serial port — close it first (pkill -f firmware.gui).")

    start = 0
    if not args.only and not args.yes:
        start = choose_start(tests, load_results(results_path))
    # handleJog matches the name with a case-sensitive compare and silently does
    # nothing on a miss, so an unnormalised or misspelled joint drives nothing and
    # the criterion reports on an actuator that never moved.
    joint = args.joint
    if joint and joint not in KNOWN_JOINTS:
        print(f"unknown joint {joint!r}; expected one of {', '.join(sorted(KNOWN_JOINTS))}",
              file=sys.stderr)
        return 2
    context = {"joint": joint} if joint else {}
    if joint:
        print(f"driving: {joint}")
    blocked = [t.ac for t in tests if t.requires]
    if blocked:
        print(f"needs hardware not always present: {', '.join(blocked)}")
    return run_suite(tests, port=args.port, suite=args.suite,
                     results_path=results_path, start=start, assume_yes=args.yes,
                     context=context)


def _cmd_calibrate(args: argparse.Namespace) -> int:
    if args.what in ("current", "debounce", "wiper") and not args.joint:
        print("--joint is required: the sweep drives one actuator, and driving an "
              "empty channel measures nothing.\nRun 'calibrate identify' first if you "
              "are unsure which channels are populated.", file=sys.stderr)
        return 2
    if args.what == "identify":
        return calibrate.identify(args.port, args.joints)
    if args.what == "current":
        return calibrate.current(args.port, args.joint)
    if args.what == "wiper":
        return calibrate.wiper(args.port, args.joint)
    if args.what == "pot":
        return calibrate.pot(args.port, args.joints)
    return calibrate.debounce(args.port, args.joint, args.floor)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="python3 -m firmware.bench_tests",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="show atomic checks and the suite")
    p_list.add_argument("--suite", default="task1", choices=sorted(SUITES))
    p_list.set_defaults(func=_cmd_list)

    p_check = sub.add_parser("check", help="run one atomic check")
    p_check.add_argument("name", choices=sorted(checks.CHECKS))
    p_check.add_argument("--port", required=True)
    p_check.set_defaults(func=_cmd_check)

    p_run = sub.add_parser("run", help="run the composed suite")
    p_run.add_argument("--port", required=True)
    p_run.add_argument("--suite", default="task1", choices=sorted(SUITES))
    p_run.add_argument("--only", nargs="+", metavar="AC",
                       help="run only these criteria or keys, e.g. --only 1g.1 1c.4")
    p_run.add_argument("--results", help=f"results file (default {DEFAULT_RESULTS})")
    p_run.add_argument("--joint", default="", type=_joint,
                       help="joint to drive for actuator tests, e.g. FLHY. Which "
                            "channels have motors attached varies by bench setup.")
    p_run.add_argument("--yes", action="store_true",
                       help="do not pause or prompt for a start point; only safe when "
                            "nothing needs plugging or moving")
    p_run.set_defaults(func=_cmd_run)

    p_cap = sub.add_parser("capture", help="sweep PWM and write raw samples to CSV")
    p_cap.add_argument("--port", required=True)
    p_cap.add_argument("--motor", required=True, type=_joint_list,
                       help="comma-separated channels that have an actuator")
    p_cap.add_argument("--empty", default=[], type=_joint_list,
                       help="comma-separated channels on a wired H-bridge with no "
                            "actuator. Channels whose IS pin reaches no H-bridge at "
                            "all do not belong here — a floating input is a third case.")
    p_cap.add_argument("--out", default="~/Downloads/attachment_sweep.csv")
    p_cap.set_defaults(func=lambda a: capture.sweep(a.port, a.motor, a.empty, a.out))

    p_cal = sub.add_parser("calibrate", help="measure thresholds instead of judging them")
    p_cal.add_argument("what",
                       choices=["identify", "current", "pot", "debounce", "wiper"])
    p_cal.add_argument("--port", required=True)
    p_cal.add_argument("--joint", default="", type=_joint,
                       help="actuator to drive (current, debounce, wiper)")
    p_cal.add_argument("--joints", default=[], type=_joint_list,
                       help="channels with a motor attached, e.g. FRHY,FRKL (pot). "
                            "Unconnected channels float and would skew the threshold; "
                            "omit to be asked interactively.")
    p_cal.add_argument("--floor", type=int, default=50,
                       help="candidate current floor for the debounce measurement")
    p_cal.set_defaults(func=_cmd_calibrate)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
