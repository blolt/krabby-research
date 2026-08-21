#include <cstring>
#include <limits>
#include <stdexcept>
#include <vector>

#include "unity.h"

#include "src/power_bus/power_calibration_storage.h"

void setUp() {}
void tearDown() {}

static const int CALIBRATION_ADDRESS = 66;
static const size_t STORAGE_SIZE = 96;

struct FakeEeprom
{
    std::vector<uint8_t> bytes;
    std::vector<int> writtenAddresses;
    int failBeforeWrite;
    int writeCount;

    FakeEeprom()
        : bytes(STORAGE_SIZE, 0xff),
          failBeforeWrite(-1),
          writeCount(0)
    {
    }

    void writeByte(int address, uint8_t value)
    {
        if (writeCount == failBeforeWrite)
            throw std::runtime_error("simulated power interruption");
        bytes.at(static_cast<size_t>(address)) = value;
        writtenAddresses.push_back(address);
        ++writeCount;
    }

    template <typename Value>
    void put(int address, const Value& value)
    {
        const uint8_t* raw =
            reinterpret_cast<const uint8_t*>(&value);
        for (size_t index = 0; index < sizeof(Value); ++index)
            writeByte(address + static_cast<int>(index), raw[index]);
    }

    template <typename Value>
    void get(int address, Value& value)
    {
        std::memcpy(
            &value,
            &bytes.at(static_cast<size_t>(address)),
            sizeof(Value));
    }

    void update(int address, uint8_t value)
    {
        writeByte(address, value);
    }
};

static PowerCalibrationStorageRules rules()
{
    const PowerCalibrationStorageRules result = {
        0xc8, 1, 2.0f, 0.5f, 2.0f};
    return result;
}

static PowerCalibrationData calibration(
    float packOffset = -0.031f,
    float midpointOffset = 0.017f,
    float shuntScale = 1.013f)
{
    const PowerCalibrationData result = {
        0xc8, 1, packOffset, midpointOffset, shuntScale};
    return result;
}

static void assertCalibrationEqual(
    const PowerCalibrationData& expected,
    const PowerCalibrationData& actual)
{
    TEST_ASSERT_EQUAL_UINT8(expected.magic, actual.magic);
    TEST_ASSERT_EQUAL_UINT8(expected.schema, actual.schema);
    TEST_ASSERT_EQUAL_FLOAT(
        expected.packVoltageOffset, actual.packVoltageOffset);
    TEST_ASSERT_EQUAL_FLOAT(
        expected.midpointVoltageOffset, actual.midpointVoltageOffset);
    TEST_ASSERT_EQUAL_FLOAT(expected.packShuntCal, actual.packShuntCal);
}

static void assertIdentity(const PowerCalibrationData& actual)
{
    assertCalibrationEqual(identityPowerCalibration(), actual);
}

static void seed(FakeEeprom& storage, const PowerCalibrationData& value)
{
    std::memcpy(
        &storage.bytes.at(CALIBRATION_ADDRESS),
        &value,
        sizeof(value));
}

static void test_layout_is_exactly_fourteen_bytes()
{
    TEST_ASSERT_EQUAL_UINT32(14, sizeof(PowerCalibrationData));
}

static void test_valid_block_loads_exactly()
{
    FakeEeprom storage;
    const PowerCalibrationData expected = calibration();
    seed(storage, expected);
    PowerCalibrationData result = calibration(9.0f, 8.0f, 1.5f);

    TEST_ASSERT_TRUE(loadPowerCalibration(
        storage, CALIBRATION_ADDRESS, rules(), result));
    assertCalibrationEqual(expected, result);
}

static void test_invalid_header_and_erased_storage_fall_back_to_identity()
{
    PowerCalibrationData invalid[] = {
        calibration(),
        calibration()};
    invalid[0].magic = 0;
    invalid[1].schema = 2;

    for (size_t index = 0; index < 2; ++index)
    {
        FakeEeprom storage;
        seed(storage, invalid[index]);
        PowerCalibrationData result = calibration();
        TEST_ASSERT_FALSE(loadPowerCalibration(
            storage, CALIBRATION_ADDRESS, rules(), result));
        assertIdentity(result);
    }

    FakeEeprom erased;
    PowerCalibrationData result = calibration();
    TEST_ASSERT_FALSE(loadPowerCalibration(
        erased, CALIBRATION_ADDRESS, rules(), result));
    assertIdentity(result);
}

