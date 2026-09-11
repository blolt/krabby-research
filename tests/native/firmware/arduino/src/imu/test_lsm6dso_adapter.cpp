#include "unity.h"
#include <algorithm>
#include <initializer_list>
#include "environment.h"
#include "src/imu/lsm6dso_adapter.h"

using namespace imu_native;

static TwoWire testWire(environment.bus);

static void checkScript()
{
    TEST_ASSERT_TRUE(Wire.state().events.empty());
    TEST_ASSERT_TRUE(Wire.state().errors.empty());
    if (!environment.bus.errors.empty()) TEST_FAIL_MESSAGE(environment.bus.errors.front().c_str());
    if (!environment.errors.empty()) TEST_FAIL_MESSAGE(environment.errors.front().c_str());
    TEST_ASSERT_TRUE(environment.bus.transfers.empty());
    TEST_ASSERT_TRUE(environment.sda.empty());
}
static void resetCase()
{
    checkScript();
    imu_native::reset();
    environment.devices[0x6B].present = true;
    environment.devices[0x6A].present = false;
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
static Transfer sample(std::initializer_list<int16_t> words = {256, 100, -200, 300, -1000, 2000, 4098})
{
    Transfer transfer;
    transfer.address = 0x6B;
    transfer.reported = 14;
    for (int16_t word : words)
    {
        transfer.bytes.push_back(static_cast<uint16_t>(word) & 255);
        transfer.bytes.push_back(static_cast<uint16_t>(word) >> 8);
    }
    return transfer;
}
static void enqueue(const Transfer &transfer = sample()) { environment.bus.transfers.push_back(transfer); }
static void initialize(Lsm6dsoAdapter &adapter)
{
    TEST_ASSERT_EQUAL_INT(static_cast<int>(Lsm6dsoInitializationResult::Ok), static_cast<int>(adapter.initialize()));
}
static void validRegisters(uint8_t address = 0x6B)
{
    auto &registers = environment.devices[address].registers;
    registers[0x10].value = 0x6C;
    registers[0x11].value = 0x64;
    registers[0x12].value = 0x44;
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
        {"sensor.begin",0x6B,0,0}, {"increment",1,0,0}, {"accelRange",8,0,0},
        {"accelRate",416,0,0}, {"gyroRange",500,0,0}, {"gyroRate",416,0,0},
        {"blockUpdate",1,0,0}, {"delay",5,0,0}});
    TEST_ASSERT_EQUAL_UINT32(5, millis());
    resetCase();
    environment.devices[0x6B].present = false;
    environment.devices[0x6A].present = true;
    initialize(adapter);
    TEST_ASSERT_EQUAL_UINT(2, count("sensor.begin"));
    TEST_ASSERT_EQUAL_INT(0x6B, environment.events[3].a);
    TEST_ASSERT_EQUAL_INT(0x6A, environment.events[4].a);
    Transfer transfer = sample(); transfer.address = 0x6A; enqueue(transfer);
    TEST_ASSERT_TRUE(adapter.measure().didSucceed());
}

static void test_absent_and_each_configuration_failure()
{
    for (int failure = -1; failure < 6; ++failure)
    {
        resetCase();
        Lsm6dsoAdapter adapter(testWire);
        if (failure == -1) environment.devices[0x6B].present = false;
        else environment.devices[0x6B].configuration[failure] = false;
        TEST_ASSERT_EQUAL_INT(static_cast<int>(failure == -1 ? Lsm6dsoInitializationResult::NotDetected :
            Lsm6dsoInitializationResult::ConfigurationFailed), static_cast<int>(adapter.initialize()));
        TEST_ASSERT_EQUAL_UINT(failure == -1 ? 5 : 5 + failure, environment.events.size());
        TEST_ASSERT_EQUAL_UINT(0, count("delay"));
        Storage storage;
        TEST_ASSERT_EQUAL_INT(static_cast<int>(ImuCalibrationResult::ReadFailed),
            static_cast<int>(adapter.calibrate(storage, delay)));
        TEST_ASSERT_EQUAL_UINT(0, count("wire.transmit"));
    }
}

