# Bench test procedures — IMU area (BMI270, Milestone 16 Task 1)
Traces: `patina-foundation-grants/grants/Krabby-Uno/Milestone16-I2C-Sensors/TASK-1-IMU-TELEMETRY.md` (AC 1a–1i); runbook and timing evidence live in `firmware/SETUP.md` ("Bench bring-up runbook (M16)" and "Loop timing (AC 1c)").
Hardware baseline: solo Arduino Mega 2560 R3 + Krabby-Uno shield (bench leader, `ROLE_UNKNOWN`), SparkFun BMI270 Qwiic breakout (answers at **0x69** — ADR jumper cut), Qwiic→Dupont adapter, Klein multimeter, 2× M-M Dupont jumpers; USB serial at **250000** baud (opening the port resets the board).

---

# TP-IMU-01 — 3.3 V rail voltage check before first sensor connect

| | |
|---|---|
| **Traces** | TASK-1 AC 1a; TASK-1 §1 (3.3 V-only part); SETUP.md runbook step 1 |
| **Status** | verified-on-bench |
| **Hardware** | Mega 2560 + Krabby-Uno shield, USB power, Klein multimeter, 2× M-M Dupont jumpers. BMI270 **not** connected. |
| **Est. time** | 10 min |

## Purpose
Proves the shield's `3V3` pin actually delivers 3.3 V before the BMI270 is ever connected. The BMI270 is not 5 V tolerant; a mislabeled or miswired rail destroys the sensor on first power-up. This single measurement is the check that protects the part — every other procedure in this file assumes it has passed.

## Setup (from cold)
1. No repo, venv, or firmware state is required — this is a pure electrical check. Any sketch (or none) may be on the board.
2. Confirm the BMI270 is **not** wired to the shield.
3. Plant one M-M Dupont jumper in the shield's `3V3` female header and one in `GND` (meter probes don't fit female headers; the jumper pins act as probe points).
4. **SAFETY:** keep the two jumper free-ends physically separated — touching them shorts the 3.3 V rail to ground.
5. Power the board over USB (no serial connection needed; the macOS accessory-permission gate does not affect raw power).

## Procedure
1. Set the Klein multimeter to DC volts, 20 V range (or auto).
2. Touch red probe to the free end of the `3V3` jumper, black probe to the free end of the `GND` jumper.
3. Hold the probes steady until the reading is stable, then record the value.
4. Unplug USB and remove both jumpers.

## Pass criteria
- Measured voltage is within **3.30 ± 0.1 V** (3.20–3.40 V).
- Reading is stable (no drift beyond ±0.02 V while held).
- Fail action: do NOT connect the BMI270; debug the shield rail first.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-06 | J. Bolt | n/a (electrical) | PASS | Rail within 3.30 ± 0.1 V via M-M jumper method (café-table replication, runbook step 1). BMI270 subsequently powered and survived, confirming the rail. |

---

# TP-IMU-02 — Qwiic→Dupont wiring and I2C bus scan (BMI270 address discovery)

| | |
|---|---|
| **Traces** | TASK-1 AC 1a, 1b; TASK-1 §1; SETUP.md runbook steps 2 and 6 (bus debugging ladder) |
| **Status** | verified-on-bench |
| **Hardware** | Mega + shield, BMI270 breakout, Qwiic→Dupont adapter cable, USB cable, host machine with arduino-cli |
| **Est. time** | 20 min |

## Purpose
Proves the physical I2C bus end-to-end before any driver code is trusted: correct wiring, idle-high SDA/SCL, and an ACK from the BMI270 at its actual address. Separates the three failure classes that otherwise blur together — wiring faults (a line not idle-high), jumper-strap surprises (device at an unexpected address), and driver bugs (device found but init fails). On the M16 unit this scan is what revealed the cut ADR jumper (0x69, not 0x68).

## Setup (from cold)
1. From `krabby-research/`, create the venv if absent: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt` (pyserial, for port auto-detect). One-time: install the AVR core — `arduino-cli core install arduino:avr` — and fetch the pinned BMI270 driver — `python3 firmware/scripts/fetch_arduino_libs.py`, needs network once (`make -C firmware upload-firmware` runs both itself, but the raw `arduino-cli compile` below does not).
2. TP-IMU-01 must have passed on this shield. **SAFETY:** the BMI270 is not 5 V tolerant — never wire VCC to the 5 V pin, and never wire with USB plugged in.
3. With USB unplugged, wire the Qwiic→Dupont adapter: **black→GND, red→3V3, blue→D20 (SDA), yellow→D21 (SCL)**. Either Qwiic jack on the breakout works.
4. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)`; Linux `PORT=$(ls /dev/ttyACM*)`. On macOS, if the board is powered but no device appears, approve the "Allow accessory to connect" prompt (System Settings → Privacy & Security).

## Procedure
1. Flash the scanner sketch:
   ```sh
   arduino-cli compile --fqbn arduino:avr:mega firmware/bench_sketches/i2c_scanner
   arduino-cli upload -p "$PORT" --fqbn arduino:avr:mega firmware/bench_sketches/i2c_scanner
   ```
2. Open a serial monitor at 250000 baud (opening the port resets the board — output starts from boot):
   ```sh
   python -m serial.tools.miniterm "$PORT" 250000
   ```
