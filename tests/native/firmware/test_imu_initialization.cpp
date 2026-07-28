#include <stdint.h>

#include <vector>

#include "imu_init.h"
#include "unity.h"

struct FakeImu {
    bool primaryResult;
    bool alternateResult;
    bool configureResult;
    uint8_t primaryAddress;
    uint8_t alternateAddress;
    std::vector<int> calls;

    bool begin(uint8_t address) {
        calls.push_back(address);
        if (address == primaryAddress) return primaryResult;
        if (address == alternateAddress) return alternateResult;
        TEST_FAIL_MESSAGE("unexpected IMU address");
        return false;
    }

    bool configure() {
        calls.push_back(0x100);
        return configureResult;
    }
};

struct FakeRegisters {
    int failAt;
    std::vector<int> calls;

    bool record(int call) {
        calls.push_back(call);
        return static_cast<int>(calls.size()) != failAt;
    }
    bool setIncrement(bool value) {
        TEST_ASSERT_TRUE(value);
        return record(1);
    }
    bool setAccelRange(uint8_t value) {
        TEST_ASSERT_EQUAL_UINT8(8, value);
        return record(2);
    }
    bool setAccelDataRate(uint16_t value) {
        TEST_ASSERT_EQUAL_UINT16(416, value);
        return record(3);
    }
    bool setGyroRange(uint16_t value) {
        TEST_ASSERT_EQUAL_UINT16(500, value);
        return record(4);
    }
    bool setGyroDataRate(uint16_t value) {
        TEST_ASSERT_EQUAL_UINT16(416, value);
        return record(5);
    }
    bool setBlockDataUpdate(bool value) {
        TEST_ASSERT_TRUE(value);
        return record(6);
    }
};

void setUp() {}
void tearDown() {}

static void assertCalls(
    const FakeImu &imu,
    const std::vector<int> &expected
) {
    TEST_ASSERT_EQUAL_UINT(expected.size(), imu.calls.size());
    for (size_t index = 0; index < expected.size(); ++index) {
        TEST_ASSERT_EQUAL_INT(expected[index], imu.calls[index]);
    }
}

static void test_primary_address_initializes_and_configures() {
    const uint8_t primary = 0x6B;
    FakeImu imu{true, false, true, primary, 0x6A, {}};
    uint8_t selected = 0x55;

    TEST_ASSERT_EQUAL(
        IMU_INIT_OK,
        initializeImu(imu, primary, 0x6A, selected)
    );
    TEST_ASSERT_EQUAL_HEX8(primary, selected);
    assertCalls(imu, {primary, 0x100});
}

static void test_alternate_address_initializes_after_primary_fails() {
    const uint8_t primary = 0x6B;
    const uint8_t alternate = 0x6A;
    FakeImu imu{false, true, true, primary, alternate, {}};
    uint8_t selected = 0x55;

    TEST_ASSERT_EQUAL(
        IMU_INIT_OK,
        initializeImu(imu, primary, alternate, selected)
    );
    TEST_ASSERT_EQUAL_HEX8(alternate, selected);
    assertCalls(imu, {primary, alternate, 0x100});
}

static void test_missing_imu_preserves_selected_address() {
    const uint8_t sentinel = 0x55;
    FakeImu imu{false, false, true, 0x6B, 0x6A, {}};
    uint8_t selected = sentinel;

    TEST_ASSERT_EQUAL(
        IMU_INIT_NOT_DETECTED,
        initializeImu(imu, 0x6B, 0x6A, selected)
    );
    TEST_ASSERT_EQUAL_HEX8(sentinel, selected);
    assertCalls(imu, {0x6B, 0x6A});
}

static void test_primary_configuration_failure_preserves_address() {
    const uint8_t sentinel = 0x55;
    FakeImu imu{true, true, false, 0x6B, 0x6A, {}};
    uint8_t selected = sentinel;

    TEST_ASSERT_EQUAL(
        IMU_INIT_CONFIGURATION_FAILED,
        initializeImu(imu, 0x6B, 0x6A, selected)
    );
    TEST_ASSERT_EQUAL_HEX8(sentinel, selected);
    assertCalls(imu, {0x6B, 0x100});
}

static void test_alternate_configuration_failure_preserves_address() {
    const uint8_t sentinel = 0x55;
    FakeImu imu{false, true, false, 0x6B, 0x6A, {}};
    uint8_t selected = sentinel;

    TEST_ASSERT_EQUAL(
        IMU_INIT_CONFIGURATION_FAILED,
        initializeImu(imu, 0x6B, 0x6A, selected)
    );
    TEST_ASSERT_EQUAL_HEX8(sentinel, selected);
    assertCalls(imu, {0x6B, 0x6A, 0x100});
}

static void test_each_register_configuration_failure_stops_immediately() {
    for (int failAt = 0; failAt <= 6; ++failAt) {
        FakeRegisters registers{failAt, {}};
        const bool result = configureLsm6dso(
            registers, true, 8, 416, 500, 416, true
        );
        TEST_ASSERT_EQUAL(failAt == 0, result);

        const int expectedCalls = failAt == 0 ? 6 : failAt;
        TEST_ASSERT_EQUAL_INT(expectedCalls, registers.calls.size());
        for (int index = 0; index < expectedCalls; ++index) {
            TEST_ASSERT_EQUAL_INT(index + 1, registers.calls[index]);
        }
    }
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_primary_address_initializes_and_configures);
    RUN_TEST(test_alternate_address_initializes_after_primary_fails);
    RUN_TEST(test_missing_imu_preserves_selected_address);
    RUN_TEST(test_primary_configuration_failure_preserves_address);
    RUN_TEST(test_alternate_configuration_failure_preserves_address);
    RUN_TEST(test_each_register_configuration_failure_stops_immediately);
    return UNITY_END();
}
