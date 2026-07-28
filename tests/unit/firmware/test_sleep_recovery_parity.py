"""Source guard for the SLEEP self-recovery poll in loop() (M16 Task 4, AC 4f).

The low-power branch of firmware/arduino/arduino.ino's loop() is the ONLY code
that runs once the protective FSM parks the robot in
PowerState::Sleep / PowerState::OverVolt:
the normal telemetry path (and its own Pack re-begin) is skipped entirely. So if
the Pack INA228 wedges *during* sleep, the throttled recovery poll is the last
thing that can re-init it. Drop the `if (!packOk) inaRecoverPack();` line and
packOk is false forever -> lowPowerStep never sees a trusted voltage -> the FSM
can never reach PowerState::Resuming and the robot is bricked asleep until a human
power-cycles it. That regression is invisible to every Python-level test.

SCOPE, and why this file is written the way it is: arduino.ino also calls
inaRecoverPack() on the *normal* telemetry path (battAppendTelemetry). A test
that greps the whole file for "inaRecoverPack" therefore still passes after the
bug is reverted, and is worthless. Everything below is asserted against a
brace-matched extract of the low-power branch only, and
test_extractor_is_scoped_to_the_low_power_branch guards the extractor itself.

Text/regex rather than a compile, matching the repo's parity-guard pattern (cf.
the native FSM suite) — no C/C++ is built in this suite.

Deliberately NOT covered here: inaRecoverPack()'s own body / skipReset backoff
(Task 3 code, has its own test) and the FSM's recovery decision itself
(firmware/arduino/power_fsm.h, covered by the native C++ FSM suite).
"""
import re
from functools import lru_cache
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_INO = (_REPO / "firmware/arduino/arduino.ino").read_text()
_SENSORS_H = (_REPO / "firmware/arduino/sensors_config.h").read_text()


def _define_int(name: str, text: str) -> int:
    """First integer of a #define, ignoring any U/L/UL suffix."""
    m = re.search(rf"#define\s+{name}\s+(\d+)", text)
    assert m, f"#define {name} not found"
    return int(m.group(1))


def _brace_block(text: str, brace_index: int) -> str:
    """Return the {...} block starting at text[brace_index] == '{'."""
    assert text[brace_index] == "{", "internal error: not an opening brace"
    depth = 0
    for i in range(brace_index, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_index : i + 1]
    raise AssertionError("unbalanced braces while extracting block")


@lru_cache(maxsize=1)
def _low_power_branch() -> str:
    """The body of loop()'s `SLEEP || OVER_VOLT` low-power branch, and only that."""
    loop_at = _INO.find("void loop()")
    assert loop_at != -1, "void loop() not found in arduino.ino"
    m = re.search(
        r"if\s*\(\s*isI2CClusterBoard\(\)\s*&&"
        r"[^{]*?PowerState::Sleep\s*\|\|"
        r"[^{]*?PowerState::OverVolt[^{]*?\)\s*(\{)",
        _INO[loop_at:],
        re.S,
    )
    assert m, (
        "could not locate loop()'s low-power branch "
        "(`if (isI2CClusterBoard() && "
        "(state == PowerState::Sleep || state == PowerState::OverVolt))`). "
        "If it was restructured, retarget this guard rather than deleting it — "
        "AC 4f's self-recovery still needs a home."
    )
    return _brace_block(_INO[loop_at:], m.start(1))


@lru_cache(maxsize=1)
def _recovery_poll_block() -> str:
    """The body of the throttled recovery poll inside the low-power branch."""
    branch = _low_power_branch()
    m = re.search(
        r"if\s*\([^{;]*?lastRecoveryPollMs[^{;]*?POWER_RECOVERY_POLL_MS[^{;]*?\)\s*(\{)",
        branch,
        re.S,
    )
    assert m, (
        "the low-power branch has no `now - lastRecoveryPollMs >= "
        "POWER_RECOVERY_POLL_MS` throttle guard; an unthrottled recovery poll "
        "would hammer the wedged Pack INA228 every loop tick while asleep"
    )
    return _brace_block(branch, m.start(1))


# --- extractor self-check: prove the scoping is real -------------------------
def test_extractor_is_scoped_to_the_low_power_branch():
    # If brace matching ever ran away, every assertion below would degrade into a
    # whole-file grep that survives the bug-8 revert. Pin that it did not.
    branch = _low_power_branch()
    assert len(branch) < len(_INO) / 4, "low-power branch extract is implausibly large"
    assert "while (mainSerial->available())" not in branch, (
        "extract leaked past the low-power branch into loop()'s normal path"
    )
    assert "battAppendTelemetry" not in branch, (
        "extract leaked into the normal telemetry path (which has its own "
        "inaRecoverPack call) — assertions here would no longer be scoped"
    )
    assert len(_recovery_poll_block()) < len(branch), (
        "recovery-poll extract is not inside the branch"
    )