3. Record the `idle SDA(D20)=... SCL(D21)=...` line and the address sweep results. The sweep repeats each loop; one full pass is sufficient. Exit miniterm with Ctrl+].
4. If a line reads 0 at idle: re-check wiring/shorts (step 3 of Setup). If an unexpected address ACKs: check the breakout's jumper straps. If the expected address ACKs but firmware init later fails: suspect the driver (see SETUP.md "Fetched libraries (AVR patches)").
5. Reflash the real firmware afterwards: `make -C firmware upload-firmware PORT=$PORT`.

## Pass criteria
- Scanner prints `idle SDA(D20)=1 SCL(D21)=1` (both lines idle high).
- Exactly one device ACKs in the 0x68/0x69 pair, and its address is recorded (M16 unit: **0x69**).
- No ACKs at unrelated addresses with only the BMI270 wired.
- Real firmware reflashed before the next procedure.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-06 | J. Bolt | n/a (scanner sketch) | PASS | Idle SDA/SCL both high; BMI270 ACKed at 0x69, not 0x68 — ADR jumper cut on the M16 unit. Chip ID returned and config bytes round-tripped, yet init failed `BMI2_E_CONFIG_LOAD` (-9): scan isolated the fault to the driver → vendored-library usDelay AVR patch (05423df; `delayMicroseconds` valid only to 16383 µs). Firmware now probes 0x68 then 0x69 (94edd67). |

---

# TP-IMU-03 — Firmware flash and boot-log verification (role election + IMU init)

| | |
|---|---|
| **Traces** | TASK-1 AC 1b; TASK-1 §2; SETUP.md runbook step 3 |
| **Status** | verified-on-bench |
| **Hardware** | Mega + shield, BMI270 wired per TP-IMU-02, USB cable, host with arduino-cli + venv |
| **Est. time** | 10 min |

## Purpose
Proves the real sketch brings up `Wire` at 100 kHz and initializes the BMI270 on the bench leader: role election completes (solo board elects `ROLE_UNKNOWN`, treated as bench leader), the dual-address probe (0x68 then 0x69) finds the sensor, and boot calibration runs. This is the first end-to-end check of the production firmware path rather than a bench sketch.

## Setup (from cold)
1. From `krabby-research/` on branch `m16-task1`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. BMI270 wired and bus verified per TP-IMU-01/02 (safety callouts there).
3. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory-permission prompt if nothing enumerates); Linux `PORT=$(ls /dev/ttyACM*)`.
4. Place the board on a stable surface — first boot captures gyro bias and needs ~1 s stationary.

## Procedure
1. Flash: `make -C firmware upload-firmware PORT=$PORT`.
2. Do not touch the board, then watch the boot (the port open resets the board; the script waits through the ~4 s boot):
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" watch
   ```
3. Record the `boot:` lines echoed before telemetry starts, and the ~20 s of parsed IMU samples that follow.

## Pass criteria
- Boot log contains `ROLE: UNKNOWN (front actuators)` (solo bench-leader case).
- Boot log contains `IMU CAL: BMI270 online at 0x69` (0x68 on an uncut-jumper unit).
- Boot log contains either `gyro bias captured and saved to EEPROM` (first boot) or `loaded from EEPROM` (subsequent boots) — no init-failure message.
- At least one parsed IMU sample prints during the watch window (`watch` only prints `valid=1` samples, so any printed sample proves the valid flag).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-06 | J. Bolt | 94edd67..00237a8 | PASS | Boot printed `ROLE: UNKNOWN (front actuators)` then `IMU CAL: BMI270 online at 0x69` (dual-address probe working with cut ADR jumper). First boot: `gyro bias captured and saved to EEPROM`; later boots: `loaded from EEPROM`. |

---

# TP-IMU-04 — IMU-absent graceful degradation (init failure path, valid=0, no stall)

| | |
|---|---|
| **Traces** | TASK-1 AC 1b, 1d (valid-field semantics, TASK-1 §4) |
| **Status** | verified-on-bench |
| **Hardware** | Mega + shield only — BMI270 **disconnected**. USB cable, host with venv. |
| **Est. time** | 10 min |

## Purpose
Proves an IMU init failure is logged, sets `imu_valid=0`, and neither crashes the sketch nor stalls the telemetry/gait loop (AC 1b's hard requirement). The board must boot with the sensor absent, keep shipping telemetry at nominal cadence with the `;IMU` segment carrying zeros and `valid=0`, and the Python parser must handle that segment without error.

## Setup (from cold)
1. From `krabby-research/` on branch `m16-task1`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. With USB unplugged, disconnect the BMI270 entirely (all four Dupont jumpers out).
3. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
4. Flash if the board doesn't already carry the M16 build: `make -C firmware upload-firmware PORT=$PORT`.

## Procedure
1. Capture boot + raw lines (port open resets the board):
   ```sh
   python -m serial.tools.miniterm "$PORT" 250000
   ```
   Record the init-failure boot log and ~10 telemetry lines, then exit (Ctrl+]).
2. Confirm cadence over a full capture:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" timing
   ```
   (400 lines ≈ 20 s. Note `timing` mode only matches line prefixes and timestamps arrivals — it does not parse the `;IMU` segment.)
