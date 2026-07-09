# M16 bench test procedures — index

This directory holds ATP-style bench test procedures (TPs) for Milestone 16 (I2C sensor cluster + power management), one file per area: [IMU.md](IMU.md), [OLED.md](OLED.md), [PWR.md](PWR.md), [PMGMT.md](PMGMT.md). Each TP is self-contained: run its **Setup (from cold)** section verbatim (assume nothing is wired, flashed, or configured), execute the procedure, judge against the pass criteria, and **append a row to the TP's run log** (date, operator, firmware commit, result, notes) for every run — including failures and partial runs. To add a new TP: pick the next free id in the area (`TP-<AREA>-NN`), copy the existing header-table + Purpose/Setup/Procedure/Pass criteria/Run log skeleton, fill in the **Traces** row with the acceptance criteria and spec sections it verifies, and add it to the table and traceability matrix below. Bench context (hardware baseline, serial settings, runbook, timing evidence) lives in `firmware/SETUP.md` under "I2C Sensor Cluster (Milestone 16)".

## TP inventory

| TP | Title | Traces (AC) | Status | File |
|---|---|---|---|---|
| TP-IMU-01 | 3.3 V rail voltage check before first sensor connect | 1a | already-run | [IMU.md](IMU.md) |
| TP-IMU-02 | Qwiic→Dupont wiring and I2C bus scan (BMI270 address discovery) | 1a, 1b | already-run | [IMU.md](IMU.md) |
| TP-IMU-03 | Firmware flash and boot-log verification (role election + IMU init) | 1b | already-run | [IMU.md](IMU.md) |
| TP-IMU-04 | IMU-absent graceful degradation (init failure path, valid=0, no stall) | 1b, 1d | already-run | [IMU.md](IMU.md) |
| TP-IMU-05 | Baseline loop-timing capture — upstream firmware @115200 | 1c | already-run | [IMU.md](IMU.md) |
| TP-IMU-06 | M16 loop-timing capture @250000, IMU absent (serial-path delta) | 1c | already-run | [IMU.md](IMU.md) |
| TP-IMU-07 | Static telemetry sanity — gravity, gyro bias, temperature through the real parser | 1c, 1d, 1e | already-run | [IMU.md](IMU.md) |
| TP-IMU-08 | EEPROM calibration persistence across power cycle | 1g | already-run | [IMU.md](IMU.md) |
| TP-IMU-09 | Motion-gate rejection during calibration capture | 1g | already-run | [IMU.md](IMU.md) |
| TP-IMU-10 | Confirmed flip test — physical motion verification with human in the loop | 1d, 1e | ready | [IMU.md](IMU.md) |
| TP-IMU-11 | Loop-timing capture with IMU attached — fill the TBD table row | 1c | ready | [IMU.md](IMU.md) |
| TP-IMU-12 | Runtime hot-disconnect resilience (valid drops to 0, no gait-loop stall) | 1b, 1d | ready | [IMU.md](IMU.md) |
| TP-IMU-13 | GUI IMU readout with live board | 1e, 1h | ready | [IMU.md](IMU.md) |
| TP-IMU-14 | Sensor→body axis-transform verification at mount time | 1i | blocked — IMU not mounted to a robot body; transform is identity until a chassis mount exists | [IMU.md](IMU.md) |
| TP-IMU-15 | Three-board leader-only behavior — IMU on the FRONT line only, followers untouched | 1a, 1d, 1f | blocked — only one Mega on the bench; needs the three-board rig | [IMU.md](IMU.md) |
| TP-IMU-16 | Full three-board integration timing run (`tests/integration/test_timing.py`) | 1c | blocked — needs the three-board rig (robot integration) | [IMU.md](IMU.md) |
| TP-OLED-01 | Bus integration scan: OLED daisy-chained at 0x3D alongside BMI270 | 2a | ready | [OLED.md](OLED.md) |
| TP-OLED-02 | OLED init and krab render on solo bench leader | 2a, 2b | ready | [OLED.md](OLED.md) |
| TP-OLED-03 | Init-failure resilience: boot with OLED unplugged | 2a | ready | [OLED.md](OLED.md) |
| TP-OLED-04 | Hot-pull refresh-failure resilience | 2a | ready | [OLED.md](OLED.md) |
| TP-OLED-05 | Floating-channel noise characterization (bug reproduction, threshold selection) | 2e, 2f | ready | [OLED.md](OLED.md) |
| TP-OLED-06 | Disconnected detection + position filtering, all channels floating (negative side) | 2e, 2f | ready | [OLED.md](OLED.md) |
| TP-OLED-07 | Discrete red status LED / alarm GPIO on disconnected-motor | 2g | ready | [OLED.md](OLED.md) |
| TP-OLED-08 | Loop-timing baseline without OLED (pre-existing) | 2h | already-run | [OLED.md](OLED.md) |
| TP-OLED-09 | Loop timing A/B with OLED active vs removed | 2h | ready | [OLED.md](OLED.md) |
| TP-OLED-10 | Actuator state glyphs under jog (extend/retract/holding) | 2d | blocked — no actuator on the bench to jog | [OLED.md](OLED.md) |
| TP-OLED-11 | Live disconnected-motor detection end-to-end (unplug a real actuator) | 2e, 2f, 2g | blocked — needs a real actuator wired to the shield | [OLED.md](OLED.md) |
| TP-OLED-12 | Controller presence: follower power-off flips body-third to missing and recovers | 2c | blocked — needs follower boards (three-board rig) | [OLED.md](OLED.md) |
| TP-PWR-01 | INA228 pair I2C presence on bench bus (no battery) | 3d, 3h | ready | [PWR.md](PWR.md) |
| TP-PWR-02 | Onboard 15 mΩ shunt trace-cut on both INA228s + continuity verification + photo | 3e (photo feeds 3j) | ready | [PWR.md](PWR.md) |
| TP-PWR-03 | Firmware bring-up: setShunt cal, per-tick reads, BATT frame emission, sensor-absent safety | 3f, 3g, 3h | ready | [PWR.md](PWR.md) |
| TP-PWR-04 | Loop timing with full I2C cluster (IMU + OLED + 2× INA228 polled on-tick) | 3f/3h cadence; extends 1c | ready | [PWR.md](PWR.md) |
| TP-PWR-05 | BATT frame end-to-end: SDK parse, GUI display, OLED battery bars | 3g | ready | [PWR.md](PWR.md) |
| TP-PWR-06 | VBUS reference check and per-board offset trim vs Klein DMM (Mega rails as reference) | 3i | ready | [PWR.md](PWR.md) |
| TP-PWR-07 | Divergence-flag logic simulation using split rail voltages (no battery) | 3g | ready | [PWR.md](PWR.md) |
| TP-PWR-08 | INA228 calibration EEPROM persistence across power cycle | 3i | ready | [PWR.md](PWR.md) |
| TP-PWR-09 | SAFETY gate: pre-energize battery-safety checklist (gates all pack-connected procedures) | 3b | blocked — no battery pack on the bench yet | [PWR.md](PWR.md) |
| TP-PWR-10 | Bench-octopus assembly and first energize (fuse → shunt → load topology) | 3a, 3b, 3c, 3d, 3j | blocked — needs the pack; gated by TP-PWR-09 | [PWR.md](PWR.md) |
| TP-PWR-11 | Pack and per-battery voltage accuracy vs DMM on the live pack | 3f, 3g, 3i | blocked — needs energized bench octopus (TP-PWR-10) | [PWR.md](PWR.md) |
| TP-PWR-12 | Shunt current calibration cross-check under known load + charge accumulation | 3f, 3i | blocked — needs energized pack + clamp meter / known load | [PWR.md](PWR.md) |
| TP-PWR-13 | Real divergence trip at 0.5 V and OLED battery bars tracking live pack state | 3g, 3h | blocked — needs energized pack (TP-PWR-10) | [PWR.md](PWR.md) |
| TP-PMGMT-01 | Simulated pack-voltage threshold walk through all five states | 4a | ready | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-02 | Power-state message emission and host-side parse (schema_version) | 4b | ready | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-03 | SOFT_CUT graceful sequence on solo bench (no ack → 60 s timeout) | 4c | ready | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-04 | SHUTDOWN_ACK handshake with laptop as Orin stand-in | 4c, 4j | ready | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-05 | HARD_CUT immediate emergency path | 4d | ready | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-06 | OVER_VOLT one-way cutout with no auto-recovery | 4e | ready | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-07 | Low-power mode poll discipline and ~30 s recovery cadence | 4f | ready | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-08 | Dead-battery OLED splash + red LED cadence, OLED silenced below HARD_CUT floor | 4g | ready | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-09 | RECOVERY auto-resume with ≥ 0.4 V hysteresis | 4f | ready | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-10 | Orin power-control GPIO cycle on bare Mega (multimeter, no Orin) | 4i (MCU side) | ready | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-11 | Real-voltage PSU ramp end-to-end (AC 4k bench test) | 4k, 4a | blocked — needs an adjustable current-limited lab PSU | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-12 | Appendix-C threshold validation against the real M12 pack (resting vs loaded) | 4h | blocked — needs the real M12 battery pair | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-13 | Orin power-control hardware build and bring-up (supply switch / PWR_BTN optocoupler) | 4i | blocked — needs the Orin + MOSFET/optocoupler parts | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-14 | Orin power daemon handshake and clean container→host poweroff | 4j | blocked — needs the Orin | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-15 | Full auto-recovery: RESUMING powers the Orin and the stack cold-boots | 4i, 4j | blocked — needs TP-PMGMT-13 + TP-PMGMT-14 complete | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-16 | 60 s no-response force-off against a real unresponsive Orin | 4i | blocked — needs Orin power-control hardware (TP-PMGMT-13) | [PMGMT.md](PMGMT.md) |
| TP-PMGMT-17 | SOFT_CUT belly-down park with real actuators | 4c | blocked — needs real actuators wired | [PMGMT.md](PMGMT.md) |

