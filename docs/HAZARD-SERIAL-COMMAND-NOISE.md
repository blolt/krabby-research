# HAZARD: Serial command dispatcher trusts single noise bytes — spurious auto-calibration

| | |
|---|---|
| **Status** | Open — unaddressed on all upstream branches as of 2026-07-07 |
| **Severity** | Unexpected whole-robot motion (all joints driven to mechanical stops); secondary: control-loop lockup |
| **Introduced by** | Pre-existing on upstream `main` — **not** introduced by M16 (M16's baud change makes garbage *rarer*, not possible) |
| **First written up** | `docs/M16-DESIGN-DECISIONS.md` §1.5 (M16 review); this report expands that finding |
| **Affects** | `firmware/arduino/arduino.ino` (leader + follower Megas), every serial link: host USB↔leader, leader↔follower UARTs |

## Summary

The Mega firmware's command dispatcher in `loop()` treats the first byte after any newline as a command code with no framing, checksum, or confirmation, so a single garbage byte `0x43` (`'C'`) on the USB or follower UART links starts auto-calibration — physically driving **every actuator on all three boards** into its mechanical stops. Garbage bytes are not hypothetical on this system: they arise from baud mismatches across firmware-version boundaries, USB hot-plug/enumeration transients, floating RX lines, and motor EMI (a real bench incident, 2026-07-03, produced a runaway actuator from serial garbage). A related defect in the `'B'` jog-bridge handler can stall the control loop indefinitely on a partial line, freezing telemetry and actuator updates until a newline happens to arrive.

## Mechanism

All paths run through the command dispatcher at the top of `loop()` in `firmware/arduino/arduino.ino` (shape below is upstream `main` / branch `m16-task1`; line numbers deliberately omitted — the file is under active change on `upstream/m17`):

```cpp
while (mainSerial->available())
{
    char cmdType = mainSerial->peek();
    if      (cmdType == 'T') { /* read(); payload = readStringUntil('\n'); parseCommands(...) */ }
    else if (cmdType == 'B')
    {
        mainSerial->read();
        // ...forward "B " to followers...
        while (true)                                       // <-- no exit except a '\n'
        {
            String name = mainSerial->readStringUntil(' ');
            int pwm = mainSerial->readStringUntil(' ').toInt();
            actuatorManager->handleJog(name, pwm);
            // ...forward name/pwm to followers...
            if (mainSerial->peek() == '\n') { mainSerial->readStringUntil('\n'); break; }
        }
    }
    else if (cmdType == 'J') { /* read(); name + pwm; handleJog(name, pwm) */ }
    else if (cmdType == 'C')
    {
        mainSerial->read();
        mainSerial->readStringUntil('\n');
        actuatorManager->startAutoCalibration();           // <-- ALL local joints move
        if (leftSerial)  leftSerial->println("C");         // <-- and both followers
        if (rightSerial) rightSerial->println("C");
    }
    else if (cmdType == 'H') { /* holdAll(), forwarded */ }
    else if (cmdType == 'V') { /* version query */ }
    else { /* readStringUntil('\n'); SYNC handling */ }
}
```

The load-bearing defects:

1. **`'C'` is a bare, unauthenticated actuation trigger.** Dispatch is on a single `peek()`ed byte at line-start position. The rest of the line is read *and discarded* — no payload is validated. `startAutoCalibration()` (`firmware/arduino/actuator_manager.h`) drives every joint via stall detection to find limits, and the leader forwards a bare `"C"` line to both followers, so one garbage byte on the host link moves the whole robot. `'H'` (hold-all) and `'V'` are similarly single-byte-gated but benign.
2. **Garbage cannot fake a `'T'` motion command, but it doesn't need to.** `'T'` payloads must survive `parseCommands` (`firmware/arduino/command.h`); random bytes get dropped and actuators hold. The hazard concentrates entirely in the two commands where a first byte alone suffices: `'C'` (motion) and `'B'` (lockup, below). `'J'` needs a garbage token to string-match a real actuator name — negligible probability, noted for completeness.
3. **A partial `'B'` line blocks `loop()`.** The `while (true)` bridge loop exits only when `peek() == '\n'`. If the sender dies mid-line (host hot-unplug, garbled `'\n'`), `peek()` returns `-1`, the loop never breaks, and each `readStringUntil(' ')` blocks up to the Stream timeout (Arduino default **1000 ms**; no `setTimeout` is issued on `main`). The board spins there — no telemetry, no `actuatorManager->updateAll()`, no follower draining — until a `'\n'` eventually arrives on the wire. Fail-frozen rather than fail-safe.
4. **Every link is an ingress point.** The dispatcher runs on `mainSerial`, which is the host USB CDC port on the leader and the inter-board UART on followers. The follower UARTs (`SERIAL_LEFT`/`SERIAL_RIGHT`) additionally feed the leader through the telemetry-forwarding path, and on upstream `main` those RX pins float when a cable is out.

## Trigger probability

**Per-garbage-byte odds.** The dispatcher consumes garbage in newline-delimited chunks: it dispatches on the chunk's first byte and `readStringUntil('\n')` swallows the rest. Modeling garbage as uniform random bytes, a chunk ends (byte == `'\n'`) with p ≈ 1/256, so chunks average ≈256 B, and each chunk's first byte is `'C'` with p ≈ 1/256. Expectation: **one spurious auto-calibration per ≈ 256 × 256 B ≈ 64 KiB of sustained garbage.** Caveat, honestly held: framing-error output is *not* uniform — it's biased by the bit-pattern relationship of the two baud rates and line idle state (runs of 0x00/0xFF are overrepresented) — so treat 1/256 as an order-of-magnitude figure; the true rate for `0x43` specifically could be several× higher or lower. The qualitative conclusion (bounded kilobytes of garbage, not gigabytes, between events) is robust.

**When do garbage bytes occur, and at what rate?**

| Source | Mechanism | Rate estimate | Confidence |
|---|---|---|---|
| Baud mismatch across a version boundary | M16 moves the link 115200→250000 (`docs/M16-DESIGN-DECISIONS.md` §1). A 250000 board talking to a 115200 peer, or a stale host config, delivers framing-error garbage at full traffic rate. Telemetry links carry ~12 kB/s (589 B per 50 ms tick, three-board fleet), so 64 KiB of garbage ≈ **5–10 s of mixed-baud operation** to expected spurious cal. | Near-certain trigger if a mixed fleet ever runs; prevented today only by procedure (simultaneous reflash, §1.6) | High on the math; the exposure window is operational discipline, not code |
| Hot-plug / port open | USB CDC connect, DTR-pulse resets (macOS pulses DTR on every open — see `firmware/SETUP.md`), and cable reseating emit short bursts of junk bytes. | A handful of bytes per event; per event-leading byte ≈ 0.4 % chance of `'C'` at chunk start. Rare per event, but port opens happen dozens of times per bench day. | Medium — burst sizes unmeasured |
| EMI near motors | Motor switching noise coupling into UART lines. **Not hypothetical:** upstream m17 commit `17b4c8e` cites a real incident ("bench 2026-07-03, runaway FLHY") caused by motor-EMI serial garbage. | Unquantified; scales with motor load, wiring dress, cable length. Worst exactly when the robot is energized and moving — i.e., when a spurious cal is most dangerous. | Low precision, high consequence |
| Floating RX (dead/absent peer) | On upstream `main`, an unplugged follower cable or dead USB bridge leaves RX floating → continuous noise bytes. | Potentially kB/s of sustained garbage → spurious cal within minutes. Mitigated on `upstream/m17` (pull-ups), **still live on `main`**. | High on main |

## Worst case

**Spurious full-limb auto-calibration under load or near people.** One garbage `'C'` at chunk start → all local joints drive to mechanical stops via stall detection, and the leader forwards `"C"` to both followers, so all ~12 actuators move without any operator action. For the hardware this is the load calibration is designed to apply (stall-current-bounded). For anything *on or near* the robot it is the same hazard class as a legitimate auto-cal issued at the worst possible moment: a loaded robot shifts or collapses; a hand inside the leg envelope gets pinched at stall force. The EMI ingress path makes this most likely precisely when motors are energized.

**`'B'` partial-line lockup.** A truncated jog-bridge line freezes `loop()` indefinitely (1 s blocking timeout per read, loop never exits without a `'\n'`): telemetry stops, `updateAll()` stops, follower buffers overflow. If it hits mid-jog, the last commanded PWM state persists unrefreshed. Fail-frozen, not fail-safe — a denial of service on the only control channel.

## Prior art

Findings from a full survey of `flliver/krabby-research` (all branches, issues, PRs — 2026-07-07):

- **`upstream/m17`** (active, unmerged to `main`) hardens noise *ingress* and loop *starvation*, not command authenticity: commit `17b4c8e` ("firmware: harden leader loop against motor-EMI serial garbage") adds bounded drains (`FWD_DRAIN_BUDGET`), printable-ASCII filtering of follower→leader relay, RX0 pull-up, and single-byte non-blocking discard of unknown bytes; earlier m17 Task 1 work adds RX pull-ups on Serial1/Serial2, `RX_DRAIN_BUDGET`, and `setTimeout(50)` on all ports (documented in `firmware/COMMS_DEBUG.md` on m17; guarded by `tests/unit/firmware/test_floating_rx_guard.py`). **On m17 the `'C'` path still ends in unauthenticated actuation and still forwards `"C"` to followers; the `'B'` `while (true)` loop survives**, merely bounded per-read at 50 ms.
- **No checksum/CRC exists anywhere on the command protocol.** `git log --all -S checksum -S CRC` finds CRC only for EEPROM blocks (`firmware/arduino/eeprom_layout.h`). No issue, PR, or TODO on any branch acknowledges this specific hazard.
- **`upstream/main` and `upstream/mainline`** have none of the m17 mitigations; the dispatcher is fully exposed as quoted above.
- The only prior written acknowledgment is `docs/M16-DESIGN-DECISIONS.md` §1.5 (branch `m16-task1`), which names the fix direction ("a checksum or multi-byte preamble on command lines would close the hazard properly") and records it as out of M16 scope.
- Practical note: m17 touches exactly this dispatcher and is moving (last commit 2026-07-06); any fix should target **m17's dispatcher shape**, not main's.

## Mitigation options

| Option | What it does | Effort | Wire-format compatibility | Residual risk | Plausible owner |
|---|---|---|---|---|---|
| **A. Exact multi-byte calibration keyword + confirmation** — replace bare `'C'` with e.g. `CAL START\n` requiring exact token match; anything else on a `C`-leading line is discarded. Optionally require a second confirm line within a window. | Removes the single highest-severity path: garbage must now spell an exact ≥9-byte string (p ≈ 256⁻⁹ per chunk — effectively never). | **Low** — one dispatcher branch + the few cal senders (`firmware/cli.py`, GUI). m17 already parses a `CALL` variant on this path; coordinate there. | Breaks only cal senders; update host + firmware in one commit (same discipline as the M16 baud change). Follower forwarding switches to the same keyword — leader/follower flash together as already required. | `'B'` lockup and hypothetical garbage-`'J'` remain; telemetry/`'T'` untouched. | **M17** (dispatcher already in flight there) |
| **B. Line-level checksum on all command lines** — NMEA-style `*XX` suffix (CRC-8/XOR over the line); firmware rejects unchecksummed or bad-sum lines. | Authenticates every command, closing `'C'`, `'B'`, `'J'`, `'H'` in one mechanism. | **Medium** — firmware verify + all six host senders (`firmware/krabby_mcu.py`, `cli.py`, `gui/`, `hal/server/jetson/krabby_mcusdk.py`, `hal_server.py`) + leader→follower forwarding must re-sum or pass through. | **Not append-only**: old hosts break against new firmware unless a dual-accept transition mode is added, which temporarily voids the guarantee. Fits naturally into m17's planned "system-token vocabulary" comms work (see m17 TODO in `arduino.ino`). | Near zero for command spoofing; telemetry direction still unframed (acceptable — telemetry can't move motors). | **M17 follow-on / M18** |
| **C. Start-of-frame + length framing** — binary or `$`-prefixed frames with length byte and checksum; parser resyncs on SOF. | Full protocol integrity incl. partial-line handling (fixes `'B'` lockup structurally). | **High** — rewrite of both firmware parser and every host sender; test surface across three boards. | Complete break; requires a versioned cutover of the entire fleet + hosts. | Lowest of all options. | Dedicated protocol milestone (not M16/M17 scope) |
| **D. Rate-limit / ignore-when-armed** — accept `'C'` only when idle (no `'T'` traffic in last N s), or require two `'C'` lines within a window; drop otherwise. | Heuristic gate on the dangerous transition. | **Low** — firmware-only. | **Fully compatible** — zero wire change; old hosts keep working. | Heuristic: garbage arriving while idle still calibrates; does nothing for `'B'` lockup; "idle" is exactly when a bench operator's hands are in the robot. | M17 (stopgap only) |