static void test_burst_protocol_signed_samples_and_units()
{
    Lsm6dsoAdapter adapter(testWire); initialize(adapter);
    environment.events.clear();
    // Explicit little-endian bytes, distinct across all seven channels.
    Transfer transfer;
    transfer.address = 0x6B;
    transfer.reported = 14;
    transfer.bytes = {0x00,0xFF, 0x64,0x00, 0x38,0xFF, 0x2C,0x01,
                      0x18,0xFC, 0xD0,0x07, 0x02,0x10};
    enqueue(transfer);
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
    const Event prefix[] = {{"wire.transmit",0x6B,0,0}, {"wire.write",0x20,0,0},
        {"wire.endTransmission",0,0,0}, {"wire.request",0x6B,14,1}};
    TEST_ASSERT_EQUAL_UINT(18, environment.events.size());
    for (size_t i = 0; i < 4; ++i) TEST_ASSERT_TRUE(prefix[i] == environment.events[i]);
    TEST_ASSERT_EQUAL_UINT(14, count("wire.read"));
    TEST_ASSERT_EQUAL_UINT(0, count("sensor.register"));
    enqueue(sample({-32768,-32768,32767,-1,32767,-32768,1}));
    const auto extreme = adapter.measure();
    TEST_ASSERT_EQUAL_FLOAT(-103.0f, extreme.temperature.value());
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, -10.008421f, extreme.angularRate[0].value());
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, -78.408011f, extreme.acceleration[1].value());
}

static void test_failed_transfer_and_every_truncated_buffer()
{
    for (int kind = 0; kind < 4; ++kind)
        for (int n = 0; n < (kind >= 2 ? 14 : 1); ++n)
        {
            resetCase();
            Lsm6dsoAdapter adapter(testWire); initialize(adapter);
            environment.events.clear();
            Transfer transfer = sample();
            if (kind == 0) transfer.written = 0;
            if (kind == 1) transfer.status = 2;
            if (kind == 2) transfer.reported = n;
            if (kind == 3) transfer.bytes.resize(n);
            enqueue(transfer); failedMeasurement(adapter);
            TEST_ASSERT_EQUAL_UINT(kind == 3 ? n : 0, count("wire.read"));
            TEST_ASSERT_EQUAL_UINT(kind == 0 ? 0 : 1, count("wire.endTransmission"));
            TEST_ASSERT_EQUAL_UINT(kind < 2 ? 0 : 1, count("wire.request"));
            TEST_ASSERT_EQUAL_UINT(0, count("sensor.register"));
            // A failed read makes the next call wait for recovery, not read again.
            failedMeasurement(adapter);
            TEST_ASSERT_EQUAL_UINT(1, count("wire.transmit"));
        }
}

static void test_zero_motion_checks_configuration_and_nonzero_motion_does_not()
{
    for (int channel = 0; channel < 6; ++channel)
    {
        resetCase();
        Lsm6dsoAdapter adapter(testWire); initialize(adapter);
        Transfer transfer = sample({0,0,0,0,0,0,0});
        transfer.bytes[2 + channel * 2] = 1;
        enqueue(transfer); TEST_ASSERT_TRUE(adapter.measure().didSucceed());
        TEST_ASSERT_EQUAL_UINT(0, count("sensor.register"));
    }
    for (int reg = 0; reg < 3; ++reg)
        for (int bit = 0; bit < 8; ++bit)
        {
            resetCase();
            Lsm6dsoAdapter adapter(testWire); initialize(adapter); validRegisters();
            const uint8_t masks[] = {0xFC, 0xFE, 0x44};
            environment.devices[0x6B].registers[0x10 + reg].value ^= 1 << bit;
            enqueue(sample({256,0,0,0,0,0,0}));
            TEST_ASSERT_EQUAL_INT((masks[reg] & (1 << bit)) == 0, adapter.measure().didSucceed());
            TEST_ASSERT_EQUAL_UINT(3, count("sensor.register"));
        }
    resetCase();
    Lsm6dsoAdapter adapter(testWire); initialize(adapter); validRegisters();
    enqueue(sample({0,0,0,0,0,0,0}));
    TEST_ASSERT_TRUE(adapter.measure().didSucceed());
}