3. Exercise the real parser on the `valid=0` segment:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" watch
   ```
   `watch` runs every line through `parse_telemetry_line`; with `valid=0` throughout it must print **zero** samples and exit cleanly after its 20 s window.

## Pass criteria
- Boot log contains `IMU CAL: BMI270 init failed at 0x68 and 0x69; shipping valid=0.`; the sketch continues to telemetry (no reset loop, no silence).
- Every telemetry line recorded in step 1 carries an `;IMU` segment ending in `0` (`valid=0`) with zeroed accel/gyro fields.
- Timing capture completes 400 lines with mean tick within 50 ± 2 ms and max < 65 ms (no stall).
- The `watch` run prints zero samples (all lines are `valid=0`, which it filters) and exits with no parser exception.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-06 | J. Bolt | 94edd67..00237a8 | PASS | Entire M16@250000 IMU-absent timing run is this path: 400 lines of 229 B telemetry, mean 50.77 ms tick, `valid=0` zeros, no crash/stall. Init-failure logging also observed during the pre-patch `BMI2_E_CONFIG_LOAD` (-9) episode — firmware logged and continued. |

---

# TP-IMU-05 — Baseline loop-timing capture — upstream firmware @115200

| | |
|---|---|
| **Traces** | TASK-1 AC 1c; TASK-1 §6 (before/after loop timing); SETUP.md timing table |
| **Status** | verified-on-bench |
| **Hardware** | Mega + shield, USB cable, host with arduino-cli + venv. IMU wiring state irrelevant (upstream firmware has no IMU code). |
| **Est. time** | 15 min |

## Purpose
Establishes the "before" row of the AC 1c before/after comparison: loop timing of the unmodified upstream firmware at its original 115200 baud. Without this row the M16 numbers have nothing to be compared against, and "no measurable change to loop timing" cannot be claimed.

## Setup (from cold)
1. From `krabby-research/`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
3. Overlay the upstream sketch while keeping the M16 bench script available (checking out the whole upstream tree would delete `imu_bench.py`):
   ```sh
   git fetch upstream
   git checkout upstream/main -- firmware/arduino
   ```
4. Flash the upstream build: `make -C firmware upload-firmware PORT=$PORT`.
5. Place the board on a stable surface.

## Procedure
1. With the board still, capture 400 lines at the upstream baud:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" timing --baud 115200
   ```
2. Record mean / p50 / p95 / max inter-line ms and the mean line length into the SETUP.md timing table ("Loop timing (AC 1c) and serial budget").
3. Restore the M16 sketch and reflash:
   ```sh
   git checkout m16-task1 -- firmware/arduino
   make -C firmware upload-firmware PORT=$PORT
   ```

## Pass criteria
- Capture completes 400 lines with the board untouched throughout.
- Mean, p95, max (ms) and line length (B) recorded in SETUP.md.
- Mean tick within 50 ± 2 ms (sanity check that the upstream 50 ms cadence is being measured, not noise).
- Working tree restored to the `m16-task1` sketch and reflashed.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-06 | J. Bolt | upstream/main | PASS | Solo Mega 2560 R3 (ROLE_UNKNOWN bench leader), 400 lines: mean 50.72 ms, p95 53.29 ms, max 57.09 ms, 180 B lines, @115200. |

---

# TP-IMU-06 — M16 loop-timing capture @250000, IMU absent (serial-path delta)

| | |
|---|---|
| **Traces** | TASK-1 AC 1c; TASK-1 §6; SETUP.md "Loop timing (AC 1c) and serial budget" |
| **Status** | verified-on-bench |
| **Hardware** | Mega + shield, USB cable, host with venv. BMI270 **disconnected** (valid=0 path isolates the serial cost from the I2C cost). |
| **Est. time** | 10 min |

## Purpose
Proves the two serial-path changes — the ~50–70 B `;IMU` segment appended to every line (+49 B measured on the bench) and the 115200→250000 baud change — cause no measurable change to loop timing, compared row-to-row against the TP-IMU-05 baseline. Running with the sensor disconnected deliberately excludes the live I2C read so the serial delta is measured in isolation (the I2C cost is TP-IMU-11).

## Setup (from cold)
1. From `krabby-research/` on branch `m16-task1`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. With USB unplugged, disconnect the BMI270 (all four jumpers out).
3. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
4. Flash the M16 build: `make -C firmware upload-firmware PORT=$PORT`.
5. Place the board on a stable surface. TP-IMU-05 must have been run (this row is meaningless without the baseline).

