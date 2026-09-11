#include "unity.h"
#include <math.h>
#include <initializer_list>
#include <algorithm>
#include <vector>

#include "src/power_monitor/ina228_adapter.h"

static uint32_t fakeNow;
static std::vector<unsigned long> delays;
uint32_t millis() { return fakeNow; }
void delay(unsigned long milliseconds) { delays.push_back(milliseconds); }

void setUp() { fakeNow = 0; delays.clear(); }
void tearDown() {}

static void assertCalls(const FakeInaDevice &device, std::initializer_list<const char *> expected)
{
    TEST_ASSERT_EQUAL_UINT(expected.size(), device.calls.size());
    size_t i = 0;
    for (const char *call : expected)
        TEST_ASSERT_EQUAL_STRING(call, device.calls[i++].c_str());
}

static void assertUnavailable(const PowerMonitorMeasurement &reading)
{
    TEST_ASSERT_FALSE(reading.isValid);
    TEST_ASSERT_TRUE(isnan(reading.voltage.value()));
    TEST_ASSERT_TRUE(isnan(reading.current.value()));
    TEST_ASSERT_TRUE(isnan(reading.power.value()));
    TEST_ASSERT_TRUE(isnan(reading.charge.value()));
}

static void assertValues(const PowerMonitorMeasurement &reading, const FakeInaDevice &device)
{
    TEST_ASSERT_TRUE(reading.isValid);
    TEST_ASSERT_EQUAL_FLOAT(device.voltage, reading.voltage.value());
    TEST_ASSERT_EQUAL_FLOAT(device.current, reading.current.value());
    TEST_ASSERT_EQUAL_FLOAT(device.power, reading.power.value());
    TEST_ASSERT_EQUAL_FLOAT(static_cast<float>(device.charge), reading.charge.value());
}

static void test_unbound_adapter_does_not_attempt_recovery()
{
    Ina228Adapter sensor(0x41);
    for (int i = 0; i < 10; ++i) assertUnavailable(sensor.measure());
    TEST_ASSERT_FALSE(sensor.begin(nullptr));
    assertUnavailable(sensor.measure());
    TEST_ASSERT_FALSE(sensor.isUp());
    TEST_ASSERT_EQUAL_UINT8(0, sensor.badTicks());
    TEST_ASSERT_TRUE(delays.empty());
}

static void test_initial_configuration_and_current_snapshot()
{
    TwoWire wire;
    FakeInaDevices devices(wire);
    auto &device = inaDevices(wire)[0x40];
    Ina228Adapter pack(0x40, 0.000375f, 200.0f, true);
    TEST_ASSERT_TRUE(pack.begin(&wire));
    TEST_ASSERT_TRUE(pack.isUp());
    TEST_ASSERT_EQUAL_HEX8(0x40, pack.address());
    assertCalls(device, {"begin", "reset", "alert", "mode", "calibrate", "accumulators"});
    TEST_ASSERT_TRUE(device.alertEnabled);
    TEST_ASSERT_EQUAL_INT(15, device.mode);
    TEST_ASSERT_EQUAL_FLOAT(0.000375f, device.shuntResistance);
    TEST_ASSERT_EQUAL_FLOAT(200.0f, device.maxCurrent);
    TEST_ASSERT_EQUAL_UINT(1, delays.size());
    TEST_ASSERT_EQUAL_UINT(2, delays[0]);
    device.calls.clear();
    const auto first = pack.measure();
    assertValues(first, device);
    assertCalls(device, {"voltage", "current", "power", "charge"});
    device.voltage = 12.375f;
    assertValues(pack.measure(), device);
    TEST_ASSERT_EQUAL_FLOAT(26.25f, first.voltage.value());
    TEST_ASSERT_TRUE(wire.state().events.empty());
}

static void test_shunt_and_accumulator_configuration_are_explicit()
{
    TwoWire wire;
    FakeInaDevices devices(wire);
    Ina228Adapter midpoint(0x41);
    TEST_ASSERT_TRUE(midpoint.begin(&wire));
    assertCalls(inaDevices(wire)[0x41], {"begin", "reset", "alert", "mode"});
    TEST_ASSERT_EQUAL_HEX8(0x41, midpoint.address());
    Ina228Adapter explicitZero(0x42, 0.0f, 0.0f);
    TEST_ASSERT_TRUE(explicitZero.begin(&wire));
    assertCalls(inaDevices(wire)[0x42], {"begin", "reset", "alert", "mode", "calibrate"});
    TEST_ASSERT_EQUAL_FLOAT(0.0f, inaDevices(wire)[0x42].shuntResistance);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, inaDevices(wire)[0x42].maxCurrent);
}

