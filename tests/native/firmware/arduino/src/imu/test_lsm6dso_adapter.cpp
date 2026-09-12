#include "unity.h"
#include <algorithm>
#include <initializer_list>
#include <memory>
#include <vector>
#include "environment.h"
#include "src/imu/lsm6dso_adapter.h"

using namespace imu_native;
using lsm6dso_native::Sample;

static TwoWire testWire(environment.bus);

static void checkScript()
{
    TEST_ASSERT_TRUE(Wire.state().events.empty());
    TEST_ASSERT_TRUE(Wire.state().errors.empty());
    if (!environment.bus.errors.empty()) TEST_FAIL_MESSAGE(environment.bus.errors.front().c_str());
    if (!environment.errors.empty()) TEST_FAIL_MESSAGE(environment.errors.front().c_str());
    TEST_ASSERT_TRUE(environment.bus.transfers.empty());
    for (const auto &entry : environment.devices) TEST_ASSERT_TRUE(entry.second.samples.empty());
    TEST_ASSERT_TRUE(environment.sda.empty());
}
static void resetCase()
{
    checkScript();
    imu_native::reset();
    device(0x6B);
    device(0x6A).present = false;
}
void setUp() { imu_native::reset(); resetCase(); }
void tearDown() { checkScript(); }

static void assertEvents(std::initializer_list<Event> expected)
{
    TEST_ASSERT_EQUAL_UINT(expected.size(), environment.events.size());
    size_t i = 0;
    for (const auto &event : expected)
    {
        const auto &actual = environment.events[i++];
        TEST_ASSERT_EQUAL_STRING(event.name.c_str(), actual.name.c_str());
        TEST_ASSERT_EQUAL_INT(event.a, actual.a);
        TEST_ASSERT_EQUAL_INT(event.b, actual.b);
        TEST_ASSERT_EQUAL_INT(event.c, actual.c);
    }
}
static size_t count(const char *name)
{
    size_t result = 0;
    for (const auto &event : environment.events) if (event.name == name) ++result;
    return result;
}
// Transfer-level Wire events, which the merged event log leaves out.
static size_t busCount(const char *name)
{
    size_t result = 0;
    for (const auto &event : environment.bus.events) if (event.name == name) ++result;
    return result;
}
static bool busIs(const wire_native::Event &event, const char *name, std::initializer_list<long> args)
{
    return event.name == name && event.args == std::vector<long>(args);
}
static void clearEvents()
{
    environment.events.clear();
    environment.bus.events.clear();
    for (auto &entry : environment.devices) entry.second.clearLog();
}
static size_t configurationReads(uint8_t address = 0x6B)
{
    const auto &sensor = device(address);
    return sensor.readCount(lsm6dso_native::CTRL1_XL) + sensor.readCount(lsm6dso_native::CTRL2_G) +
           sensor.readCount(lsm6dso_native::CTRL3_C);
}

static constexpr Sample DEFAULT_SAMPLE = {{256, 100, -200, 300, -1000, 2000, 4098}};
static Sample sample(std::initializer_list<int16_t> words)
{
    Sample value{};
    std::copy(words.begin(), words.end(), value.begin());
    return value;
}
static void enqueue(const Sample &value = DEFAULT_SAMPLE, uint8_t address = 0x6B)
{ device(address).samples.push_back(value); }

static bool failsBurstRead(uint8_t reg, bool isWrite, uint8_t)
{ return !isWrite && reg == lsm6dso_native::OUT_TEMP_L; }
// NACK the index-th register write: each configuration call makes exactly one.
static void failWrite(size_t index)
{
    const auto writes = std::make_shared<size_t>(0);
    device(0x6B).nack = [index, writes](uint8_t, bool isWrite, uint8_t) { return isWrite && (*writes)++ == index; };
}

static void initialize(Lsm6dsoAdapter &adapter)
{
    TEST_ASSERT_EQUAL_INT(static_cast<int>(Lsm6dsoInitializationResult::Ok), static_cast<int>(adapter.initialize()));
}
static void failedMeasurement(Lsm6dsoAdapter &adapter)
{ TEST_ASSERT_FALSE(adapter.measure().didSucceed()); }
static void atMilliseconds(uint64_t ms) { environment.microseconds = ms * 1000; }