static void test_every_nonfinite_field_falls_back_to_identity()
{
    const float nonfinite[] = {
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity()};

    for (size_t valueIndex = 0; valueIndex < 3; ++valueIndex)
    {
        for (size_t fieldIndex = 0; fieldIndex < 3; ++fieldIndex)
        {
            PowerCalibrationData invalid = calibration();
            float* fields[] = {
                &invalid.packVoltageOffset,
                &invalid.midpointVoltageOffset,
                &invalid.packShuntCal};
            *fields[fieldIndex] = nonfinite[valueIndex];
            FakeEeprom storage;
            seed(storage, invalid);
            PowerCalibrationData result = calibration();
            TEST_ASSERT_FALSE(loadPowerCalibration(
                storage, CALIBRATION_ADDRESS, rules(), result));
            assertIdentity(result);
        }
    }
}

static void test_exact_bounds_load_and_just_outside_bounds_fall_back()
{
    const PowerCalibrationData accepted[] = {
        calibration(-2.0f, 2.0f, 0.5f),
        calibration(2.0f, -2.0f, 2.0f)};
    for (size_t index = 0; index < 2; ++index)
    {
        FakeEeprom storage;
        seed(storage, accepted[index]);
        PowerCalibrationData result = identityPowerCalibration();
        TEST_ASSERT_TRUE(loadPowerCalibration(
            storage, CALIBRATION_ADDRESS, rules(), result));
        assertCalibrationEqual(accepted[index], result);
    }

    const PowerCalibrationData rejected[] = {
        calibration(-2.001f, 0.0f, 1.0f),
        calibration(2.001f, 0.0f, 1.0f),
        calibration(0.0f, -2.001f, 1.0f),
        calibration(0.0f, 2.001f, 1.0f),
        calibration(0.0f, 0.0f, 0.499f),
        calibration(0.0f, 0.0f, 2.001f)};
    for (size_t index = 0;
         index < sizeof(rejected) / sizeof(rejected[0]);
         ++index)
    {
        FakeEeprom storage;
        seed(storage, rejected[index]);
        PowerCalibrationData result = calibration();
        TEST_ASSERT_FALSE(loadPowerCalibration(
            storage, CALIBRATION_ADDRESS, rules(), result));
        assertIdentity(result);
    }
}

static void test_invalid_rules_reject_the_block()
{
    PowerCalibrationStorageRules invalid[] = {
        {0xc8, 1, -1.0f, 0.5f, 2.0f},
        {0xc8, 1, std::numeric_limits<float>::infinity(), 0.5f, 2.0f},
        {0xc8, 1, 2.0f, 2.0f, 0.5f},
        {0xc8, 1, 2.0f, std::numeric_limits<float>::quiet_NaN(), 2.0f}};

    for (size_t index = 0; index < 4; ++index)
        TEST_ASSERT_FALSE(powerCalibrationIsPlausible(
            calibration(), invalid[index]));
}

static void test_identity_calibration_is_neutral_and_not_stored_valid()
{
    const PowerCalibrationData identity = identityPowerCalibration();
    TEST_ASSERT_FALSE(powerCalibrationIsPlausible(identity, rules()));

    const float voltage = 24.137f;
    const float current = -3.204f;
    TEST_ASSERT_EQUAL_FLOAT(
        voltage, voltage + identity.packVoltageOffset);
    TEST_ASSERT_EQUAL_FLOAT(
        voltage, voltage + identity.midpointVoltageOffset);
    TEST_ASSERT_EQUAL_FLOAT(
        current, current * identity.packShuntCal);
}

static void test_persist_uses_local_copy_and_valid_magic_is_last_write()
{
    FakeEeprom storage;
    PowerCalibrationData active = calibration();
    active.magic = 12;
    active.schema = 34;

    persistPowerCalibration(
        storage, CALIBRATION_ADDRESS, rules(), active);

    TEST_ASSERT_EQUAL_UINT32(
        sizeof(PowerCalibrationData) + 1,
        storage.writtenAddresses.size());
    TEST_ASSERT_EQUAL_INT(
        CALIBRATION_ADDRESS, storage.writtenAddresses.front());
    TEST_ASSERT_EQUAL_INT(
        CALIBRATION_ADDRESS, storage.writtenAddresses.back());
    TEST_ASSERT_EQUAL_UINT8(0xc8, storage.bytes[CALIBRATION_ADDRESS]);
    TEST_ASSERT_EQUAL_UINT8(0xc8, active.magic);
    TEST_ASSERT_EQUAL_UINT8(1, active.schema);

    PowerCalibrationData loaded = identityPowerCalibration();
    TEST_ASSERT_TRUE(loadPowerCalibration(
        storage, CALIBRATION_ADDRESS, rules(), loaded));
    assertCalibrationEqual(active, loaded);
}

