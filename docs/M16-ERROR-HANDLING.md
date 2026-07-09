# M16 Error-Handling Design: IMU Telemetry Parsing (Task 1)

Design doc for host-side error handling of the `;IMU` telemetry segment
(`firmware/interfaces/joint_telemetry.py`, `firmware/krabby_mcu.py`,
`firmware/gui/app.py`). Written before implementation; file references are by
module/function name only, never by line.

---

## 1. Context: three distinct failure classes

The IMU path can "fail" in three ways that look superficially similar (the GUI
shows no fresh IMU number) but have different causes, different audiences, and
different correct responses. Collapsing them into one code path is the main
design risk.

### Class A — expected per-line parse failure (lossy stream, steady state)

The Orin reads a 20 Hz ASCII line from a USB serial link. Corruption is
*normal operation*: truncated lines at connect time, garbled bytes from a
marginal cable, interleaved output during firmware reset, AVR printing `nan`/
`inf`/`ovf` for non-finite floats. A malformed `;IMU` segment on one tick is
not actionable by anyone; the next tick (50 ms later) almost certainly carries
a good sample.

- Frequency: potentially per-segment, per-tick — a hot path.
- Audience: nobody, unless it *keeps* happening (then: the person debugging
  the cable).
- Correct response: drop the sample, keep the last good one, keep parsing the
  rest of the line (a bad IMU segment must never cost us the joint data on the
  same line).

### Class B — leader IMU init/read failure (exceptional, actionable)

Per the Task 1 spec (acceptance 1b), the leader firmware initializes the
BMI270 in `setup()`; on failure it logs on the MCU side, sets `imu_valid=0`,
and keeps the gait loop running. The host therefore *sees* this class on the
wire: a well-formed `;IMU` segment with `valid=0`, every tick. The same wire
state also covers a sensor that initialized but stops responding mid-run.

- Frequency: once per boot (or a persistent condition), not per-tick noise.
- Audience: a human — this means "check the Qwiic wiring / I2C address / 3.3 V
  rail." It is actionable, and the *reason* lives on the MCU (host only knows
  "not valid").
- Correct response: surface it (GUI `STALE` flag, log once), preserve the fact
  on the SDK so callers can query it, do not degrade anything else. This is a
  distinct case from Class C: a leader whose IMU failed to initialize is a
  hardware fault; a follower that never had an IMU is by design.

### Class C — follower / old-firmware / absent hardware (non-failure)

Only the leader carries the BMI270 (spec 1a). Follower lines (`LEFT;`,
`RIGHT;`) never contain an `;IMU` segment, and neither do lines from firmware
predating this task. `sdk.imu is None` before the first leader IMU line is the
normal state of a correctly functioning system.

- Frequency: every follower line, forever.
- Audience: nobody. Ever. Logging here is noise that trains operators to
  ignore logs.
- Correct response: nothing. `None` as the default value is the honest
  representation of "no IMU data has been seen," and follower lines must not
  overwrite a previously stored leader sample.

### Why one handling path cannot serve all three

Any single policy is wrong for at least two classes:

- **Raise everywhere**: turns Class A line noise into a raise-per-segment hot
  loop at 20 Hz and turns Class C (the majority of lines on a three-board
  robot) into a permanent exception storm. Unwinding is the expensive path in
  CPython even after 3.11's zero-cost `try`.
- **Silent `None` everywhere**: correct for Class C, tolerable for Class A
  only if the silencing is observable, and actively harmful for Class B — it
  throws away the one bit ("sensor present but dead") a human needs.
- **Log everywhere**: floods on A and C, burying the one B message that
  matters.

So the design assigns each class its own channel, and the rest of this
document justifies each choice.

## 2. Existing house style

A survey of the host-side Python (parse layer, firmware SDK, HAL drivers,
`hal_server` orchestration, CLI, data collection, teleop edge) shows a
coherent layered strategy, even though it has never been written down:

1. **Parse layer** — tolerant, `None`-returning, no logging, no exceptions.
   `JointTelemetry.from_tokens` returns `None` on any malformed shape;
   `parse_ver_reply` in `krabby_mcu.py` does the same; unknown segments are
   dropped to honor the append-only wire contract.
2. **Driver layer** — raise `RuntimeError`/`ValueError` on init and contract
   violations, with actionable fix-it hints (install commands, wiring advice);
   return `None`/`False` for transient data absence (ZED frame-grab miss,
   `read_version` timeout); factories convert init-raise into
   `logger.error` + `None`.