## Traceability matrix (hardware-verifiable ACs → TPs)

Every acceptance criterion from TASK-1..TASK-4 that requires verification **on hardware** is listed. Coverage: ✅ = at least one covering TP already run; 🟡 = covered, TP(s) ready but not yet run; 🔒 = covered only by blocked TP(s); **GAP** = no covering TP.

**Gaps found: none.** Every hardware-verifiable AC has at least one covering TP.

### Task 1 — IMU telemetry

| AC | Requirement (hardware aspect) | Covering TPs | Coverage |
|---|---|---|---|
| 1a | BMI270 on leader only, 3.3 V, D20/D21 via Qwiic→Dupont | TP-IMU-01, TP-IMU-02, TP-IMU-15 | ✅ solo half run; leader-only half 🔒 TP-IMU-15 |
| 1b | I2C @100 kHz init; init failure logged, `imu_valid=0`, no crash/stall | TP-IMU-03, TP-IMU-04, TP-IMU-12 | ✅ (runtime hot-disconnect residual 🟡 TP-IMU-12) |
| 1c | Per-tick reads with no measurable loop-timing change | TP-IMU-05, TP-IMU-06, TP-IMU-07, TP-IMU-11, TP-IMU-16, TP-PWR-04 | ✅ baseline + serial delta run; IMU-attached row 🟡 TP-IMU-11; integration 🔒 TP-IMU-16 |
| 1d | `IMU` segment appended, append-only, valid-field semantics | TP-IMU-04, TP-IMU-07, TP-IMU-10, TP-IMU-12, TP-IMU-15 | ✅ |
| 1e | Parse into `ImuTelemetry`, stored, shown in `format_compact`/GUI | TP-IMU-07, TP-IMU-10, TP-IMU-13 | ✅ parser half run; GUI half 🟡 TP-IMU-13 |
| 1f | Role prefixes unchanged on the wire (no `controller_role`) | TP-IMU-15 (negative half is code review) | 🔒 |
| 1g | Boot calibration captured stationary, persisted in EEPROM, reused | TP-IMU-08, TP-IMU-09 | ✅ |
| 1h | IMU values in the existing telemetry stream (no new CLI — code review) | TP-IMU-13 | 🟡 |
| 1i | Sensor→body transform documented **and correct at mount** | TP-IMU-14 (README text is a doc check) | 🔒 |