static void test_persist_does_not_touch_neighboring_bytes()
{
    FakeEeprom storage;
    storage.bytes[CALIBRATION_ADDRESS - 1] = 0x5a;
    storage.bytes[
        CALIBRATION_ADDRESS + sizeof(PowerCalibrationData)] = 0xa5;
    PowerCalibrationData active = calibration();

    persistPowerCalibration(
        storage, CALIBRATION_ADDRESS, rules(), active);

    TEST_ASSERT_EQUAL_HEX8(0x5a, storage.bytes[CALIBRATION_ADDRESS - 1]);
    TEST_ASSERT_EQUAL_HEX8(
        0xa5,
        storage.bytes[
            CALIBRATION_ADDRESS + sizeof(PowerCalibrationData)]);
    for (size_t index = 0; index < storage.writtenAddresses.size(); ++index)
    {
        TEST_ASSERT_GREATER_OR_EQUAL(
            CALIBRATION_ADDRESS, storage.writtenAddresses[index]);
        TEST_ASSERT_LESS_THAN(
            CALIBRATION_ADDRESS + sizeof(PowerCalibrationData),
            storage.writtenAddresses[index]);
    }
}

static void test_every_interruption_after_invalidation_rejects_partial_overwrite()
{
    const PowerCalibrationData prior = calibration(-0.1f, 0.2f, 1.1f);
    const PowerCalibrationData replacement = calibration(0.3f, -0.4f, 0.9f);

    // Write zero writes the invalid magic. Every later interruption before the
    // final valid-magic update must make the mixed block unloadable.
    for (int failBeforeWrite = 1;
         failBeforeWrite <= static_cast<int>(sizeof(PowerCalibrationData));
         ++failBeforeWrite)
    {
        FakeEeprom storage;
        seed(storage, prior);
        storage.failBeforeWrite = failBeforeWrite;
        PowerCalibrationData active = replacement;
        bool interrupted = false;
        try
        {
            persistPowerCalibration(
                storage, CALIBRATION_ADDRESS, rules(), active);
        }
        catch (const std::runtime_error&)
        {
            interrupted = true;
        }
        TEST_ASSERT_TRUE(interrupted);
        assertCalibrationEqual(replacement, active);

        PowerCalibrationData loaded = calibration();
        TEST_ASSERT_FALSE(loadPowerCalibration(
            storage, CALIBRATION_ADDRESS, rules(), loaded));
        assertIdentity(loaded);
    }
}

static void test_interruption_before_first_write_preserves_prior_valid_block()
{
    FakeEeprom storage;
    const PowerCalibrationData prior = calibration(-0.1f, 0.2f, 1.1f);
    seed(storage, prior);
    storage.failBeforeWrite = 0;
    PowerCalibrationData active = calibration(0.3f, -0.4f, 0.9f);

    try
    {
        persistPowerCalibration(
            storage, CALIBRATION_ADDRESS, rules(), active);
        TEST_FAIL_MESSAGE("expected simulated interruption");
    }
    catch (const std::runtime_error&)
    {
    }

    PowerCalibrationData loaded = identityPowerCalibration();
    TEST_ASSERT_TRUE(loadPowerCalibration(
        storage, CALIBRATION_ADDRESS, rules(), loaded));
    assertCalibrationEqual(prior, loaded);
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_layout_is_exactly_fourteen_bytes);
    RUN_TEST(test_valid_block_loads_exactly);
    RUN_TEST(test_invalid_header_and_erased_storage_fall_back_to_identity);
    RUN_TEST(test_every_nonfinite_field_falls_back_to_identity);
    RUN_TEST(test_exact_bounds_load_and_just_outside_bounds_fall_back);
    RUN_TEST(test_invalid_rules_reject_the_block);
    RUN_TEST(test_identity_calibration_is_neutral_and_not_stored_valid);
    RUN_TEST(test_persist_uses_local_copy_and_valid_magic_is_last_write);
    RUN_TEST(test_persist_does_not_touch_neighboring_bytes);
    RUN_TEST(test_every_interruption_after_invalidation_rejects_partial_overwrite);
    RUN_TEST(test_interruption_before_first_write_preserves_prior_valid_block);
    return UNITY_END();
}
