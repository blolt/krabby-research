#pragma once

#include <stdint.h>
#include "measurement_units.h"

// I2C sensor cluster configuration (Milestone 16).
// Single home for the wiring/contract constants of the shared I2C bus on the
// primary (leader) MCU. The bus lives on the Mega's hardware I2C pins:
//   SDA = D20, SCL = D21, sensors powered from 3.3V (LSM6DSO is a 1.71-3.6V part).
// Followers never initialize this bus; role election decides at runtime.

// --- Bus ---
// Fast-mode I2C keeps the OLED driver's worst-case dirty-page transfer inside
// the 50 ms sensor/control/telemetry budget. All devices on the leader's Qwiic
// cluster support 400 kHz. The physical Qwiic->Dupont run still needs bench
// validation for signal integrity at this rate.
#define I2C_BUS_CLOCK_HZ 400000UL

// Bound every I2C transaction so a wedged bus degrades telemetry (valid=0)
// instead of stalling the gait loop. AVR measures the whole blocking transfer,
// so this must exceed the longest single transaction on the bus — today the
// 25-wire-byte sensor-data read (address byte + 24 data; 225 bit-times at
// 9 bits/byte = 2.25 ms at 100 kHz, plus ISR overhead). The ceiling for any
// AVR Wire transfer is a full 32-byte chunk (33 wire bytes ≈ 2.97 ms), so
// 10 ms clears both and stays well under the 50 ms telemetry tick. Reviewed for
// Tasks 2-3: the OLED chunks its framebuffer into <=32-byte Wire writes and an
// INA228 register read is 3 wire bytes, so both sit under the same 32-byte
// ceiling already bounded here; 10 ms stands.
#define I2C_WIRE_TIMEOUT_US 10000UL

// --- Telemetry cadence ---
// Moved from arduino.ino. 50 ms = 20 Hz. The Orin control loop runs 100 Hz and
// the model ~50 Hz; the IMU rides this tick. If the model needs faster
// proprioception, lower this as an explicit, documented decision.
static constexpr Milliseconds TELEMETRY_POLL_INTERVAL(50U);

// --- LSM6DSO IMU (SparkFun Qwiic 6DoF, STMicro LSM6DSO, leader board only) ---
// Init probes the primary address then the alternate, so a breakout with the
// ADR jumper cut works unmodified. 0x6B is the SparkFun breakout default (SA0/ADR
// pulled high); cutting the ADR jumper pulls SA0 low -> 0x6A. The library rejects
// any address other than these two in begin().
#define LSM6DSO_I2C_ADDR     0x6B
#define LSM6DSO_I2C_ADDR_ALT 0x6A

// Explicit register configuration. Do not replace this with the library's
// BASIC_SETTINGS helper: that helper discards every register-write result and
// reports success even when configuration failed.
#define LSM6DSO_ACCEL_RANGE_G       8
#define LSM6DSO_GYRO_RANGE_DPS      500
#define LSM6DSO_ACCEL_DATA_RATE_HZ  416
#define LSM6DSO_GYRO_DATA_RATE_HZ   416
#define LSM6DSO_AUTO_INCREMENT      true
#define LSM6DSO_BLOCK_DATA_UPDATE   true
// Datasheet sensitivities for the configured full-scale ranges above.
#define LSM6DSO_ACCEL_G_PER_LSB      0.000244f
#define LSM6DSO_GYRO_DPS_PER_LSB     0.0175f
#define LSM6DSO_TEMP_C_PER_LSB       (1.0f / 256.0f)
#define LSM6DSO_TEMP_OFFSET_C        25.0f

// Sensor->body axis transform. body[i] = IMU_AXIS_SIGN[i] * sensor[IMU_AXIS_SRC[i]]
// Identity until the breakout's mounting orientation is fixed at bring-up;
// update these and the firmware README together (grant AC 1i).
const uint8_t IMU_AXIS_SRC[3]  = {0, 1, 2};
const int8_t  IMU_AXIS_SIGN[3] = {1, 1, 1};

// Units shipped in the IMU telemetry segment: accel m/s^2, gyro rad/s, temp C.
#define IMU_ACCEL_G_TO_MS2   9.80665f
#define IMU_GYRO_DEG_TO_RAD  0.017453293f

// Boot calibration: average this many samples while stationary to capture the
// gyro zero-rate bias (~1 s at 5 ms/sample).
#define IMU_CAL_SAMPLES        200
#define IMU_CAL_SAMPLE_DELAY_MS 5
// Reject the capture if any gyro axis spreads more than this peak-to-peak
// (deg/s) across the samples — the robot was moving, so don't persist a bad
// bias to EEPROM; leaving it unwritten retries on the next boot.
#define IMU_CAL_MAX_SPREAD_DPS 2.0f
// Plausibility bound on a stored gyro bias (deg/s). A stationary LSM6DSO's
// zero-rate bias is well under 1 deg/s; a magnitude above this means the loaded
// EEPROM block is garbage (e.g. a torn write), so it is discarded and recaptured
// rather than subtracted from every sample. Far below the +/-2000 deg/s range.
#define IMU_CAL_MAX_BIAS_DPS 10.0f

