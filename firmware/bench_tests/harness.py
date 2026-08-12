"""Interactive runner: one prompt, one measurement, one verdict per test.

Results persist to a JSON file after every test, so a session can be stopped and
resumed. On resume the selector defaults to the first test that has not yet
passed.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

RULE = "─" * 76
MARK = {True: "PASS", False: "FAIL", None: "skip"}


@dataclass
class Result:
    passed: Optional[bool]           # None = skipped
    detail: str


@dataclass
class BenchTest:
    ac: str                          # acceptance criterion, e.g. "1g.1"
    title: str
    criterion: str                   # requirement text, quoted
    setup: str                       # what the operator must do first
    expect: str                      # what result counts as a pass
    run: Callable[..., Result]
    key: str = ""                    # unique id; several tests may share one ac
    needs_cal_reset: bool = False
    manual: bool = False             # no serial access; operator confirms

    def __post_init__(self) -> None:
        if not self.key:
            self.key = self.ac


# --------------------------------------------------------------- persistence
def load_results(path: str) -> Dict[str, dict]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path) as handle:
            return {r["key"]: r for r in json.load(handle).get("results", [])}
    except (json.JSONDecodeError, KeyError, OSError):
        print(f"  warning: could not read {path}; starting fresh")
        return {}


def save_results(path: str, suite: str, records: Dict[str, dict]) -> None:
    if not path:
        return
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    payload = {
        "suite": suite,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": list(records.values()),
    }
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _status_of(record: Optional[dict]) -> str:
    if record is None:
        return "not run"
    return {True: "passed", False: "FAILED", None: "skipped"}[record.get("passed")]


# --------------------------------------------------------------- selector
def choose_start(tests: List[BenchTest], records: Dict[str, dict]) -> int:
    """Show prior results and let the operator pick where to begin.

    Defaults to the first test that has not passed — the last failure, or the
    next one never run.
    """
    default = next(
        (i for i, t in enumerate(tests) if records.get(t.key, {}).get("passed") is not True),
        0,
    )
    print(f"\n{RULE}\nTests\n{RULE}")
    for i, test in enumerate(tests):
        record = records.get(test.key)
        status = _status_of(record)
        when = f"  {record['at'][:16].replace('T', ' ')}" if record else ""
        cursor = ">" if i == default else " "
        print(f" {cursor} {i + 1:>2}. {test.ac:<7} {test.title[:44]:<44} {status:<8}{when}")
    if not records:
        return 0
    answer = input(
        f"\n  start at [{default + 1}] · [a] run all from 1 · number > "
    ).strip().lower()
    if answer == "a":
        return 0
    if answer.isdigit() and 1 <= int(answer) <= len(tests):
        return int(answer) - 1
    return default


# --------------------------------------------------------------- runner
def run_suite(
    tests: List[BenchTest],
    port: str,
    suite: str = "task1",
    results_path: str = "",
    start: int = 0,
    assume_yes: bool = False,
) -> int:
    records = load_results(results_path)
    for index in range(start, len(tests)):
        test = tests[index]
        print(f"\n{RULE}\n[{index + 1}/{len(tests)}]  {test.ac} — {test.title}\n{RULE}")
        print(f"  Criterion : {test.criterion}")
        print(f"  Set up    : {test.setup}")
        print(f"  Passes if : {test.expect}")
        if test.needs_cal_reset:
            print("  Note      : clears the stored IMU calibration, then reflashes (~40 s).")
        prior = records.get(test.key)
        if prior:
            print(f"  Last run  : {_status_of(prior)} at {prior['at'][:16].replace('T', ' ')}")

        if not assume_yes:
            answer = input("\n  [Enter] run · [s] skip · [q] quit > ").strip().lower()
            if answer == "q":
                break
            if answer == "s":
                result = Result(None, "skipped by operator")
            else:
                result = _execute(test, port)
        else:
            result = _execute(test, port)

        print(f"\n  {MARK[result.passed]}")
        for line in result.detail.splitlines():
            print(f"     {line}")
        records[test.key] = {
            "key": test.key,
            "ac": test.ac,
            "title": test.title,
            "passed": result.passed,
            "detail": result.detail,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        save_results(results_path, suite, records)

    return _summarise(tests, records, results_path)


def _execute(test: BenchTest, port: str) -> Result:
    started = time.monotonic()
    try:
        result = test.run(port=port)
    except Exception as exc:                          # noqa: BLE001 — bench tool
        result = Result(False, f"error: {type(exc).__name__}: {exc}")
    took = time.monotonic() - started
    return Result(result.passed, f"{result.detail}\n({took:.1f}s)")


def _summarise(tests: List[BenchTest], records: Dict[str, dict], path: str) -> int:
    print(f"\n{RULE}\nSummary\n{RULE}")
    width = max((len(t.ac) for t in tests), default=4)
    for test in tests:
        record = records.get(test.key)
        print(f"  {test.ac:<{width}}  {_status_of(record):<8}  {test.title[:46]}")
    failed = [t.ac for t in tests if records.get(t.key, {}).get("passed") is False]
    outstanding = [
        t.ac for t in tests if records.get(t.key, {}).get("passed") is not True
    ]
    if path:
        print(f"\n  results: {path}")
    if failed:
        print(f"  FAILED : {', '.join(failed)}")
    if outstanding:
        print(f"  outstanding: {', '.join(outstanding)}")
        return 1 if failed else 0
    print("\n  every test in this suite has passed")
    return 0
