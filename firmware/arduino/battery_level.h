#pragma once

#include <math.h>

#include "measurement_units.h"

// The rear OLED battery bars are coarse voltage gauges, not state-of-charge
// estimates. LiFePO4 voltage is flat through much of its discharge curve and
// moves with load and charging, so these documented endpoints only provide a
// useful at-a-glance level.
static const float BATTERY_LEVEL_EMPTY_VOLTS = 12.0f;
static const float BATTERY_LEVEL_FULL_VOLTS = 13.4f;

class BatteryLevel {
 public:
  static BatteryLevel fromVoltage(Volts voltage) {
    const float measuredVolts = voltage.value();
    if (!isfinite(measuredVolts)) {
      return BatteryLevel(0.0f);
    }

    float level =
        (measuredVolts - BATTERY_LEVEL_EMPTY_VOLTS) /
        (BATTERY_LEVEL_FULL_VOLTS - BATTERY_LEVEL_EMPTY_VOLTS);
    if (level < 0.0f) {
      level = 0.0f;
    } else if (level > 1.0f) {
      level = 1.0f;
    }
    return BatteryLevel(level);
  }

  float value() const { return value_; }

 private:
  explicit BatteryLevel(float value) : value_(value) {}

  float value_;
};