## Procedure
1. With the board still, capture 400 lines:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" timing
   ```
2. Record mean / p95 / max and line length into the SETUP.md timing table, alongside the TP-IMU-05 row.
3. Compute the mean-tick delta vs the upstream row.

## Pass criteria
- Capture completes 400 lines with the board untouched.
- Mean-tick delta vs the TP-IMU-05 baseline is within run-to-run noise (< 0.5 ms).
- p95 and max within 10% of the baseline row.
- Line length consistent with the `;IMU` segment addition (baseline + 40–70 B; the seeded run measured +49 B, 180→229).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-06 | J. Bolt | 94edd67..00237a8 | PASS | Mean 50.77 ms, p95 53.38 ms, max 58.84 ms, 229 B lines. Delta vs upstream baseline +0.05 ms mean — inside run-to-run noise; "no measurable change" satisfied for the serial path. 250000 verified as 0%-error divider on the 16 MHz Mega; ~48% link utilization per the `TELEMETRY_LINE_MAX` byte accounting. |

---

# TP-IMU-07 — Static telemetry sanity — gravity, gyro bias, temperature through the real parser

| | |
|---|---|
| **Traces** | TASK-1 AC 1c, 1d, 1e; TASK-1 §4, §6 (end-to-end); SETUP.md runbook step 4 |
| **Status** | verified-on-bench |
| **Hardware** | Mega + shield, BMI270 wired per TP-IMU-02, USB cable, host with venv |
| **Est. time** | 10 min |

## Purpose
Proves live accel/gyro/temperature values ship in the `;IMU` segment with correct SI units and parse end-to-end through the production parser — `imu_bench.py` imports `firmware.interfaces.joint_telemetry.parse_telemetry_line` and prints via `ImuTelemetry.format_compact`, so this run exercises the exact AC 1e code path, not a copy. At rest, physics provides the ground truth: |accel| must equal gravity, bias-subtracted gyro must be near zero, and die temperature must be plausible for the room.

## Setup (from cold)
1. From `krabby-research/` on branch `m16-task1`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. BMI270 wired and verified per TP-IMU-01/02 (safety callouts there); firmware flashed per TP-IMU-03.
3. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
4. Place the breakout flat and still on the bench (any orientation, but stationary — boot calibration and the rest-gyro criterion require it).

## Procedure
1. Leave board and breakout untouched, and stream parsed samples through the ~4 s boot and a 20 s window:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" watch
   ```
2. Record ~10 printed samples. Compute |accel| = sqrt(ax²+ay²+az²) for three of them.

## Pass criteria
- All printed samples have `valid=1`.
- |accel| within **9.81 ± 0.3 m/s²** on every checked sample (SI units confirmed — a value near 1.0 would mean g shipped unconverted).
- Each bias-subtracted gyro axis within **±0.02 rad/s** at rest.
- Die temperature within **15–35 °C** (plausible for the room, not 0.0 and not raw-register garbage).
- Samples printed via `format_compact` with no parser exception (AC 1e path).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-03, 2026-07-06 | J. Bolt | 94edd67..00237a8 | PASS | `watch` runs: \|accel\| ≈ 9.81 m/s² gravity magnitude, gyro ~0.002 rad/s at rest post-calibration, die temp ~25 °C, valid=1 — parsed through the real `parse_telemetry_line`, printed via `ImuTelemetry.format_compact` (AC 1e formatter exercised). |

---

# TP-IMU-08 — EEPROM calibration persistence across power cycle

| | |
|---|---|
| **Traces** | TASK-1 AC 1g; TASK-1 §5, §6 (Calibration); SETUP.md "Boot calibration (EEPROM)" |
| **Status** | verified-on-bench |
| **Hardware** | Mega + shield, BMI270 wired per TP-IMU-02, USB cable, host with venv |
| **Est. time** | 10 min |

## Purpose
Proves the gyro zero-rate bias captured at boot (200 samples, ~1 s stationary) is persisted at EEPROM bytes 40–65 (`ImuCalData`, magic `0xC7`, schema 1 — non-colliding with joint `CalData` at 0–25 and role bytes at 32–33) and reused across reboots: a power-cycled board must report `loaded from EEPROM` and read gyro ≈ 0 at rest without re-capturing. This is AC 1g's persistence requirement, distinct from merely capturing once.

## Setup (from cold)
1. From `krabby-research/` on branch `m16-task1`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. BMI270 wired and verified per TP-IMU-01/02; firmware flashed per TP-IMU-03.
3. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
4. Board flat and stationary on the bench.

## Procedure
1. First boot with the board untouched — confirm a capture (or a prior load) happens:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" watch
   ```
   Record whether the boot log says `gyro bias captured and saved to EEPROM` or `loaded from EEPROM`. (To force a fresh capture, clear the cal magic byte — concrete method in TP-IMU-09 Setup step 4.)
2. Physically power-cycle: unplug the USB cable, confirm all board LEDs are dark, plug it back in. (A true power cycle, not a DTR reset — EEPROM persistence across power loss is the claim.)
3. Re-run with the board untouched:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" watch
   ```
4. Record the boot-calibration log line and ~5 gyro samples.

## Pass criteria
- Post-power-cycle boot log says `IMU CAL: loaded from EEPROM` — not `captured`.
- Post-power-cycle gyro reads within **±0.02 rad/s** per axis at rest (stored bias applied, no re-capture).
- No calibration-capture delay or `motion detected` message on the reload boot.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-03, 2026-07-06 | J. Bolt | 94edd67..00237a8 | PASS | Capture→reload verified across a physical power cycle: first boot `gyro bias captured and saved to EEPROM`, subsequent boots `loaded from EEPROM`; gyro ~0.002 rad/s at rest with no boot re-capture. |

---

# TP-IMU-09 — Motion-gate rejection during calibration capture

| | |
|---|---|
| **Traces** | TASK-1 AC 1g (stationary capture requirement); SETUP.md "Boot calibration" (`IMU_CAL_MAX_SPREAD_DPS` gate) |
| **Status** | verified-on-bench |
| **Hardware** | Mega + shield, BMI270 wired per TP-IMU-02, USB cable, host with venv |
| **Est. time** | 10 min |

## Purpose
Proves a bad calibration cannot be persisted: if the board is moving during the ~1 s boot capture window, the gyro-spread gate (`IMU_CAL_MAX_SPREAD_DPS`) must reject the capture, write nothing to EEPROM, and retry on the next boot. This de-risks a robot that boots mid-handling from baking motion into its gyro bias for every subsequent boot.