struct Storage
{
    ImuCalibrationRecord record{};
    std::vector<int> operations;
    bool corrupt = false;
    void load(ImuCalibrationRecord &value)
    {
        operations.push_back(0);
        value = record;
        if (corrupt && operations.size() > 1) value.schema = 0;
    }
    void writeRecord(const ImuCalibrationRecord &value)
    {
        TEST_ASSERT_EQUAL_HEX8(0, value.magic);
        operations.push_back(1);
        record = value;
    }
    void updateMagic(uint8_t magic)
    {
        operations.push_back(2);
        record.magic = magic;
    }
};
static Storage storedCalibration()
{
    Storage storage;
    storage.record.magic = 0xC7;
    storage.record.schema = 1;
    storage.record.gyroBiasDegreesPerSecond[0] = 1.75f;
    storage.record.accelBiasG[1] = 0.1f;
    return storage;
}

static void test_initialization_and_address_fallback()
{
    Lsm6dsoAdapter adapter(testWire);
    initialize(adapter);
    assertEvents({{"wire.begin",0,0,0}, {"wire.clock",100000,0,0}, {"wire.timeout",10000,1,0},
        {"sensor.identify",0x6B,0,0}, {"sensor.write",0x12,0x04,0}, {"sensor.write",0x10,0x0C,0},
        {"sensor.write",0x10,0x6C,0}, {"sensor.write",0x11,0x04,0}, {"sensor.write",0x11,0x64,0},
        {"sensor.write",0x12,0x44,0}, {"delay",5,0,0}});
    TEST_ASSERT_EQUAL_UINT32(5, millis());
    // The driver's read-modify-write setters leave the configuration the adapter verifies.
    TEST_ASSERT_EQUAL_HEX8(0x6C, device(0x6B).registerValue(lsm6dso_native::CTRL1_XL));
    TEST_ASSERT_EQUAL_HEX8(0x64, device(0x6B).registerValue(lsm6dso_native::CTRL2_G));
    TEST_ASSERT_EQUAL_HEX8(0x44, device(0x6B).registerValue(lsm6dso_native::CTRL3_C));
    resetCase();
    device(0x6B).present = false;
    device(0x6A).present = true;
    initialize(adapter);
    TEST_ASSERT_EQUAL_UINT(2, count("sensor.identify"));
    TEST_ASSERT_EQUAL_INT(0x6B, environment.events[3].a);
    TEST_ASSERT_EQUAL_INT(0x6A, environment.events[4].a);
    enqueue(DEFAULT_SAMPLE, 0x6A);
    TEST_ASSERT_TRUE(adapter.measure().didSucceed());
}

static void test_driver_accepts_any_responding_device()
{
    // The SparkFun driver reads WHO_AM_I but never rejects a mismatch, so another
    // chip answering at 0x6B is configured as though it were an LSM6DSO.
    device(0x6B).setRegister(lsm6dso_native::WHO_AM_I, 0x00);
    Lsm6dsoAdapter adapter(testWire);
    initialize(adapter);
    TEST_ASSERT_EQUAL_UINT(1, count("sensor.identify"));
    TEST_ASSERT_EQUAL_HEX8(0x6C, device(0x6B).registerValue(lsm6dso_native::CTRL1_XL));
}

static void test_absent_and_each_configuration_failure()
{
    for (int failure = -1; failure < 6; ++failure)
    {
        resetCase();
        Lsm6dsoAdapter adapter(testWire);
        if (failure == -1) device(0x6B).present = false;
        else failWrite(size_t(failure));
        TEST_ASSERT_EQUAL_INT(static_cast<int>(failure == -1 ? Lsm6dsoInitializationResult::NotDetected :
            Lsm6dsoInitializationResult::ConfigurationFailed), static_cast<int>(adapter.initialize()));
        TEST_ASSERT_EQUAL_UINT(failure == -1 ? 5 : 5 + failure, environment.events.size());
        TEST_ASSERT_EQUAL_UINT(0, count("delay"));
        clearEvents();
        Storage storage;
        TEST_ASSERT_EQUAL_INT(static_cast<int>(ImuCalibrationResult::ReadFailed),
            static_cast<int>(adapter.calibrate(storage, delay)));
        TEST_ASSERT_EQUAL_UINT(0, busCount("wire.transmit"));
    }
}