3. **Orchestration layer** (`hal_server.py`, `main.py`) — narrow-catch
   expected absence → `logger.warning` + degrade (optional hardware); fail
   fast only when the subsystem is required for the current mode (gamepad
   mode without an MCU is `sys.exit(1)`); one-shot boolean flags dedupe
   repeating warnings; shape mismatches raise (contract, not transience).
4. **CLI layer** — `sys.exit(message)` and stderr prints; best-effort probes
   swallow everything; bounded retry for the V-probe because followers cannot
   answer over USB — expected absence rendered as text, not error.
5. **Threads/loops** — never crash the process: catch, log, record
   `self.last_error`, set `running=False` and die (serial reader) or retry
   forever with log-level decay (portal reconnect).

Cross-cutting conventions: `logging.getLogger(__name__)`; `debug` = shutdown
noise and best-effort swallows, `warning` = degraded optional hardware and
malformed input, `error` = real failures with `exc_info=True` when unexpected;
repeated-log suppression via one-shot flags or timestamp gates
(`krabby_mcu.py` already rate-limits its DEBUG joint dump with a
last-log-timestamp check).

Honest caveats — the style is coherent but not uniform:

- `krabby_mcu.py` uses a named `"KrabbySDK"` logger plus an import-time
  `basicConfig` fallback, deviating from `getLogger(__name__)`.
- Send-on-closed-serial is a silent no-op in the firmware SDK but raises in
  the Jetson SDK — same condition, two conventions.
- The Jetson SDK's `connect()` both raises and returns a bool (dead code
  after the raise).
- The follower/optional-hardware distinction (Class C above) already has
  strong precedent: the CLI's bounded V-probe, `hal_server`'s narrow-catch
  "expected absence" vs broad-catch "unexpected," and mode-dependent
  requiredness in `main.py`.

The IMU parse work sits squarely at layers 1–2, so the design below extends
those layers' conventions rather than inventing new ones. The known
inconsistencies are noted so we don't "fix" one file to match another by
accident; repairing them is out of scope (§5).

## 3. Alternatives, per failure class

Scoring axes: functionality, maintenance, correctness, efficiency,
readability, extensibility, simplicity, reversibility.

### Class A — malformed segment on the hot path