static void test_each_configuration_failure_stops_setup()
{
    const char *steps[] = {"begin", "reset", "alert", "mode", "calibrate", "accumulators"};
    for (int failed = 0; failed < 6; ++failed)
    {
        delays.clear();
        TwoWire wire;
        FakeInaDevices devices(wire);
        auto &device = inaDevices(wire)[0x40];
        if (failed == 0) device.beginSucceeds = false;
        int *statuses[] = {&device.resetStatus, &device.alertStatus, &device.modeStatus,
            &device.calibrationStatus, &device.accumulatorStatus};
        if (failed > 0) *statuses[failed - 1] = 0x1001;
        Ina228Adapter sensor(0x40, 0.000375f, 200.0f, true);
        TEST_ASSERT_FALSE(sensor.begin(&wire));
        TEST_ASSERT_FALSE(sensor.isUp());
        TEST_ASSERT_EQUAL_UINT(failed + 1, device.calls.size());
        for (int i = 0; i <= failed; ++i)
            TEST_ASSERT_EQUAL_STRING(steps[i], device.calls[i].c_str());
        TEST_ASSERT_EQUAL_UINT(failed >= 4 ? 1 : 0, delays.size());
        const auto calls = device.calls;
        assertUnavailable(sensor.measure());
        TEST_ASSERT_TRUE(calls == device.calls);
        device.beginSucceeds = true;
        for (int *status : statuses) *status = 0;
        device.calls.clear();
        TEST_ASSERT_TRUE(sensor.begin(&wire));
        TEST_ASSERT_TRUE(sensor.isUp());
        assertCalls(device, {"begin", "reset", "alert", "mode", "calibrate", "accumulators"});
    }
}

static void test_all_read_failure_combinations_preserve_successful_fields()
{
    TwoWire wire;
    FakeInaDevices devices(wire);
    auto &device = inaDevices(wire)[0x40];
    Ina228Adapter sensor(0x40);
    TEST_ASSERT_TRUE(sensor.begin(&wire));
    const float expected[] = {26.25f, -2.5f, -65.625f, -12345.125f};
    for (int writes = 0; writes < 2; ++writes)
        for (int mask = 0; mask < 16; ++mask)
        {
            for (int field = 0; field < 4; ++field)
            {
                device.readStatus[field] = 0;
                device.writesOutput[field] = true;
            }
            assertValues(sensor.measure(), device);
            for (int field = 0; field < 4; ++field)
            {
                device.readStatus[field] = (mask & (1 << field)) ? (writes ? -1 : 0x1001) : 0;
                device.writesOutput[field] = writes || device.readStatus[field] == 0;
            }
            device.calls.clear();
            const auto reading = sensor.measure();
            TEST_ASSERT_EQUAL_INT(mask == 0, reading.isValid);
            const float values[] = {reading.voltage.value(), reading.current.value(),
                reading.power.value(), reading.charge.value()};
            for (int field = 0; field < 4; ++field)
                if (mask & (1 << field)) TEST_ASSERT_TRUE(isnan(values[field]));
                else TEST_ASSERT_EQUAL_FLOAT(expected[field], values[field]);
            assertCalls(device, {"voltage", "current", "power", "charge"});
            TEST_ASSERT_TRUE(sensor.isUp());
            TEST_ASSERT_EQUAL_UINT8(mask == 0 ? 0 : 1, sensor.badTicks());
        }
    for (int field = 0; field < 4; ++field)
    {
        device.readStatus[field] = 0;
        device.writesOutput[field] = true;
    }
    assertValues(sensor.measure(), device);
    TEST_ASSERT_TRUE(wire.state().events.empty());
}