static void test_burst_protocol_signed_samples_and_units()
{
    Lsm6dsoAdapter adapter(testWire); initialize(adapter);
    clearEvents();
    // Distinct words across all seven channels, including a negative temperature word.
    enqueue(sample({-256, 100, -200, 300, -1000, 2000, 4098}));
    const auto reading = adapter.measure();
    TEST_ASSERT_TRUE(reading.didSucceed());
    TEST_ASSERT_EQUAL_FLOAT(24.0f, reading.temperature.value());
    const float rates[] = {0.030543262f, -0.061086524f, 0.091629786f};
    const float acceleration[] = {-2.3928226f, 4.7856452f, 9.8057870f};
    for (int axis = 0; axis < 3; ++axis)
    {
        TEST_ASSERT_FLOAT_WITHIN(0.000001f, rates[axis], reading.angularRate[axis].value());
        TEST_ASSERT_FLOAT_WITHIN(0.00001f, acceleration[axis], reading.acceleration[axis].value());
    }
    const auto &bus = environment.bus.events;
    TEST_ASSERT_EQUAL_UINT(18, bus.size());
    TEST_ASSERT_TRUE(busIs(bus[0], "wire.transmit", {0x6B}));
    TEST_ASSERT_TRUE(busIs(bus[1], "wire.write", {0x20}));
    TEST_ASSERT_TRUE(busIs(bus[2], "wire.endTransmission", {0}));
    TEST_ASSERT_TRUE(busIs(bus[3], "wire.request", {0x6B, 14, 1}));
    TEST_ASSERT_EQUAL_UINT(14, busCount("wire.read"));
    TEST_ASSERT_EQUAL_UINT(0, configurationReads());
    enqueue(sample({-32768, -32768, 32767, -1, 32767, -32768, 1}));
    const auto extreme = adapter.measure();
    TEST_ASSERT_EQUAL_FLOAT(-103.0f, extreme.temperature.value());
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, -10.008421f, extreme.angularRate[0].value());
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, -78.408011f, extreme.acceleration[1].value());
}

static void test_failed_transfer_and_every_short_read()
{
    for (int kind = 0; kind < 2; ++kind)
        for (int n = 0; n < (kind == 1 ? 14 : 1); ++n)
        {
            resetCase();
            Lsm6dsoAdapter adapter(testWire); initialize(adapter);
            clearEvents();
            if (kind == 0) device(0x6B).nack = failsBurstRead;
            else device(0x6B).maxReadBytes = size_t(n);
            failedMeasurement(adapter);
            TEST_ASSERT_EQUAL_UINT(0, busCount("wire.read"));
            TEST_ASSERT_EQUAL_UINT(1, busCount("wire.endTransmission"));
            TEST_ASSERT_EQUAL_UINT(kind, busCount("wire.request"));
            TEST_ASSERT_EQUAL_UINT(0, configurationReads());
            // A failed read makes the next call wait for recovery, not read again.
            failedMeasurement(adapter);
            TEST_ASSERT_EQUAL_UINT(1, busCount("wire.transmit"));
        }
}

static void test_zero_motion_checks_configuration_and_nonzero_motion_does_not()
{
    for (int channel = 0; channel < 6; ++channel)
    {
        resetCase();
        Lsm6dsoAdapter adapter(testWire); initialize(adapter);
        clearEvents();
        Sample motion{};
        motion[1 + channel] = 1;
        enqueue(motion); TEST_ASSERT_TRUE(adapter.measure().didSucceed());
        TEST_ASSERT_EQUAL_UINT(0, configurationReads());
    }
    for (int reg = 0; reg < 3; ++reg)
        for (int bit = 0; bit < 8; ++bit)
        {
            resetCase();
            Lsm6dsoAdapter adapter(testWire); initialize(adapter);
            clearEvents();
            const uint8_t masks[] = {0xFC, 0xFE, 0x44};
            auto &sensor = device(0x6B);
            const uint8_t address = uint8_t(lsm6dso_native::CTRL1_XL + reg);
            sensor.setRegister(address, uint8_t(sensor.registerValue(address) ^ (1 << bit)));
            enqueue(sample({256, 0, 0, 0, 0, 0, 0}));
            TEST_ASSERT_EQUAL_INT((masks[reg] & (1 << bit)) == 0, adapter.measure().didSucceed());
            TEST_ASSERT_EQUAL_UINT(3, configurationReads());
        }
    resetCase();
    Lsm6dsoAdapter adapter(testWire); initialize(adapter);
    enqueue(sample({0, 0, 0, 0, 0, 0, 0}));
    TEST_ASSERT_TRUE(adapter.measure().didSucceed());
}

