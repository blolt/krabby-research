#include "unity.h"

#include "src/power_bus/ina_pack_lifecycle.h"

void setUp() {}
void tearDown() {}

struct FakeWire {};

struct RecordingIna
{
    bool beginResult;
    int beginCalls;
    uint8_t address;
    FakeWire* wire;
    bool skipReset;
    int setShuntCalls;
    float shuntOhms;
    float maxAmps;
    int resetAccumulatorCalls;

    bool begin(uint8_t requestedAddress, FakeWire* requestedWire, bool requestedSkipReset)
    {
        ++beginCalls;
        address = requestedAddress;
        wire = requestedWire;
        skipReset = requestedSkipReset;
        return beginResult;
    }

    void setShunt(float resistance, float current)
    {
        ++setShuntCalls;
        shuntOhms = resistance;
        maxAmps = current;
    }

    void resetAccumulators()
    {
        ++resetAccumulatorCalls;
    }
};

static RecordingIna makeIna(bool beginResult)
{
    RecordingIna ina = {};
    ina.beginResult = beginResult;
    return ina;
}

static void test_boot_starts_configures_and_resets_accumulators()
{
    FakeWire wire;
    RecordingIna ina = makeIna(true);

    TEST_ASSERT_TRUE(
        startPackIna(ina, INA228_PACK_I2C_ADDR, &wire, PackInaStart::Boot));

    TEST_ASSERT_EQUAL_INT(1, ina.beginCalls);
    TEST_ASSERT_EQUAL_HEX8(INA228_PACK_I2C_ADDR, ina.address);
    TEST_ASSERT_EQUAL_PTR(&wire, ina.wire);
    TEST_ASSERT_FALSE(ina.skipReset);
    TEST_ASSERT_EQUAL_INT(1, ina.setShuntCalls);
    TEST_ASSERT_FLOAT_WITHIN(
        0.0000001f, INA228_SHUNT_RESISTANCE.value, ina.shuntOhms);
    TEST_ASSERT_FLOAT_WITHIN(
        0.0001f, INA228_SHUNT_MAX_CURRENT.value, ina.maxAmps);
    TEST_ASSERT_EQUAL_INT(1, ina.resetAccumulatorCalls);
}

static void test_recovery_starts_and_configures_without_resetting_accumulators()
{
    FakeWire wire;
    RecordingIna ina = makeIna(true);

    TEST_ASSERT_TRUE(
        startPackIna(ina, INA228_PACK_I2C_ADDR, &wire, PackInaStart::Recovery));

    TEST_ASSERT_EQUAL_INT(1, ina.beginCalls);
    TEST_ASSERT_TRUE(ina.skipReset);
    TEST_ASSERT_EQUAL_INT(1, ina.setShuntCalls);
    TEST_ASSERT_EQUAL_INT(0, ina.resetAccumulatorCalls);
}

static void test_failed_boot_does_not_configure_or_reset()
{
    FakeWire wire;
    RecordingIna ina = makeIna(false);

    TEST_ASSERT_FALSE(
        startPackIna(ina, INA228_PACK_I2C_ADDR, &wire, PackInaStart::Boot));

    TEST_ASSERT_EQUAL_INT(1, ina.beginCalls);
    TEST_ASSERT_FALSE(ina.skipReset);
    TEST_ASSERT_EQUAL_INT(0, ina.setShuntCalls);
    TEST_ASSERT_EQUAL_INT(0, ina.resetAccumulatorCalls);
}

static void test_failed_recovery_does_not_configure_or_reset()
{
    FakeWire wire;
    RecordingIna ina = makeIna(false);

    TEST_ASSERT_FALSE(
        startPackIna(ina, INA228_PACK_I2C_ADDR, &wire, PackInaStart::Recovery));

    TEST_ASSERT_EQUAL_INT(1, ina.beginCalls);
    TEST_ASSERT_TRUE(ina.skipReset);
    TEST_ASSERT_EQUAL_INT(0, ina.setShuntCalls);
    TEST_ASSERT_EQUAL_INT(0, ina.resetAccumulatorCalls);
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_boot_starts_configures_and_resets_accumulators);
    RUN_TEST(test_recovery_starts_and_configures_without_resetting_accumulators);
    RUN_TEST(test_failed_boot_does_not_configure_or_reset);
    RUN_TEST(test_failed_recovery_does_not_configure_or_reset);
    return UNITY_END();
}
