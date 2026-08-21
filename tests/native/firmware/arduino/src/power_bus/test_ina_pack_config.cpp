#include <type_traits>

#include "unity.h"

#include "src/power_bus/ina_pack_config.h"

static_assert(
    std::is_same<decltype(INA228_SHUNT_RESISTANCE), const Ohms>::value,
    "shunt resistance must retain its unit");
static_assert(
    std::is_same<decltype(INA228_SHUNT_MAX_CURRENT), const Amps>::value,
    "shunt current rating must retain its unit");
static_assert(
    std::is_same<decltype(INA228_DIVERGENCE_THRESHOLD), const Volts>::value,
    "divergence threshold must retain its unit");

void setUp() {}
void tearDown() {}

struct RecordingIna
{
    int setShuntCalls;
    float shuntOhms;
    float maxAmps;

    void setShunt(float resistance, float current)
    {
        ++setShuntCalls;
        shuntOhms = resistance;
        maxAmps = current;
    }
};

static void test_pack_configuration_sets_external_shunt_once()
{
    RecordingIna ina = {0, 0.0f, 0.0f};

    configurePackIna(ina);

    TEST_ASSERT_EQUAL_INT(1, ina.setShuntCalls);
    TEST_ASSERT_FLOAT_WITHIN(0.0000001f, 0.000375f, ina.shuntOhms);
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 200.0f, ina.maxAmps);
}

static void test_pack_and_midpoint_addresses_match_wiring()
{
    // Swapped from spec §3 (Pack=0x40, Midpoint=0x41): the onboard-shunt desolder
    // was done on the already-A0-bridged board, and Pack is defined by carrying
    // the external shunt rather than by which address it answers on.
    TEST_ASSERT_EQUAL_HEX8(0x41, INA228_PACK_I2C_ADDR);
    TEST_ASSERT_EQUAL_HEX8(0x40, INA228_MID_I2C_ADDR);
    // Whatever the assignment, the two must differ or one device answers twice.
    TEST_ASSERT_NOT_EQUAL(INA228_PACK_I2C_ADDR, INA228_MID_I2C_ADDR);
}

static void test_divergence_threshold_matches_default()
{
    TEST_ASSERT_FLOAT_WITHIN(
        0.000001f, 0.5f, INA228_DIVERGENCE_THRESHOLD.value);
}

static void test_named_values_match_200_amp_75_millivolt_shunt()
{
    TEST_ASSERT_FLOAT_WITHIN(
        0.0000001f, 0.000375f, INA228_SHUNT_RESISTANCE.value);
    TEST_ASSERT_FLOAT_WITHIN(
        0.0001f, 200.0f, INA228_SHUNT_MAX_CURRENT.value);
    TEST_ASSERT_FLOAT_WITHIN(
        0.000001f,
        0.075f,
        INA228_SHUNT_RESISTANCE.value *
            INA228_SHUNT_MAX_CURRENT.value);
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_pack_configuration_sets_external_shunt_once);
    RUN_TEST(test_pack_and_midpoint_addresses_match_wiring);
    RUN_TEST(test_divergence_threshold_matches_default);
    RUN_TEST(test_named_values_match_200_amp_75_millivolt_shunt);
    return UNITY_END();
}
