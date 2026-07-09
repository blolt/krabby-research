# Bench test procedures — PWR: octopus power bus + INA228 battery monitoring (M16 Task 3)
Traces: `patina-foundation-grants/grants/Krabby-Uno/Milestone16-I2C-Sensors/TASK-3-POWER-BUS-INA228.md` (AC 3a–3j), plus OVERVIEW no-new-transport constraint and Task 1 AC 1c timing method.
Hardware baseline: Arduino Mega 2560 R3 + Krabby-Uno shield (solo bench leader, ROLE_UNKNOWN), BMI270 @0x69 (ADR cut), Qwiic OLED @0x3D, 2× Adafruit INA228 @0x40/0x41, 200 A/75 mV shunt, 150 A ANL fuse, Klein DMM; TP-PWR-09..13 additionally require the M12 2× 12 V 100 Ah LiFePO4 pack (blocked until M12).

---

# TP-PWR-01 — INA228 pair I2C presence on bench bus (no battery)

| | |
|---|---|
| **Traces** | TASK-3 AC 3d (0x41 A0 strap), 3h (addresses); spec §3 topology |
| **Status** | draft |
| **Hardware** | Mega 2560 + Krabby-Uno shield, BMI270 breakout, Qwiic OLED, 2× Adafruit INA228, Qwiic cables + Qwiic→Dupont adapter, soldering iron (A0 strap), USB cable |
| **Est. time** | 20 min |

## Purpose
Proves both INA228 boards enumerate at their assigned addresses (Pack 0x40 default, Midpoint 0x41 via A0 solder-jumper strap) on the shared 100 kHz bus behind the BMI270 and OLED, with zero battery risk — INA228 logic runs from Qwiic 3.3 V and the VBUS/shunt pins stay unconnected. Catches address-strap mistakes, bus shorts, and dead boards before any firmware or power work depends on them.

## Setup (from cold)
1. Clone `krabby-research`, check out the M16 Task 3 working branch (the branch this file lives on), `cd krabby-research`.
2. `make venv && source testenv/bin/activate && pip install -r firmware/requirements.txt`
3. Install `arduino-cli` (see `firmware/SETUP.md` §2, "Make + arduino-cli" bullet) and the AVR core: `arduino-cli core install arduino:avr`. (`make -C firmware upload-firmware` installs the core itself, but the bare `arduino-cli compile` below does not.)
4. Solder-bridge the **A0 jumper on the Midpoint INA228 only** (sets 0x41; the Pack board stays default 0x40). Mark the Midpoint board physically so the two can't be swapped later.
5. **SAFETY:** wire with USB unplugged, and only onto the Mega **3V3** pin — the BMI270 sharing this bus is not 5 V tolerant. Wiring: Qwiic→Dupont black→GND, red→3V3, blue→D20 (SDA), yellow→D21 (SCL); then daisy-chain BMI270 → OLED → Pack INA228 → Midpoint INA228 with Qwiic cables. Leave every INA228 VBUS/IN+/IN− screw terminal empty.
6. Plug in USB. Find the port: `ls /dev/cu.usbmodem*` (macOS — if nothing enumerates, approve the board under System Settings → Privacy & Security "Allow accessory to connect") or `ls /dev/ttyACM*` (Linux), then `export PORT=<device>`.
7. Flash the scanner sketch:
   ```sh
   arduino-cli compile --fqbn arduino:avr:mega firmware/bench_sketches/i2c_scanner
   arduino-cli upload -p $PORT --fqbn arduino:avr:mega firmware/bench_sketches/i2c_scanner
   ```

## Procedure
1. Open the serial monitor. Opening the port resets the board, which is what you want here: the `idle SDA/SCL` line prints **once at boot** (right after the reset), then the `FOUND`/`scan done` block repeats every ~3 s:
   ```sh
   python -m serial.tools.miniterm $PORT 250000
   ```
2. Record the `idle SDA(D20)=... SCL(D21)=...` line and every `FOUND 0x..` line from one complete scan cycle (exit with Ctrl+]).
3. If an expected address is missing: reseat that board's Qwiic cable and re-read one scan cycle. No `0x41` (and `devices: 3`) means the A0 strap didn't take — re-solder and rescan. (Two devices strapped to the same address ACK as one `FOUND` line — the device count dropping by one is the tell.)
4. Reflash the real firmware afterwards: `make -C firmware upload-firmware PORT=$PORT`.

## Pass criteria
- `idle SDA(D20)=1 SCL(D21)=1` (neither line stuck low).
- Scan reports exactly: `FOUND 0x3D` (OLED), `FOUND 0x40` (Pack INA228), `FOUND 0x41` (Midpoint INA228), `FOUND 0x69` (BMI270, ADR cut).
- `scan done, devices: 4` and no `BUS TIMEOUT` lines.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-06 | John Bolt | 94edd67..00237a8 | partial | Scanner methodology validated on this bench: idle SDA/SCL both 1, FOUND 0x69 (BMI270, confirming cut ADR jumper). INA228s not yet on the bus — full 4-device scan pending. |

---

# TP-PWR-02 — Onboard 15 mOhm shunt trace-cut on both INA228s + continuity verification + photo

