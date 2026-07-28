#pragma once

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
// 10 ms clears both and stays well under the 50 ms telemetry tick. Revisit
// when the OLED (longer framebuffer writes) and INA228s join the bus in
// Tasks 2-3.
#define I2C_WIRE_TIMEOUT_US 10000UL

// --- Telemetry cadence ---
// Moved from arduino.ino. 50 ms = 20 Hz. The Orin control loop runs 100 Hz and
// the model ~50 Hz; the IMU rides this tick. If the model needs faster
// proprioception, lower this as an explicit, documented decision.
const int TELEMETRY_INTERVAL_MS = 50;

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