static void test_each_configuration_register_read_error()
{
    for (int reg = 0; reg < 3; ++reg)
    {
        resetCase();
        Lsm6dsoAdapter adapter(testWire); initialize(adapter); validRegisters();
        environment.devices[0x6B].registers[0x10 + reg].status = IMU_HW_ERROR;
        enqueue(sample({0,0,0,0,0,0,0})); failedMeasurement(adapter);
        TEST_ASSERT_EQUAL_UINT(reg + 1, count("sensor.register"));
    }
}

static void test_stored_calibration_applied_and_retained_during_recovery()
{
    Lsm6dsoAdapter adapter(testWire); initialize(adapter);
    Storage storage = storedCalibration();
    TEST_ASSERT_EQUAL_INT(static_cast<int>(ImuCalibrationResult::Loaded), static_cast<int>(adapter.calibrate(storage, delay)));
    TEST_ASSERT_EQUAL_UINT(1, storage.operations.size());
    TEST_ASSERT_EQUAL_UINT(0, count("wire.transmit"));
    enqueue(); const auto reading = adapter.measure();
    TEST_ASSERT_FLOAT_WITHIN(0.000001f, 0, reading.angularRate[0].value());
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 3.8049802f, reading.acceleration[1].value());
    Transfer failure = sample(); failure.status = 2; enqueue(failure); failedMeasurement(adapter);
    failedMeasurement(adapter);
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
        if (outcome == 1)
        {
            Transfer failure = sample(); failure.status = 2; enqueue(failure);
        }
        else
            for (int n = 0; n < 200; ++n)
                enqueue(outcome == 2 && n == 199 ? sample({256,1000,0,0,0,0,4098}) : sample());
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
            enqueue(sample({256,200,-200,300,-1000,2000,4098}));
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
    TEST_ASSERT_EQUAL_UINT(1, count("sensor.begin"));
    TEST_ASSERT_EQUAL_UINT(2, count("wire.begin"));
}

static void test_retry_boundary_rollover_and_failed_reconfiguration()
{
    for (uint64_t start : {uint64_t(0), uint64_t(UINT32_MAX) - 499})
    {
        resetCase(); atMilliseconds(start);
        Lsm6dsoAdapter adapter(testWire);
        environment.devices[0x6B].configuration[2] = false;
        failedMeasurement(adapter); failedMeasurement(adapter); failedMeasurement(adapter);
        TEST_ASSERT_EQUAL_UINT(1, count("sensor.begin"));
        environment.devices[0x6B].configuration[2] = true;
        atMilliseconds(start + 999);
        for (int i = 0; i < 3; ++i) failedMeasurement(adapter);
        TEST_ASSERT_EQUAL_UINT(1, count("sensor.begin"));
        atMilliseconds(start + 1000); enqueue();
        TEST_ASSERT_TRUE(adapter.measure().didSucceed());
        TEST_ASSERT_EQUAL_UINT(2, count("sensor.begin"));
        // Success resets the failure qualification count.
        Transfer failure = sample(); failure.status = 2; enqueue(failure); failedMeasurement(adapter);
        failedMeasurement(adapter);
        TEST_ASSERT_EQUAL_UINT(2, count("sensor.begin"));
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
    TEST_ASSERT_EQUAL_UINT(0, count("sensor.begin"));
    atMilliseconds(1000); environment.events.clear();
    for (int i = 0; i < 3; ++i) failedMeasurement(adapter);
    TEST_ASSERT_EQUAL_UINT(0, count("digitalWrite"));
    TEST_ASSERT_EQUAL_UINT(0, count("wire.begin"));
    environment.sdaHigh = true; atMilliseconds(2000);
    failedMeasurement(adapter); failedMeasurement(adapter); enqueue();
    TEST_ASSERT_TRUE(adapter.measure().didSucceed());
    TEST_ASSERT_EQUAL_UINT(0, count("digitalWrite"));
    TEST_ASSERT_EQUAL_UINT(1, count("sensor.begin"));
}

static void test_explicit_initialize_resets_recovery_policy_and_latch()
{
    Lsm6dsoAdapter adapter(testWire); environment.sdaHigh = false;
    failedMeasurement(adapter); failedMeasurement(adapter); failedMeasurement(adapter);
    environment.devices[0x6B].present = false;
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
    RUN_TEST(test_absent_and_each_configuration_failure);
    RUN_TEST(test_burst_protocol_signed_samples_and_units);
    RUN_TEST(test_failed_transfer_and_every_truncated_buffer);
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