static void test_each_configuration_register_read_error()
{
    for (int reg = 0; reg < 3; ++reg)
    {
        resetCase();
        Lsm6dsoAdapter adapter(testWire); initialize(adapter);
        clearEvents();
        device(0x6B).nack = [reg](uint8_t address, bool isWrite, uint8_t) {
            return !isWrite && address == lsm6dso_native::CTRL1_XL + reg;
        };
        enqueue(sample({0, 0, 0, 0, 0, 0, 0})); failedMeasurement(adapter);
        TEST_ASSERT_EQUAL_UINT(reg + 1, configurationReads());
    }
}

static void test_stored_calibration_applied_and_retained_during_recovery()
{
    Lsm6dsoAdapter adapter(testWire); initialize(adapter);
    clearEvents();
    Storage storage = storedCalibration();
    TEST_ASSERT_EQUAL_INT(static_cast<int>(ImuCalibrationResult::Loaded), static_cast<int>(adapter.calibrate(storage, delay)));
    TEST_ASSERT_EQUAL_UINT(1, storage.operations.size());
    TEST_ASSERT_EQUAL_UINT(0, busCount("wire.transmit"));
    enqueue(); const auto reading = adapter.measure();
    TEST_ASSERT_FLOAT_WITHIN(0.000001f, 0, reading.angularRate[0].value());
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 3.8049802f, reading.acceleration[1].value());
    device(0x6B).nack = failsBurstRead; failedMeasurement(adapter);
    failedMeasurement(adapter);
    device(0x6B).nack = nullptr;
    enqueue(); const auto recovered = adapter.measure();
    TEST_ASSERT_TRUE(recovered.didSucceed());
    TEST_ASSERT_FLOAT_WITHIN(0.000001f, 0, recovered.angularRate[0].value());
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 3.8049802f, recovered.acceleration[1].value());
    initialize(adapter);
    enqueue(); const auto reset = adapter.measure();
    TEST_ASSERT_FLOAT_WITHIN(0.000001f, 0.030543262f, reset.angularRate[0].value());
}

static void test_calibration_capture_and_failures_use_real_samples()
{
    for (int outcome = 0; outcome < 4; ++outcome)
    {
        resetCase();
        Lsm6dsoAdapter adapter(testWire); initialize(adapter);
        Storage storage;
        storage.corrupt = outcome == 3;
        if (outcome == 1) device(0x6B).nack = failsBurstRead;
        else
            for (int n = 0; n < 200; ++n)
                enqueue(outcome == 2 && n == 199 ? sample({256, 1000, 0, 0, 0, 0, 4098}) : DEFAULT_SAMPLE);
        const auto result = adapter.calibrate(storage, delay);
        const ImuCalibrationResult expected[] = {ImuCalibrationResult::Captured, ImuCalibrationResult::ReadFailed,
            ImuCalibrationResult::MotionDetected, ImuCalibrationResult::VerificationFailed};
        TEST_ASSERT_EQUAL_INT(static_cast<int>(expected[outcome]), static_cast<int>(result));
        TEST_ASSERT_EQUAL_UINT(outcome == 1 ? 1 : 201, count("delay"));
        if (outcome == 0 || outcome == 3)
        {
            TEST_ASSERT_TRUE(storage.operations == std::vector<int>({0,1,2,0}));
            TEST_ASSERT_EQUAL_HEX8(0xC7, storage.record.magic);
            TEST_ASSERT_EQUAL_FLOAT(1.75f, storage.record.gyroBiasDegreesPerSecond[0]);
        }
        else TEST_ASSERT_TRUE(storage.operations == std::vector<int>({0}));
        if (outcome == 0)
        {
            enqueue(sample({256, 200, -200, 300, -1000, 2000, 4098}));
            const auto reading = adapter.measure();
            TEST_ASSERT_FLOAT_WITHIN(0.000001f, 0.030543262f, reading.angularRate[0].value());
            TEST_ASSERT_FLOAT_WITHIN(0.000001f, 0, reading.angularRate[1].value());
        }
    }
}