// Runtime IMU health (imuAppendTelemetry / imuMaybeRecover): after this many
// consecutive bad ticks (all-zero data from a powered-down/absent sensor) the sensor is
// declared invalid and the wire ships valid=0 — throttled to once per interval.
// The blocking config re-upload is NOT run in-loop (it would stall the gait
// loop), so a wedged sensor recovers only on the next reboot. Recovery is silent
// (no Serial print) — it runs mid-telemetry-line and must not splice it.
// ~20 ticks = ~1 s at 20 Hz. Both constants stay defined here: a later task reuses them.
#define IMU_REINIT_AFTER_BAD_TICKS 20
#define IMU_REINIT_INTERVAL_MS     5000UL

// --- Battery-protective state machine (M16 Task 4) ---
// Pack voltage thresholds for the 8S LiFePO4 pack (2x 12V drop-ins in series),
// from the grant Appendix C. The state machine reads pack_v from the Task 3
// Pack INA228 and drives WARN / SOFT_CUT / HARD_CUT / OVER_VOLT / RECOVERY.
// LiFePO4's discharge curve is very flat, so these cluster near the knee.
// DEFAULTS ONLY — validate against the real M12 pair under load (resting vs.
// loaded differs by internal-resistance x current) before relying on them.
#define PACK_WARN_V       24.8f  // ~20-30% SoC; telemetry only, no behavior change
#define PACK_SOFT_CUT_V   24.0f  // ~10% SoC; begin graceful shutdown (park + signal Orin)
#define PACK_HARD_CUT_V   22.4f  // margin above the ~20V internal-BMS cutoff; immediate stop
#define PACK_OVER_VOLT_V  29.6f  // charger/BMS fault; one-way protective cutout, no auto-resume
#define PACK_RECOVERY_V   25.8f  // auto-resume gate. PROVISIONAL (4h tunes vs real pack). This is a
                                 // RESTING-voltage gate: SLEEP de-energizes the motors, so it must
                                 // clear on the unloaded pack. Set at ~nominal 8S resting (~25.6V,
                                 // 3.23V/cell) so a half-charged pack can wake; still ~1.8V above the
                                 // LOADED SOFT_CUT (24.0V), which is ample anti-chatter margin. (Was
                                 // 26.4V, ~50-60% SoC resting — a genuinely half pack rested below it
                                 // and could never wake. See M16 review F13/D36.)
// Downward-cut debounce: a SOFT_CUT or HARD_CUT only latches after this many
// CONSECUTIVE valid ticks below the respective threshold, so a transient sag
// under a current spike (LiFePO4 sags ~internal_R x I) does not trip a shutdown.
// The telemetry-only WARN transition is instantaneous (no debounce).
// At the 20 Hz telemetry tick (TELEMETRY_INTERVAL_MS) 4 ticks ≈ 200 ms sustained.
// Keep in sync with power_fsm.py / power_fsm.h POWER_CUT_DEBOUNCE_TICKS.
#define POWER_CUT_DEBOUNCE_TICKS 4
// Over-voltage debounce: OVER_VOLT only latches after this many CONSECUTIVE valid
// ticks at or above PACK_OVER_VOLT_V, so a single glitchy high reading (an INA228
// misread / regen spike) does not trip the one-way protective cutout. 3 ticks ≈
// 150 ms at the 20 Hz tick — short, because a real over-voltage must still cut
// fast, but long enough to reject a lone sample. Keep in sync with
// power_fsm.py / power_fsm.h POWER_OVER_VOLT_DEBOUNCE_TICKS.
#define POWER_OVER_VOLT_DEBOUNCE_TICKS 3
// Low-power-mode cadences (§3): recovery poll and the LED/OLED dead-battery blink.
#define POWER_RECOVERY_POLL_MS   30000UL
#define POWER_LOW_BATT_BLINK_MS  10000UL
// Force-off: if the Orin neither acks nor stops telemetry within this window of
// a shutdown command, the MCU hard-cuts its supply (4i).
#define ORIN_FORCE_OFF_MS        60000UL
// D19: once the Orin has ACKed the shutdown it is already running `poweroff`, so
// the MCU only needs a short grace before cutting the rail rather than the full
// no-response force-off window. 15 s covers a clean Jetson poweroff + fs flush.
#define ORIN_ACKED_OFF_MS        15000UL