| | |
|---|---|
| **Traces** | TASK-3 AC 3e; spec §3 (only the external shunt may carry pack current) |
| **Status** | draft |
| **Hardware** | 2× Adafruit INA228, hobby knife/scalpel, Klein DMM (continuity/ohms), phone camera, magnifier or phone macro, bench bus from TP-PWR-01 |
| **Est. time** | 30 min |

## Purpose
Proves the onboard 15 mΩ shunt is electrically removed from both INA228 boards. Left uncut, it sits in parallel with the 0.375 mΩ external shunt: it corrupts the current calibration and can itself carry damaging current. This must precede any battery work, and the trace-cut photo is the AC 3e deliverable.

## Setup (from cold)
1. Complete TP-PWR-01 (both boards known-alive at 0x40/0x41 — the post-cut rescan needs a known-good "before").
2. Unplug USB and disconnect both INA228s from the Qwiic chain; work on each board bare at the bench.

## Procedure
1. On the Pack board (0x40), baseline the DMM: continuity mode across IN+ ↔ IN− screw terminals. The intact 15 mΩ shunt reads as a near-short (continuity beep / ~0 Ω — the DMM cannot resolve 15 mΩ; near-zero is the expected "before").
2. Cut the onboard-shunt trace on the back of the board per the Adafruit INA228 guide ("disable the onboard shunt" jumper cut). Make two parallel cuts and lift the sliver of trace between them.
3. Re-measure IN+ ↔ IN−: must now read open (no beep; OL or > 1 MΩ). If it still beeps, deepen the cut and re-measure.
4. Repeat steps 1–3 on the Midpoint board (0x41).
5. Photograph both cuts close-up (board label or A0 strap visible so Pack vs Midpoint is identifiable in the photo).
6. Rewire the bench bus and re-run TP-PWR-01's scan to confirm neither board was killed by the cut (both must still enumerate).
7. Commit the photos:
   ```sh
   cp <photo-pack>.jpg assets/m16-ina228-trace-cut-pack.jpg
   cp <photo-midpoint>.jpg assets/m16-ina228-trace-cut-midpoint.jpg
   git add assets/ && git commit -m "M16 Task 3: INA228 onboard-shunt trace-cut photos (AC 3e)"
   ```

## Pass criteria
- Before cut: IN+ ↔ IN− continuity (near 0 Ω) on both boards.
- After cut: IN+ ↔ IN− open (OL / > 1 MΩ) on both boards.
- Post-cut I2C scan still reports `FOUND 0x40` and `FOUND 0x41`.
- Two identifiable trace-cut photos committed under `krabby-research/assets/`.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-03 — Firmware bring-up: setShunt cal, per-tick reads, BATT frame emission, sensor-absent safety

| | |
|---|---|
| **Traces** | TASK-3 AC 3f, 3g (frame emission), 3h; spec §4 poll cadence |
| **Status** | draft |
| **Hardware** | Bench bus from TP-PWR-01 (BMI270 + OLED + both INA228s, trace-cut per TP-PWR-02), USB cable |
| **Est. time** | 30 min |

## Purpose
Proves the Task 3 firmware path end-to-end on the logic side: constants live in `sensors_config.h`, `pack.setShunt(0.000375, 200.0)` is applied at init, both INA228s are read on every telemetry tick, the `;BATT` segment appends to the leader line with SI units, and a missing sensor degrades gracefully (mirroring the IMU `valid=0` pattern) instead of stalling the gait loop. All with VBUS unpowered, so expected readings are ~0 V / ~0 A.

## Setup (from cold)
1. TP-PWR-01 setup steps 1–6 (venv, arduino-cli, bus wired with both INA228s, `$PORT` exported).
2. TP-PWR-02 complete (trace cuts done — bring-up should run on final-configuration boards).
3. Verify the constants contract before flashing:
   ```sh
   grep -n "INA228\|SHUNT\|DIVERGENCE\|TELEMETRY_INTERVAL_MS" firmware/arduino/sensors_config.h
   ```
   Expect: addresses 0x40/0x41, shunt 0.000375 / 200.0, divergence 0.5, and reads keyed to `TELEMETRY_INTERVAL_MS` (50 ms). Cross-check the firmware's unit conversion against the `Adafruit_INA228.h` reader return units (mV/mA vs SI; header materialized under gitignored `firmware/arduino/libraries/` once Task 3 adds the INA228 row to `firmware/scripts/fetch_arduino_libs.py` per the BMI270 pattern — run it or `make -C firmware compile-firmware` first — else the upstream repo linked in spec §3) — telemetry must be V/A/W/C.
4. Flash: `make -C firmware upload-firmware PORT=$PORT`

## Procedure
1. Watch the boot log and raw lines (opening the port resets the board; wait through the ~4 s boot):
   ```sh
   python -m serial.tools.miniterm $PORT 250000
   ```
   Record the INA228 init lines (both addresses online, shunt cal applied) and one full telemetry line showing the trailing `;BATT ...` segment. Exit with Ctrl+].
