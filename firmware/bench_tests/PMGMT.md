# Bench test procedures — PMGMT (M16 Task 4: power management)
Traces: `patina-foundation-grants/grants/Krabby-Uno/Milestone16-I2C-Sensors/TASK-4-POWER-MANAGEMENT.md` (AC 4a–4k) + OVERVIEW Task 4.
Hardware baseline: solo Mega 2560 R3 + Krabby-Uno shield (bench leader, ROLE_UNKNOWN), Qwiic chain (BMI270 @0x69, OLED @0x3D, 2× INA228 @0x40/0x41), Klein multimeter; PSU / M12 pack / Orin only where a TP says so.

## Conventions (read once, referenced by every TP)

- **Venv + port.** All commands run from `krabby-research` repo root in the `testenv` venv (`make venv`, `source testenv/bin/activate`, `pip install -r firmware/requirements.txt`). Port discovery: `ls /dev/cu.usbmodem*` (macOS — if nothing enumerates, clear the accessory-permission gate in System Settings → Privacy & Security) or `ls /dev/ttyACM*` (Linux). `export PORT=<device>`. Serial is **250000** baud; **opening the port resets the board** (macOS pulses DTR regardless of pyserial settings — see SETUP.md), so each TP opens the console **once** and keeps it open for the whole procedure.
- **Firmware prerequisite.** Every TP requires a firmware build containing the Task 4 state machine + sim hook (and the Task 2 OLED/LED and Task 3 BATT paths where a TP uses them). On earlier builds (e.g. the `m16-task1` bench firmware, `94edd67..00237a8`) `SIMV` is silently ignored and there is no BATT frame or `power_state` — nothing here can pass. Confirm before starting: send `V` on the console and check the reported branch/commit is a Task 4 build.
- **Sim hook assumption.** These TPs assume the Task 4 pack-voltage sim hook is the serial command **`SIMV <volts>`** (override `pack_v` at the INA228 read site, so it stays effective inside low-power mode) and **`SIMV OFF`** (clear). If the implemented command or a build flag differs, update every TP here in the same commit. The hook must be engaged **before** the state machine can act on a real reading: on a bench with no pack, real `pack_v` reads ~0 V, which is below HARD_CUT — the implementation must gate on a valid Pack INA228 reading or the sim hook, or every bench boot instantly hard-cuts.
- **Thresholds.** The five named constants in `firmware/arduino/sensors_config.h` (AC 4a), Appendix-C defaults: WARN 24.8, SOFT_CUT 24.0, HARD_CUT 22.4, RECOVERY 26.4, OVER_VOLT 29.6 V. TPs use values 0.1 V either side of each constant; re-derive the numbers if the constants change.
- **Timestamped serial console** (the capture tool every TP means by "the console"). Substitute the TP's log file name for `tpNN.log`. A blank Enter press is logged as an empty `>>>` stamp and sent as a bare newline — harmless to the firmware (unknown/blank lines are consumed and ignored in `arduino.ino`'s command dispatch); TP-PMGMT-10/16 rely on this as the keepalive:

```bash
python -c '
import sys, time, threading, serial
ser = serial.Serial(sys.argv[1], 250000, timeout=1)
log = open(sys.argv[2], "a", buffering=1)
def rx():
    while True:
        b = ser.readline()
        if b:
            s = "%.3f %s" % (time.time(), b.decode(errors="replace").rstrip())
            print(s); log.write(s + "\n")
threading.Thread(target=rx, daemon=True).start()
print("console ready - firmware commands (e.g. SIMV 23.9); blank Enter = keepalive; Ctrl-C to exit")
for cmd in sys.stdin:
    line = cmd.strip()
    log.write("%.3f >>> %s\n" % (time.time(), line))
    ser.write(line.encode() + b"\n")
' "$PORT" tpNN.log
```

- **Cross-references.** Baseline wiring + flash procedure: SETUP.md "Bench bring-up runbook (M16)". Bus diagnostics: `firmware/bench_sketches/i2c_scanner/` (flash instructions in the sketch header; reflash real firmware afterwards). IMU sanity/timing: `python firmware/scripts/imu_bench.py $PORT watch|timing|flip`.

---

# TP-PMGMT-01 — Simulated pack-voltage threshold walk through all five states

| | |
|---|---|
| **Traces** | AC 4a; TASK-4 §1 (state machine); OVERVIEW Task 4 |
| **Status** | draft — ready to run |
| **Hardware** | Mega + shield, Pack INA228 (0x40) on the Qwiic chain, USB, laptop |
| **Est. time** | 20 min |

## Purpose
Proves the state machine reads the Task 3 `pack_v` path and transitions WARN → SOFT_CUT → HARD_CUT (and separately OVER_VOLT) at exactly the five named constants in `sensors_config.h` — i.e. the thresholds are real, tunable configuration, not buried logic — before any real voltage source ever touches the bench. Everything downstream (TP-02…10) leans on these transitions firing at the right values.

## Setup (from cold)
1. Venv + `PORT` per Conventions.
2. **SAFETY:** before first sensor connect, verify the 3V3 rail = 3.30 ± 0.1 V per SETUP.md runbook step 1 (Dupont jumpers in `3V3`/`GND`, probe the free ends). The BMI270/Qwiic parts are not 5 V tolerant — this check is the one that saves the sensor cluster.
3. Wire (USB unplugged) the Qwiic chain per SETUP.md wiring table; Pack INA228 strapped to **0x40** at the shunt sense point per the Task 3 bench setup. TP precondition: BATT frame flowing (Task 3 alive).
4. Flash: `make -C firmware upload-firmware PORT=$PORT`.
5. Open the console (Conventions) with log file `tp01.log`; wait through the ~4 s boot until telemetry lines flow.

## Procedure
1. Engage the sim at nominal: type `SIMV 25.6`. Confirm the BATT frame shows `power_state` = nominal/OK and `pack_v` = 25.60.
2. WARN boundary: `SIMV 24.9` → still nominal; `SIMV 24.7` → `power_state` = WARN in the next BATT frame. Telemetry must otherwise continue unchanged (WARN is telemetry-only).
3. Back out: `SIMV 25.6` → WARN clears (WARN has no hysteresis latch per spec §1).
4. SOFT_CUT boundary: `SIMV 24.1` → still WARN; `SIMV 23.9` → `POWERING_DOWN` appears and shutdown begins. Do not ack; let it run to sleep (detail verified in TP-03).
5. Press the Mega **RESET** button (do not close/reopen the port); wait for reboot telemetry, re-engage `SIMV 25.6`.
6. HARD_CUT boundary, upper side: `SIMV 22.5` → `POWERING_DOWN` appears and telemetry keeps flowing into the ack window (22.5 V is below SOFT_CUT but above HARD_CUT, so the graceful path fires — proving 22.5 V does **not** hard-cut). RESET, re-engage `SIMV 25.6`.
7. HARD_CUT boundary, lower side: `SIMV 22.3` → telemetry stops immediately, no `POWERING_DOWN` (immediate cut, no handshake). RESET, re-engage `SIMV 25.6`.
8. OVER_VOLT boundary: `SIMV 29.5` → nominal; `SIMV 29.7` → `OVER_VOLTAGE_SHUTDOWN` appears, telemetry stops. RESET.
9. `SIMV OFF`, Ctrl-C the console, keep `tp01.log` as evidence.

## Pass criteria
- `power_state` in the BATT frame changes at the constant values: transition present at 24.7/23.9/22.3/29.7 V, absent at 24.9/24.1/29.5 V.
- HARD_CUT boundary bracketed: at 22.5 V `POWERING_DOWN` is emitted and telemetry continues into the ack window (graceful path); at 22.3 V no `POWERING_DOWN` and telemetry stops within 2 telemetry ticks (immediate path).
- SOFT_CUT emits `POWERING_DOWN`; HARD_CUT emits nothing and telemetry stops; OVER_VOLT emits `OVER_VOLTAGE_SHUTDOWN`.
- WARN changes `power_state` only — telemetry cadence and joint segments unaffected.
- All five values used came from `sensors_config.h` constants, not literals in the test.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-02 — Power-state message emission and host-side parse (schema_version)

| | |
|---|---|
| **Traces** | AC 4b; TASK-4 §5 |
| **Status** | draft — ready to run |
| **Hardware** | Same as TP-PMGMT-01 |
| **Est. time** | 20 min |

## Purpose
Proves every Mega→Orin power message (`POWERING_DOWN` with each reason code, `RESUMING`, `OVER_VOLTAGE_SHUTDOWN`) carries the leading `schema_version` byte and round-trips through the parser definitions committed under `firmware/interfaces/` (AC 4b), and that the append-only telemetry contract holds — legacy telemetry parsing is unaffected by the new message types on the same link. The laptop stands in for the Orin reader; this is the exact stream the §6 daemon will consume.

## Setup (from cold)
1. Steps 1–4 of TP-PMGMT-01 Setup (venv, safety check, wiring, flash).
2. Open the console with log file `tp02.log`.

## Procedure
1. `SIMV 25.6` to engage the sim at nominal.
2. `SIMV 23.9` → capture `POWERING_DOWN` reason `under_voltage_soft`. Let the 60 s window lapse to sleep, then `SIMV 26.5` → capture `RESUMING` reason `voltage_recovered`.
3. If the firmware exposes a manual shutdown command (reason `manual`, per §5 table), trigger it and capture that `POWERING_DOWN` variant; otherwise record "manual reason not triggerable from bench" in the run log.
4. `SIMV 29.7` → capture `OVER_VOLTAGE_SHUTDOWN`. Press RESET.
5. Ctrl-C the console. Parse the capture with the committed interface definitions:

```bash
python -c '
import sys
from firmware.interfaces.joint_telemetry import parse_telemetry_line
# power-message parser: import from the module committed under firmware/interfaces/ per AC 4b
# (fill in the final module/function name when Task 4 lands and delete this comment)
from firmware.interfaces.power_messages import parse_power_message  # AC 4b module
telem = power = bad = 0
for raw in open("tp02.log"):
    line = raw.split(" ", 1)[-1].strip()
    if line.startswith((">>>",)) or not line: continue
    msg = parse_power_message(line)
    if msg is not None:
        power += 1; print(msg); continue
    p = parse_telemetry_line(line)
    telem += 1 if p and p.joints else 0
print(f"telemetry lines parsed: {telem}, power messages parsed: {power}")
'
```

6. Legacy-contract check: confirm `parse_telemetry_line` parsed the interleaved telemetry lines from `tp02.log` at the normal rate (no drop while power messages were in-stream).