static void test_success_status_does_not_imply_finite_readings()
{
    TwoWire wire;
    FakeInaDevices devices(wire);
    auto &device = inaDevices(wire)[0x40];
    Ina228Adapter sensor(0x40);
    TEST_ASSERT_TRUE(sensor.begin(&wire));
    for (float value : {NAN, INFINITY, -INFINITY})
    {
        device.voltage = device.current = device.power = value;
        device.charge = value;
        const auto reading = sensor.measure();
        TEST_ASSERT_TRUE(reading.isValid);
        for (float actual : {reading.voltage.value(), reading.current.value(),
                             reading.power.value(), reading.charge.value()})
            if (isnan(value)) TEST_ASSERT_TRUE(isnan(actual));
            else TEST_ASSERT_TRUE(actual == value);
    }
    TEST_ASSERT_TRUE(sensor.isUp());
    TEST_ASSERT_EQUAL_UINT8(0, sensor.badTicks());
}

static void test_raw_accessors_preserve_units_and_handle_error_status()
{
    TwoWire wire;
    FakeInaDevices devices(wire);
    auto &device = inaDevices(wire)[0x40];
    Ina228Adapter sensor(0x40);
    TEST_ASSERT_TRUE(sensor.begin(&wire));
    device.calls.clear();
    TEST_ASSERT_EQUAL_FLOAT(26.25f, sensor.readBusVoltage().value());
    TEST_ASSERT_EQUAL_FLOAT(-2.5f, sensor.readCurrent().value());
    TEST_ASSERT_EQUAL_FLOAT(-65.625f, sensor.readPower().value());
    TEST_ASSERT_EQUAL_FLOAT(-12345.125f, sensor.readCharge().value());
    assertCalls(device, {"voltage", "current", "power", "charge"});
    for (int writes = 0; writes < 2; ++writes)
    {
        for (int field = 0; field < 4; ++field)
        {
            device.readStatus[field] = writes ? -1 : 0x1001;
            device.writesOutput[field] = writes;
        }
        TEST_ASSERT_TRUE(isnan(sensor.readBusVoltage().value()));
        TEST_ASSERT_TRUE(isnan(sensor.readCurrent().value()));
        TEST_ASSERT_TRUE(isnan(sensor.readPower().value()));
        TEST_ASSERT_TRUE(isnan(sensor.readCharge().value()));
    }
}

static void test_pack_recovery_preserves_charge_and_reads_in_same_call()
{
    TwoWire wire;
    FakeInaDevices devices(wire);
    auto &device = inaDevices(wire)[0x40];
    device.beginSucceeds = false;
    Ina228Adapter sensor(0x40, 0.000375f, 200.0f, true);
    TEST_ASSERT_FALSE(sensor.begin(&wire));
    device.calls.clear();
    const auto unavailable = sensor.measure();
    assertUnavailable(unavailable);
    assertUnavailable(sensor.measure());
    TEST_ASSERT_TRUE(device.calls.empty());
    device.beginSucceeds = true;
    assertValues(sensor.measure(), device);
    assertCalls(device, {"begin", "alert", "mode", "calibrate", "voltage", "current", "power", "charge"});
    TEST_ASSERT_EQUAL_UINT(1, delays.size());
    TEST_ASSERT_EQUAL_UINT(2, delays[0]);
    TEST_ASSERT_EQUAL_UINT8(0, sensor.badTicks());
    assertUnavailable(unavailable);
}

static void test_recovery_reconfigures_when_charge_preservation_is_disabled()
{
    for (bool hasShunt : {false, true})
    {
        TwoWire wire;
        FakeInaDevices devices(wire);
        auto &device = inaDevices(wire)[0x41];
        device.beginSucceeds = false;
        Ina228Adapter sensor = hasShunt ? Ina228Adapter(0x41, 0.000375f, 200.0f) : Ina228Adapter(0x41);
        TEST_ASSERT_FALSE(sensor.begin(&wire));
        assertUnavailable(sensor.measure());
        assertUnavailable(sensor.measure());
        device.beginSucceeds = true;
        device.calls.clear();
        assertValues(sensor.measure(), device);
        if (hasShunt)
            assertCalls(device, {"begin", "reset", "alert", "mode", "calibrate", "voltage", "current", "power", "charge"});
        else
            assertCalls(device, {"begin", "reset", "alert", "mode", "voltage", "current", "power", "charge"});
    }
}