| | A1: raise `TelemetryParseError` | A2: return `None`, silent (status quo shape) | A3: return `None` + reason enum + counter + throttled warning | A4: `Result[T, E]`-style return (`tuple`/library) |
|---|---|---|---|---|
| Functionality | Caller must try/except per segment or lose the whole line | Works; information destroyed | Works; information preserved out-of-band | Works; information in-band |
| Maintenance | Every new segment type needs handler plumbing | Lowest | Low — one enum + one counter per parser | Every caller signature churns when reasons change |
| Correctness | Risk: one bad segment aborts joint parsing unless carefully scoped | Correct but unobservable (violates PEP 20's "unless *explicitly* silenced") | Correct and observable | Correct; heaviest to keep honest |
| Efficiency | Raise-per-segment-per-tick during a noisy-cable episode; unwind is the expensive path | Best | ~Best (int increment; log gated by timestamp) | Tuple allocation per call; fine but pointless overhead |
| Readability | Fights stdlib precedent (`re.match` returns `None`; `str.find` vs `str.index` exists *because* expected-miss APIs return sentinels) | Familiar | Familiar + one extra attribute to learn | Un-Pythonic in a repo with zero `Result` usage; new dependency or hand-rolled type |
| Extensibility | OK | Poor (nothing to extend) | Good — enum grows per segment type; Task 3 `BATT` reuses the pattern | Good but invasive |
| Simplicity | Try/except at every call site | Simplest | Near-simplest | Least simple |
| Reversibility | High churn to undo | Trivial | Trivial (additive) | High churn to undo |

**EAFP does not apply here.** The Python glossary defines EAFP as the common
style *presuming valid input*; on a lossy serial stream, invalid input is the
steady state, which is exactly where the stdlib itself switches to sentinel
returns (`re.match`, `dict.get`, `bytes.decode(errors="replace")`,
pyserial's own timeout-returns-short-read). `json.loads` raises because
malformed JSON *handed to you* is exceptional; malformed serial is not.

### Class B — leader IMU present but not valid (init/read failure)

| | B1: raise from the reader thread | B2: store `valid=False` sample + surface (GUI flag, log-once, queryable SDK state) | B3: silent `valid=False` sample only |
|---|---|---|---|
| Functionality | Kills the reader thread (house rule: thread catches, logs, dies) — losing *joint* telemetry because the *IMU* is unwired is unacceptable | Full: data flows, humans informed, callers can query | Data flows but the GUI is the only witness |
| Correctness | Punishes an optional sensor as if required | Matches spec 1b ("does not crash or stall") on the host side too | Loses the once-per-boot actionable event in the noise |
| Readability / simplicity | Complex recovery story | One flag + one log-once gate | Simplest, too quiet |
| Extensibility | — | Same shape serves Task 3 battery validity | — |

### Class C — follower / absent hardware

| | C1: log per follower line | C2: `sdk.imu` defaults to `None`; follower lines never touch it; no logging | C3: sentinel "NoImu" object |
|---|---|---|---|
| Functionality | Log storm at line rate | Correct; `None` is the honest "never seen" | Works |
| Readability | — | `if sdk.imu is None` is the idiomatic check | Callers must learn a bespoke sentinel; fights `Optional` typing |
| Simplicity | — | Free — it is the dataclass default | Extra class for zero information |

## 4. Decision

**Class A: keep the `Optional`-returning parser; make the silencing explicit
and observable (A3).** `from_tokens` continues to return `None` on every
malformed shape — that is the idiomatic Python signal for "attempt that may
not produce a value," backed by stdlib precedent and by this repo's entire
parse layer. What changes is that the drop is no longer information-free:

- A small `enum.Enum` of parse-failure reasons (wrong tag, bad token count,
  non-numeric token, non-finite value). Enums are grep-able and testable;
  string reasons drift.
- A monotonically increasing parse-error counter and a
  last-parse-error-reason attribute on the SDK, mirroring the existing
  `last_error` attribute the reader thread already maintains. The GUI's
  existing SDK poll can display the counter; no new channel needed.
- A throttled `logger.warning` (order of once per second, first occurrence
  never suppressed) carrying the reason and a truncated copy of the offending
  segment. This reuses the timestamp-gate idiom `krabby_mcu.py` already uses
  for its DEBUG joint dump, which is also the shape ROS blessed as a
  first-class API (`throttle_duration_sec` in rclpy, `logwarn_throttle` in
  rospy) because every driver needs it. Per-line detail stays at DEBUG.

**Class B: three-state model, surfaced.** The host distinguishes: `sdk.imu is
None` (never seen — Class C), `sdk.imu.valid is False` (sensor present but
not responding — Class B, rendered `STALE` by `format_compact` and the GUI),
and `sdk.imu.valid is True` (fresh sample). A transition into the invalid
state is logged once at WARNING (one-shot flag, `hal_server` idiom), not per
tick. No exception is raised: the reader thread's contract is catch-log-die
for *transport* failures only, and an unhappy optional sensor is not a
transport failure. The failure *reason* (which BMI270 status code) exists
only on the MCU; the host preserves everything the wire gives it (`valid`)
rather than discarding it behind a bare `None`. This is deliberately a no-op
for control flow but not for information — callers and humans can both see it.

**Class C: `None` default, no logging, by design.** Not initializing because
we are a follower is not a failure mode and must never share a code path with
Class B. The dataclass default plus "follower lines preserve the last leader
sample" is the entire mechanism.

**Init-failure strategy generally (host SDK).** The survey's layered strategy
is adopted as written policy for code this milestone touches: parse layer
returns `None` and never logs above DEBUG on its own; the SDK owns
observability state (counters, last-reason, throttled/one-shot logs); raising
is reserved for broken preconditions and contract violations, not data
absence. Files outside this task's surface keep their current behavior even
where inconsistent (§2 caveats); repairing those is proposed as follow-up,
not smuggled into this diff.

### The append-only contract constrains the wire, not host-side reporting

The contract (spec 1d) says: old parsers must *ignore* unknown appended
segments, so the wire can grow without breaking deployed hosts. That forces
exactly one behavior — `parse_telemetry_line` must not fail, raise, or refuse
a line because it contains a segment it does not recognize. It does **not**
require the host to stay silent about segments it *does* recognize but cannot
parse. A malformed `;IMU ...` segment (known tag, bad payload) is corruption,
not forward compatibility, and may be counted and warned about freely. So no
— the contract is not what limits us to bare `None` across IMU failure
modes; bare `None` is simply the parse layer's inherited default, which this
design upgrades to observed-`None`.

One genuine ambiguity remains where the two categories collide:

> **Question for Fletcher:** an unrecognized segment can be (a) a future
> tagged segment from newer firmware (must stay silent — that is the whole
> point of append-only) or (b) a corrupted joint segment (would be nice to
> count). Can we rely on the convention that every future appended segment
> starts with an alphabetic tag token (`IMU`, `BATT`, ...), so the host may
> treat "unknown alphabetic tag" as silent-by-contract and only count
> tagless/degenerate segments as corruption? If not, unknown-segment
> accounting stays at DEBUG only.

## 5. Scoped implementation plan

This milestone changes:

1. `firmware/interfaces/joint_telemetry.py` — parse-failure reason enum;
   `ImuTelemetry.from_tokens` (and the line parser) report a reason through a
   lightweight stats hook/aggregate rather than a changed return type;
   docstrings state the contract in commit-agnostic terms.
2. `firmware/krabby_mcu.py` — SDK gains `imu` (last sample, default `None`),
   a parse-error counter, and a last-parse-reason attribute alongside the
   existing `last_error`; throttled WARNING for Class A; one-shot WARNING on
   the Class B valid→invalid transition.
3. `firmware/gui/app.py` — IMU readout renders the three states distinctly
   (absent / STALE / fresh); named constants for any wire- or UI-magic values.
4. `tests/unit/firmware/` — parametrized malformed-shape matrix with
   intent-revealing ids; reason-enum and counter assertions; throttle
   first-warning test; three-state tests (absent, `valid=0`, fresh); follower
   lines preserve last leader sample.

Explicitly **not** in scope:

- No change to the wire format or any `firmware/arduino/` code.
- No repair of pre-existing inconsistencies outside this surface
  (`"KrabbySDK"` logger name, `basicConfig` fallback, Jetson SDK
  raise-and-return, closed-serial send conventions) — noted in §2, proposed
  as separate follow-up.
- No `Result`-type library, no reconnect logic, no changes to the reader
  thread's catch-log-die contract, no role-election code.
- No new CLI surface (spec 1h).

## 6. Design options: telemetry parsing API organization (decision deferred)

A separate organizational concern: the plan above leaves the parsing surface
with several similarly named entry points — `JointTelemetry.from_tokens`,
`JointTelemetry.parse_line` (a thin delegate kept for existing callers),
`ImuTelemetry.from_tokens`, module-level `parse_telemetry_line`, and the
`ParsedTelemetry` product type whose name reads as a participle rather than a
thing. Three reorganization options, **decision deferred to John
(hand-coding); no implementation in this milestone's diff**:

**Option 1 — keep current shape, rename the product type.**
`ParsedTelemetry` → `TelemetryFrame` (a noun: one line = one frame);
module-level `parse_telemetry_line(line) -> TelemetryFrame` stays the single
entry point; `JointTelemetry.parse_line` is deprecated in favor of calling
the module function.
*Trade-offs:* smallest diff, callers barely churn; but two `from_tokens`
methods remain "package-private in spirit, public in fact," and the module
function vs classmethod split stays unwritten convention.

**Option 2 — the frame owns its parsing.** `TelemetryFrame.parse(line)`
classmethod as the only public entry point; `from_tokens` on the segment
dataclasses becomes explicitly internal (`_from_tokens`); the parse-stats
aggregate (§4) lives on the frame, so "what failed while parsing this line"
travels with the result.
*Trade-offs:* one obvious front door, stats co-located with data, segment
parsers become an implementation detail free to change; slightly larger
diff, and per-frame stats must still be rolled up by the SDK for cross-line
counters.

**Option 3 — `TelemetryLine` value object, parse-on-init.** A class holding
`raw: str` plus parsed fields, parsing in `__init__` (or a `from_raw`
constructor); raw text retained for diagnostics/replay (pairs well with the
existing `KRABBY_MCU_RAW_RX` debug facility and future bag recording).
*Trade-offs:* best diagnosability (offending raw line is always attached to
its parse result) and most extensible toward data collection; heaviest
object per tick, parse-in-constructor makes "cheap to construct" no longer
true, and it drifts furthest from the repo's current dataclass-plus-function
style.

All three keep `Optional`/three-state semantics from §4 unchanged; this
section is purely about naming and ownership of the entry points.