## Pass criteria
- All three Mega→Orin message types (`POWERING_DOWN`, `RESUMING`, `OVER_VOLTAGE_SHUTDOWN`) captured and parsed by the `firmware/interfaces/` definitions with zero parse errors. (`SHUTDOWN_ACK` is Orin→Mega — its wire exchange is TP-PMGMT-04's job.)
- Every parsed message reports the expected `schema_version` value, and the byte is leading (first field on the wire).
- `POWERING_DOWN` carries a machine-readable reason code: `under_voltage_soft` observed; `manual` observed or explicitly waived per procedure step 3.
- Telemetry lines/second in the 30 s around each power message is within 10% of a message-free 30 s window from the same capture (append-only contract intact).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-03 — SOFT_CUT graceful sequence on solo bench (no ack → 60 s timeout)

| | |
|---|---|
| **Traces** | AC 4c; TASK-4 §2 |
| **Status** | draft — ready to run |
| **Hardware** | Same as TP-PMGMT-01 + Klein multimeter, two M-M Dupont jumpers |
| **Est. time** | 15 min |

## Purpose
Proves the ordered SOFT_CUT sequence with no host ack: `POWERING_DOWN(under_voltage_soft)` → park/de-energize (`ActuatorManager::holdAll()` drops EN + PWM — on the motorless bench, observable as EN pins D22–D27 falling to 0 V) → full ~60 s ack window → low-power sleep. Records the actual timeout duration for the AC 4k evidence table. The physical park posture needs real legs and is deferred to TP-PMGMT-17; this TP owns the EN-drop half.

## Setup (from cold)
1. Steps 1–4 of TP-PMGMT-01 Setup.
2. Plant a Dupont jumper in header **D22** and one in **GND** for meter access (female headers don't take probes — same trick as the SETUP.md 3V3 check). **SAFETY:** keep the two free jumper ends from touching each other or adjacent pins while the board is powered — D22's neighbors are live outputs.
3. Open the console with log file `tp03.log`.

## Procedure
1. `SIMV 25.6`. Energize the FL yaw channel so the EN drop is observable: type `T LHY 0.5` (repeat every few seconds to keep the target fresh). Hold the meter on D22↔GND: it must read ≥ 4.5 V. If the bench board's safety layer refuses to energize without pots attached, record that and fall back to verifying D22 stays 0 V throughout (serial-sequence evidence still binding).
2. Keep holding the meter on D22. Type `SIMV 23.9` and do not send any ack.
3. Observe in order: `POWERING_DOWN` in the console; D22 falls to < 0.5 V (park/de-energize); then silence.
4. Hold hands off for the full window. When telemetry stops (sleep entry), Ctrl-C the console.
5. Compute the ack window from `tp03.log` host timestamps: last-telemetry-line time minus `POWERING_DOWN` time.
6. Probe D22–D27 in turn (board asleep): all < 0.5 V.

## Pass criteria
- Exact order on the wire: `POWERING_DOWN(under_voltage_soft)` precedes EN drop precedes telemetry stop.
- D22 reads ≥ 4.5 V energized before the trigger (or the documented fallback), and every EN pin D22–D27 reads < 0.5 V after park.
- Measured ack window = 60 ± 3 s from `POWERING_DOWN` to telemetry stop, no ack sent.
- No `RESUMING` and no telemetry for ≥ 60 s after sleep entry (sim still at 23.9 V).
- Measured window recorded in the run log (feeds the 4k evidence table).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-04 — SHUTDOWN_ACK handshake with laptop as Orin stand-in

| | |
|---|---|
| **Traces** | AC 4c, 4j (protocol half); TASK-4 §2, §6 |
| **Status** | draft — ready to run |
| **Hardware** | Same as TP-PMGMT-01 |
| **Est. time** | 15 min |

## Purpose
Proves the firmware side of the ack protocol: on `SHUTDOWN_ACK` received mid-window, the Mega proceeds to sleep promptly instead of burning the rest of the 60 s. This de-risks the exact wire exchange the §6 Orin daemon will implement, using only the bench laptop, before any Orin hardware exists. Caution baked into the procedure: opening the port resets the board, so trigger and ack must travel over one persistent connection.

## Setup (from cold)
1. Steps 1–4 of TP-PMGMT-01 Setup.
2. Open the console with log file `tp04.log` — this single connection carries both the trigger and the ack.

## Procedure
1. `SIMV 25.6`, confirm nominal BATT frames.
2. `SIMV 23.9`. Wait for `POWERING_DOWN` in the console.
3. Roughly 10 s into the window (any point well inside it; the log timestamps the actual moment), type the ack line exactly as defined in `firmware/interfaces/` (AC 4b wire format — e.g. `SHUTDOWN_ACK`; use the committed definition, not this placeholder).
4. Observe telemetry stop (sleep entry). Ctrl-C.
5. From `tp04.log`: compute ack-to-sleep delay (last telemetry line minus the `>>>` ack timestamp) and total window (sleep minus `POWERING_DOWN`).

## Pass criteria
- Firmware sleeps within 5 s of the ack, and the total window (`POWERING_DOWN` → telemetry stop) is at least 40 s shorter than the TP-PMGMT-03 no-ack measurement.
- Park/EN-drop still occurred before sleep (no telemetry after the ack shows re-energized joints).
- The ack was sent on the same connection that saw `POWERING_DOWN` (no port reopen anywhere in the procedure).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-05 — HARD_CUT immediate emergency path

| | |
|---|---|
| **Traces** | AC 4d; TASK-4 §2 |
| **Status** | draft — ready to run |
| **Hardware** | Same as TP-PMGMT-03 (meter + jumpers on D22/GND) |
| **Est. time** | 10 min |

## Purpose
Proves HARD_CUT is the no-ceremony path: EN drops immediately, no park delay, no `POWERING_DOWN`, no 60 s wait — straight to sleep, and telemetry simply stops. That silence is the out-of-band signal the Orin is specced to detect (§2). Also timestamps trigger-to-cut latency from the host log.

## Setup (from cold)
1. Steps 1–2 of TP-PMGMT-03 Setup (wiring, flash, meter jumpers on D22/GND).
2. Open the console with log file `tp05.log`.

## Procedure
1. `SIMV 25.6`; energize FL yaw with `T LHY 0.5` and confirm D22 ≥ 4.5 V on the meter (or the TP-03 fallback).
2. Hold the meter on D22. Type `SIMV 22.3` (directly below HARD_CUT, skipping the SOFT_CUT band).
3. Watch the meter: D22 must fall to < 0.5 V essentially at the keystroke. Watch the console: nothing new prints; telemetry just stops.
4. Wait 90 s hands-off, then Ctrl-C.
5. From `tp05.log`: trigger-to-silence latency = last telemetry line minus the `>>> SIMV 22.3` timestamp.

## Pass criteria
- No `POWERING_DOWN`, no `OVER_VOLTAGE_SHUTDOWN`, no handshake traffic after the trigger — the capture shows only telemetry ending.
- D22 < 0.5 V after the trigger, observed while holding the probe through the keystroke.
- Trigger-to-telemetry-stop latency ≤ 2 telemetry ticks = ≤ 120 ms per host timestamps (measured tick on this bench: mean 50.77 ms, max 58.84 ms — SETUP.md "Loop timing (AC 1c)" table).
- No resume activity within the 90 s hold (sim still below HARD_CUT).
- Latency recorded in the run log.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-06 — OVER_VOLT one-way cutout with no auto-recovery

| | |
|---|---|
| **Traces** | AC 4e; TASK-4 §2 |
| **Status** | draft — ready to run |
| **Hardware** | Same as TP-PMGMT-01 |
| **Est. time** | 15 min |

## Purpose
Proves the over-voltage cutout is one-way: `OVER_VOLTAGE_SHUTDOWN` is sent, motors drop, the board sleeps, and it must NOT resume when the voltage returns to nominal — even across multiple 30 s recovery-poll cycles. Only a manual reset recovers it. This is the protection against a charger/BMS fault chattering the robot back onto a faulted pack.

## Setup (from cold)
1. Steps 1–4 of TP-PMGMT-01 Setup.
2. Open the console with log file `tp06.log`.

## Procedure
1. `SIMV 25.6`, confirm nominal.
2. `SIMV 29.7` → capture `OVER_VOLTAGE_SHUTDOWN`, telemetry stops.
3. Return the sim to nominal: `SIMV 25.6`. Hold hands-off for **120 s** (≥ 3 recovery-poll cycles at the ~30 s cadence, plus margin).
4. Confirm the console stayed silent for the whole hold: no `RESUMING`, no telemetry.
5. Press the Mega **RESET** button (manual recovery — do not reopen the port). Watch the console for normal boot logs and telemetry resuming.
6. Ctrl-C; `tp06.log` is the evidence.

## Pass criteria
- `OVER_VOLTAGE_SHUTDOWN` present exactly once; telemetry stops after it.
- Zero output (no `RESUMING`, no telemetry, no splash-related serial) during the 120 s nominal-voltage hold.
- After the physical RESET, the board boots and telemetry flows normally.
- No `POWERING_DOWN`/ack traffic anywhere in the capture (this path has no handshake).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-07 — Low-power mode poll discipline and ~30 s recovery cadence

| | |
|---|---|
| **Traces** | AC 4f; TASK-4 §3 |
| **Status** | draft — ready to run |
| **Hardware** | Same as TP-PMGMT-01 (OLED on the chain, visible to the operator) |
| **Est. time** | 25 min |

## Purpose
Proves the low-power behavioral contract: after SOFT_CUT sleep the board does nothing but poll the Pack INA228 and blink/splash — normal telemetry stops, the normal OLED UI stops, no IMU activity — and the recovery check runs on a ~30 s cadence. Cadence is measured by raising sim voltage above RECOVERY at a logged instant and timestamping when resume fires relative to it, repeated to bracket the poll clock.

## Setup (from cold)
1. Steps 1–4 of TP-PMGMT-01 Setup. OLED (0x3D) must be on the chain and face the operator.
2. Open the console with log file `tp07.log`.

## Procedure
1. `SIMV 25.6`, confirm normal telemetry and the normal OLED UI rendering.
2. `SIMV 23.9`, no ack; wait through the 60 s window into sleep.
3. Quiet-mode check (2 min hands-off): console shows no telemetry; OLED shows no normal UI (only the ~10 s dead-battery splash, which TP-PMGMT-08 owns); no `;IMU` segments anywhere post-sleep. Optional bus double-check if something looks alive: the `bench_sketches/i2c_scanner` pattern (requires reflash — diagnostic only, restart this TP afterwards).
4. Cadence measurement: type `SIMV 26.5` (just above RECOVERY) and note the `>>>` timestamp; measure time until `RESUMING` appears. Record Δ₁.
5. Repeat twice more: after resume, `SIMV 23.9` → wait through window to sleep → `SIMV 26.5` → record Δ₂, Δ₃.
6. Ctrl-C; compute Δ values from `tp07.log`.

## Pass criteria
- Zero telemetry lines and zero `;IMU` segments between sleep entry and `RESUMING`, in all three cycles.
- Normal OLED UI verifiably absent during sleep (operator observes only periodic splash, never the live status screen).
- All three Δ ≤ 35 s, and at least one Δ > 5 s (free-running ~30 s poll, not continuous checking).
- All three Δ values recorded in the run log (feeds the 4k evidence table).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-08 — Dead-battery OLED splash + red LED cadence, OLED silenced below HARD_CUT floor

| | |
|---|---|
| **Traces** | AC 4g; TASK-4 §3 |
| **Status** | draft — ready to run |
| **Hardware** | Same as TP-PMGMT-01 + red LED wired to the Task 2 status-LED pin (per `board_pins.h`, Task 2 bench wiring) + phone camera |
| **Est. time** | 20 min |

## Purpose
Proves the low-power indicator contract: in sleep, a dead-battery splash on the Qwiic OLED plus a red-LED blink on a ~10 s cadence; and once `pack_v` falls below the HARD_CUT floor, the OLED splash stops entirely (it drains an already-critical pack) while the LED blink continues (or the board goes fully dark — record which the implementation chose). Records both cadences for the 4k evidence table.

## Setup (from cold)
1. Steps 1–4 of TP-PMGMT-01 Setup, plus the Task 2 red LED wired to its `board_pins.h` pin.
2. Position OLED and LED in one phone-camera frame.
3. Open the console with log file `tp08.log`.

## Procedure
1. `SIMV 25.6`, then `SIMV 23.9`, no ack; wait into sleep.
2. Start a 90 s phone video of OLED + LED. (Counting events on video converts a fuzzy human timing judgment into a countable, binary record.)
3. From the video: count OLED splashes N_oled and LED blink events N_led in the 90 s window. Cadence = 90/N.
4. Type `SIMV 22.0` (below the HARD_CUT floor, board already asleep). Record a second 90 s video.
5. From the second video: count splashes (expect 0) and LED blinks (expect the cadence to continue — or note fully-dark behavior if that's what shipped).
6. Ctrl-C; keep both videos with `tp08.log`.

## Pass criteria
- First window: N_oled and N_led both in 7–11 events per 90 s (≈10 s cadence), splash visibly the dead-battery icon, not the normal UI.
- Second window (below HARD_CUT floor): N_oled = 0.
- Second window: LED blink cadence unchanged (7–11 per 90 s), OR the board is documented fully dark by design — one of the two, recorded explicitly.
- Both cadences written into the run log (feeds the 4k evidence table).

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-09 — RECOVERY auto-resume with ≥ 0.4 V hysteresis

| | |
|---|---|
| **Traces** | AC 4f; TASK-4 §1, §4 |
| **Status** | draft — ready to run |
| **Hardware** | Same as TP-PMGMT-03 (meter on an EN pin for the motor-EN-return check) |
| **Est. time** | 20 min |

## Purpose
Proves the hysteresis band holds and the resume path is complete: sim voltage between SOFT_CUT and RECOVERY must NOT wake the board (no chatter at the boundary); crossing RECOVERY (≥ 0.4 V above SOFT_CUT) must emit `RESUMING(voltage_recovered)` and restore normal polling, telemetry, OLED UI, and motor-EN behavior. A down-up-down cycle proves no oscillation.

## Setup (from cold)
1. Steps 1–2 of TP-PMGMT-03 Setup (meter jumpers on D22/GND).
2. Open the console with log file `tp09.log`.

## Procedure
1. `SIMV 25.6`, then `SIMV 23.9`, no ack; wait into sleep.
2. Hysteresis hold: `SIMV 25.0` (inside the 24.0–26.4 band). Hands off for **120 s** (≥ 3 poll cycles). The console must stay silent.
3. Cross RECOVERY: `SIMV 26.5`. Capture `RESUMING` (reason `voltage_recovered`) and telemetry restarting; operator confirms the normal OLED UI is back.
4. Motor-EN return: `T LHY 0.5` and read D22 on the meter — ≥ 4.5 V again (or the TP-03 fallback); `;IMU` segments present again in telemetry.
5. Oscillation cycle: `SIMV 23.9` (down — capture second `POWERING_DOWN`, wait into sleep) → `SIMV 26.5` (up — capture second `RESUMING`) → `SIMV 23.9` (down again, wait into sleep). Each edge must produce exactly one transition.
6. Ctrl-C; count transitions in `tp09.log`.

## Pass criteria
- Zero `RESUMING` and zero telemetry during the 120 s in-band hold at 25.0 V.
- `RESUMING(voltage_recovered)` within 35 s of crossing to 26.5 V (one poll period).
- Post-resume: telemetry cadence normal, `;IMU` segments present, OLED UI restored, D22 re-energizable.
- Down-up-down cycle yields exactly 2× `POWERING_DOWN` + 2× `RESUMING` in total across the whole log — no duplicate or bounced transitions at any boundary.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-10 — Orin power-control GPIO cycle on bare Mega (multimeter, no Orin)

| | |
|---|---|
| **Traces** | AC 4i (MCU side); TASK-4 §4 force-off rule |
| **Status** | draft — ready to run |
| **Hardware** | Same as TP-PMGMT-01 + meter jumper on the Task 4 Orin power-control GPIO (spare pin per `board_pins.h` — use the pin the implementation defines, e.g. `PIN_ORIN_PWR`) |
| **Est. time** | 20 min |

## Purpose
Proves the entire 4i control logic on the bare Mega with a multimeter, before the supply-switch/optocoupler hardware exists: the control GPIO asserts off on SOFT_CUT/HARD_CUT sleep entry, re-asserts on `RESUMING`, and flips to force-off at the 60 s mark after an unacked shutdown with the host link still active. When TP-PMGMT-13 builds the real hardware, bring-up becomes wiring-only.

## Setup (from cold)
1. Steps 1–4 of TP-PMGMT-01 Setup.
2. Confirm the chosen GPIO number in `firmware/arduino/board_pins.h` (Task 4 addition; do not guess — same discipline as the Task 2 LED pin selection). Plant a meter jumper in that header pin and one in GND (the TP-PMGMT-03 setup step 2 shorting caution applies to these jumper ends too).
3. Note the polarity convention the implementation documents (assume here: HIGH = Orin powered; invert readings below if the implementation chose active-low).
4. Open the console with log file `tp10.log`.

## Procedure
1. `SIMV 25.6`. Meter on the GPIO: reads the "Orin on" level (≥ 4.5 V for active-high).
2. SOFT_CUT entry: `SIMV 23.9`, no ack, hold the meter through the sequence. At sleep entry the GPIO must read the "off" level (< 0.5 V active-high). Note from `tp10.log` whether it flipped at sleep entry vs at the 60 s force-off mark — record which.
3. Resume: `SIMV 26.5` → on `RESUMING`, GPIO returns to "on".
4. Force-off timing: `SIMV 23.9` again, no ack, and keep the host link visibly active by pressing Enter (blank keepalive lines land in the log as `>>>` stamps) every ~5 s. Hold the meter on the GPIO; when it flips off, immediately press Enter once more — the delta between that `>>>` stamp and the `POWERING_DOWN` stamp bounds the force-off time to within a few seconds.
5. HARD_CUT: RESET the board, `SIMV 25.6`, then `SIMV 22.3` — GPIO must read "off" after the cut.
6. Ctrl-C; extract timings from `tp10.log`.

## Pass criteria
- GPIO at "on" level in normal operation; "off" after SOFT_CUT sleep entry; "off" after HARD_CUT; back to "on" on `RESUMING` — all four observed on the meter.
- Force-off flip occurs at 60 ± 5 s after `POWERING_DOWN` per the log-bounded measurement, despite continuing host traffic and no ack.
- Polarity and pin number match what `board_pins.h` + the 4i wiring doc claim.
- Measured force-off time recorded in the run log.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-11 — Real-voltage PSU ramp end-to-end (AC 4k bench test)

| | |
|---|---|
| **Traces** | AC 4k, 4a; TASK-4 §8 |
| **Status** | draft — blocked: adjustable current-limited lab PSU (22–30 V range) not on hand |
| **Hardware** | Mega + shield + full Qwiic chain, adjustable current-limited lab PSU (22–30 V), Pack INA228 VBUS sense wiring, Klein multimeter |
| **Est. time** | 45 min |

## Purpose
The AC 4k spec test: replaces the sim hook with real voltage at the Pack INA228 VBUS sense point and re-proves the full cycle against real ADC readings — ramp down through WARN → SOFT_CUT (park, `POWERING_DOWN`, 60 s window, sleep), back up through RECOVERY (`RESUMING`), and separately above OVER_VOLT (one-way cutout) — while confirming the ~30 s recovery poll and ~10 s indicator cadence survive contact with real measurement noise. All timings recorded per spec.

## Setup (from cold)
1. **BLOCKED:** requires an adjustable current-limited lab PSU covering 22–30 V; not on hand. Everything below is written so the TP runs the day the PSU arrives.
2. Steps 1–4 of TP-PMGMT-01 Setup, with the sim hook left **disengaged** (never send `SIMV`; or build without the sim flag).
3. **SAFETY:** set the PSU current limit to ≤ 100 mA and output-off before touching wiring. Connect PSU+ to the Pack INA228 VBUS sense point (pack side of the shunt per the Task 3 bench setup) and PSU− to battery-negative/GND. Meter-verify polarity at the INA terminals before enabling output — the INA228 VBUS pin is the only thing this PSU should be able to hurt, and only if reversed or over-ranged.
4. Open the console with log file `tp11.log`.

## Procedure
1. PSU on at 26.8 V (resting-full). Confirm the BATT frame `pack_v` tracks the PSU within 1% (cross-check the Klein meter at the INA terminals).
2. Ramp down slowly (~0.1 V/step, pausing ≥ 2 telemetry ticks per step): record the `pack_v` at which WARN appears, then continue to SOFT_CUT — observe `POWERING_DOWN`, EN drop, 60 s window (no ack), sleep.
3. In sleep: verify the ~10 s splash/LED cadence (count over 90 s, TP-08 method) and hold 25.0 V for 120 s to confirm the hysteresis band on real voltage.
4. Ramp up to 26.6 V: observe `RESUMING` within one ~30 s poll; note the actual `pack_v` at resume.
5. RESET the board. Separately ramp up from 26.8 V until `OVER_VOLTAGE_SHUTDOWN` fires; record the trip voltage; return to 26.8 V and confirm no resume for 120 s; RESET.
6. Ctrl-C; extract every timing and trip voltage from `tp11.log`.

## Pass criteria
- Each observed trip voltage within ±0.15 V of its `sensors_config.h` constant (real-ADC tolerance; tighten after INA calibration data exists).
- Full SOFT_CUT sequence, 60 ± 3 s window, sleep, and resume-on-RECOVERY all reproduce the TP-03/07/09 sim results on real voltage.
- ~30 s recovery poll and ~10 s indicator cadence confirmed (same numeric bounds as TP-07/TP-08).
- OVER_VOLT one-way behavior reproduces TP-06 on real voltage.
- All trip points and timings recorded in the run log — this row IS the 4k evidence.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-12 — Appendix-C threshold validation against the real M12 pack (resting vs loaded)

| | |
|---|---|
| **Traces** | AC 4h; TASK-4 §7 |
| **Status** | draft — blocked: M12 battery pair (2× 12 V / 100 Ah LiFePO4) not on hand (Milestone 12 dependency) |
| **Hardware** | M12 pack pair (8S series), 200A/75mV shunt, 150 A fuse, Klein multimeter, Pack INA228, representative load |
| **Est. time** | 60 min |

## Purpose
Validates the Appendix-C threshold table (WARN 24.8 / SOFT_CUT 24.0 / RECOVERY 26.4 / HARD_CUT 22.4 / OVER_VOLT 29.6 V) against the actual pack chemistry: measure resting-full, nominal, and loaded voltages, quantify the resting-vs-loaded delta (pack internal resistance × current — LiFePO4's flat curve makes this delta the whole ballgame near the knee), and update both `sensors_config.h` and the Appendix-C table with evidence. Needs ODE-free arithmetic only, but the flat discharge curve means small voltage errors are large SoC errors — hence real-pack validation.

## Setup (from cold)
1. **BLOCKED:** requires the M12 pack pair; arrives with Milestone 12 hardware.
2. Steps 1–4 of TP-PMGMT-01 Setup.
3. **SAFETY:** high-amperage rules from the Task 3 bench procedure apply for every step with the pack connected: 150 A fuse in the positive lead before anything else, connections torqued before energizing, no hot-plugging the high-current path, shunt (200A/75mV) in the negative return per the Task 3 wiring, meter leads rated for the pack voltage, and remove rings/metal from hands.
4. Wire pack → fuse → shunt → load path with the Pack INA228 sensing per Task 3; console open with log `tp12.log`.

## Procedure
1. Resting-full: pack rested ≥ 1 h off charger, no load. Record meter voltage at the pack terminals AND BATT-frame `pack_v` (they must agree within the Task 3 calibration tolerance).
2. Nominal: repeat at mid-SoC (record SoC estimate and both readings).
3. Loaded: apply the representative load, record steady-state meter + `pack_v` + BATT-frame current simultaneously.
4. Compute internal resistance: R = (V_rest − V_loaded) / I_load. Compute the loaded-equivalent of each Appendix-C threshold (threshold − I·R) and tabulate.
5. Decide + apply: update `sensors_config.h` constants if the loaded deltas move any threshold's effective SoC materially; update the Appendix-C table in TASK-4 §7 with measured rows and the resting-vs-loaded note.
6. Re-run TP-PMGMT-01 (sim walk) against the updated constants to confirm the state machine tracks the new values.

## Pass criteria
- Resting-full, nominal, and loaded voltages each recorded twice (meter + `pack_v`) and agreeing within the Task 3 INA calibration tolerance.
- R computed from measured V/I, with the raw numbers in the run log.
- `sensors_config.h` and Appendix-C table updated in the same commit (or an explicit "no change needed" decision recorded with the numbers that justify it).
- TP-PMGMT-01 re-run passes against the final constants.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-13 — Orin power-control hardware build and bring-up (supply switch / PWR_BTN optocoupler)

| | |
|---|---|
| **Traces** | AC 4i; TASK-4 §4 |
| **Status** | draft — blocked: power-control hardware not designed/built; Orin (reComputer J4012/J401) not at bench; J401 control-header pins unconfirmed against schematic |
| **Hardware** | Mega + shield, high-side MOSFET/SSR module and/or optocoupler, Orin J4012 on J401 carrier + its 9–19 V supply, Klein multimeter |
| **Est. time** | 90 min |

## Purpose
Builds and verifies the hardware that makes `RESUMING` actually boot the Orin — the gap the OVERVIEW names explicitly. Preferred path (1): J401 auto-power-on jumper set + MCU-driven high-side MOSFET/SSR switching the Orin's 9–19 V supply, so cutting/restoring supply is a clean hard-off/boot. Alternate/additional path (2): optocoupler across the J401 power-button pins — momentary pulse soft powers on/off, ≥ 10 s hold force-offs. TP-PMGMT-10 already proved the GPIO logic; this TP proves the electrons.

## Setup (from cold)
1. **BLOCKED:** hardware not built and Orin not at bench. Additionally: confirm the exact J401 control-header pin numbers against the J401 schematic PDF (linked in TASK-4 §4) before wiring anything — do not guess pin numbers.
2. Steps 1–4 of TP-PMGMT-01 Setup; TP-PMGMT-10 must be green on the same firmware commit first.
3. Build path (1): wire GPIO → MOSFET/SSR gate; switch output in the Orin supply's positive lead. Set the J401 auto-power-on jumper per the Seeed wiki. Build path (2): GPIO → optocoupler LED (with series resistor); opto output across the J401 PWR_BTN pins.
4. **SAFETY:** meter-verify the switch output in both GPIO states (on: supply voltage present; off: 0 V) with the Orin **disconnected**, before the Orin is ever wired downstream. Only connect the Orin after both states measure correct.
5. Console open with log `tp13.log`.

## Procedure
1. Path (1) dry test (Orin disconnected): `SIMV 25.6` → switch output = supply voltage on the meter; `SIMV 23.9` no-ack through to sleep → output = 0 V; `SIMV 26.5` → output returns.
2. Connect the Orin. Cold-power test: with GPIO "on", the Orin must boot unattended (auto-power-on jumper doing its job) — verify by its status LEDs/console.
3. Live cycle: trigger SOFT_CUT (no ack) → at force-off/sleep the Orin loses supply and powers down hard; `SIMV 26.5` → supply restored → Orin boots by itself.
4. Path (2), if built: with the Orin off, command the momentary pulse → Orin soft powers on; command it again from a running state → graceful shutdown request observed; command the ≥ 10 s hold → force-off.
5. Document the as-built wiring (pins, part numbers, polarity, which of (1)/(2) shipped) per AC 4i alongside this TP.

## Pass criteria
- Switch output measures correct in both states before the Orin is connected (SAFETY gate satisfied and logged).
- Orin boots unattended on supply restore (path 1) and/or responds correctly to pulse / ≥ 10 s hold (path 2) — each demonstrated at least twice.
- Full MCU-driven cycle works end to end: SOFT_CUT ⇒ Orin down; `RESUMING` ⇒ Orin boots, no human touch.
- Wiring documentation committed (AC 4i "wiring documented").

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-14 — Orin power daemon handshake and clean container→host poweroff

| | |
|---|---|
| **Traces** | AC 4j; TASK-4 §6 |
| **Status** | draft — blocked: Orin not at bench; container→host poweroff mechanism is an open item (spec §6.2) |
| **Hardware** | Orin J4012 running the locomotion container, Mega + shield on the Orin's USB, bench pack or PSU per TP-11 |
| **Est. time** | 45 min |

## Purpose
Proves the Orin half of the handshake in its production shape: the power daemon — started by `hal/server/jetson/main.py` inside the locomotion container via `krabby run` — receives `POWERING_DOWN` off the **existing single serial reader** (`KrabbyMCUSDK._reader_loop`; a second reader on the same device is the known bug to avoid), sends `SHUTDOWN_ACK` within the 60 s window, and performs a clean host poweroff from inside the container via whatever mechanism §6.2's open item resolves to. Also proves a normal boot brings the daemon up alongside HAL server + client + model.

## Setup (from cold)
1. **BLOCKED:** requires the Orin at bench and the §6.2 container→host poweroff mechanism chosen and implemented (host-systemd passthrough, host-side helper, or documented reliance on the MCU supply cut post-ack).
2. Orin side: locomotion image installed; start the stack with `krabby run` (flags per the Task 4 implementation if the daemon needs one).
3. Mega side: flashed per TP-PMGMT-01 step 4 (use `make -C firmware flash-remote REMOTE=<orin> PORT=/dev/ttyACM0` from the build machine if flashing through the Orin — see SETUP.md §2.3).
4. Sim hook available on the Mega (or PSU per TP-11 for a real-voltage trigger).

## Procedure
1. Boot the Orin normally; confirm via logs/process list that the daemon thread started alongside HAL server + client + model from `hal/server/jetson/main.py` (same pattern as the collector/teleop threads).
2. Trigger SOFT_CUT on the Mega (sim `SIMV 23.9` via a second bench command path if exposed, or PSU ramp per TP-11 step 2).
3. From the Orin-side logs: daemon logs receipt of `POWERING_DOWN`; `SHUTDOWN_ACK` sent (Mega-side evidence: sleep occurs ack-promptly per the TP-04 signature, not at the 60 s timeout).
4. Observe the Orin perform a clean host poweroff (filesystems unmounted, not a supply yank) via the documented §6.2 mechanism.
5. Power the Orin back on (TP-13 hardware or manually); confirm the full stack — including the daemon — returns with no manual steps beyond power.

## Pass criteria
- Daemon demonstrably started by the production entry point (not launched by hand).
- `SHUTDOWN_ACK` reaches the Mega inside the 60 s window; Mega sleeps promptly on ack (TP-04 timing signature reproduced with the real daemon).
- Host poweroff is clean (journal shows an orderly shutdown, no dirty-mount recovery on next boot) and uses the documented mechanism.
- Exactly one serial reader on the device throughout (no second `open()` of the port by the daemon).
- Normal boot brings up HAL server + client + model + daemon together.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-15 — Full auto-recovery: RESUMING powers the Orin and the stack cold-boots

| | |
|---|---|
| **Traces** | AC 4i, 4j; TASK-4 §4, §6; OVERVIEW "closes the gap RESUMING currently can't" |
| **Status** | draft — blocked: needs Orin + TP-PMGMT-13 hardware + TP-PMGMT-14 daemon all green |
| **Hardware** | Everything from TP-PMGMT-13 + TP-PMGMT-14, PSU or sim trigger |
| **Est. time** | 30 min |

## Purpose
The integration proof that shutdown and recovery compose into an unattended cycle: from low-power sleep with the Orin powered off, voltage crossing RECOVERY makes the MCU send `RESUMING`, the TP-13 hardware restores Orin power, the J401 auto-powers-on, and the production entry point brings up HAL server + inference client + power daemon — zero human intervention from dead to running. This is the single scenario the whole Task 4 stack exists for.

## Setup (from cold)
1. **BLOCKED:** prerequisite TPs 13 and 14 must both be green on the same firmware commit and wiring.
2. Full TP-13 wiring in place; Orin configured per TP-14; voltage source = PSU (preferred, real 4k conditions) or sim hook.
3. Console/log capture on both sides: Mega serial log + Orin journal.

## Procedure
1. Establish the shutdown state: drive voltage below SOFT_CUT, no manual ack (daemon acks); confirm Mega asleep and Orin powered fully off (meter on the switched supply: 0 V).
2. Hands off. Raise voltage above RECOVERY (PSU ramp or sim) and start a stopwatch log entry.
3. Observe, touching nothing: `RESUMING` from the Mega → switched supply live (meter) → Orin boot LEDs → stack up (HAL server + client + model + daemon in the process list) → telemetry flowing end to end.
4. Record total dead-to-running time and each stage's timestamp.
5. Repeat the full cycle once more back-to-back to prove it isn't a one-shot.

## Pass criteria
- Zero human actions between the voltage crossing RECOVERY and the full stack running — verified twice consecutively.
- Every stage observed in order: `RESUMING` → supply restored → Orin boot → entry point brings up all four components → telemetry resumes.
- Total recovery time recorded for both cycles; both complete without any component started by hand.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-16 — 60 s no-response force-off against a real unresponsive Orin

| | |
|---|---|
| **Traces** | AC 4i (force-off rule); TASK-4 §4, §8 |
| **Status** | draft — blocked: needs Orin + TP-PMGMT-13 hardware (TP-PMGMT-10 already covers the GPIO-timing half on the bench) |
| **Hardware** | Everything from TP-PMGMT-13, with the TP-14 daemon deliberately disabled |
| **Est. time** | 20 min |

## Purpose
Proves the robot cannot be held out of protective sleep by a hung Orin draining a critical pack: with the daemon disabled (no `SHUTDOWN_ACK`) but the serial link still active, a shutdown command must end in the MCU hard-cutting the Orin at the 60 s mark — supply switch off, or ≥ 10 s PWR_BTN hold, whichever TP-13 built. This is TP-PMGMT-10's timing test with real electrons and a real victim.

## Setup (from cold)
1. **BLOCKED:** same prerequisites as TP-PMGMT-13 (hardware + Orin).
2. Boot the Orin with the power daemon disabled (comment out / flag off its startup in `hal/server/jetson/main.py`, or stop the container's daemon thread per the Task 4 implementation's disable switch) while leaving the HAL serial reader running so link activity continues.
3. Mega console capturing to `tp16.log`; meter on the switched Orin supply.

## Procedure
1. Confirm the Orin is up and serial traffic is flowing (telemetry consumed, no ack capability).
2. Trigger SOFT_CUT (sim or PSU). Capture the `POWERING_DOWN` timestamp.
3. Hands off. Watch the meter on the switched supply: it must stay live through the window and drop at the 60 s mark (or observe the ≥ 10 s PWR_BTN hold sequence if that path shipped).
4. Bound the timing per the TP-10 keepalive method (Enter-keepalives into the Mega log; stamp the flip).
5. Confirm the Orin is actually down (LEDs off / supply at 0 V) and the Mega proceeded to sleep.
6. Re-enable the daemon afterwards and rerun one TP-14 handshake to confirm nothing was left disabled.

## Pass criteria
- No `SHUTDOWN_ACK` anywhere in the capture; serial link demonstrably active during the window.
- Orin supply cut (or force-off hold executed) at 60 ± 5 s after `POWERING_DOWN`.
- Orin verified fully off; Mega in low-power sleep after the cut.
- Observed timing recorded in the run log; daemon re-enabled and TP-14 spot-check passed afterwards.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |

---

# TP-PMGMT-17 — SOFT_CUT belly-down park with real actuators

| | |
|---|---|
| **Traces** | AC 4c (park step); TASK-4 §2 |
| **Status** | draft — blocked: needs the 3-board robot with actuators (solo bench Mega has no motors; the EN-drop half is covered by TP-PMGMT-03) |
| **Hardware** | Assembled 3-board robot (front leader + left/right followers), actuators powered, calibrated joints, sim or PSU trigger, area clear around the robot |
| **Est. time** | 30 min |

## Purpose
Proves the physical half of the graceful shutdown that no bench test can: on SOFT_CUT the robot lowers its body to its belly **first**, and only then de-energizes every actuator via the `ActuatorManager::holdAll()` path (EN + PWM dropped on every channel, coordinated by the front leader across all three boards). A robot that de-energizes mid-stance falls; the ordering is the safety property.

## Setup (from cold)
1. **BLOCKED:** requires the assembled robot; the solo bench cannot express a park posture.
2. Robot on flat ground with clearance on all sides; joints calibrated (SETUP.md auto-calibration); all three boards flashed with the same Task 4 firmware (`krabby-firmware update` or `flash-remote` per SETUP.md §2.3, one board at a time).
3. Serial console on the leader capturing to `tp17.log`; video camera framing the whole robot.
4. **SAFETY:** treat the robot as live machinery — no hands or feet under the chassis from actuator power-on until the post-park EN check confirms all channels dead.

## Procedure
1. Power the stack; bring the robot to a standing/neutral pose so the park has somewhere to go.
2. Start video. Trigger SOFT_CUT (sim `SIMV 23.9` on the leader, or PSU per TP-11), no ack.
3. Observe: `POWERING_DOWN` on serial → body lowers to belly contact → then (and only then) all actuators go limp.
4. After telemetry stops, verify de-energization electrically: telemetry's final frames show EN 0 on all 6+ channels across all three board segments; spot-check one EN pin per board with the meter.
5. Manually attempt to move one leg joint by hand (board asleep): it must move freely (no PWM holding torque).
6. Review the video: park motion completes before any joint goes limp.

## Pass criteria
- Video shows belly contact **before** any actuator de-energizes — ordering unambiguous.
- Final telemetry frames show EN = 0 and PWM = 0 on every channel of all three boards (leader + both forwarded follower lines).
- All joints move freely by hand after sleep (no residual drive).
- `POWERING_DOWN` → park → EN-drop → 60 s window → sleep sequence matches the TP-03 serial signature on the leader log.

## Run log
| Date | Operator | FW commit | Result | Notes |
|---|---|---|---|---|
| | | | | |
