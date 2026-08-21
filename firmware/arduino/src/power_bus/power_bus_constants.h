#pragma once

#include "../../units.h"
#include "../imu/imu_constants.h"
#include "../telemetry.h"

// Task 3 power-monitor cadence and quiet recovery bounds. The shared I2C bus
// configuration remains owned by src/i2c_bus_constants.h.
// How often the INA228s are read (AC 3h.6). Defined as the telemetry period
// rather than restated, because the poll rides the shared telemetry tick: the
// two cannot drift, and there is no second gate to keep in step.
static constexpr Milliseconds POWER_POLL_INTERVAL(TELEMETRY_INTERVAL_MS);
// Quiet recovery bounds, consumed by InaRecoveryPolicy. A single bad read is not
// evidence — the bus is shared with the IMU and the panel, so a transient
// collision looks the same as a dead device — and a device that is genuinely
// gone must not be retried on every poll.
static constexpr uint8_t INA_REINIT_AFTER_BAD_TICKS = 3;
static constexpr uint32_t INA_REINIT_INTERVAL_MILLISECONDS = 2000UL;

// --- INA228 power monitors (Task 3, leader board only) ---
// Two Adafruit INA228 on the same Qwiic->Dupont bus as the LSM6DSO and OLED.
//   Pack     (0x41): total 24 V pack V/I/P/charge across the external shunt.
//   Midpoint (0x40): lower-battery VBUS only (current channel grounded);
//                    upper battery = pack_v - midpoint_v.
// I2C chain, in the physical daisy-chain order as built (bus order is
// electrically irrelevant): LSM6DSO 0x6B (or 0x6A) -> OLED 0x3D -> Pack 0x41 ->
// Midpoint 0x40. Wiring diagram: assets/m16-power-bus-wiring.md.
//
// Deviation from spec §3, which assigns Pack=0x40 and Midpoint=0x41 on the
// reasoning that Pack should be the unmodified board. The roles are set by
// wiring, not by address: Pack is whichever board has its onboard shunt removed
// and the external shunt's Kelvin taps landed on it. That desolder was done on
// the already-A0-bridged board, so the two addresses are swapped. Electrically
// identical; only the labels move. (Recorded against 3c, 3d, 3h.1, 3h.2.)
#define INA228_PACK_I2C_ADDR 0x41                    // A0 jumper solder-bridged
#define INA228_MID_I2C_ADDR  0x40                    // default address

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
// (POWER_POLL_INTERVAL, 20 Hz) — no separate slow path in normal operation.
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