All options should be paired with the m17 bounded-read pattern for `'B'` (exit the bridge loop on read timeout/empty token rather than spinning until `'\n'`) — that is a two-line change independent of wire format.

## Recommendation

**Option A — exact multi-byte calibration keyword with confirmation, targeted at `upstream/m17`'s dispatcher, paired with a timeout-exit in the `'B'` bridge loop.** Justification: the probability analysis shows the hazard is concentrated in the two first-byte-suffices commands, and only `'C'` produces motion; hardening it from a 1-in-256 chunk-start event to a ≥9-exact-byte match eliminates the actuation hazard outright for roughly a one-file firmware change plus two host call sites. Option B is the durable fix but is not append-only — it forces a coordinated all-hosts cutover on a file m17 is actively rewriting, and m17's own TODO already anticipates a system-token vocabulary that a checksum should be designed into rather than bolted ahead of. Option D's compatibility is attractive but it fails exactly the bench-operator scenario the worst case describes. Record Option B as the follow-on once m17's comms vocabulary lands.

## Validation

A bench TP in the existing `firmware/bench_tests/` ATP style (per `firmware/bench_tests/INDEX.md`: header table with **Traces**, Purpose, **Setup (from cold)**, Procedure, Pass criteria, Run log; next free id in a new area, e.g. `TP-CMD-01/02`, added to the INDEX inventory and traceability matrix). Reuse the timestamped serial console from the PMGMT.md Conventions block for evidence capture.