static void test_absence_and_failed_recovery_respect_exact_retry_boundary()
{
    for (uint32_t start : {uint32_t(0), UINT32_MAX - 999u})
    {
        TwoWire wire;
        FakeInaDevices devices(wire);
        auto &device = inaDevices(wire)[0x41];
        device.beginSucceeds = false;
        Ina228Adapter sensor(0x41);
        TEST_ASSERT_FALSE(sensor.begin(&wire));
        device.calls.clear();
        fakeNow = start;
        assertUnavailable(sensor.measure());
        assertUnavailable(sensor.measure());
        TEST_ASSERT_TRUE(wire.state().events.empty());
        assertUnavailable(sensor.measure());
        assertCalls(device, {"begin"});
        fakeNow = start + 1999u;
        for (int i = 0; i < 3; ++i) assertUnavailable(sensor.measure());
        assertCalls(device, {"begin"});
        fakeNow = start + 2000u;
        assertUnavailable(sensor.measure());
        assertCalls(device, {"begin", "begin"});
        TEST_ASSERT_FALSE(sensor.isUp());
        device.beginSucceeds = true;
        fakeNow = start + 3999u;
        for (int i = 0; i < 3; ++i) assertUnavailable(sensor.measure());
        device.calls.clear();
        fakeNow = start + 4000u;
        assertValues(sensor.measure(), device);
        assertCalls(device, {"begin", "reset", "alert", "mode", "voltage", "current", "power", "charge"});
        TEST_ASSERT_TRUE(wire.state().events.empty());
    }
}

static void test_failed_recovery_configuration_returns_no_measurement()
{
    for (int failure = 0; failure < 3; ++failure)
    {
        fakeNow = 0;
        TwoWire wire;
        FakeInaDevices devices(wire);
        auto &device = inaDevices(wire)[0x40];
        device.beginSucceeds = false;
        Ina228Adapter sensor(0x40, 0.000375f, 200.0f, true);
        TEST_ASSERT_FALSE(sensor.begin(&wire));
        assertUnavailable(sensor.measure());
        assertUnavailable(sensor.measure());
        device.beginSucceeds = true;
        int *statuses[] = {&device.alertStatus, &device.modeStatus, &device.calibrationStatus};
        *statuses[failure] = -1;
        device.calls.clear();
        assertUnavailable(sensor.measure());
        TEST_ASSERT_FALSE(sensor.isUp());
        const char *expected[] = {"begin", "alert", "mode", "calibrate"};
        TEST_ASSERT_EQUAL_UINT(failure + 2, device.calls.size());
        for (int i = 0; i < failure + 2; ++i)
            TEST_ASSERT_EQUAL_STRING(expected[i], device.calls[i].c_str());
        *statuses[failure] = 0;
        fakeNow = 2000;
        assertUnavailable(sensor.measure());
        assertUnavailable(sensor.measure());
        device.calls.clear();
        assertValues(sensor.measure(), device);
        assertCalls(device, {"begin", "alert", "mode", "calibrate", "voltage", "current", "power", "charge"});
    }
}

static void test_monitor_failures_and_recovery_are_independent()
{
    for (uint8_t failedAddress : {0x40, 0x41})
    {
        fakeNow = 0;
        TwoWire wire;
        FakeInaDevices devices(wire);
        auto &packDevice = inaDevices(wire)[0x40];
        auto &midDevice = inaDevices(wire)[0x41];
        midDevice.voltage = 13.0f;
        auto &failed = inaDevices(wire)[failedAddress];
        auto &healthy = inaDevices(wire)[failedAddress == 0x40 ? 0x41 : 0x40];
        failed.beginSucceeds = false;
        Ina228Adapter pack(0x40, 0.000375f, 200.0f, true);
        Ina228Adapter midpoint(0x41);
        TEST_ASSERT_EQUAL_INT(failedAddress != 0x40, pack.begin(&wire));
        TEST_ASSERT_EQUAL_INT(failedAddress != 0x41, midpoint.begin(&wire));
        Ina228Adapter &unavailable = failedAddress == 0x40 ? pack : midpoint;
        Ina228Adapter &available = failedAddress == 0x40 ? midpoint : pack;
        healthy.calls.clear();
        for (int i = 0; i < 2; ++i)
        {
            assertUnavailable(unavailable.measure());
            assertValues(available.measure(), healthy);
            TEST_ASSERT_EQUAL_UINT8(0, available.badTicks());
        }
        failed.beginSucceeds = true;
        assertValues(unavailable.measure(), failed);
        assertValues(available.measure(), healthy);
        assertCalls(healthy, {"voltage", "current", "power", "charge", "voltage", "current", "power", "charge", "voltage", "current", "power", "charge"});
        TEST_ASSERT_TRUE(wire.state().events.empty());
        TEST_ASSERT_EQUAL_FLOAT(0.000375f, packDevice.shuntResistance);
        TEST_ASSERT_EQUAL_FLOAT(-1.0f, midDevice.shuntResistance);
        failed.readStatus[1] = -1;
        const auto partial = unavailable.measure();
        TEST_ASSERT_FALSE(partial.isValid);
        TEST_ASSERT_TRUE(isnan(partial.current.value()));
        TEST_ASSERT_EQUAL_FLOAT(failed.voltage, partial.voltage.value());
        assertValues(available.measure(), healthy);
        fakeNow = 2000;
        TEST_ASSERT_FALSE(unavailable.measure().isValid);
        assertValues(available.measure(), healthy);
        TEST_ASSERT_EQUAL_UINT8(2, unavailable.badTicks());
        failed.calls.clear();
        TEST_ASSERT_FALSE(unavailable.measure().isValid);
        TEST_ASSERT_TRUE(std::find(failed.calls.begin(), failed.calls.end(), "begin") != failed.calls.end());
        assertValues(available.measure(), healthy);
        TEST_ASSERT_EQUAL_UINT8(0, available.badTicks());
        failed.readStatus[1] = 0;
        assertValues(unavailable.measure(), failed);
    }
}