static void test_free_bus_recovery_order_and_same_call_read()
{
    Lsm6dsoAdapter adapter(testWire);
    failedMeasurement(adapter); failedMeasurement(adapter);
    TEST_ASSERT_TRUE(environment.events.empty());
    enqueue(); TEST_ASSERT_TRUE(adapter.measure().didSucceed());
    const Event prefix[] = {{"wire.end",0,0,0}, {"pinMode",20,2,0}, {"pinMode",21,2,0},
        {"pinMode",20,2,0}, {"digitalRead",20,1,0}, {"pinMode",20,2,0}, {"digitalRead",20,1,0},
        {"wire.begin",0,0,0}, {"wire.clock",100000,0,0}, {"wire.timeout",10000,1,0}};
    TEST_ASSERT_TRUE(environment.events.size() > 10);
    for (size_t i = 0; i < 10; ++i) TEST_ASSERT_TRUE(prefix[i] == environment.events[i]);
    TEST_ASSERT_EQUAL_UINT(0, count("digitalWrite"));
    TEST_ASSERT_EQUAL_UINT(1, count("sensor.identify"));
    TEST_ASSERT_EQUAL_UINT(2, count("wire.begin"));
}

static void test_retry_boundary_rollover_and_failed_reconfiguration()
{
    for (uint64_t start : {uint64_t(0), uint64_t(UINT32_MAX) - 499})
    {
        resetCase(); atMilliseconds(start);
        Lsm6dsoAdapter adapter(testWire);
        failWrite(2);
        failedMeasurement(adapter); failedMeasurement(adapter); failedMeasurement(adapter);
        TEST_ASSERT_EQUAL_UINT(1, count("sensor.identify"));
        device(0x6B).nack = nullptr;
        atMilliseconds(start + 999);
        for (int i = 0; i < 3; ++i) failedMeasurement(adapter);
        TEST_ASSERT_EQUAL_UINT(1, count("sensor.identify"));
        atMilliseconds(start + 1000); enqueue();
        TEST_ASSERT_TRUE(adapter.measure().didSucceed());
        TEST_ASSERT_EQUAL_UINT(2, count("sensor.identify"));
        // Success resets the failure qualification count.
        device(0x6B).nack = failsBurstRead; failedMeasurement(adapter);
        failedMeasurement(adapter);
        TEST_ASSERT_EQUAL_UINT(2, count("sensor.identify"));
        device(0x6B).nack = nullptr;
        atMilliseconds(start + 2000); enqueue();
        TEST_ASSERT_TRUE(adapter.measure().didSucceed());
    }
}

static void test_bus_clear_pulses_stop_and_restart()
{
    Lsm6dsoAdapter adapter(testWire);
    environment.sda = {0,0,0,1,1};
    failedMeasurement(adapter); failedMeasurement(adapter); enqueue();
    TEST_ASSERT_TRUE(adapter.measure().didSucceed());
    std::vector<Event> writes;
    for (const auto &event : environment.events)
        if (event.name == "digitalWrite" || event.name == "delayUs") writes.push_back(event);
    const std::vector<Event> expected = {{"digitalWrite",21,0,0}, {"delayUs",5,0,0}, {"delayUs",5,0,0},
        {"digitalWrite",21,0,0}, {"delayUs",5,0,0}, {"delayUs",5,0,0},
        {"digitalWrite",20,0,0}, {"delayUs",5,0,0}, {"delayUs",5,0,0}, {"delayUs",5,0,0}};
    TEST_ASSERT_TRUE(writes == expected);
    // GPIO sequencing after the final SDA check includes the open-drain STOP.
    const auto stop = std::find_if(environment.events.begin(), environment.events.end(),
        [](const Event &e) { return e.name == "digitalWrite" && e.a == 20; });
    TEST_ASSERT_TRUE(stop != environment.events.end());
    const Event sequence[] = {{"digitalWrite",20,0,0}, {"pinMode",20,1,0}, {"delayUs",5,0,0},
        {"pinMode",21,2,0}, {"delayUs",5,0,0}, {"pinMode",20,2,0}, {"delayUs",5,0,0}, {"wire.begin",0,0,0}};
    TEST_ASSERT_TRUE(environment.events.end() - stop >= 8);
    for (int i = 0; i < 8; ++i) TEST_ASSERT_TRUE(sequence[i] == stop[i]);
    TEST_ASSERT_EQUAL_UINT64(5035, environment.microseconds);
}

