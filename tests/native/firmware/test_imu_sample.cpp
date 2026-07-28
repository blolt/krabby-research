#include <math.h>
#include <stdint.h>

#include <vector>

#include "imu_sample.h"
#include "sensors_config.h"
#include "unity.h"

struct FakeWire {
    uint8_t writeCount = 1;
    uint8_t transmissionResult = 0;
    uint8_t requestResult = LSM6DSO_OUTPUT_SAMPLE_BYTES;
    int availableBytes = LSM6DSO_OUTPUT_SAMPLE_BYTES;
    std::vector<uint8_t> payload;
    std::vector<int> calls;
    unsigned int readIndex = 0;

    void beginTransmission(uint8_t address) {
        calls.push_back(0x100 + address);
    }
    uint8_t write(uint8_t value) {
        calls.push_back(0x200 + value);
        return writeCount;
    }
    uint8_t endTransmission(bool sendStop) {
        TEST_ASSERT_FALSE(sendStop);
        calls.push_back(0x300);
        return transmissionResult;
    }
    uint8_t requestFrom(uint8_t address, uint8_t length, uint8_t sendStop) {
        TEST_ASSERT_EQUAL_HEX8(0x6B, address);
        TEST_ASSERT_EQUAL_UINT8(LSM6DSO_OUTPUT_SAMPLE_BYTES, length);
        TEST_ASSERT_TRUE(sendStop);
        calls.push_back(0x400 + length);
        return requestResult;
    }
    int available() {
        return availableBytes - static_cast<int>(readIndex);
    }
    int read() {
        TEST_ASSERT_LESS_THAN_UINT(payload.size(), readIndex);
        calls.push_back(0x500);
        return payload[readIndex++];
    }
};

void setUp() {}
void tearDown() {}

static void appendInt16(std::vector<uint8_t> &bytes, int16_t value) {
    const uint16_t bits = static_cast<uint16_t>(value);
    bytes.push_back(static_cast<uint8_t>(bits & 0xFF));
    bytes.push_back(static_cast<uint8_t>(bits >> 8));
}

static FakeWire completeWire() {
    FakeWire wire;
    appendInt16(wire.payload, -32768);
    appendInt16(wire.payload, -32768);
    appendInt16(wire.payload, -1);
    appendInt16(wire.payload, 32767);
    appendInt16(wire.payload, 0);
    appendInt16(wire.payload, 1);
    appendInt16(wire.payload, 32767);
    return wire;
}

static Lsm6dsoOutputSample sentinelSample() {
    return {1234, {1234, 1234, 1234}, {1234, 1234, 1234}};
}

static void assertUnchanged(const Lsm6dsoOutputSample &sample) {
    TEST_ASSERT_EQUAL_INT16(1234, sample.temperature);
    for (int axis = 0; axis < 3; ++axis) {
        TEST_ASSERT_EQUAL_INT16(1234, sample.gyro[axis]);
        TEST_ASSERT_EQUAL_INT16(1234, sample.accel[axis]);
    }
}

static void test_constants_and_complete_sample_decode() {
    TEST_ASSERT_EQUAL_HEX8(0x20, LSM6DSO_OUTPUT_START_REGISTER);
    TEST_ASSERT_EQUAL_UINT8(14, LSM6DSO_OUTPUT_SAMPLE_BYTES);

    FakeWire wire = completeWire();
    Lsm6dsoOutputSample sample = {};
    TEST_ASSERT_TRUE(readLsm6dsoOutputSample(wire, 0x6B, sample));
    TEST_ASSERT_EQUAL_INT16(-32768, sample.temperature);
    TEST_ASSERT_EQUAL_INT16(-32768, sample.gyro[0]);
    TEST_ASSERT_EQUAL_INT16(-1, sample.gyro[1]);
    TEST_ASSERT_EQUAL_INT16(32767, sample.gyro[2]);
    TEST_ASSERT_EQUAL_INT16(0, sample.accel[0]);
    TEST_ASSERT_EQUAL_INT16(1, sample.accel[1]);
    TEST_ASSERT_EQUAL_INT16(32767, sample.accel[2]);
    TEST_ASSERT_EQUAL_UINT(LSM6DSO_OUTPUT_SAMPLE_BYTES, wire.readIndex);
    TEST_ASSERT_EQUAL_INT(0x100 + 0x6B, wire.calls[0]);
    TEST_ASSERT_EQUAL_INT(
        0x200 + LSM6DSO_OUTPUT_START_REGISTER, wire.calls[1]
    );
    TEST_ASSERT_EQUAL_INT(0x300, wire.calls[2]);
    TEST_ASSERT_EQUAL_INT(
        0x400 + LSM6DSO_OUTPUT_SAMPLE_BYTES, wire.calls[3]
    );
}

static void test_scaling_constants() {
    TEST_ASSERT_FLOAT_WITHIN(
        1e-9f, 0.000244f, LSM6DSO_ACCEL_G_PER_LSB
    );
    TEST_ASSERT_FLOAT_WITHIN(
        1e-7f, -0.0175f, -LSM6DSO_GYRO_DPS_PER_LSB
    );
    TEST_ASSERT_FLOAT_WITHIN(
        1e-7f, 25.0f, LSM6DSO_TEMP_OFFSET_C
    );
    TEST_ASSERT_FLOAT_WITHIN(
        1e-7f,
        26.0f,
        256 * LSM6DSO_TEMP_C_PER_LSB + LSM6DSO_TEMP_OFFSET_C
    );
    TEST_ASSERT_FLOAT_WITHIN(
        1e-7f,
        24.0f,
        -256 * LSM6DSO_TEMP_C_PER_LSB + LSM6DSO_TEMP_OFFSET_C
    );
}

static void test_failed_register_write_preserves_prior_sample() {
    FakeWire wire = completeWire();
    wire.writeCount = 0;
    Lsm6dsoOutputSample sample = sentinelSample();
    TEST_ASSERT_FALSE(readLsm6dsoOutputSample(wire, 0x6B, sample));
    assertUnchanged(sample);
    TEST_ASSERT_EQUAL_UINT(2, wire.calls.size());
}

static void test_every_end_transmission_error_preserves_prior_sample() {
    for (uint8_t error = 1; error <= 5; ++error) {
        FakeWire wire = completeWire();
        wire.transmissionResult = error;
        Lsm6dsoOutputSample sample = sentinelSample();
        TEST_ASSERT_FALSE(readLsm6dsoOutputSample(wire, 0x6B, sample));
        assertUnchanged(sample);
        TEST_ASSERT_EQUAL_UINT(3, wire.calls.size());
    }
}

static void test_every_short_request_preserves_prior_sample() {
    for (uint8_t length = 0;
         length < LSM6DSO_OUTPUT_SAMPLE_BYTES;
         ++length) {
        FakeWire wire = completeWire();
        wire.requestResult = length;
        Lsm6dsoOutputSample sample = sentinelSample();
        TEST_ASSERT_FALSE(readLsm6dsoOutputSample(wire, 0x6B, sample));
        assertUnchanged(sample);
        TEST_ASSERT_EQUAL_UINT(0, wire.readIndex);
    }
}

static void test_every_short_available_read_preserves_prior_sample() {
    for (int available = 0;
         available < LSM6DSO_OUTPUT_SAMPLE_BYTES;
         ++available) {
        FakeWire wire = completeWire();
        wire.availableBytes = available;
        Lsm6dsoOutputSample sample = sentinelSample();
        TEST_ASSERT_FALSE(readLsm6dsoOutputSample(wire, 0x6B, sample));
        assertUnchanged(sample);
        TEST_ASSERT_EQUAL_INT(available, wire.readIndex);
    }
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_constants_and_complete_sample_decode);
    RUN_TEST(test_scaling_constants);
    RUN_TEST(test_failed_register_write_preserves_prior_sample);
    RUN_TEST(test_every_end_transmission_error_preserves_prior_sample);
    RUN_TEST(test_every_short_request_preserves_prior_sample);
    RUN_TEST(test_every_short_available_read_preserves_prior_sample);
    return UNITY_END();
}
