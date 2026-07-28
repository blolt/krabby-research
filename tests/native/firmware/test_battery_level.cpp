#include <limits>

#include "unity.h"

#include "battery_level.h"

namespace {

void assertLevel(float expected, float volts) {
  TEST_ASSERT_FLOAT_WITHIN(
      0.00001f,
      expected,
      BatteryLevel::fromVoltage(Volts(volts)).value());
}

void test_voltage_below_empty_is_empty() {
  assertLevel(0.0f, 11.0f);
}

void test_exact_empty_voltage_is_empty() {
  assertLevel(0.0f, BATTERY_LEVEL_EMPTY_VOLTS);
}

void test_intermediate_voltage_is_fractional() {
  assertLevel(0.5f, 12.7f);
  assertLevel(0.25f, 12.35f);
}

void test_exact_full_voltage_is_full() {
  assertLevel(1.0f, BATTERY_LEVEL_FULL_VOLTS);
}

void test_voltage_above_full_is_full() {
  assertLevel(1.0f, 14.0f);
}

void test_nonfinite_voltage_is_unavailable_baseline() {
  assertLevel(0.0f, std::numeric_limits<float>::quiet_NaN());
  assertLevel(0.0f, std::numeric_limits<float>::infinity());
  assertLevel(0.0f, -std::numeric_limits<float>::infinity());
}

}  // namespace

void setUp() {}
void tearDown() {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_voltage_below_empty_is_empty);
  RUN_TEST(test_exact_empty_voltage_is_empty);
  RUN_TEST(test_intermediate_voltage_is_fractional);
  RUN_TEST(test_exact_full_voltage_is_full);
  RUN_TEST(test_voltage_above_full_is_full);
  RUN_TEST(test_nonfinite_voltage_is_unavailable_baseline);
  return UNITY_END();
}