// EEPROM layout (see arduino.ino: joint CalData = bytes 0-25, role = 32-33).
// IMU calibration lives at byte 40+ with its own sentinel and schema version.
#define EEPROM_IMU_CAL_ADDR   40
#define EEPROM_IMU_CAL_INVALID_MAGIC 0x00
#define EEPROM_IMU_CAL_MAGIC  0xC7
#define EEPROM_IMU_CAL_SCHEMA 1
// ImuCalData (arduino.ino) = magic + schema + 3x gyro-bias float + 3x
// accel-bias float = 26 bytes on AVR: EEPROM bytes 40-65 inclusive. The unit
// EEPROM-layout contract verifies this stored shape and its non-overlap with
// the inherited joint-calibration and role blocks.
#define EEPROM_IMU_CAL_SIZE 26
// First free EEPROM byte after the IMU block; Task 3 (INA228 cal) and later
// sensor-cluster blocks allocate from here, each with its own magic + schema.
#define EEPROM_SENSOR_CAL_NEXT_ADDR (EEPROM_IMU_CAL_ADDR + EEPROM_IMU_CAL_SIZE)

// --- INA228 power monitors (Task 3, leader board only) ---
// Two Adafruit INA228 on the same Qwiic->Dupont bus as the LSM6DSO and OLED.
//   Pack     (0x40): total 24 V pack V/I/P/charge across the external shunt.
//   Midpoint (0x41): lower-battery VBUS only (current channel grounded);
//                    upper battery = pack_v - midpoint_v.
// I2C chain: LSM6DSO 0x6B (or 0x6A) -> OLED 0x3D -> Pack 0x40 ->
// Midpoint 0x41.
#define INA228_PACK_I2C_ADDR 0x40                    // default address
#define INA228_MID_I2C_ADDR  0x41                    // A0 jumper solder-bridged (AC 3d)

// External shunt. Both onboard 15 mOhm resistors are removed (the accepted
// implementation of AC 3e) so only the external 200 A / 75 mV bar carries pack
// current: 75 mV / 200 A = 0.000375 ohm.
// setShunt(resistance, max current) derives the INA228 current LSB from these
// two values. Keep their units explicit until the Adafruit API boundary.
static constexpr Ohms INA228_SHUNT_RESISTANCE(0.000375f);
static constexpr Amps INA228_SHUNT_MAX_CURRENT(200.0f);

// Per-battery divergence alarm: |Va - Vb| above this (volts) sets the BATT
// frame's divergence flag. 0.5 V across two nominally-equal 12 V batteries flags
// a cell imbalance / a failing battery before Task 4's protective logic. (AC 3h.)
static constexpr Volts INA228_DIVERGENCE_THRESHOLD(0.5f);

// Poll cadence: both INA228s are read on the existing telemetry tick
// (TELEMETRY_POLL_INTERVAL, 20 Hz) — no separate slow path in normal operation.
// The low-power slow path is Task 4. (AC 3h; spec §4.)

// EEPROM: INA228 calibration block, immediately after the IMU block, its own
// magic + schema. PowerCalibrationData = magic + schema + per-board VBUS offset
// trims (Pack, Midpoint) + a Pack shunt-cal constant; static_asserts in the
// storage header and arduino.ino pin its size to EEPROM_INA_CAL_SIZE. Layout is
// finalized with the calibration procedure (AC 3i).
#define EEPROM_INA_CAL_ADDR   EEPROM_SENSOR_CAL_NEXT_ADDR    // = 66
#define EEPROM_INA_CAL_MAGIC  0xC8                           // distinct from IMU's 0xC7
#define EEPROM_INA_CAL_SCHEMA 1
// magic + schema + 3 floats: Pack VBUS offset, Midpoint VBUS offset, Pack
// shunt-cal = 1 + 1 + 3*4 = 14 bytes: EEPROM bytes 66-79 inclusive.
#define EEPROM_INA_CAL_SIZE   14
// First free EEPROM byte after the INA228 block, for later sensor-cluster blocks.
#define EEPROM_INA_CAL_NEXT_ADDR (EEPROM_INA_CAL_ADDR + EEPROM_INA_CAL_SIZE)

// --- INA228 implementation of power-sensing bench calibration (AC 3i) ---
// VBUS calibration needs an EXTERNAL known reference (a DMM on the live pack),
// so unlike the IMU gyro-bias capture it cannot self-run at boot — the operator
// triggers it from the bench with the hardware-agnostic `C PWR_SENSE ...` command
// family. Full bench procedure: docs/M16-INA228-CALIBRATION.md.
//
// Plausibility bounds shared by the capture routines and the stored-block loader
// powerCalibrationIsPlausible(). A captured trim outside these is rejected and NOT persisted,
// so a fat-fingered bench reference can never brick a board's telemetry — the
// prior (or identity) calibration stays in force.
#define INA228_CAL_PACK_REF_MAX_V   40.0f  // operator pack reference ceiling (V)
#define INA228_CAL_MID_REF_MAX_V    20.0f  // operator midpoint reference ceiling (V)
#define INA228_CAL_MAX_VOFFSET_V     2.0f  // max |VBUS offset| a capture may write (V)
#define INA228_CAL_MIN_GAIN          0.5f  // shunt-trim floor (unitless)
#define INA228_CAL_MAX_GAIN          2.0f  // shunt-trim ceiling (unitless)
#define INA228_CAL_MIN_SHUNT_TRIM_A  0.1f  // min |current| (A) for a valid shunt-trim point