## Setup (from cold)
1. From `krabby-research/` on branch `m16-task1`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. BMI270 wired and verified per TP-IMU-01/02; firmware flashed per TP-IMU-03.
3. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
4. Force the capture path (the M16 unit already carries a stored cal; a board that has never captured needs no clearing). No invalidation command exists in the firmware, menu, or CLI — clear the magic byte with a one-off sketch:
   ```sh
   mkdir -p /tmp/clear_imu_cal
   printf '#include <EEPROM.h>\nvoid setup() { EEPROM.write(40, 0xFF); }\nvoid loop() {}\n' > /tmp/clear_imu_cal/clear_imu_cal.ino
   arduino-cli compile --fqbn arduino:avr:mega /tmp/clear_imu_cal
   arduino-cli upload -p "$PORT" --fqbn arduino:avr:mega /tmp/clear_imu_cal
   ```
   (Byte 40 is the `EEPROM_IMU_CAL_ADDR` magic sentinel; `0xFF` fails the `0xC7` check — see `sensors_config.h`.)
5. Reflash the real firmware — `make -C firmware upload-firmware PORT=$PORT` — and **unplug USB within ~3 s of the upload finishing**. The post-flash boot runs on the bench: a *stationary* boot with a cleared magic byte re-captures and saves within ~4 s (3 s role election + IMU init + ~1 s capture), which would void this setup.

## Procedure
1. With USB still unplugged, pick the board+breakout up in one hand, start a continuous slow tilting motion, plug USB back in **while moving**, and keep the motion going without pause until the boot log line appears:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" watch
   ```
   (Opening the port resets the board, so the capture window begins after the reset — the hold must span it; the printed log line is the verifiable end of the hold.)
2. Record the boot log — expect the `motion detected` rejection line and no `saved to EEPROM`.
3. Set the board down flat. Power-cycle (unplug USB, LEDs dark, replug) and re-run:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" watch
   ```
4. Record the boot log — expect a successful stationary capture (`gyro bias captured and saved to EEPROM`).

## Pass criteria
- Moving boot logs a `motion detected` rejection and does **not** log `saved to EEPROM`.
- Next stationary boot logs `gyro bias captured and saved to EEPROM` (retry happened, nothing stale loaded).
- Post-capture gyro at rest within **±0.02 rad/s** per axis (the eventually-saved bias is a good one).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| 2026-07-03, 2026-07-06 | J. Bolt | 94edd67..00237a8 | PASS | Capture attempted while the board was moving was rejected with `motion detected`; nothing written to EEPROM; capture retried successfully on the next stationary boot. |

---

# TP-IMU-10 — Confirmed flip test — physical motion verification with human in the loop (residual)

| | |
|---|---|
| **Traces** | TASK-1 AC 1d, 1e; TASK-1 §6 ("move the robot and watch accel/gyro change") |
| **Status** | draft |
| **Hardware** | Mega + shield, BMI270 wired per TP-IMU-02 (cable slack enough to invert the breakout), USB cable, host with venv |
| **Est. time** | 10 min |

## Purpose
Proves the telemetry tracks real physical motion rather than merely producing plausible static values — the one failure mode TP-IMU-07 cannot catch (a frozen or replayed sample also reads 9.81 at rest). The `flip` mode is deliberately binary and timing-proof: PASS requires >20 samples with negative accel-Z, and the `-> DOWN` console banner additionally requires accel-Z below −3 m/s² — neither happens unless the breakout itself is physically inverted and held. One of the two residuals from the 2026-07-03/06 sessions.

## Setup (from cold)
1. From `krabby-research/` on branch `m16-task1`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. BMI270 wired and verified per TP-IMU-01/02; firmware flashed per TP-IMU-03; TP-IMU-07 passing (static values sane).
3. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
4. Confirm the Dupont run has enough slack to turn the breakout fully upside down without tugging a jumper out.

## Procedure
1. Start the 60 s window (the script waits through the ~4 s boot first):
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" flip --seconds 60
   ```
2. When the window banner prints, pick up the **breakout board itself** (not the Mega — the sensor is the thing at the end of the cable), turn it fully upside down, and hold it inverted and still until the console has reported the `-> DOWN` transition and at least 10 s of samples have accumulated (the >20-inverted-sample count is the verifiable end of the hold, not a stopwatch).
3. Return the breakout right-side-up on the bench and leave it until the window closes and the verdict line prints.
4. Record the final `samples / inverted / peak|gyro| / verdict` line.

## Pass criteria
- Script verdict is `PASS` (>20 samples with accel-Z < 0; the `-> DOWN` state banner separately requires accel-Z < −3 m/s²).
- Console reported at least two orientation transitions (`up` → `DOWN` → `up`).
- Reported peak |gyro| > 0.5 rad/s (the rotation itself was seen, not just the end states).
- No `valid=0` dropout during the handling (cable survived the flip).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-IMU-11 — Loop-timing capture with IMU attached — fill the TBD table row (residual)

| | |
|---|---|
| **Traces** | TASK-1 AC 1c; TASK-1 §6; SETUP.md timing table (IMU-attached row is _TBD_) |
| **Status** | draft |
| **Hardware** | Mega + shield, BMI270 wired per TP-IMU-02, USB cable, host with venv |
| **Est. time** | 10 min |

## Purpose
Completes the AC 1c evidence set: TP-IMU-06 proved the serial-path delta with the sensor absent, but the attached sensor adds the live ~3.5–4 ms I2C read (bounded by `I2C_WIRE_TIMEOUT_US`) inside each tick. This run shows that read fits inside the 50 ms budget and fills the `_TBD_` IMU-attached row in the SETUP.md timing table.

## Setup (from cold)
1. From `krabby-research/` on branch `m16-task1`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. BMI270 wired and verified per TP-IMU-01/02; firmware flashed per TP-IMU-03 (boot log shows the sensor online).
3. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
4. Place the board and breakout on a stable surface. TP-IMU-05/06 rows must exist for comparison.

## Procedure
1. With board and breakout untouched, capture 400 lines:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" timing
   ```
