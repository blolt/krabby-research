"""Run the Task 3 power-monitor bench checks with attached hardware."""
from __future__ import annotations

import argparse
import sys

from firmware.bench_tests import checks, task3
from firmware.bench_tests.harness import choose_start, load_results, run_suite

SUITES = {"task3": task3.TESTS}
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
    context = {}
    blocked = [t.ac for t in tests if t.requires]
    if blocked:
        print(f"needs hardware not always present: {', '.join(blocked)}")
    return run_suite(tests, port=args.port, suite=args.suite,
                     results_path=results_path, start=start, assume_yes=args.yes,
                     context=context)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="show checks and acceptance criteria")
    listing.add_argument("--suite", default="task3", choices=sorted(SUITES))
    listing.set_defaults(func=_cmd_list)
    check = sub.add_parser("check", help="run one measurement")
    check.add_argument("name", choices=sorted(checks.CHECKS))
    check.add_argument("--port", required=True)
    check.set_defaults(func=_cmd_check)
    run = sub.add_parser("run", help="run the Task 3 suite")
    run.add_argument("--port", required=True)
    run.add_argument("--suite", default="task3", choices=sorted(SUITES))
    run.add_argument("--only", nargs="+", metavar="AC")
    run.add_argument("--results")
    run.add_argument("--yes", action="store_true", help="skip the starting-point prompt")
    run.set_defaults(func=_cmd_run)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
