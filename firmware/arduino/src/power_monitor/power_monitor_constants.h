#pragma once

#include <stdint.h>

#include "../../eeprom_layout.h"
#include "../units/electrical_units.h"
#include "../units/time_units.h"
#include "../telemetry.h"

// Power monitoring shares the telemetry tick.
static constexpr Milliseconds POWER_POLL_INTERVAL(TELEMETRY_INTERVAL_MS);
static constexpr uint8_t POWER_MONITOR_REINIT_AFTER_BAD_TICKS = 3;
static constexpr uint32_t POWER_MONITOR_REINIT_INTERVAL_MILLISECONDS = 2000UL;

// Maximum permitted difference between the two 12 V batteries.
static constexpr Volts BATTERY_DIVERGENCE_THRESHOLD(0.5f);

static constexpr uint8_t EEPROM_POWER_CAL_INVALID_MAGIC = 0x00;
static constexpr uint8_t EEPROM_POWER_CAL_MAGIC = 0xC8;
static constexpr uint8_t EEPROM_POWER_CAL_SCHEMA = 1;

// Reject implausible bench calibration references and trims.
static constexpr float POWER_CAL_PACK_REF_MAX_V = 40.0f;
static constexpr float POWER_CAL_MID_REF_MAX_V = 20.0f;
static constexpr float POWER_CAL_MAX_VOFFSET_V = 2.0f;
static constexpr float POWER_CAL_MIN_GAIN = 0.5f;
static constexpr float POWER_CAL_MAX_GAIN = 2.0f;
static constexpr float POWER_CAL_MIN_SHUNT_TRIM_A = 0.1f;
