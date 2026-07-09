# Bench tests — OLED status display & disconnected-motor detection (M16 Task 2)
Traces: `patina-foundation-grants/grants/Krabby-Uno/Milestone16-I2C-Sensors/TASK-2-OLED-STATUS-DISPLAY.md` (AC 2a–2h) + OVERVIEW Qwiic daisy-chain pattern.
Hardware baseline: solo Arduino Mega 2560 R3 + Krabby-Uno shield (bench leader, ROLE_UNKNOWN), Qwiic OLED 1.3" @0x3D, SparkFun BMI270 @0x69 (ADR jumper cut), Qwiic→Dupont bus on 3V3/GND/D20/D21, Klein multimeter; TP-10/11 need an actuator rig, TP-12 the 3-board robot.

---

# TP-OLED-01 — Bus integration scan: OLED daisy-chained at 0x3D alongside BMI270

| | |
|---|---|
| **Traces** | TASK-2 AC 2a; spec §1 (0x3D default, 0x3C jumpered); OVERVIEW Qwiic daisy-chain pattern |
| **Status** | draft |
| **Hardware** | Mega 2560 + Krabby-Uno shield, SparkFun BMI270 (ADR cut), Qwiic OLED 1.3", Qwiic→Dupont adapter + one Qwiic cable, 2× M-M Dupont jumpers, Klein multimeter |
| **Est. time** | 20 min |

## Purpose
Proves the Qwiic OLED coexists on the shared leader I2C bus with the BMI270 — both ACK at their expected addresses (0x3D and 0x69), no address conflict, and the bus is electrically healthy (idle SDA/SCL high, 3V3 rail in spec under the added load) — before any driver code runs. Specifically de-risks the earlier-draft 0x3C confusion: 0x3D is the OLED default; 0x3C means the address jumper is set.