2. Confirm (via a quick `watch` run or the boot log) that the capture ran with `valid=1` — an IMU that silently failed init would reproduce the TP-IMU-06 row, not this one.
3. Record mean / p95 / max and line length into the SETUP.md "Loop timing (AC 1c)" table, replacing the `_TBD_` row.

## Pass criteria
- Capture completes 400 lines, board untouched, IMU `valid=1` throughout.
- Mean tick within 50 ± 2 ms (the ~4 ms I2C read absorbed inside the tick, not added to it).
- Mean-tick delta vs the TP-IMU-06 (IMU-absent) row < 1 ms; max tick < 65 ms.
- SETUP.md `_TBD_` row replaced with the measured numbers.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-IMU-12 — Runtime hot-disconnect resilience (valid drops to 0, no gait-loop stall)

| | |
|---|---|
| **Traces** | TASK-1 AC 1b (no crash/stall), 1d (valid = "sensor not responding"); TASK-1 §4; SETUP.md nan-temperature note |
| **Status** | draft |
| **Hardware** | Mega + shield, BMI270 wired per TP-IMU-02, USB cable, host with venv |
| **Est. time** | 15 min |

## Purpose
Proves the per-tick `valid`-flag semantics at runtime, not just at init: when the sensor vanishes mid-stream, `valid` must drop to 0 within a tick or two, the loop cadence must hold (`I2C_WIRE_TIMEOUT_US` bounds the stall), failed temperature reads must ship `nan` (which the Python parser drops rather than fabricating 0.0 °C — see SETUP.md "Telemetry segment"), and the system must recover after reconnection. De-risks a Qwiic cable working loose on a walking robot.

## Setup (from cold)
1. From `krabby-research/` on branch `m16-task1`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. BMI270 wired and verified per TP-IMU-01/02; firmware flashed per TP-IMU-03.
3. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
4. Identify the blue (SDA→D20) jumper so it can be pulled one-handed without disturbing the others.

## Procedure
1. Open a raw stream and confirm live `;IMU` samples with `valid=1`:
   ```sh
   python -m serial.tools.miniterm "$PORT" 250000
   ```
2. Pull the blue SDA jumper out of D20 and leave it out (binary state — jumper is either seated or not). Watch the stream: record how many lines pass before the `;IMU` segment reads `valid=0`, and whether the temp field prints `nan` on failed temperature reads.
3. Keep the jumper out for at least 20 telemetry lines (~1 s of data, verifiable by counting lines), confirming the line cadence visually holds (no multi-second gaps). Exit miniterm (Ctrl+]).
4. Re-seat the SDA jumper (note whether `valid` returns to 1 on a live re-seat — either recovery mode is acceptable in step 6; record which). Then quantify the no-stall claim across a disconnect: start a timing capture and pull the jumper again mid-capture, leaving it out until the 400 lines complete:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" timing
   ```
5. With the jumper still out, confirm parser behavior on the failure-path lines (the serial port is exclusive — run this only after the previous command has exited, never in parallel):
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" watch
   ```
   `watch` parses every line; `nan`/`valid=0` ticks must yield zero printed samples and no exception (the parser drops non-finite segments — no fabricated `0.0 °C`).
6. Re-seat the SDA jumper, power-cycle (unplug USB, LEDs dark, replug), and run:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" watch
   ```
   Record that `valid` returns to 1 (with the step-4 note on whether live re-seat alone had already recovered, or only the power cycle did).

## Pass criteria
- `valid` drops from 1 to 0 within **≤ 2 telemetry lines** (~100 ms) of the jumper pull.
- Telemetry lines keep flowing during the disconnect; the timing capture spanning the pull shows max tick < 65 ms (no stall beyond the I2C timeout bound).
- Failed temperature reads print `nan` on the wire; the Python parser yields no sample for those ticks (no fake 0.0 °C).
- After re-seat + power cycle, boot log shows the sensor online and `valid=1` samples resume.
- No firmware reset (no unexpected boot banner) at any point during the disconnect.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-IMU-13 — GUI IMU readout with live board

| | |
|---|---|
| **Traces** | TASK-1 AC 1e, 1h; TASK-1 §4 display change, §6 end-to-end (`python -m firmware.gui` / `KRABBY_MCU_RAW_RX=1`) |
| **Status** | draft |
| **Hardware** | Mega + shield, BMI270 wired per TP-IMU-02, USB cable, host with venv and a display |
| **Est. time** | 10 min |

## Purpose
Proves the operator-facing display path: the GUI shows the IMU readout near the header and updates it live from real hardware. `imu_bench.py` already exercised the parser and `format_compact`, but the GUI widget itself (`firmware/gui/app.py`) has not been run against a live board. Also confirms AC 1h by inspection: IMU values appear only in existing surfaces — no new `krabby-cli telemetry --imu` command exists.

## Setup (from cold)
1. From `krabby-research/` on branch `m16-task1`: `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
2. BMI270 wired and verified per TP-IMU-01/02; firmware flashed per TP-IMU-03.
3. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
4. Close any other process holding the serial port (miniterm, imu_bench) — the GUI needs exclusive access.

## Procedure
1. Launch the GUI (add `--port "$PORT"` if auto-detect picks the wrong device):
   ```sh
   python -m firmware.gui
   ```
2. Confirm the IMU readout appears near the header and shows values consistent with rest (|accel| ≈ 9.81 m/s², gyro ≈ 0).
3. Pick up the breakout, tip it onto one edge, and hold it there until the displayed accel axes visibly settle at the new orientation (the changed steady-state reading is the verifiable end of the hold). Return it flat and confirm the readout returns.
4. Optionally re-launch with raw-line dumping to eyeball the `;IMU` segment feeding the widget:
   ```sh
   KRABBY_MCU_RAW_RX=1 python -m firmware.gui
   ```
5. AC 1h inspection: confirm no IMU-specific CLI command was added:
   ```sh
   grep -ni "imu" firmware/cli.py || echo "no IMU CLI surface"
   ```

## Pass criteria
- GUI launches, connects, and renders an IMU readout near the header without error.
- Readout at rest shows |accel| within 9.81 ± 0.3 m/s² and each gyro axis within ±0.02 rad/s (the TP-IMU-07 bounds).
- During the held tilt, the displayed accel components settle at a distinctly different steady state, and return when laid flat (live updates, not a static paint).
- `KRABBY_MCU_RAW_RX=1` run shows the raw `;IMU` segment on the console for the same lines the GUI displays.
- Grep confirms no `krabby-cli telemetry --imu` (or any new IMU CLI command) exists.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-IMU-14 — Sensor→body axis-transform verification at mount time

| | |
|---|---|
| **Traces** | TASK-1 AC 1i; TASK-1 §2 (apply and document the transform), §3 (`IMU_AXIS_SIGN`/`IMU_AXIS_SRC`); SETUP.md "Axis convention" (currently identity) |
| **Status** | draft |
| **Hardware** | Robot chassis (or final mount fixture) with the BMI270 breakout fixed in its final orientation; Mega + shield, USB cable, host with venv |
| **Est. time** | 30 min |

## Purpose
Proves the `IMU_AXIS_SRC`/`IMU_AXIS_SIGN` constants in `sensors_config.h` map sensor axes to the robot body frame correctly once the breakout is physically mounted. The transform is intentionally identity today because the mount is not final; a wrong sign or swapped axis here silently corrupts every downstream consumer of body-frame inertial data, so the check must be redone against the physical mount, all six gravity orientations plus rotation signs.

## Setup (from cold)
1. **BLOCKED:** the breakout's mounting orientation on the robot is not final; the transform is intentionally identity until then. Do not run this procedure before the mount is fixed — results against a temporary mount are void.
2. From `krabby-research/` on branch `m16-task1` (or its successor): `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
3. Breakout fixed in its final mount; wiring verified per TP-IMU-01/02; firmware flashed per TP-IMU-03.
4. Plug in USB and find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
5. Have the robot body-frame convention written down (which way is body +X/+Y/+Z) before touching the hardware.

## Procedure
1. Start a long parsed stream:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" watch --seconds 300
   ```
2. Gravity check, six orientations: for each of body +X, −X, +Y, −Y, +Z, −Z in turn, orient that body axis vertically **up** and hold the robot/mount still until at least 5 consecutive printed samples agree (the agreeing samples are the verifiable end of each hold). Record which telemetry axis shows ≈ +9.81 m/s² and its sign.
3. Rotation check, three axes: rotate the body about each body axis in the right-hand-positive sense through roughly a quarter turn and back, pausing at each end; record which gyro axis moved and its sign during each rotation.
4. If any axis/sign disagrees with the body convention: edit `IMU_AXIS_SRC`/`IMU_AXIS_SIGN` in `firmware/arduino/sensors_config.h`, update SETUP.md "Axis convention / sensor→body transform" in the same change, reflash (`make -C firmware upload-firmware PORT=$PORT`), and repeat steps 1–3 from scratch.

## Pass criteria
- For each of the 6 orientations, the expected **body** axis reads +9.81 ± 0.3 m/s² and both other axes read < 1.0 m/s² in magnitude.
- For each of the 3 rotations, the expected body gyro axis carries the dominant signal with right-hand-rule sign.
- `sensors_config.h` constants and the SETUP.md axis-convention section were updated together (AC 1i) and the final constants are the ones the passing run was made with.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-IMU-15 — Three-board leader-only behavior — IMU on the FRONT line only, followers untouched

