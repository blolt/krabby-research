#include "unity.h"

#include "src/power_monitor/ina228_adapter.h"

float fakeInaBusVoltage;
float fakeInaCurrent;
float fakeInaPower;
float fakeInaCharge;
bool shouldInaBeginSucceed;
uint8_t fakeInaBeginAddress;
bool didInaBeginSkipReset;
uint8_t fakeInaBeginCount;
uint8_t fakeInaSetShuntCount;
float fakeInaShuntResistance;
float fakeInaShuntMaxCurrent;
uint8_t fakeInaResetAccumulatorsCount;
uint8_t fakeWireEndTransmissionResult;
uint8_t fakeWireLastAddress;
uint8_t fakeWireBeginTransmissionCount;

void setUp()
{
    fakeInaBusVoltage = 0.0f;
    fakeInaCurrent = 0.0f;
    fakeInaPower = 0.0f;
    fakeInaCharge = 0.0f;
    shouldInaBeginSucceed = true;
    fakeInaBeginAddress = 0;
    didInaBeginSkipReset = false;
    fakeInaBeginCount = 0;
    fakeInaSetShuntCount = 0;
    fakeInaShuntResistance = 0.0f;
    fakeInaShuntMaxCurrent = 0.0f;
    fakeInaResetAccumulatorsCount = 0;
    fakeWireEndTransmissionResult = 0;
    fakeWireLastAddress = 0;
    fakeWireBeginTransmissionCount = 0;
}
void tearDown() {}

static void test_roles_select_the_wired_addresses()
{
    Ina228Adapter pack(PowerMonitorRole::Pack);
    Ina228Adapter midpoint(PowerMonitorRole::Midpoint);

    TEST_ASSERT_EQUAL_HEX8(0x40, pack.address());
    TEST_ASSERT_EQUAL_HEX8(0x41, midpoint.address());
}

static void test_pack_initialization_configures_the_external_shunt()
{
    TwoWire wire;
    Ina228Adapter pack(PowerMonitorRole::Pack);

    TEST_ASSERT_TRUE(pack.begin(&wire));
    TEST_ASSERT_EQUAL_HEX8(0x40, fakeInaBeginAddress);
    TEST_ASSERT_FALSE(didInaBeginSkipReset);
    TEST_ASSERT_EQUAL_UINT8(1, fakeInaSetShuntCount);
    TEST_ASSERT_FLOAT_WITHIN(
        0.0000001f, 0.000375f, fakeInaShuntResistance);
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 200.0f, fakeInaShuntMaxCurrent);
    TEST_ASSERT_EQUAL_UINT8(1, fakeInaResetAccumulatorsCount);
}

static void test_pack_recovery_preserves_accumulated_charge()
{
    TwoWire wire;
    Ina228Adapter pack(PowerMonitorRole::Pack);
    TEST_ASSERT_TRUE(pack.begin(&wire));

    pack.noteRead(false, &wire, 1000);
    pack.noteRead(false, &wire, 1001);
    pack.noteRead(false, &wire, 1002);

    TEST_ASSERT_TRUE(pack.isUp());
    TEST_ASSERT_EQUAL_UINT8(2, fakeInaSetShuntCount);
    TEST_ASSERT_EQUAL_UINT8(1, fakeInaResetAccumulatorsCount);
}

static void test_success_clears_pending_failures()
{
    TwoWire wire;
    Ina228Adapter pack(PowerMonitorRole::Pack);
    TEST_ASSERT_TRUE(pack.begin(&wire));

    pack.noteRead(false, &wire, 1000);
    pack.noteRead(false, &wire, 1001);
    TEST_ASSERT_FALSE(pack.isUp());
    TEST_ASSERT_EQUAL_UINT8(2, pack.badTicks());

    pack.noteRead(true, &wire, 1002);
    TEST_ASSERT_TRUE(pack.isUp());
    TEST_ASSERT_EQUAL_UINT8(0, pack.badTicks());
}

static void test_failed_initialization_can_recover_without_resetting_charge()
{
    TwoWire wire;
    Ina228Adapter pack(PowerMonitorRole::Pack);
    shouldInaBeginSucceed = false;
    TEST_ASSERT_FALSE(pack.begin(&wire));

    shouldInaBeginSucceed = true;
    pack.noteRead(false, &wire, 1000);
    pack.noteRead(false, &wire, 1001);
    pack.noteRead(false, &wire, 1002);

    TEST_ASSERT_TRUE(pack.isUp());
    TEST_ASSERT_EQUAL_UINT8(2, fakeInaBeginCount);
    TEST_ASSERT_TRUE(didInaBeginSkipReset);
    TEST_ASSERT_EQUAL_UINT8(1, fakeInaSetShuntCount);
    TEST_ASSERT_EQUAL_UINT8(0, fakeInaResetAccumulatorsCount);
}