# --- BUG #8: the self-recovery call must live in the low-power branch --------
def test_low_power_branch_reinits_wedged_pack_ina228():
    poll = _recovery_poll_block()
    m = re.search(
        r"if\s*\(\s*!\s*(\w+)\s*\)\s*(?:\{\s*)?inaRecoverPack\s*\(\s*\)\s*;",
        poll,
        re.S,
    )
    assert m, (
        "AC 4f regression: loop()'s throttled low-power recovery poll no longer "
        "calls `if (!packOk) inaRecoverPack();`. Without it a Pack INA228 that "
        "wedges during SLEEP is never re-inited, packOk stays false forever, the "
        "FSM can never reach PowerState::Resuming, and the robot stays asleep until a "
        "hard reset. (The inaRecoverPack call on the normal telemetry path does "
        "NOT cover this — that path is skipped entirely while asleep.)"
    )
    guard_var = m.group(1)
    read = re.search(r"\b(\w+)\s*=\s*powerReadPackV\s*\(\s*&\s*(\w+)\s*\)", poll)
    assert read, "recovery poll no longer reads the pack via powerReadPackV(&ok)"
    assert guard_var == read.group(2), (
        f"recovery is gated on `{guard_var}`, not on the validity flag "
        f"`{read.group(2)}` that powerReadPackV just wrote"
    )


def test_recovery_call_is_between_the_pack_read_and_the_fsm_step():
    poll = _recovery_poll_block()
    # Ordering matters: re-begin only after this tick's read proved the device is
    # wedged, and before handing the result to the FSM.
    for token in ("powerReadPackV", "inaRecoverPack", "lowPowerStep"):
        assert token in poll, (
            f"the low-power recovery poll no longer calls {token}(); see "
            "test_low_power_branch_reinits_wedged_pack_ina228 for why AC 4f "
            f"needs all three. Poll body:\n{poll}"
        )
    i_read = poll.index("powerReadPackV")
    i_recover = poll.index("inaRecoverPack")
    i_step = poll.index("lowPowerStep")
    assert i_read < i_recover < i_step, (
        "expected powerReadPackV -> inaRecoverPack -> lowPowerStep ordering in "
        f"the recovery poll, got offsets read={i_read} recover={i_recover} "
        f"step={i_step}"
    )


# --- the poll stays throttled and still drives the FSM ----------------------
def test_recovery_poll_stamps_its_timestamp_before_touching_the_bus():
    poll = _recovery_poll_block()
    m = re.search(r"lastRecoveryPollMs\s*=\s*(\w+)\s*;", poll)
    assert m, (
        "the recovery poll never re-stamps lastRecoveryPollMs, so the throttle "
        "never advances and the poll would fire every loop tick"
    )
    assert m.start() < poll.index("powerReadPackV"), (
        "lastRecoveryPollMs must be stamped before the I2C read, so a read that "
        "wedges/blocks cannot leave the throttle unadvanced"
    )


def test_low_power_step_gets_this_ticks_voltage_and_validity():
    poll = _recovery_poll_block()
    read = re.search(r"\b(\w+)\s*=\s*powerReadPackV\s*\(\s*&\s*(\w+)\s*\)", poll)
    assert read, "recovery poll no longer reads the pack via powerReadPackV(&ok)"
    packv, packok = read.group(1), read.group(2)
    assert re.search(
        rf"lowPowerStep\s*\(\s*{packv}\s*,\s*{packok}\s*\)", poll
    ), (
        f"lowPowerStep must be called with the freshly-read ({packv}, {packok}) "
        "from this poll — a stale/cached value would let SLEEP resume (or fail to "
        f"resume) on a voltage nobody just measured. Poll body:\n{poll}"
    )


def test_recovery_poll_cadence_is_a_real_throttle():
    ms = _define_int("POWER_RECOVERY_POLL_MS", _SENSORS_H)
    # ~30 s per AC 4f: long enough to be a genuine low-power cadence, short enough
    # that a recovered pack is noticed in human time.
    assert 1_000 <= ms <= 120_000, (
        f"POWER_RECOVERY_POLL_MS={ms} is outside the plausible low-power "
        "recovery cadence (1 s .. 120 s)"
    )