static void test_same_address_on_different_buses_and_rebinding()
{
    TwoWire firstWire, secondWire;
    FakeInaDevices firstDevices(firstWire), secondDevices(secondWire);
    inaDevices(firstWire)[0x40].voltage = 12.0f;
    inaDevices(secondWire)[0x40].voltage = 24.0f;
    Ina228Adapter first(0x40), second(0x40);
    TEST_ASSERT_TRUE(first.begin(&firstWire));
    TEST_ASSERT_TRUE(second.begin(&secondWire));
    assertValues(first.measure(), inaDevices(firstWire)[0x40]);
    assertValues(second.measure(), inaDevices(secondWire)[0x40]);
    inaDevices(firstWire)[0x40].calls.clear();
    TEST_ASSERT_TRUE(first.begin(&secondWire));
    assertValues(first.measure(), inaDevices(secondWire)[0x40]);
    TEST_ASSERT_TRUE(inaDevices(firstWire)[0x40].calls.empty());
    TEST_ASSERT_FALSE(first.begin(nullptr));
    inaDevices(secondWire)[0x40].calls.clear();
    for (int i = 0; i < 3; ++i) assertUnavailable(first.measure());
    TEST_ASSERT_TRUE(inaDevices(secondWire)[0x40].calls.empty());
    assertValues(second.measure(), inaDevices(secondWire)[0x40]);
}

static void test_transient_failures_clear_and_qualified_failure_keeps_partial_sample()
{
    TwoWire wire;
    FakeInaDevices devices(wire);
    auto &device = inaDevices(wire)[0x40];
    Ina228Adapter sensor(0x40, 0.000375f, 200.0f, true);
    TEST_ASSERT_TRUE(sensor.begin(&wire));
    for (int round = 0; round < 2; ++round)
    {
        device.readStatus[1] = -1;
        for (int n = 1; n <= 2; ++n)
        {
            device.calls.clear();
            TEST_ASSERT_FALSE(sensor.measure().isValid);
            TEST_ASSERT_EQUAL_UINT8(n, sensor.badTicks());
            TEST_ASSERT_TRUE(sensor.isUp());
            assertCalls(device, {"voltage", "current", "power", "charge"});
        }
        device.readStatus[1] = 0;
        assertValues(sensor.measure(), device);
        TEST_ASSERT_EQUAL_UINT8(0, sensor.badTicks());
    }
    device.readStatus[1] = -1;
    TEST_ASSERT_FALSE(sensor.measure().isValid);
    TEST_ASSERT_FALSE(sensor.measure().isValid);
    device.calls.clear();
    const auto third = sensor.measure();
    TEST_ASSERT_FALSE(third.isValid);
    TEST_ASSERT_EQUAL_FLOAT(26.25f, third.voltage.value());
    TEST_ASSERT_TRUE(isnan(third.current.value()));
    TEST_ASSERT_TRUE(sensor.isUp());
    assertCalls(device, {"voltage", "current", "power", "charge", "begin", "alert", "mode", "calibrate"});
}