### Task 2 — OLED status display

| AC | Requirement (hardware aspect) | Covering TPs | Coverage |
|---|---|---|---|
| 2a | OLED at 0x3D on the shared bus; init/refresh failure non-fatal | TP-OLED-01, TP-OLED-02, TP-OLED-03, TP-OLED-04 | 🟡 |
| 2b | Stylized krab rendered (3 thirds, 6 legs, battery bars) | TP-OLED-02 | 🟡 |
| 2c | Per-controller detected/active vs missing (election + freshness) | TP-OLED-12 | 🔒 |
| 2d | Per-actuator state glyphs (▲/▼/●/○) | TP-OLED-10 | 🔒 |
| 2e | Current-based attachment detection (`isConnected()`) | TP-OLED-05, TP-OLED-06, TP-OLED-11 | 🟡 floating-channel side; live-actuator side 🔒 |
| 2f | Position filtering — no noise on OLED **and** telemetry | TP-OLED-05, TP-OLED-06, TP-OLED-11 | 🟡 floating-channel side; live-actuator side 🔒 |
| 2g | Discrete red LED on free GPIO on disconnected-motor | TP-OLED-07, TP-OLED-11 | 🟡 |
| 2h | OLED refresh does not impact gait-loop timing | TP-OLED-08, TP-OLED-09 | ✅ baseline run; A/B 🟡 |

### Task 3 — Power bus + INA228

| AC | Requirement (hardware aspect) | Covering TPs | Coverage |
|---|---|---|---|
| 3a | Bench-octopus built as documented (doc half is a doc check) | TP-PWR-10 | 🔒 |
| 3b | Safety checklist followed; 150 A fuse first on Pack+ | TP-PWR-09, TP-PWR-10 | 🔒 |
| 3c | 200 A/75 mV shunt inline downstream of fuse; Kelvin sense to 0x40; VBUS load side | TP-PWR-10 | 🔒 |
| 3d | Midpoint INA228 at 0x41 (A0 strapped), current channel grounded, per-battery math | TP-PWR-01, TP-PWR-10 | 🟡 address strap; midpoint wiring 🔒 |
| 3e | Both onboard 15 mΩ shunts trace-cut; photo | TP-PWR-02 | 🟡 |
| 3f | `setShunt(0.000375, 200.0)`; V/I/P/charge + midpoint V read | TP-PWR-03, TP-PWR-11, TP-PWR-12 | 🟡 firmware reads; accuracy on live pack 🔒 |
| 3g | `BATT` frame (incl. divergence_flag, power_state) parsed; GUI + OLED bars | TP-PWR-03, TP-PWR-05, TP-PWR-07, TP-PWR-11, TP-PWR-13 | 🟡 bench side; live-pack side 🔒 |
| 3h | Addresses/shunt/threshold/cadence as configured actually observed on hardware | TP-PWR-01, TP-PWR-03, TP-PWR-04, TP-PWR-13 | 🟡 (header contents are code review) |
| 3i | Shunt constant + VBUS offset trim captured, persisted in EEPROM | TP-PWR-06, TP-PWR-08, TP-PWR-11, TP-PWR-12 | 🟡 trim + persistence; live-pack cross-check 🔒 |
| 3j | Wiring diagram + assembled-harness photos | TP-PWR-02 (trace-cut photo), TP-PWR-10 (harness photos) | 🟡/🔒 |

### Task 4 — Power management

| AC | Requirement (hardware aspect) | Covering TPs | Coverage |
|---|---|---|---|
| 4a | Five thresholds drive the state machine correctly | TP-PMGMT-01, TP-PMGMT-11 | 🟡 simulated walk; real-voltage 🔒 |
| 4b | Power-state messages emitted and parsed (schema_version) | TP-PMGMT-02 | 🟡 |
| 4c | SOFT_CUT: `POWERING_DOWN` → park → ≤60 s ack/timeout → sleep | TP-PMGMT-03, TP-PMGMT-04, TP-PMGMT-17 | 🟡 sequence + handshake; real-actuator park 🔒 |
| 4d | HARD_CUT: immediate EN drop + sleep, no park/handshake | TP-PMGMT-05 | 🟡 |
| 4e | OVER_VOLT: one-way cutout, no auto-recovery | TP-PMGMT-06 | 🟡 |
| 4f | Low-power polls Pack INA228 only; ~30 s recovery check, ≥0.4 V hysteresis | TP-PMGMT-07, TP-PMGMT-09 | 🟡 |
| 4g | ~10 s OLED splash + red LED blink; OLED silenced below HARD_CUT | TP-PMGMT-08 | 🟡 |
| 4h | Appendix-C thresholds validated on real M12 pack, resting vs loaded | TP-PMGMT-12 | 🔒 |
| 4i | Orin power-control hardware; `RESUMING` powers Orin; 60 s force-off | TP-PMGMT-10, TP-PMGMT-13, TP-PMGMT-15, TP-PMGMT-16 | 🟡 GPIO half; Orin hardware 🔒 |
| 4j | Orin power daemon: ack + clean poweroff, started by entry point | TP-PMGMT-04, TP-PMGMT-14, TP-PMGMT-15 | 🟡 protocol half; real Orin 🔒 |
| 4k | PSU ramp through SOFT_CUT/RECOVERY/OVER_VOLT with timings recorded | TP-PMGMT-11 | 🔒 |

Code/doc-only AC aspects (no bench hardware needed, verified by review): 1f negative half (no `controller_role` field added), 1h negative half (no new CLI command), 1i README text, 3a octopus documentation, 3h `sensors_config.h` contents, 4a constants naming/placement, 4b message definitions under `firmware/interfaces/`.