static void test_absent_monitor_stays_down_without_reinitialization()
{
    TwoWire wire;
    Ina228Adapter pack(PowerMonitorRole::Pack);
    TEST_ASSERT_TRUE(pack.begin(&wire));
    fakeWireEndTransmissionResult = 1;

    pack.noteRead(false, &wire, 1000);
    pack.noteRead(false, &wire, 1001);
    pack.noteRead(false, &wire, 1002);

    TEST_ASSERT_FALSE(pack.isUp());
    TEST_ASSERT_EQUAL_HEX8(0x40, fakeWireLastAddress);
    TEST_ASSERT_EQUAL_UINT8(1, fakeWireBeginTransmissionCount);
    TEST_ASSERT_EQUAL_UINT8(1, fakeInaBeginCount);
    TEST_ASSERT_EQUAL_UINT8(1, fakeInaSetShuntCount);
}

static void test_never_initialized_absent_monitor_stays_down()
{
    TwoWire wire;
    Ina228Adapter pack(PowerMonitorRole::Pack);
    shouldInaBeginSucceed = false;
    TEST_ASSERT_FALSE(pack.begin(&wire));
    fakeWireEndTransmissionResult = 1;

    pack.noteRead(false, &wire, 1000);
    pack.noteRead(false, &wire, 1001);
    pack.noteRead(false, &wire, 1002);

    TEST_ASSERT_FALSE(pack.isUp());
    TEST_ASSERT_EQUAL_UINT8(1, fakeInaBeginCount);
}

static void test_failed_recovery_begin_leaves_monitor_down()
{
    TwoWire wire;
    Ina228Adapter pack(PowerMonitorRole::Pack);
    shouldInaBeginSucceed = false;
    TEST_ASSERT_FALSE(pack.begin(&wire));

    pack.noteRead(false, &wire, 1000);
    pack.noteRead(false, &wire, 1001);
    pack.noteRead(false, &wire, 1002);

    TEST_ASSERT_FALSE(pack.isUp());
    TEST_ASSERT_EQUAL_UINT8(2, fakeInaBeginCount);
    TEST_ASSERT_EQUAL_UINT8(0, fakeInaSetShuntCount);
}

static void test_midpoint_recovery_does_not_apply_pack_configuration()
{
    TwoWire wire;
    Ina228Adapter midpoint(PowerMonitorRole::Midpoint);
    TEST_ASSERT_TRUE(midpoint.begin(&wire));

    midpoint.noteRead(false, &wire, 1000);
    midpoint.noteRead(false, &wire, 1001);
    midpoint.noteRead(false, &wire, 1002);

    TEST_ASSERT_TRUE(midpoint.isUp());
    TEST_ASSERT_EQUAL_UINT8(0, fakeInaSetShuntCount);
    TEST_ASSERT_EQUAL_UINT8(1, fakeInaBeginCount);
}

static void test_midpoint_uses_default_device_configuration()
{
    TwoWire wire;
    Ina228Adapter midpoint(PowerMonitorRole::Midpoint);

    TEST_ASSERT_TRUE(midpoint.begin(&wire));
    TEST_ASSERT_EQUAL_HEX8(0x41, fakeInaBeginAddress);
    TEST_ASSERT_EQUAL_UINT8(0, fakeInaSetShuntCount);
    TEST_ASSERT_EQUAL_UINT8(0, fakeInaResetAccumulatorsCount);
}

static void test_measurements_are_exposed_as_firmware_units()
{
    fakeInaBusVoltage = 26.0f;
    fakeInaCurrent = 1500.0f;
    fakeInaPower = 37500.0f;
    fakeInaCharge = 123.0f;
    Ina228Adapter adapter(PowerMonitorRole::Pack);

    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, 26.5f,
        adapter.readBusVoltage(Volts(0.5f)).value());
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, 1.5f, adapter.readCurrent().value());
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, 37.5f, adapter.readPower().value());
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, 123.0f, adapter.readCharge().value());
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_roles_select_the_wired_addresses);
    RUN_TEST(test_pack_initialization_configures_the_external_shunt);
    RUN_TEST(test_pack_recovery_preserves_accumulated_charge);
    RUN_TEST(test_success_clears_pending_failures);
    RUN_TEST(test_failed_initialization_can_recover_without_resetting_charge);
    RUN_TEST(test_absent_monitor_stays_down_without_reinitialization);
    RUN_TEST(test_never_initialized_absent_monitor_stays_down);
    RUN_TEST(test_failed_recovery_begin_leaves_monitor_down);
    RUN_TEST(test_midpoint_recovery_does_not_apply_pack_configuration);
    RUN_TEST(test_midpoint_uses_default_device_configuration);
    RUN_TEST(test_measurements_are_exposed_as_firmware_units);
    return UNITY_END();
}