- **TP-CMD-01 — garbage-injection soak (no spurious actuation).** Setup: solo bench Mega + shield, fixed firmware commit, actuators connected or hall channels monitored. Procedure: (1) from a pyserial script, inject ≥ 1 MiB of uniform random bytes at the correct baud (≈16× the 64 KiB expectation — on unfixed firmware this run *should* trigger ≥ several spurious cals, establishing the test detects the defect); (2) repeat with the port opened at 115200 against 250000 firmware to reproduce the framing-error distribution; (3) throughout, log telemetry timestamps and any calibration start markers. Pass: **zero** `startAutoCalibration()` invocations (no cal log line, no hall-position movement), telemetry inter-line gap never exceeds 2× the 50 ms tick, and a valid `V` command round-trips normally after injection. Run first against unfixed firmware to record the failing baseline in the run log, then against the fix.
- **TP-CMD-02 — partial-`'B'`-line stall.** Procedure: send `B FLHY 100 ` (trailing space, **no newline**), then nothing for 30 s while watching telemetry timestamps; then send `\n` and a `V`. Pass (fixed firmware): telemetry cadence never gaps more than the bridge-loop timeout budget (e.g. ≤ 2 ticks), and the board answers `V` during the 30 s window. Unfixed firmware fails visibly: telemetry freezes for the full 30 s.
- **Regression guard:** a host-side unit test alongside `tests/unit/firmware/test_floating_rx_guard.py` asserting the firmware source no longer contains a single-byte `'C'` dispatch (same source-inspection pattern that file already uses), so the hazard cannot silently return in a dispatcher refactor.