static void test_runtime_failed_restart_and_recovered_bad_read_count_once()
{
    TwoWire wire;
    FakeInaDevices devices(wire);
    auto &device = inaDevices(wire)[0x40];
    Ina228Adapter sensor(0x40, 0.000375f, 200.0f, true);
    TEST_ASSERT_TRUE(sensor.begin(&wire));
    device.readStatus[1] = -1;
    device.beginSucceeds = false;
    TEST_ASSERT_FALSE(sensor.measure().isValid);
    TEST_ASSERT_FALSE(sensor.measure().isValid);
    const auto third = sensor.measure();
    TEST_ASSERT_EQUAL_FLOAT(26.25f, third.voltage.value());
    TEST_ASSERT_FALSE(sensor.isUp());
    assertUnavailable(sensor.measure());
    assertUnavailable(sensor.measure());
    fakeNow = 1999;
    device.calls.clear();
    assertUnavailable(sensor.measure());
    TEST_ASSERT_TRUE(device.calls.empty());
    fakeNow = 2000; device.beginSucceeds = true;
    const auto recovered = sensor.measure();
    TEST_ASSERT_FALSE(recovered.isValid);
    TEST_ASSERT_EQUAL_FLOAT(26.25f, recovered.voltage.value());
    TEST_ASSERT_EQUAL_UINT8(0, sensor.badTicks());
    assertCalls(device, {"begin", "alert", "mode", "calibrate", "voltage", "current", "power", "charge"});
    device.calls.clear();
    TEST_ASSERT_FALSE(sensor.measure().isValid);
    TEST_ASSERT_EQUAL_UINT8(1, sensor.badTicks());
    device.readStatus[1] = 0;
    assertValues(sensor.measure(), device);
}

static void test_continuous_read_failures_respect_cooldown_and_rollover()
{
    for (uint32_t start : {uint32_t(0), UINT32_MAX - 999u})
    {
        TwoWire wire;
        FakeInaDevices devices(wire);
        auto &device = inaDevices(wire)[0x40];
        Ina228Adapter sensor(0x40, 0.000375f, 200.0f, true);
        TEST_ASSERT_TRUE(sensor.begin(&wire));
        fakeNow = start;
        for (int &status : device.readStatus) status = -1;
        for (int n = 0; n < 3; ++n) assertUnavailable(sensor.measure());
        fakeNow = start + 1999u; device.calls.clear();
        for (int n = 0; n < 3; ++n) assertUnavailable(sensor.measure());
        TEST_ASSERT_EQUAL_UINT(12, device.calls.size());
        fakeNow = start + 2000u; device.calls.clear();
        assertUnavailable(sensor.measure());
        assertCalls(device, {"voltage", "current", "power", "charge", "begin", "alert", "mode", "calibrate"});
        TEST_ASSERT_TRUE(sensor.isUp());
    }
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_transient_failures_clear_and_qualified_failure_keeps_partial_sample);
    RUN_TEST(test_runtime_failed_restart_and_recovered_bad_read_count_once);
    RUN_TEST(test_continuous_read_failures_respect_cooldown_and_rollover);
    RUN_TEST(test_unbound_adapter_does_not_attempt_recovery);
    RUN_TEST(test_initial_configuration_and_current_snapshot);
    RUN_TEST(test_shunt_and_accumulator_configuration_are_explicit);
    RUN_TEST(test_each_configuration_failure_stops_setup);
    RUN_TEST(test_all_read_failure_combinations_preserve_successful_fields);
    RUN_TEST(test_success_status_does_not_imply_finite_readings);
    RUN_TEST(test_raw_accessors_preserve_units_and_handle_error_status);
    RUN_TEST(test_pack_recovery_preserves_charge_and_reads_in_same_call);
    RUN_TEST(test_recovery_reconfigures_when_charge_preservation_is_disabled);
    RUN_TEST(test_absence_and_failed_recovery_respect_exact_retry_boundary);
    RUN_TEST(test_failed_recovery_configuration_returns_no_measurement);
    RUN_TEST(test_monitor_failures_and_recovery_are_independent);
    RUN_TEST(test_same_address_on_different_buses_and_rebinding);
    return UNITY_END();
}