## Setup (from cold)
1. From `krabby-research`: `make venv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. Plug the Mega in over USB. Find the port: `ls /dev/cu.usbmodem*` (macOS) or `ls /dev/ttyACM*` (Linux). macOS: if nothing enumerates, approve the board under System Settings → Privacy & Security ("Allow accessory to connect"). Then `export PORT=<device>`.
3. **SAFETY:** Before connecting any sensor, verify the shield's 3V3 rail per SETUP.md "Bench bring-up runbook" step 1 (M-M jumpers in 3V3/GND, probe the free ends): expect **3.30 ± 0.1 V**. Both the BMI270 and the OLED are 3.3 V parts — this check is the one that saves them.
4. Unplug USB. Wire the Qwiic→Dupont adapter per SETUP.md runbook step 2 (black→GND, red→3V3, blue→D20, yellow→D21) into the BMI270's first Qwiic jack, then daisy-chain the OLED off the BMI270's second Qwiic jack with the Qwiic cable.
5. Re-plug USB and flash the scanner:
   ```sh
   arduino-cli compile --fqbn arduino:avr:mega firmware/bench_sketches/i2c_scanner
   arduino-cli upload -p $PORT --fqbn arduino:avr:mega firmware/bench_sketches/i2c_scanner
   ```

## Procedure
1. Open the serial monitor (opening the port resets the board — expect the banner after ~2 s):
   ```sh
   python -m serial.tools.miniterm $PORT 250000
   ```
2. Read the first line: `idle SDA(D20)=1 SCL(D21)=1`.
3. Let at least two full scan sweeps print (`scan done, devices: N` twice). Record every `FOUND 0x..` line.
4. With the scanner still running (bus under load), repeat the 3V3 rail measurement from Setup step 3 and record the reading.
5. Exit miniterm (Ctrl-]) and reflash the real firmware: `make -C firmware upload-firmware PORT=$PORT`.

## Pass criteria
- Idle levels report `SDA(D20)=1 SCL(D21)=1`.
- Exactly two devices found, at **0x3D** and **0x69**, identical across both sweeps.
- No `BUS TIMEOUT` line in either sweep.
- 3V3 rail with both devices attached reads 3.30 ± 0.1 V.
- 0x3C does **not** appear (if it does: OLED address jumper is set — fix the jumper, not the firmware).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-06 | John Bolt | 94edd67..00237a8 | partial | Task 1 bring-up: same bus scanned with BMI270 only — found 0x69 (ADR cut), idle SDA/SCL=1, 3V3 rail verified in spec per runbook step 1. OLED not yet attached. |

---

# TP-OLED-02 — OLED init and krab render on solo bench leader

| | |
|---|---|
| **Traces** | TASK-2 AC 2a, 2b; spec §2 layout, §5 "Display up" |
| **Status** | draft |
| **Hardware** | TP-OLED-01 rig (Mega + shield, BMI270 + OLED daisy-chained) |
| **Est. time** | 15 min |

## Purpose
Proves the Task 2 firmware initializes the `Qwiic1in3OLED` at 0x3D and renders the stylized krab — three controller-thirds, six legs/hips, two rear battery bars (placeholder), edge text strip (role, IMU roll/pitch) — legibly at 128×64. On the solo bench board both follower thirds must render "missing", which is the degenerate AC 2c case (no election peers, no forwarded telemetry) reachable without the robot.

## Setup (from cold)
1. Venv + port discovery as in TP-OLED-01 Setup steps 1–2.
2. Bus wired and verified per TP-OLED-01 (BMI270 + OLED both ACKing).
3. From the Task 2 working branch, flash: `make -C firmware upload-firmware PORT=$PORT`.

## Procedure
1. Watch boot and telemetry: `python firmware/scripts/imu_bench.py $PORT watch --seconds 20`. Expect the solo-leader boot sequence per SETUP.md runbook step 3 (`ROLE: UNKNOWN`, `IMU CAL: BMI270 online at 0x69`) plus the Task 2 OLED-init log line reporting success at 0x3D.
2. Inspect the panel and record yes/no for each: (a) body drawn as three distinct controller regions; (b) six legs/hips drawn; (c) two stacked battery bars on the rear; (d) edge text strip showing role and IMU roll/pitch; (e) each element distinguishable at arm's length.
3. Solo-board presence check: confirm the front/own third renders **filled** and both follower thirds render **outline/missing**.
4. Live-data check (hold-based): pick the board+sensor up, roll it ~90° onto its side, and **hold it there for 10 s**. The text-strip roll value must move from ≈0° to a held ≈±90° and stay there while held; return it flat and confirm roll returns to ≈0°.

## Pass criteria
- Boot log contains an OLED init-success line naming address 0x3D.
- All five render elements from Procedure step 2 present and distinguishable (5/5 yes).
- Own third filled; both follower thirds render as missing/outline.
- Text-strip roll reads within ±15° of 0 when flat and within ±25° of 90 while held on its side, for the full 10 s hold.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-OLED-03 — Init-failure resilience: boot with OLED unplugged

| | |
|---|---|
| **Traces** | TASK-2 AC 2a; spec §5 "init/refresh failure handled" |
| **Status** | draft |
| **Hardware** | TP-OLED-01 rig with the OLED's Qwiic cable disconnected; BMI270 stays wired |
| **Est. time** | 10 min |

## Purpose
Proves a failed OLED init is non-fatal to control: with the display absent at boot, role election completes, telemetry keeps streaming at 250000 baud, and the IMU segment stays valid. This is the "customer unplugged the face panel" case — the robot must not brick.

## Setup (from cold)
1. Venv + port discovery as in TP-OLED-01 Setup steps 1–2.
2. Task 2 firmware already flashed (TP-OLED-02 Setup step 3).
3. With USB unplugged, disconnect the OLED's Qwiic plug; leave the BMI270 wired to the Mega.

## Procedure
1. Plug USB in and run `python firmware/scripts/imu_bench.py $PORT watch --seconds 30` (port open resets the board; boot logs are echoed).
2. Record the boot lines: role election result, IMU init result, and the OLED init-failure line.
3. Confirm parsed IMU samples print for the full 30 s window (~1/s) with `|accel| ≈ 9.81 m/s²`.
4. Watch for gaps between printed samples. `imu_bench.py` watch mode does **not** echo boot lines once telemetry has started, so a reset is detected by silence, not by a reprinted banner: a crash/reset costs ≥4 s of boot + role election, which shows as a >3 s gap in the ~1/s sample stream.

## Pass criteria
- Boot log shows an explicit OLED init-failure message (not a hang) followed by `ROLE: UNKNOWN (front actuators)` telemetry startup.
- Telemetry lines flow continuously for 30 s; IMU segment `valid=1` throughout (samples print).
- No gap >3 s between consecutive printed samples (a watchdog/crash reset would cost ≥4 s of boot and show as a gap; watch mode cannot show the banner itself).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-OLED-04 — Hot-pull refresh-failure resilience

| | |
|---|---|
| **Traces** | TASK-2 AC 2a; spec §5 "pull its Qwiic plug and confirm the firmware keeps running" |
| **Status** | draft |
| **Hardware** | TP-OLED-01 rig, OLED at the **end** of the daisy chain (Mega → BMI270 → OLED) so pulling it leaves the BMI270 connected |
| **Est. time** | 15 min |

## Purpose
Proves a refresh-time I2C failure (display yanked mid-operation) does not stall the gait/telemetry loop: no hang on the failed write, no watchdog reset, tick cadence unchanged in the serial stream, and the BMI270 upstream of the pulled plug keeps reporting `valid=1`. Recovery on replug is a nice-to-have; non-crash is the AC.

## Setup (from cold)
1. Venv + port discovery as in TP-OLED-01 Setup steps 1–2.
2. Full TP-OLED-01 wiring with the chain ordered Mega → BMI270 → OLED; Task 2 firmware flashed; display rendering (TP-OLED-02 passing).

## Procedure
1. Start a timing capture: `python firmware/scripts/imu_bench.py $PORT timing --lines 400` (≈20 s window). Keep the board still.
2. About 5 s into the capture, pull the OLED's Qwiic plug and **hold it disconnected for the remainder of the capture** (hold-based: the effect is verifiable in the timing stats and boot-log absence, not in when exactly you pulled).
3. Record the printed mean/p50/p95/max. Timing mode silently skips non-telemetry lines, so a mid-capture reset is detected in the stats, not on screen: a reset costs ≥4 s of boot + role election and would blow the max stat past several thousand ms.
4. Verify the IMU survived the pull: `python firmware/scripts/imu_bench.py $PORT watch --seconds 15` — samples must print (`valid=1`).
5. Optional (recovery, non-gating): replug the OLED and note whether the render resumes without a power cycle.

## Pass criteria
- Timing capture completes all 400 lines (no stream stall).
- Mean tick within ±1.0 ms and max below 70 ms vs the TP-OLED-08 / TP-OLED-09 baselines (no hang-induced outlier from the pull). The 70 ms max bound doubles as the reset detector — a watchdog reset would appear as a ≥4 s outlier.
- Post-pull IMU watch prints valid samples for the full 15 s.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-OLED-05 — Floating-channel noise characterization (bug reproduction, threshold selection)

| | |
|---|---|
| **Traces** | TASK-2 AC 2e, 2f; spec §4 "real bug" — floating pinIS/pinPot stream noise |
| **Status** | draft |
| **Hardware** | Mega + shield, no motors wired (the solo shield's natural state); BMI270/OLED presence irrelevant |
| **Est. time** | 30 min |

## Purpose
Reproduces and quantifies the bug Task 2 fixes: with no motor wired, `pinPot` (A0–A5) and `pinIS` (A6–A11) float and the firmware streams the ADC noise as real position/current. Per-channel statistics — pot/pos jitter band, and `avgIS` behavior with EN driven vs idle — are the data that set the `isConnected()` current-signature threshold and the sane-band pot check in `actuator_manager.h`. Existing Task 1 captures (commits 94edd67..00237a8, all six channels floating) are a starting corpus, but per-channel stats have not been extracted; this procedure produces them.

## Setup (from cold)
1. Venv + port discovery as in TP-OLED-01 Setup steps 1–2.
2. Confirm zero motors/actuators are wired to the shield's channel headers.
3. Flash current firmware (pre-fix Task 1 build reproduces the bug; the Task 2 build must expose raw pot/current for the same analysis): `make -C firmware upload-firmware PORT=$PORT`.

## Procedure
1. Capture 60 s of raw telemetry, EN idle (key-control tool not running):
   ```sh
   python3 - "$PORT" <<'EOF'
   import sys, time, serial
   ser = serial.Serial(sys.argv[1], 250000, timeout=2)
   end = time.time() + 60
   with open("firmware/build/floating_idle.txt", "w") as f:
       while time.time() < end:
           f.write(ser.readline().decode("ascii", errors="replace"))
   ser.close()
   EOF
   ```
2. Extract per-channel stats through the real parser:
   ```sh
   python3 - firmware/build/floating_idle.txt <<'EOF'
   import sys, statistics as st
   from firmware.interfaces.joint_telemetry import parse_telemetry_line
   chans = {}
   for line in open(sys.argv[1]):
       for j in parse_telemetry_line(line).joints:
           d = chans.setdefault(j.name, {"pos": [], "pot": [], "cur": []})
           d["pos"].append(j.pos); d["pot"].append(j.pot); d["cur"].append(j.current)
   for name, d in sorted(chans.items()):
       print(name, " ".join(f"{k}: mean {st.mean(v):.3f} std {st.pstdev(v):.3f} min {min(v):.3f} max {max(v):.3f}"
                            for k, v in d.items()))
   EOF
   ```
   (Each `JointTelemetry` carries `pos`, `pot`, `current`, `en`, `pwm`, `saf` — the fixed 9-token layout in SETUP.md §2.2.)
3. EN-driven capture (current signature with EN high, no motor): the interactive tool is **direct key control** (no menu options, no joint-name prompt — `firmware/__main__.py`; SETUP.md's "Feature 2" text predates this). The slot-0 channel (LHY wiring: D2/D3, EN D22, A0, A6) is joint **`FLHY`**, extend key **'E'**. Capture the raw wire to a file while you drive it:
   ```sh
   KRABBY_MCU_RAW_RX=1 python -m firmware --debug 2> firmware/build/floating_driven.txt
   ```
   then **hold 'E' continuously for 30 s** (with no '1'/'2' held, keys drive the FRONT set), release, and quit with ESC. The hold is the binary action — EN/PWM are visible per-tick in the captured segments, so the driven window is identifiable in the data, not by wall-clock. (Each captured line carries a `[serial rx] ` prefix; the parser drops that segment and still parses the joint segments.)
4. Repeat step 2's analysis over `firmware/build/floating_driven.txt` (filter to `FLHY` segments whose `en` tuple is nonzero) and record floating-`avgIS`-while-driven vs idle.
5. Record the per-channel table and a proposed `isConnected()` current threshold + pot sane-band in the grant folder notes (`patina-foundation-grants/grants/Krabby-Uno/Milestone16-I2C-Sensors/NOTES.md`).

## Pass criteria
- ≥ 500 telemetry lines parsed per capture; all six channels present in the stats table.
- Per-channel mean/std/min/max recorded for pos, pot, current, for both idle and EN-driven conditions.
- Bug confirmed: at least one floating channel shows pot/pos std > 0 (noise streamed as position).
- A concrete threshold proposal (current signature + pot sane-band, with the measured floating band it must reject) is written down.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-OLED-06 — Disconnected detection + position filtering, all channels floating (negative side)

| | |
|---|---|
| **Traces** | TASK-2 AC 2e, 2f; spec §4.1, §4.2, §5 "Disconnect" |
| **Status** | draft |
| **Hardware** | TP-OLED-01 rig (OLED attached), no motors wired |
| **Est. time** | 15 min |

## Purpose
Verifies the fix end-to-end on the negative side, needing no actuator: with Task 2 firmware and zero motors wired, all six channels must report `isConnected()==false` — the OLED renders hollow/✕ on every leg (never a spurious ▲/▼ from noise), and `printTelemetry()` reports the invalid sentinel or held last-valid value instead of live floating-ADC noise, checked on the wire through the extended `joint_telemetry.py` parser.

## Setup (from cold)
1. Venv + port discovery as in TP-OLED-01 Setup steps 1–2.
2. TP-OLED-01 wiring, zero motors on the channel headers; Task 2 firmware flashed: `make -C firmware upload-firmware PORT=$PORT`.

## Procedure
1. Capture 60 s of telemetry and check every joint segment through the parser:
   ```sh
   python3 - "$PORT" <<'EOF'
   import sys, time, serial
   from firmware.interfaces.joint_telemetry import parse_telemetry_line
   ser = serial.Serial(sys.argv[1], 250000, timeout=2)
   end = time.time() + 60
   pos_seen, bad = {}, 0
   while time.time() < end:
       p = parse_telemetry_line(ser.readline().decode("ascii", errors="replace"))
       for j in p.joints:
           pos_seen.setdefault(j.name, set()).add(j.pos)
           if getattr(j, "connected", 0):
               bad += 1
   for name, vals in sorted(pos_seen.items()):
       print(name, "distinct pos values:", len(vals), sorted(vals)[:3])
   print("segments claiming connected=1:", bad)
   EOF
   ```
   (If the connected flag rides in a different field name, adapt the one `getattr` — the wire extension is append-only per spec §4.)
2. While the capture runs, watch the OLED for the full 60 s and record whether any leg glyph ever shows ▲ or ▼.
3. Optional cross-check on the GUI parser path: `python -m firmware.gui --port $PORT` and confirm the six joints show the sentinel/held position, not moving values.

## Pass criteria
- Zero segments report connected=1 over the 60 s capture — **non-vacuously**: first confirm the extended parser actually exposes the connected field on a parsed segment (print the field name in use). If the `getattr` never finds the field, the run is invalid, not a pass.
- Each channel's reported position is the sentinel or a single held value (distinct-value count = 1 per channel) — not a noise stream.
- No leg glyph shows ▲/▼ at any point in the 60 s observation; all six show ○/✕.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-OLED-07 — Discrete red status LED / alarm GPIO on disconnected-motor

| | |
|---|---|
| **Traces** | TASK-2 AC 2g; spec §1 free-pin check vs board_pins.h, §4 "Reflect disconnected on the discrete LED"; reused by Task 4 |
| **Status** | draft |
| **Hardware** | TP-OLED-06 rig, red LED + ~330 Ω resistor (Klein multimeter substitutes if no LED in hand), 2× M-M Dupont jumpers |
| **Est. time** | 20 min |

## Purpose
Proves the discrete alarm GPIO: the chosen pin is genuinely free for `KRABBY_PIN_REV 3` (D2–D13 PWM, D22–D27 EN, D50–D52/A12–A14 Hall are taken; the D30–D49 band is open), it stays quiet through boot (no false alarm during init), and it asserts — LED lit/blinking — while any channel is disconnected, which on the bare bench is all of them. The same pin is reused for Task 4's low-battery alarm, so the electrical verification pays twice.

## Setup (from cold)
1. Venv + port discovery as in TP-OLED-01 Setup steps 1–2.
2. Verify the chosen pin (candidate: D30) is unclaimed. `board_pins.h` only defines PWM + EN — Hall pins are port-masked in `hall_hw.h` (rev 3: D50–D52 + A12–A14, per its header comment) and D20/D21 are the I2C bus. Check all three: `grep -n "PIN_" firmware/arduino/board_pins.h` (pin absent from the active `KRABBY_PIN_REV == 3` block), `sed -n 1,10p firmware/arduino/hall_hw.h` (pin not in the rev-3 Hall list), and confirm it is not D20/D21.
3. With USB unplugged, wire pin → resistor → LED anode, LED cathode → GND (or clip the Klein meter, DC volts, between the pin and GND if no LED yet).
4. Task 2 firmware (with the alarm pin compiled in) flashed: `make -C firmware upload-firmware PORT=$PORT`. No motors wired — every channel will read disconnected.

## Procedure
1. With the meter across the pin, plug USB in and watch the reading continuously through the whole boot (role election + sensor init, ~4 s): it must stay low until detection has actually settled.
2. After telemetry starts (verify with `python firmware/scripts/imu_bench.py $PORT watch --seconds 10`), observe the LED/meter for 60 s: solid-on reads > 4.0 V; blinking shows as the meter alternating between < 0.5 V and > 4.0 V (and the LED visibly flashing).
3. Record which behavior (solid vs blink) the firmware implements and its period if blinking (count flashes over a 30 s hold).
4. Note: the "extinguishes when no alarm" half cannot be shown on the bare bench (all channels are always disconnected here); it is exercised by TP-OLED-11's replug step.

## Pass criteria
- Chosen pin absent from every active pin define in `board_pins.h` (rev 3 block).
- Pin reads < 0.5 V for the entire boot window (no false alarm during init).
- After detection settles, LED is visibly lit or blinking for the full 60 s observation; meter confirms > 4.0 V asserted level.
- Behavior (solid/blink + period) recorded for Task 4 reuse.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-OLED-08 — Loop-timing baseline without OLED (pre-existing)

| | |
|---|---|
| **Traces** | TASK-2 AC 2h; spec §3 "Non-blocking"; SETUP.md "Loop timing (AC 1c)" table |
| **Status** | verified-on-bench |
| **Hardware** | Solo Mega 2560 R3 + shield, USB only (BMI270 optional — rows exist for absent/attached) |
| **Est. time** | 15 min |

## Purpose
Establishes the no-OLED loop-timing baseline that the AC 2h A/B comparison (TP-OLED-09) is judged against: host-side inter-line arrival stats for the solo bench leader's telemetry, captured with `imu_bench.py` timing mode. Already run during Task 1 bring-up; the numbers live in SETUP.md's "Loop timing (AC 1c)" table and are mirrored in the run log below.

## Setup (from cold)
1. Venv + port discovery as in TP-OLED-01 Setup steps 1–2.
2. No OLED on the bus. Flash the build under test: `make -C firmware upload-firmware PORT=$PORT`.
3. Place the board on the bench and leave it untouched for the capture.

## Procedure
1. `python firmware/scripts/imu_bench.py $PORT timing --lines 400` (keep the board still; port open resets the board and the tool waits through boot).
2. Record line length, mean/p50/p95/max into SETUP.md's timing table with build + baud noted.

## Pass criteria
- 400 lines captured with no stream stall.
- Mean tick within 50 ± 2 ms (the 50 ms telemetry tick, not serial-bound).
- Stats recorded in SETUP.md "Loop timing (AC 1c)" table with build identity.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-03 | John Bolt | upstream/main | pass | @115200: 180 B lines, mean 50.72 ms, p95 53.29, max 57.09 (400 lines). |
| 2026-07-06 | John Bolt | 94edd67..00237a8 | pass | M16 Task 1 @250000, IMU absent (valid=0 path): 229 B lines, mean 50.77 ms, p95 53.38, max 58.84. Delta +0.05 ms mean vs upstream — inside run-to-run noise. IMU-attached row still TBD in SETUP.md. |

---

# TP-OLED-09 — Loop timing A/B with OLED active vs removed

| | |
|---|---|
| **Traces** | TASK-2 AC 2h; spec §5 "Timing: loop timing unchanged with the OLED active vs removed" |
| **Status** | draft |
| **Hardware** | TP-OLED-01 rig (BMI270 + OLED), Task 2 firmware |
| **Est. time** | 25 min |

## Purpose
The AC 2h evidence: with the Task 2 build's throttled (5–10 Hz, partial-page) refresh active, loop timing must be unchanged vs the display removed and vs the TP-OLED-08 baseline. The IMU-attached-no-OLED row (currently TBD in SETUP.md) is captured first so the OLED's delta is isolated from the ~4 ms live IMU read that also lands inside the tick.

## Setup (from cold)
1. Venv + port discovery as in TP-OLED-01 Setup steps 1–2.
2. TP-OLED-01 wiring; Task 2 firmware flashed: `make -C firmware upload-firmware PORT=$PORT`; TP-OLED-02 passing (display rendering).
3. Board still on the bench for every capture.

## Procedure
1. Run A — IMU attached, OLED **unplugged** (pull the Qwiic plug at the OLED end before opening the port): `python firmware/scripts/imu_bench.py $PORT timing --lines 400`. This also fills SETUP.md's TBD "IMU attached" row for the Task 2 build.
2. Run B — OLED **attached and rendering** (replug, power-cycle, confirm the krab is drawn): `python firmware/scripts/imu_bench.py $PORT timing --lines 400`.
3. Repeat runs A and B once each (2×2 total) to bound run-to-run noise.
4. Log all four rows (build, baud, condition, line length, mean/p95/max) into SETUP.md's "Loop timing (AC 1c)" table and this run log.

## Pass criteria
- All four captures complete 400 lines.
- OLED-on vs OLED-off: |Δmean| ≤ 0.5 ms and |Δp95| ≤ 2.0 ms (each within the spread of its own repeat pair).
- OLED-on vs TP-OLED-08 IMU-absent baseline: mean within ±1.0 ms, max < 70 ms.
- SETUP.md timing table updated, including the previously-TBD IMU-attached row.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-OLED-10 — Actuator state glyphs under jog (extend/retract/holding)

| | |
|---|---|
| **Traces** | TASK-2 AC 2d; spec §1 glyph table, §3 per-actuator state, §5 "Glyphs" |
| **Status** | draft — blocked (actuator rig) |
| **Hardware** | TP-OLED-01 rig **plus** one real linear actuator on a shield channel, BTS7960 driver, 12 V motor supply |
| **Est. time** | 30 min |

## Purpose
Proves the `currentPwm`/`hasTarget`-to-glyph mapping with a real load: extend (+PWM) renders ▲, retract (−PWM) renders ▼, and released-with-target-held (attached, ~0 PWM) renders the filled dot ● — i.e. `isConnected()==true` renders as an attached state, never hollow. This is the positive case TP-OLED-06 cannot show.

## Setup (from cold)
1. **BLOCKER:** requires a real linear actuator + BTS7960 channel powered from a 12 V motor supply — not in the bench kit (actuators live on the 3-board robot). Document stands ready; do not attempt with a floating channel.
2. Venv + port discovery as in TP-OLED-01 Setup steps 1–2.
3. With USB and 12 V both unplugged, wire one actuator to channel `LHY` per SETUP.md §1 (PWM D2/D3, EN D22, pot A0, IS A6) — this channel is joint **`FLHY`** in commands and telemetry. **SAFETY:** connect the 12 V motor supply last, after all signal wiring is seated, and keep hands clear of the actuator's travel during jogs.
4. Task 2 firmware flashed: `make -C firmware upload-firmware PORT=$PORT`. Run auto-calibration once if this actuator has never been calibrated on this board: press **'9'** in the key-control tool (step 1 below) — stand back first, the calibration sequence drives the wired actuator through its full travel.

## Procedure
1. Start the interactive key-control tool: `python -m firmware` (auto-detects the port; set `KRABBY_MCU_PORT=$PORT` to pin it). There is no menu or joint prompt — keys map directly to joints (`firmware/__main__.py`; SETUP.md's "Feature 2" text predates this): extend Q W E R T Y / retract A S D F G H over the FRONT set `FLKL FLHL FLHY FRHY FRHL FRKL`, so `FLHY` = extend **'E'**, retract **'D'**. ESC quits.
2. **Hold 'E' for a full 5 s** (extend, no '1'/'2' held). While held: OLED glyph for that leg must show ▲, and pwm sign in telemetry is + for the whole hold.
3. Release, then **hold 'D' for a full 5 s** (retract): glyph ▼, pwm sign −.
4. Release with the target held (attached, ~0 PWM): within one refresh interval the glyph must settle to ● and stay ● for a 10 s observation.
5. Cross-check the wire: a second terminal on the same port is not possible (the tool owns it), so quit (ESC) and rerun with the raw wire captured to a file — `KRABBY_MCU_RAW_RX=1 python -m firmware 2> firmware/build/glyph_jog.txt` — repeat steps 2–4, quit, then read the `FLHY` EN/PWM fields in the captured segments to confirm glyph-state ↔ telemetry-state agreement.

## Pass criteria
- ▲ shown for the entire extend hold; ▼ for the entire retract hold; no glyph flicker to ○/✕ while driving.
- ● shown within one refresh period of release and held for 10 s.
- Telemetry PWM sign matches the glyph in every observed state (agreement in the captured-wire pass).
- The wired channel never renders ○/✕ while powered and connected.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-OLED-11 — Live disconnected-motor detection end-to-end (unplug a real actuator)

| | |
|---|---|
| **Traces** | TASK-2 AC 2e, 2f, 2g; spec §4, §5 "Disconnect" — explicitly requested |
| **Status** | draft — blocked (actuator rig) |
| **Hardware** | TP-OLED-10 rig (actuator + 12 V supply) plus the TP-OLED-07 status LED |
| **Est. time** | 20 min |

## Purpose
The definitive positive-to-negative proof that the current-signature threshold separates connected from floating — the transition TP-OLED-06 cannot exercise. With an actuator attached and showing ●, unplugging its motor connector live must flip the glyph to ○/✕, light the discrete red LED, and freeze that joint's telemetry position to sentinel/last-valid instead of streaming floating-ADC noise; replugging must re-detect. This is the spec §5 "Disconnect" scenario verbatim.

## Setup (from cold)
1. **BLOCKER:** same rig as TP-OLED-10 (real linear actuator + 12 V motor supply); blocked until that hardware is on the bench.
2. TP-OLED-10 setup complete and passing (actuator on `FLHY`, calibrated, glyph ● at rest); status LED wired per TP-OLED-07.

## Procedure
1. Run `python -m firmware --debug` so per-tick segments scroll (stderr) while you work. Confirm `FLHY` shows connected/● and the status LED matches the expected bare-bench state for the other five channels (per TP-OLED-07 behavior).
2. **SAFETY:** confirm ~0 PWM on `FLHY` (holding state, no jog keys held) before touching the connector — never separate a motor connector under drive; the inductive kick arcs the contacts.
3. Unplug the actuator's motor connector and **hold it disconnected for 30 s**. Record: (a) time for the glyph to flip to ○/✕, (b) status LED asserting, (c) the `FLHY` position field in the scrolling telemetry — it must freeze at sentinel/last-valid, not wander.
4. Replug the connector and **leave it seated for 30 s**. Record re-detection: glyph returns to ●, position field resumes tracking the pot.
5. Repeat the unplug/replug cycle once more to show the detection is not a one-shot.

## Pass criteria
- Glyph flips ● → ○/✕ within 2 s of unplug, both cycles.
- Status LED asserts while unplugged and clears (for this channel's contribution) on replug, both cycles.
- During each 30 s unplugged hold, the reported position is the sentinel or one held value — zero noise-driven position changes.
- On replug, connected state and live position tracking return within 5 s, both cycles.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-OLED-12 — Controller presence: follower power-off flips body-third to missing and recovers

| | |
|---|---|
| **Traces** | TASK-2 AC 2c; spec §3 per-controller presence (election + forwarded-telemetry freshness), §5 "Presence" |
| **Status** | draft — blocked (3-board robot) |
| **Hardware** | Assembled 3-board robot: leader (FRONT, USB + OLED) + two follower Megas with Serial1/Serial2 cross-wiring |
| **Est. time** | 30 min |

## Purpose
Proves presence is derived from forwarded-telemetry freshness (`forwardFullLines` last-seen tracking), not just boot-time election: killing a live follower must flip its body-third from filled to outline within the staleness timeout, and restoring it must recover the third. The solo ROLE_UNKNOWN bench board cannot exercise this — it has no serial peers — so this runs only on the assembled robot.

## Setup (from cold)
1. **BLOCKER:** requires the 3-board robot (two follower Megas + leader with serial cross-wiring); not runnable on the solo bench kit.
2. Venv + port discovery as in TP-OLED-01 Setup steps 1–2, against the **leader's** USB port. Note the leader needs the 256-byte RX buffer — any `make`-built image has it (SETUP.md §2.1).
3. Flash all three boards with the Task 2 build (`make -C firmware upload-firmware PORT=...` per board, or `make -C firmware flash-remote REMOTE=... PORT=...` if the robot hangs off the Orin). OLED on the elected FRONT leader.
4. Power the robot; confirm election yields FRONT + LEFT + RIGHT (all three thirds filled on the OLED) and forwarded lines from both followers appear on the leader's USB stream.

## Procedure
1. Watch the leader stream: `python firmware/scripts/imu_bench.py $PORT watch --seconds 300` in one terminal (boot logs + IMU keep-alive), eyes on the OLED.
2. Power off the LEFT follower and **keep it off for 60 s**. Record: time from power-off to its body-third flipping filled → outline (must be within the firmware's staleness timeout, which mirrors the OLED command-freshness timeout), and that the leader's own telemetry keeps streaming throughout.
3. Power the LEFT follower back on and **leave it on for 60 s**: its third must return to filled once its forwarded lines resume.
4. Repeat steps 2–3 for the RIGHT follower.
5. Confirm at no point did the FRONT third flip or the leader reset. Watch mode does not echo boot lines after telemetry starts, so a leader reset shows as a >3 s silence in the ~1/s IMU sample stream (boot + role election costs ≥4 s), not as a banner.

## Pass criteria
- Each powered-off follower's third flips to outline/missing within the configured staleness timeout + one OLED refresh period, for both followers.
- Each third recovers to filled within 10 s of the follower's telemetry resuming, for both followers.
- Leader telemetry stream uninterrupted across all four transitions: no gap > 3 s between printed watch samples (nominal cadence is ~1 s by design — `imu_bench.py` throttles to one print per second — so a 3 s bound is the reset/stall detector).
- FRONT third stays filled throughout.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |
