#include <type_traits>

#include "unity.h"

#include "src/power_bus/power_bus_constants.h"

static_assert(
    std::is_same<decltype(INA228_SHUNT_RESISTANCE), const Ohms>::value,
    "shunt resistance must retain its unit");
static_assert(
    std::is_same<decltype(INA228_SHUNT_MAX_CURRENT), const Amps>::value,
    "shunt current rating must retain its unit");
static_assert(
    std::is_same<decltype(INA228_DIVERGENCE_THRESHOLD), const Volts>::value,
    "divergence threshold must retain its unit");
static_assert(
    std::is_same<decltype(INA228_PACK_I2C_ADDR), const uint8_t>::value,
    "Pack address must be explicitly typed");
static_assert(
    std::is_same<decltype(EEPROM_INA_CAL_ADDR), const uint16_t>::value,
    "EEPROM address must be explicitly typed");

void setUp() {}
void tearDown() {}

static void test_monitor_addresses_match_the_build()
{
    TEST_ASSERT_EQUAL_HEX8(0x41, INA228_PACK_I2C_ADDR);
    TEST_ASSERT_EQUAL_HEX8(0x40, INA228_MID_I2C_ADDR);
    TEST_ASSERT_NOT_EQUAL(INA228_PACK_I2C_ADDR, INA228_MID_I2C_ADDR);
}

static void test_power_bus_values_match_the_hardware()
{
    TEST_ASSERT_FLOAT_WITHIN(
        0.0000001f, 0.000375f, INA228_SHUNT_RESISTANCE.value());
    TEST_ASSERT_FLOAT_WITHIN(
        0.0001f, 200.0f, INA228_SHUNT_MAX_CURRENT.value());
    TEST_ASSERT_FLOAT_WITHIN(
        0.000001f, 0.5f, INA228_DIVERGENCE_THRESHOLD.value());
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_monitor_addresses_match_the_build);
    RUN_TEST(test_power_bus_values_match_the_hardware);
    return UNITY_END();
}
