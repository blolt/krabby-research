#pragma once

#include <stdint.h>

#include "../units/electrical_units.h"
#include "../imu/imu_constants.h"
#include "../telemetry.h"

// INA polling shares the telemetry tick.
static constexpr Milliseconds POWER_POLL_INTERVAL(TELEMETRY_INTERVAL_MS);
// Retry only after repeated failures and at a bounded cadence.
static constexpr uint8_t INA_REINIT_AFTER_BAD_TICKS = 3;
static constexpr uint32_t INA_REINIT_INTERVAL_MILLISECONDS = 2000UL;

// Pack uses the external shunt; Midpoint measures the lower battery only.
static constexpr uint8_t INA228_PACK_I2C_ADDR = 0x41;  // A0 jumper solder-bridged
static constexpr uint8_t INA228_MID_I2C_ADDR = 0x40;   // default address

// External 200 A / 75 mV shunt; onboard shunts are removed.
static constexpr Ohms INA228_SHUNT_RESISTANCE(0.000375f);
static constexpr Amps INA228_SHUNT_MAX_CURRENT(200.0f);

// Maximum permitted difference between the two 12 V batteries.
static constexpr Volts INA228_DIVERGENCE_THRESHOLD(0.5f);

// Calibration follows the IMU block in EEPROM.
static constexpr uint16_t EEPROM_INA_CAL_ADDR = EEPROM_SENSOR_CAL_NEXT_ADDR;  // = 66
static constexpr uint8_t EEPROM_INA_CAL_MAGIC = 0xC8;  // distinct from IMU's 0xC7
static constexpr uint8_t EEPROM_INA_CAL_SCHEMA = 1;
static constexpr uint16_t EEPROM_INA_CAL_SIZE = 14;
static constexpr uint16_t EEPROM_INA_CAL_NEXT_ADDR =
    EEPROM_INA_CAL_ADDR + EEPROM_INA_CAL_SIZE;

// Reject implausible bench calibration references and trims.
static constexpr float INA228_CAL_PACK_REF_MAX_V = 40.0f;
static constexpr float INA228_CAL_MID_REF_MAX_V = 20.0f;
static constexpr float INA228_CAL_MAX_VOFFSET_V = 2.0f;
static constexpr float INA228_CAL_MIN_GAIN = 0.5f;
static constexpr float INA228_CAL_MAX_GAIN = 2.0f;
static constexpr float INA228_CAL_MIN_SHUNT_TRIM_A = 0.1f;