static void test_stuck_bus_latches_until_release()
{
    Lsm6dsoAdapter adapter(testWire); environment.sdaHigh = false;
    failedMeasurement(adapter); failedMeasurement(adapter); failedMeasurement(adapter);
    TEST_ASSERT_EQUAL_UINT(9, count("digitalWrite"));
    TEST_ASSERT_EQUAL_UINT(0, count("wire.begin"));
    TEST_ASSERT_EQUAL_UINT(0, count("sensor.identify"));
    atMilliseconds(1000); environment.events.clear();
    for (int i = 0; i < 3; ++i) failedMeasurement(adapter);
    TEST_ASSERT_EQUAL_UINT(0, count("digitalWrite"));
    TEST_ASSERT_EQUAL_UINT(0, count("wire.begin"));
    environment.sdaHigh = true; atMilliseconds(2000);
    failedMeasurement(adapter); failedMeasurement(adapter); enqueue();
    TEST_ASSERT_TRUE(adapter.measure().didSucceed());
    TEST_ASSERT_EQUAL_UINT(0, count("digitalWrite"));
    TEST_ASSERT_EQUAL_UINT(1, count("sensor.identify"));
}

static void test_explicit_initialize_resets_recovery_policy_and_latch()
{
    Lsm6dsoAdapter adapter(testWire); environment.sdaHigh = false;
    failedMeasurement(adapter); failedMeasurement(adapter); failedMeasurement(adapter);
    device(0x6B).present = false;
    TEST_ASSERT_EQUAL_INT(static_cast<int>(Lsm6dsoInitializationResult::NotDetected), static_cast<int>(adapter.initialize()));
    environment.events.clear();
    failedMeasurement(adapter); failedMeasurement(adapter); failedMeasurement(adapter);
    // The explicit initialize allows a fresh attempt even before the old retry interval.
    TEST_ASSERT_EQUAL_UINT(9, count("digitalWrite"));
}

static void test_bus_delay_has_one_microsecond_minimum()
{
    ArduinoI2cBus bus(testWire, 2000000, 10000);
    environment.events.clear();
    bus.halfBit();
    assertEvents({{"delayUs",1,0,0}});
    TEST_ASSERT_EQUAL_UINT64(1, environment.microseconds);
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_bus_delay_has_one_microsecond_minimum);
    RUN_TEST(test_initialization_and_address_fallback);
    RUN_TEST(test_driver_accepts_any_responding_device);
    RUN_TEST(test_absent_and_each_configuration_failure);
    RUN_TEST(test_burst_protocol_signed_samples_and_units);
    RUN_TEST(test_failed_transfer_and_every_short_read);
    RUN_TEST(test_zero_motion_checks_configuration_and_nonzero_motion_does_not);
    RUN_TEST(test_each_configuration_register_read_error);
    RUN_TEST(test_stored_calibration_applied_and_retained_during_recovery);
    RUN_TEST(test_calibration_capture_and_failures_use_real_samples);
    RUN_TEST(test_free_bus_recovery_order_and_same_call_read);
    RUN_TEST(test_retry_boundary_rollover_and_failed_reconfiguration);
    RUN_TEST(test_bus_clear_pulses_stop_and_restart);
    RUN_TEST(test_stuck_bus_latches_until_release);
    RUN_TEST(test_explicit_initialize_resets_recovery_policy_and_latch);
    return UNITY_END();
}