2. Confirm the segment is on every line, not a slow path: capture 100 consecutive lines and count `;BATT` occurrences:
   ```sh
   python - "$PORT" <<'EOF'
   import sys, time, serial
   ser = serial.Serial(sys.argv[1], 250000, timeout=2.0)
   t0 = time.time(); n = batt = 0
   while time.time() - t0 < 12:  # ride out the port-open reset/boot
       if ser.readline().decode(errors="replace").startswith(("UNKWN;", "FRONT;")): break
   while n < 100:
       line = ser.readline().decode(errors="replace").strip()
       if line.startswith(("UNKWN;", "FRONT;")):
           n += 1; batt += ";BATT " in line
   print(f"lines {n}  with-BATT {batt}")
   EOF
   ```
3. Sensor-absent test (physical, binary, hold-based): with telemetry streaming, **unplug the Midpoint INA228's Qwiic cable and hold it disconnected for at least 15 s**, then replug. The data window itself proves the hold — no stopwatch needed.
4. During the unplugged window, confirm in the miniterm stream: telemetry lines keep arriving at tick cadence, joint segments are unchanged, and the BATT segment flags the missing sensor (Task 3's analog of IMU `valid=0`) rather than freezing or resetting the board.

## Pass criteria
- Boot log reports both INA228s online at 0x40 and 0x41 and shunt cal `0.000375 / 200.0` applied.
- Step 2 prints `with-BATT 100` (segment present on 100/100 leader lines — per-tick, no separate cadence).
- BATT fields with VBUS unconnected: `pack_v` and `batt_a_v` each < 0.1 V, `pack_i` within ±0.05 A of 0, `divergence_flag` 0 — values in SI units (a mV-scale value like 4500 is an instant fail).
- During the ≥15 s unplug window: no gap > 200 ms between telemetry lines, no board reset (no boot banner), missing sensor indicated in the BATT segment; normal values resume after replug without a power cycle.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-04 — Loop timing with full I2C cluster (IMU + OLED + 2x INA228 polled on-tick)

| | |
|---|---|
| **Traces** | TASK-3 AC 3f/3h poll cadence on `TELEMETRY_INTERVAL_MS`; OVERVIEW no-new-transport constraint; extends Task 1 AC 1c method |
| **Status** | draft |
| **Hardware** | Bench bus from TP-PWR-03 (full cluster: BMI270 + OLED + 2× INA228), USB cable |
| **Est. time** | 15 min |

## Purpose
Proves the two extra INA228 I2C transactions per tick fit inside the existing 50 ms telemetry tick with no separate slow path and no serial-budget regression, using the exact host-side inter-line timing method that produced the Task 1 AC 1c evidence. The result becomes a new row in the SETUP.md "Loop timing (AC 1c)" table next to the existing baselines.

## Setup (from cold)
1. TP-PWR-03 setup complete (venv, full cluster wired, Task 3 firmware flashed, `$PORT` exported).
2. Keep the board and breakouts still on the bench for the capture (per `imu_bench.py` timing mode; motion doesn't invalidate inter-line timing but stillness keeps the run comparable to the baselines).

## Procedure
1. Run the timing capture (the script waits through the ~4 s port-open reset itself):
   ```sh
   python firmware/scripts/imu_bench.py $PORT timing --lines 400
   ```
2. Record mean/p50/p95/max inter-line ms and mean/max line length from the output.
3. Add a row `M16 Task 3 @ 250000, full cluster (IMU + OLED + 2× INA228)` to the timing table in `firmware/SETUP.md` ("Loop timing (AC 1c) and serial budget") and note the FW commit.

## Pass criteria
- Mean inter-line time in 49.5–51.5 ms (tick still ~50 ms; baselines: upstream@115200 mean 50.72, M16 IMU-absent@250000 mean 50.77).
- p95 ≤ 55 ms and max ≤ 65 ms (comparable to baseline p95 53.29/53.38, max 57.09/58.84 — no new tail).
- Mean line length minus the 229 B Task 1 baseline is between 40 and 80 B (the `;BATT` segment's expected width), and max line length ≤ `TELEMETRY_LINE_MAX` per the byte-accounting comment in `arduino.ino` — well under the 1250 B/tick budget at 250000 baud.
- SETUP.md table row committed.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-05 — BATT frame end-to-end: SDK parse, GUI display, OLED battery bars

| | |
|---|---|
| **Traces** | TASK-3 AC 3g; spec §4 parser/SDK/GUI, §6 end-to-end |
| **Status** | draft |
| **Hardware** | Bench bus from TP-PWR-03, USB cable, host machine with GUI display |
| **Est. time** | 30 min |

## Purpose
Proves the whole telemetry pipe for battery data with bench (~0 V) values: firmware `;BATT` segment → `joint_telemetry.py` `BatteryTelemetry` dataclass → `KrabbyMCUSDK` storage → GUI + compact debug log → Task 2 OLED battery bars — plus the append-only backward-compat contract (a pre-Task-3 parser must drop the segment cleanly). Bars *moving with real pack state* is deferred to TP-PWR-13; this is the plumbing proof.

## Setup (from cold)
1. TP-PWR-03 setup complete (venv, full cluster wired, Task 3 firmware flashed, `$PORT` exported).

## Procedure
1. Parser + SDK-level check — stream parsed battery objects through the real parser:
   ```sh
   python - "$PORT" <<'EOF'
   import sys, time, serial
   sys.path.insert(0, ".")
   from firmware.interfaces.joint_telemetry import parse_telemetry_line
   ser = serial.Serial(sys.argv[1], 250000, timeout=2.0)
   t0 = time.time()
   while time.time() - t0 < 12:  # port-open resets the board; ride out boot
       if ser.readline().decode(errors="replace").startswith(("UNKWN;", "FRONT;")): break
   last = 0.0
   while time.time() - t0 < 32:
       p = parse_telemetry_line(ser.readline().decode(errors="replace"))
       b = getattr(p, "batt", None)
       if b is not None and time.time() - last > 1.0:
           last = time.time(); print(b)
   EOF
   ```
   (Attribute name per the Task 3 parser addition on `ParsedTelemetry`, alongside `.imu`.)
2. Compact debug log: `python -m firmware --debug` — confirm pack/per-battery values appear in the debug output, then quit the menu.
3. GUI: `python -m firmware.gui --port $PORT` — confirm the pack and per-battery values render (all ≈ 0 with VBUS unpowered).
4. OLED (physical observation, binary): confirm the Task 2 battery bars render on the 1.3" display in the near-empty state matching ~0 V — bars present, not garbage or absent.
5. Backward-compat check — feed a captured Task 3 line to a pre-Task-3 parser build:
   ```sh
   git show 00237a8:firmware/interfaces/joint_telemetry.py > /tmp/old_jt.py
   python - <<'EOF'
   import importlib.util
   spec = importlib.util.spec_from_file_location("old_jt", "/tmp/old_jt.py")
   old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
   line = "UNKWN; FLHY 0.723 740 694 0 0 0 0 0;IMU 0.1 0.2 9.81 0 0 0 25.0 1;BATT 0.01 0.00 0.00 0.0 0.01 0.00 0 0"
   p = old.parse_telemetry_line(line)
   print("joints:", len(p.joints), "imu:", p.imu is not None)  # must parse fine, BATT silently dropped
   EOF
   ```
   Expected output: `joints: 1 imu: True`. (Replace the joint/IMU tokens with a real captured line from step 1's raw stream if the synthetic one drifts from the wire format — a real line has six joint segments, so expect `joints: 6` then.)

## Pass criteria
- Step 1 prints `BatteryTelemetry` objects at ~1/s with all eight fields populated (pack V/I/P/charge, batt_a, batt_b, divergence_flag=0, power_state=0) at bench-zero values (same bounds as TP-PWR-03: `pack_v` and `batt_a_v` < 0.1 V, `pack_i` within ±0.05 A of 0).
- Debug log and GUI both display pack and per-battery values without parse errors or crashes.
- OLED battery bars visibly rendered (photo in run-log notes).
- Old-parser check: joints and IMU parse identically, no exception, no BATT field — segment dropped cleanly (append-only contract holds).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-06 — VBUS reference check and per-board offset trim vs Klein DMM (Mega rails as reference)

| | |
|---|---|
| **Traces** | TASK-3 AC 3i (VBUS offset/gain trim); spec §5 "apply known V, record offsets" |
| **Status** | draft |
| **Hardware** | Bench bus from TP-PWR-03, Klein DMM, 4× M-M Dupont jumpers, USB cable |
| **Est. time** | 30 min |

## Purpose
Derives the per-board VBUS offset trims (the battery-free half of AC 3i) by feeding both INA228 VBUS pins from the same known node — the Mega's 5 V then 3.3 V rail — and comparing `readBusVoltage` (via the BATT telemetry fields) against the Klein DMM on that same node. After trimming, the two boards must agree with the DMM and with each other, so per-battery voltage math on the real pack is trustworthy. The shunt-constant current trim waits for TP-PWR-12.

## Setup (from cold)
1. TP-PWR-03 setup complete (venv, full cluster wired, Task 3 firmware flashed, `$PORT` exported).
2. **SAFETY:** make/break all VBUS wiring with USB unplugged; keep the DMM probe jumpers from touching each other or neighboring pins. With USB unplugged: tie each board's IN+ and IN− together and to Mega GND (Dupont jumpers), and run a Dupont from the Mega **5V** pin to a common node feeding *both* boards' VBUS terminals.
3. DMM probing trick (meter probes don't fit female headers): plant two M-M Dupont jumpers in the rail-under-test and GND, probe their free ends — per the SETUP.md bench runbook step 1.

## Procedure
1. Plug in USB; stream battery telemetry with the TP-PWR-05 step 1 parser one-liner (or `python -m firmware --debug`).
2. With both VBUS on the 5 V node: record DMM reading on the node, telemetry `pack_v` (Pack board 0x40), and `batt_a_v` (Midpoint board 0x41). Average ~10 s of samples by eye or from the printed stream.
3. Unplug USB, move the common VBUS node to the **3V3** pin, replug, and repeat the recording (DMM, `pack_v`, `batt_a_v`).
4. Compute per-board offset (and, if the two points show slope error, gain) trims: `trim = DMM − reading` at each point, per board.
5. Enter the trims into the Task 3 calibration path (`sensors_config.h` defaults or the cal-capture command, per the firmware's cal design) and reflash/re-capture: `make -C firmware upload-firmware PORT=$PORT`.
6. Re-run steps 2–3 with trims applied and record the residuals.

## Pass criteria
- Pre-trim readings recorded for both boards at both reference points (four DMM/telemetry pairs).
- Post-trim: each board within ±20 mV of the DMM at both 5 V and 3.3 V points.
- Post-trim: the two boards agree with each other within 10 mV on the same node at both points.
- Trim values written down in the run log (they feed TP-PWR-08 persistence and TP-PWR-11 refinement).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-07 — Divergence-flag logic simulation using split rail voltages (no battery)

| | |
|---|---|
| **Traces** | TASK-3 AC 3g (`divergence_flag`); spec §4 `|Va−Vb| > 0.5 V`; "divergence alarm" de-risk |
| **Status** | draft |
| **Hardware** | Bench bus from TP-PWR-03, M-M Dupont jumpers, USB cable, host with GUI |
| **Est. time** | 20 min |

## Purpose
Proves the entire divergence-alarm path — firmware computation, BATT flag bit, SDK, GUI, and OLED indication — before any battery exists, by faking a per-battery imbalance with the Mega's own rails. With Pack VBUS on 5 V and Midpoint VBUS on 3.3 V, firmware computes `batt_a = 3.3 V`, `batt_b = pack − a = 1.7 V`, `|Va−Vb| = 1.6 V > 0.5 V` → flag must read 1 everywhere. The true 0.5 V threshold trip on a real pack is TP-PWR-13.

## Setup (from cold)
1. TP-PWR-06 setup steps 1–3 (venv, firmware flashed, IN± of both boards grounded, DMM jumper trick ready).
2. **SAFETY:** make/break VBUS wiring with USB unplugged. Wire Pack INA228 (0x40) VBUS → Mega **5V** pin, Midpoint INA228 (0x41) VBUS → Mega **3V3** pin.

## Procedure
1. Plug in USB; stream parsed battery telemetry (TP-PWR-05 step 1 one-liner) and note `pack_v ≈ 5.0`, `batt_a_v ≈ 3.3`, `batt_b_v ≈ 1.7`, `divergence_flag`.
2. Confirm the flag in each display surface: GUI (`python -m firmware.gui --port $PORT`), compact debug log (`python -m firmware --debug`), and the OLED alarm indication (physical observation).
3. Clear case — unplug USB, disconnect **both** VBUS jumpers from the rails and tie both VBUS to GND (Va = 0, Vb = pack − a = 0, |Va−Vb| = 0 < 0.5). Replug and re-read the stream.
   *Note the arithmetic: putting both VBUS on the same live rail does NOT clear the flag (e.g. both at 3.3 V gives Vb = 0 and |Va−Vb| = 3.3). Only the both-at-0 configuration is a valid bench "balanced" case.*
4. Record flag values from telemetry in both configurations.

## Pass criteria
- Split-rail config: `divergence_flag = 1` in the parsed BATT frame, GUI, debug log, and OLED indication, with `pack_v` within ±0.15 V of 5.0, `batt_a_v` within ±0.1 V of 3.3, `batt_b_v` = `pack_v − batt_a_v` exactly.
- Grounded config: `divergence_flag = 0` on all the same surfaces.
- Flag transitions require no reboot beyond the wiring-change power cycles (flag state follows the measured voltages, not a latched state).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-08 — INA228 calibration EEPROM persistence across power cycle

| | |
|---|---|
| **Traces** | TASK-3 AC 3i; spec §5 (EEPROM, IMU-adjacent region, magic + schema_version) |
| **Status** | draft |
| **Hardware** | Bench bus from TP-PWR-06 (trims known), USB cable |
| **Est. time** | 20 min |

## Purpose
Proves the INA228 calibration block (shunt constant + per-board VBUS trims from TP-PWR-06) persists across a full power cycle in the sensor-cal EEPROM region at `EEPROM_SENSOR_CAL_NEXT_ADDR` (= 66, defined in `sensors_config.h`, magic + `schema_version`), alongside — and without corrupting — Task 1's `ImuCalData` at bytes 40–65. Same capture→reload pattern already proven for IMU cal on this bench.

## Setup (from cold)
1. TP-PWR-06 complete on this board (trim values in hand), venv active, Task 3 firmware flashed, `$PORT` exported (macOS accessory gate note as in TP-PWR-01).

## Procedure
1. Trigger the INA228 cal capture per the Task 3 firmware mechanism (boot-time capture or serial cal command, mirroring the IMU flow) and watch the boot/cal log in `python -m serial.tools.miniterm $PORT 250000`. Record the exact applied values (shunt constant + both VBUS trims) as printed.
2. Power cycle (physical, binary, hold-based): **unplug USB and keep it unplugged for at least 10 s** (full power removal, not just a DTR reset), then replug.
3. Re-open the monitor (`python -m serial.tools.miniterm $PORT 250000`) and record the boot log: the INA cal block must report loaded-from-EEPROM with values identical to step 1, and the IMU block must still print `IMU CAL: loaded from EEPROM.`
4. Magic-byte invalidation: use the firmware's invalidation hook (serial command or documented magic-byte clear for the INA block only), power cycle again (≥10 s unplugged), and confirm the boot log shows a clean re-capture path for the INA block — while the IMU cal STILL loads from EEPROM (adjacent block untouched).
5. Re-capture the cal (step 1) to leave the board in its calibrated state.

## Pass criteria
- Post-power-cycle boot log reports INA228 cal loaded from EEPROM with values byte-identical to those printed at capture (shunt constant + both trims).
- IMU cal (`bytes 40–65`) reports `loaded from EEPROM` on every boot throughout — no cross-corruption.
- After magic invalidation: INA block re-captures cleanly (no garbage values, no crash), IMU block still loads.
- No joint `CalData` (bytes 0–25) or role bytes (32–33) disturbance: role hint and joint calibration behave normally after the test.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-09 — SAFETY gate: pre-energize battery-safety checklist (mandatory, gates all pack-connected procedures)

| | |
|---|---|
| **Traces** | TASK-3 AC 3b; spec §2 (mandatory battery-safety section) |
| **Status** | draft |
| **Hardware** | 150 A ANL fuse or breaker, fuse holder, Klein DMM, insulated tools, eye protection, fire-safe surface, second person for first energize; 2× 12 V 100 Ah LiFePO4 (M12) |
| **Est. time** | 15 min |

## Purpose
A 24 V / 100 Ah LiFePO4 pack delivers hundreds of amps into a short and will vaporize tools, wire, and skin. This procedure is the single walk-through-and-check-off safety gate extracted from spec §2. TP-PWR-10 through TP-PWR-13 may not start until every item below is checked, and this is the ONLY place the checklist lives — the pack-connected procedures reference it rather than restate it.

## Setup (from cold)
1. **BLOCKED on M12:** the 2× 12 V 100 Ah LiFePO4 pack is not yet on the bench (fuse and shunt are on hand). This procedure can be rehearsed dry but only signed off with the real pack present.
2. Lay out the pack, fuse/breaker + holder, shunt, harness leads, DMM, and insulated tools on a fire-safe surface. No wiring yet.

## Procedure
**SAFETY:** every item below is the safety gate; check each off in writing (run-log notes) before any pack wiring or energize.
1. ☐ **Fuse first.** The 150 A ANL fuse / breaker is physically positioned to be the element closest to the battery positive terminal on Pack+, before the shunt and everything else — and the plan for ALL subsequent wiring makes/breaks connections only with the fuse pulled or the breaker open.
2. ☐ **Insulated tools only.** Every tool that will go near the pack is insulated; verify no tool on the bench is long enough to bridge Pack+ to Pack− or to chassis where it will be used.
3. ☐ **Polarity verified with the DMM before energizing** — battery terminals, INA228 IN+/IN− orientation, and VBUS orientation all confirmed against the TP-PWR-10 topology before the fuse ever goes in.
4. ☐ **Midpoint tap treated as live.** The pack midpoint sits at a live 12–14 V; its sense lead is fused/current-limited and handled like a battery terminal.
5. ☐ **Person + environment.** Eye protection on; fire-safe surface under the bench batteries; a second person present — never perform the first energize alone.

## Pass criteria
- All five items physically verified and checked off, with the checker's name and date in the run log.
- The fuse/breaker is confirmed OPEN/PULLED at sign-off (TP-PWR-10 starts from a de-energized bus).
- Sign-off recorded before any TP-PWR-10..13 activity on that bench session (a new session re-walks the checklist).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-10 — Bench-octopus assembly and first energize (fuse -> shunt -> load topology)

| | |
|---|---|
| **Traces** | TASK-3 AC 3a, 3b, 3c, 3d, 3j; spec §1 bench-octopus fallback, §3 topology diagram |
| **Status** | draft |
| **Hardware** | 2× 12 V 100 Ah LiFePO4 (M12), 150 A ANL fuse + holder, 200 A/75 mV shunt, 2 AWG pack leads + lugs, fused midpoint sense lead, bench bus from TP-PWR-03, Klein DMM, insulated tools, camera |
| **Est. time** | 60 min |

## Purpose
Builds the bench octopus (spec §1 fallback: batteries on a table, shunt wired directly into the bus exactly as on the robot) and performs the first energize, proving the AC 3a/3c/3d topology: Pack+ → 150 A fuse → 200 A/75 mV shunt → load node, Kelvin sense to the Pack INA228, midpoint tap to the Midpoint INA228. DMM readings — not firmware — are the truth source for the first energize. Produces the AC 3j wiring diagram and harness photos.

## Setup (from cold)
1. **BLOCKED on M12:** requires the battery pack plus bus-bar / 2 AWG harness hardware from the M12 build.
2. TP-PWR-09 signed off this session (**SAFETY** gate — all wiring below happens with the fuse pulled / breaker open, per that checklist).
3. TP-PWR-02 complete (both onboard shunts cut) and TP-PWR-08 complete (cal persisted).
4. Venv + `$PORT` per TP-PWR-01 steps 2 and 6; Task 3 firmware flashed (`make -C firmware upload-firmware PORT=$PORT`).

## Procedure
1. Fuse pulled: wire the two 12 V batteries in series on the table (battery 1 − → battery 2 +, forming the midpoint node).
2. Wire Pack+ → fuse holder (empty) → shunt → load/bus node with 2 AWG; Pack− → distribution ground.
3. Kelvin sense: shunt sense terminals → Pack INA228 (0x40) IN+/IN− (IN+ on the battery side); Pack INA228 VBUS → the **load side** of the shunt.
4. Midpoint tap: fused sense lead from the pack midpoint → Midpoint INA228 (0x41) VBUS; that board's IN+ and IN− tied together and to ground.
5. DMM polarity pass over every connection (TP-PWR-09 item 3) — record expected vs. observed polarity at the fuse holder, shunt, both INA228 terminal blocks.
6. First energize: insert the fuse LAST. Immediately measure with the DMM (jumper-probe trick where needed): pack voltage across Pack+/Pack− and midpoint-to-Pack−.
7. Only after the DMM numbers are sane, plug in USB and read telemetry (`python -m firmware --debug` or the TP-PWR-05 parser one-liner); record `pack_v`, `batt_a_v`, `batt_b_v`, `pack_i` (no load: ≈ 0 A).
8. Photograph the assembled harness (fuse placement visible) and draw the wiring diagram; commit both:
   ```sh
   cp <harness-photo>.jpg assets/m16-bench-octopus-harness.jpg
   cp <wiring-diagram>.png assets/m16-bench-octopus-wiring.png
   git add assets/ && git commit -m "M16 Task 3: bench-octopus harness photo + wiring diagram (AC 3j)"
   ```

## Pass criteria
- DMM pack voltage in 24.0–27.6 V; DMM midpoint in 12.0–13.8 V; midpoint within 0.5 V of pack/2 (healthy series pair).
- Telemetry `pack_v` and `batt_a_v` within 0.1 V of the corresponding DMM readings; `batt_a_v + batt_b_v = pack_v` (identity holds); `pack_i` within ±0.2 A of 0 with no load.
- Fuse is verifiably the first element on Pack+ (visible in the committed photo).
- Harness photo + wiring diagram committed under `krabby-research/assets/`.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-11 — Pack and per-battery voltage accuracy vs DMM on the live pack

| | |
|---|---|
| **Traces** | TASK-3 AC 3f, 3g, 3i; spec §6 "Pack accuracy" + "Per-battery" |
| **Status** | draft |
| **Hardware** | Energized bench octopus (TP-PWR-10), Klein DMM, insulated probes, USB cable |
| **Est. time** | 30 min |

## Purpose
Proves the telemetry voltage chain against the DMM at real pack voltage: `pack_v` vs. the DMM across the pack, `batt_a_v` (Midpoint VBUS) vs. the DMM on battery 1, and the computed `batt_b_v = pack_v − batt_a_v` vs. the DMM on battery 2. Refines the TP-PWR-06 rail-level trims at 24 V operating point and re-persists them, completing the voltage half of AC 3i on real hardware.

## Setup (from cold)
1. **BLOCKED on M12** (battery pack). TP-PWR-09 signed off this session; TP-PWR-10 assembled and energized.
2. Venv + `$PORT` per TP-PWR-01; Task 3 firmware with TP-PWR-06 trims flashed and cal loaded (TP-PWR-08 boot log check).

## Procedure
1. Stream battery telemetry (TP-PWR-05 step 1 one-liner) and let it run through the whole procedure.
2. DMM across the full pack (Pack+ to Pack−); record DMM vs. a ~10-sample average of `pack_v`.
3. DMM across battery 1 (midpoint to Pack−, matching the Midpoint INA228's node); record DMM vs. `batt_a_v`.
4. DMM across battery 2 (Pack+ to midpoint); record DMM vs. `batt_b_v`.
5. Cross-check: `batt_a_v + batt_b_v` vs. `pack_v` (identity) and DMM(batt1) + DMM(batt2) vs. DMM(pack) (sanity on the DMM readings themselves).
6. If any residual exceeds the pass band, refine the per-board VBUS offset trims at this operating point, re-persist via the TP-PWR-08 mechanics (capture → power cycle ≥10 s unplugged → verify loaded-from-EEPROM), and re-run steps 2–4.

## Pass criteria
- `pack_v` within ±50 mV of the DMM pack reading (post-trim).
- `batt_a_v` within ±50 mV of the DMM battery-1 reading (post-trim).
- `batt_b_v` within ±100 mV of the DMM battery-2 reading (it inherits both boards' residuals).
- Final trims persisted: post-power-cycle boot log shows the refined values loaded from EEPROM.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-12 — Shunt current calibration cross-check under known load + charge accumulation

| | |
|---|---|
| **Traces** | TASK-3 AC 3f (current/power/charge), 3i (shunt constant); spec §6 "compare pack_i to a clamp meter under a known load" |
| **Status** | draft |
| **Hardware** | Energized bench octopus (TP-PWR-10), a known resistive load (e.g. 24 V lamp or power resistor), Klein DMM (series, small loads only), clamp meter (larger loads), USB cable |
| **Est. time** | 45 min |

## Purpose
Verifies the `setShunt(0.000375, 200.0)` scaling against reality, not the datasheet: telemetry `pack_i` vs. an independent meter under a known load, `pack_w = pack_v × pack_i` consistency, and `pack_charge` accumulating ≈ I × t over a timed interval. Trims and persists the final shunt calibration constant, completing AC 3i.

## Setup (from cold)
1. **BLOCKED on M12** (battery pack; a clamp meter is also needed for any load beyond the Klein DMM's series-current range). TP-PWR-09 signed off this session; TP-PWR-10 energized; TP-PWR-11 voltage trims persisted.
2. Venv + `$PORT` per TP-PWR-01; battery telemetry streaming (TP-PWR-05 one-liner).
3. **SAFETY:** connect/disconnect the load and any series DMM only with the fuse pulled; the DMM in series must stay within its rated series-current range and fused input — anything larger uses the clamp meter around the load conductor instead.

## Procedure
1. Small-load point: fuse pulled, wire the load through the shunt path with the Klein DMM in series. Insert the fuse; record DMM current vs. a ~10-sample average of `pack_i` and `pack_v`, `pack_w`.
2. Larger-load point (if a clamp meter is available): fuse pulled, remove the series DMM, wire the larger load; energize and record clamp-meter current vs. `pack_i`.
3. Charge accumulation (binary, hold-based — verified in the data, not by stopwatch feel): with the load steady, record `pack_charge` and host timestamp at a start sample, **hold the load connected untouched until 60 s of telemetry has accrued**, record `pack_charge` at the end sample. Compute `ΔC / Δt` from the telemetry timestamps and compare to the measured current.
4. Compute the current-scale correction from step 1 (and 2), apply it to the shunt calibration constant, persist via TP-PWR-08 mechanics, and re-run step 1 to confirm.
5. Zero-load check: fuse pulled → reinsert with no load; `pack_i` must return to ≈ 0 (offset check after the trim).

## Pass criteria
- Post-trim `pack_i` within ±2 % or ±20 mA (whichever is larger) of the reference meter at the small-load point; within ±5 % at the clamp-meter point.
- `pack_w` within ±5 % of `pack_v × pack_i` computed from the same samples.
- Charge accumulation: `ΔC / Δt` within ±5 % of the measured load current over the ≥60 s window.
- No-load `pack_i` within ±50 mA of 0 after trim.
- Final shunt constant persisted and reloaded across a power cycle (boot-log evidence).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PWR-13 — Real divergence trip at 0.5 V and OLED battery bars tracking live pack state

| | |
|---|---|
| **Traces** | TASK-3 AC 3g (`divergence_flag`, OLED bars), 3h (threshold); spec §6 "force a small divergence" + "battery bars move with pack state" |
| **Status** | draft |
| **Hardware** | Energized bench octopus (TP-PWR-10, trims from TP-PWR-11/12 persisted), 12 V low-current load (e.g. automotive bulb) for the imbalance, main bus load from TP-PWR-12, Klein DMM, USB cable, host with GUI |
| **Est. time** | 30 min |

## Purpose
Completes the spec §6 verify list on real hardware: forces a genuine per-battery imbalance and proves `divergence_flag` trips exactly when `|Va−Vb|` crosses the 0.5 V `sensors_config.h` threshold and clears on rebalance — visible in telemetry, SDK, GUI, and OLED — then confirms the OLED battery bars move with actual pack state under load. TP-PWR-07 proved the plumbing; this proves the physics-facing threshold.

## Setup (from cold)
1. **BLOCKED on M12** (battery pack). TP-PWR-09 signed off this session; TP-PWR-10..12 complete (energized octopus, all trims persisted).
2. Venv + `$PORT` per TP-PWR-01; GUI up (`python -m firmware.gui --port $PORT`) and parsed stream running (TP-PWR-05 one-liner) so flag transitions are timestamped in data.
3. **SAFETY:** the imbalance load connects across battery 1 only, via the fused midpoint sense-lead path and within its fuse rating — never an unfused jumper across a battery. Connect/disconnect it with insulated tools only.

## Procedure
1. Baseline: record `batt_a_v`, `batt_b_v`, `|Va−Vb|`, and `divergence_flag` (expected 0 on a healthy rested pair).
2. Connect the low-current load across battery 1 (midpoint to Pack−) through the fused path and **hold it connected** while watching `|Va−Vb|` grow in the parsed stream. Simultaneously track the DMM on battery 1.
3. Record the sample at which `divergence_flag` transitions 0→1 and the `|Va−Vb|` value on that sample; confirm the flag shows on GUI, debug log, and the OLED alarm indication at that moment.
4. Disconnect the imbalance load and **hold hands-off** while the battery voltage rebounds; record the sample where the flag transitions 1→0 and its `|Va−Vb|`.
5. Bars-track-state check: apply the TP-PWR-12 main-bus load, hold it, and photograph/observe the OLED battery bars at rest vs. under load; the rendered level must follow `pack_v` sag and recovery in the same direction as telemetry.

## Pass criteria
- `divergence_flag` 0→1 transition occurs on a sample where `|batt_a_v − batt_b_v|` ≥ 0.5 V, and the last flag-0 sample before it reads < 0.5 V (trip is at the configured threshold, not early/late by more than one tick's voltage movement).
- 1→0 clear transition occurs on a sample with `|Va−Vb|` < 0.5 V after rebalance, with no oscillation burst (< 3 transitions total for the whole test unless firmware documents hysteresis).
- Flag state simultaneously consistent across parsed telemetry, GUI, debug log, and OLED at both transitions.
- OLED battery bars visibly change with the applied bus load and recover on removal, in the same direction as `pack_v` (photos in run-log notes).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |
