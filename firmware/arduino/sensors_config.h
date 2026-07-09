#pragma once

// I2C sensor cluster configuration (Milestone 16).
// Single home for the wiring/contract constants of the shared I2C bus on the
// primary (leader) MCU. The bus lives on the Mega's hardware I2C pins:
//   SDA = D20, SCL = D21, sensors powered from 3.3V (BMI270 is a 3.3V part).
// Followers never initialize this bus; role election decides at runtime.

// --- Bus ---
// 100 kHz, not 400: the model runs ~50 Hz and the per-tick payload is tiny;
// the slower clock buys noise margin on the Qwiic->Dupont run.
#define I2C_BUS_CLOCK_HZ 100000UL

// Bound every I2C transaction so a wedged bus degrades telemetry (valid=0)
// instead of stalling the gait loop. AVR measures the whole blocking transfer,
// so this must exceed the longest single transaction on the bus — today the
// 25-wire-byte sensor-data read (address byte + 24 data; 225 bit-times at
// 9 bits/byte = 2.25 ms at 100 kHz, plus ISR overhead). The ceiling for any
// AVR Wire transfer is a full 32-byte chunk (33 wire bytes ≈ 2.97 ms), so
// 10 ms clears both and stays well under the 50 ms telemetry tick. Revisit
// when the OLED (longer framebuffer writes) and INA228s join the bus in
// Tasks 2-3.
#define I2C_WIRE_TIMEOUT_US 10000UL

// --- Telemetry cadence ---
// Moved from arduino.ino. 50 ms = 20 Hz. The Orin control loop runs 100 Hz and
// the model ~50 Hz; the IMU rides this tick. If the model needs faster
// proprioception, lower this as an explicit, documented decision.
const int TELEMETRY_INTERVAL_MS = 50;

// --- BMI270 IMU (SparkFun Qwiic 6DoF, leader board only) ---
// Init probes the primary address then the alternate, so a breakout with the
// ADR jumper cut (0x69 — true of the M16 unit in hand) works unmodified.
#define BMI270_I2C_ADDR     0x68
#define BMI270_I2C_ADDR_ALT 0x69

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
// Plausibility bound on a stored gyro bias (deg/s). A stationary BMI270's
// zero-rate bias is well under 1 deg/s; a magnitude above this means the loaded
// EEPROM block is garbage (e.g. a torn write), so it is discarded and recaptured
// rather than subtracted from every sample. Far below the +/-2000 deg/s range.
#define IMU_CAL_MAX_BIAS_DPS 10.0f

// Runtime IMU health (imuAppendTelemetry): after this many consecutive bad
// ticks (getSensorData failure or all-zero data) the sensor is declared invalid
// and re-initialized, at most once per interval. ~20 ticks = ~1 s at 20 Hz.
#define IMU_REINIT_AFTER_BAD_TICKS 20
#define IMU_REINIT_INTERVAL_MS     5000UL

// EEPROM layout (see arduino.ino: joint CalData = bytes 0-25, role = 32-33).
// IMU calibration lives at byte 40+ with its own sentinel and schema version.
#define EEPROM_IMU_CAL_ADDR   40
#define EEPROM_IMU_CAL_MAGIC  0xC7
#define EEPROM_IMU_CAL_SCHEMA 1
// ImuCalData (arduino.ino) = magic + schema + 3x gyro-bias float + 3x
// accel-bias float = 26 bytes on AVR: EEPROM bytes 40-65 inclusive. A C++11
// `static_assert` — a compile-time check, evaluated by the compiler, never at
// runtime — sits directly below the ImuCalData struct in arduino.ino (line
// ~149) and verifies sizeof(ImuCalData) == EEPROM_IMU_CAL_SIZE. If the
// struct and this constant ever disagree, the firmware fails to compile with
// that assert's message; a mismatch can never reach a running board.
#define EEPROM_IMU_CAL_SIZE 26
// First free EEPROM byte after the IMU block; Task 3 (INA228 cal) and later
// sensor-cluster blocks allocate from here, each with its own magic + schema.
#define EEPROM_SENSOR_CAL_NEXT_ADDR (EEPROM_IMU_CAL_ADDR + EEPROM_IMU_CAL_SIZE)