| | |
|---|---|
| **Traces** | TASK-1 AC 1a (leader only), 1d (leader's own line, not forwarded lines), 1f (role prefixes unchanged); TASK-1 §1, §4 |
| **Status** | draft |
| **Hardware** | Full three-Mega stack (FRONT + LEFT + RIGHT with follower UART links), BMI270 on the FRONT board only, USB to host, host with venv |
| **Est. time** | 30 min |

## Purpose
Proves the leader-only scoping under real role election rather than the solo `ROLE_UNKNOWN` bench case: the FRONT board wins election and appends `;IMU` to its own line only, the forwarded LEFT/RIGHT lines carry no IMU segment, followers never initialize `Wire`, and the `FRONT;`/`LEFT ;`/`RIGHT;` prefixes are byte-identical to upstream with no `controller_role` field (AC 1f — Milestone 14 owns role-in-telemetry).

## Setup (from cold)
1. **BLOCKED:** requires the two follower Megas; only the solo bench Mega (`ROLE_UNKNOWN`) is on hand. Solo-bench procedures TP-IMU-03..13 are the interim evidence.
2. From `krabby-research/` on branch `m16-task1` (or its successor): `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`.
3. Flash all three boards with the same M16 build, one at a time: `make -C firmware upload-firmware PORT=$PORT` per board (see SETUP.md §2.3 for per-board pin revs and `flash-remote` if the stack hangs off another host).
4. Wire the BMI270 to the **FRONT-electing board only**, per TP-IMU-01/02 (safety callouts there). Followers get no I2C wiring.
5. Connect follower UARTs per the three-board harness; leader on USB. Find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.

## Procedure
1. Power all three boards and let role election complete; confirm via boot logs that one board elects FRONT and initializes the IMU.
2. Capture raw lines from all three roles on the host:
   ```sh
   KRABBY_MCU_RAW_RX=1 python -m firmware --debug
   ```
   Let it run until at least 20 lines of each prefix (`FRONT;`, `LEFT ;`, `RIGHT;`) have been dumped, then exit. (Alternatively `python -m serial.tools.miniterm "$PORT" 250000`.)
3. Inspect the capture: `;IMU` presence per prefix, prefix spelling, and absence of any role field inside segments.
4. Confirm followers never bring up the bus: their boot logs contain no IMU/Wire init lines.

## Pass criteria
- Every `FRONT;` line ends with exactly one `;IMU ...` segment with `valid=1`.
- Zero `LEFT ;` or `RIGHT;` (forwarded) lines contain an `IMU` token.
- Role prefixes are unchanged from upstream (`FRONT;`/`LEFT ;`/`RIGHT;`), and no `controller_role` field appears anywhere in any line.
- Follower boot logs contain no `IMU CAL:` or Wire-init lines.
- Existing joint segments on all three lines still parse (9 tokens each) with no corruption.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-IMU-16 — Full three-board integration timing run (tests/integration/test_timing.py)

| | |
|---|---|
| **Traces** | TASK-1 AC 1c; TASK-1 §6 (existing integration timing test); SETUP.md loop-timing note ("captured at robot integration") |
| **Status** | draft |
| **Hardware** | Assembled three-Mega stack per TP-IMU-15 (BMI270 on FRONT), USB to host, host with venv |
| **Est. time** | 30 min |

## Purpose
Proves loop timing holds under the real full load, which the solo bench cannot reproduce: three lines per 50 ms tick (leader + two forwarded follower lines, ~48% of the 1250 B/tick budget at 250000 baud) plus the live IMU I2C read plus follower-UART servicing against the 256 B RX buffers. This is the final AC 1c evidence tier above the solo-bench rows of TP-IMU-05/06/11.

## Setup (from cold)
1. **BLOCKED:** requires the assembled three-Mega stack; only the solo bench Mega is on hand. Solo-bench timing rows (TP-IMU-05/06/11) are the interim evidence.
2. From `krabby-research/` on branch `m16-task1` (or its successor): `python3.11 -m venv testenv && source testenv/bin/activate && pip install -r firmware/requirements.txt`. The integration suite additionally imports numpy/torch and the `hal`/`compute` packages — the firmware venv alone cannot run it; use the Dockerized test environment (root `make test`, which needs Docker + the GPU toolkit per `scripts/setup-docker-gpu.sh`) or a full dev install per `DEVELOPER.md`.
3. Three boards flashed, harnessed, and passing TP-IMU-15 (leader-only scoping proven first — a mis-scoped IMU invalidates the timing claim).
4. Leader on USB. Find the port: macOS `PORT=$(ls /dev/cu.usbmodem*)` (approve the accessory prompt if needed); Linux `PORT=$(ls /dev/ttyACM*)`.
5. Keep the stack stationary for the duration.

## Procedure
1. Run the existing integration timing test (the timing gate TASK-1 §6 names). Note it exercises the HAL/inference control-loop budget in software — it does not open the bench serial port; the hardware-side numbers come from step 2:
   ```sh
   pytest tests/integration/test_timing.py -v
   ```
2. Capture the host-side inter-line stats for the leader line of the assembled stack so the number is comparable to the solo-bench table rows:
   ```sh
   python firmware/scripts/imu_bench.py "$PORT" timing
   ```
3. Record both results next to the solo-bench rows in the SETUP.md "Loop timing (AC 1c)" table, noting the three-board configuration.

## Pass criteria
- `tests/integration/test_timing.py` passes (exit code 0, no timing assertion failures).
- Leader-line inter-line stats: mean tick 50 ± 2 ms, max < 65 ms. (`timing` mode prints only aggregate stats — confirm all three role prefixes are present in the stream with a short `python -m serial.tools.miniterm "$PORT" 250000` look before or after the capture.)
- No serial corruption symptoms (missing actuators, malformed segments) across the capture — the 256 B follower RX buffers keep up with the added IMU bytes.
- Numbers recorded in SETUP.md alongside the solo-bench rows.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |
