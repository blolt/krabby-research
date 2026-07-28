#include <stdint.h>

#include "unity.h"

#include "oled_transfer_budget.h"
#include "sensors_config.h"

void setUp() {}
void tearDown() {}

static void test_shared_i2c_bus_uses_fast_mode()
{
    TEST_ASSERT_EQUAL_UINT32(400000UL, I2C_BUS_CLOCK_HZ);
}

static void test_worst_case_oled_wire_time_fits_telemetry_budget()
{
    const uint32_t transferUs = oledWorstCaseWireTimeUs(I2C_BUS_CLOCK_HZ);
    const uint32_t telemetryBudgetUs =
        TELEMETRY_POLL_INTERVAL.value() * 1000UL;

    TEST_ASSERT_EQUAL_UINT32(28800UL, transferUs);
    TEST_ASSERT_LESS_THAN_UINT32(telemetryBudgetUs, transferUs);
}

static void test_old_standard_mode_cannot_meet_the_budget()
{
    const uint32_t transferUsAt100KHz = oledWorstCaseWireTimeUs(100000UL);
    const uint32_t telemetryBudgetUs =
        TELEMETRY_POLL_INTERVAL.value() * 1000UL;

    TEST_ASSERT_GREATER_THAN_UINT32(
        telemetryBudgetUs, transferUsAt100KHz);
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_shared_i2c_bus_uses_fast_mode);
    RUN_TEST(test_worst_case_oled_wire_time_fits_telemetry_budget);
    RUN_TEST(test_old_standard_mode_cannot_meet_the_budget);
    return UNITY_END();
}
