#pragma once

#include <stdint.h>

const uint8_t LSM6DSO_OUTPUT_START_REGISTER = 0x20;
const uint8_t LSM6DSO_OUTPUT_SAMPLE_BYTES = 14;

struct Lsm6dsoOutputSample
{
    int16_t temperature;
    int16_t gyro[3];
    int16_t accel[3];
};

static int16_t decodeLsm6dsoInt16(const uint8_t *bytes)
{
    return static_cast<int16_t>(
        static_cast<uint16_t>(bytes[0]) |
        (static_cast<uint16_t>(bytes[1]) << 8));
}

static void decodeLsm6dsoOutputSample(
    const uint8_t (&bytes)[LSM6DSO_OUTPUT_SAMPLE_BYTES],
    Lsm6dsoOutputSample &sample)
{
    sample.temperature = decodeLsm6dsoInt16(&bytes[0]);
    for (uint8_t axis = 0; axis < 3; ++axis)
    {
        sample.gyro[axis] = decodeLsm6dsoInt16(&bytes[2 + axis * 2]);
        sample.accel[axis] = decodeLsm6dsoInt16(&bytes[8 + axis * 2]);
    }
}

// Read the contiguous OUT_TEMP_L..OUTZ_H_A register block as one sample.
// Decode only after all 14 bytes arrive, so callers can never observe a
// partially updated sample after an I2C failure.
template <typename WireBus>
bool readLsm6dsoOutputSample(
    WireBus &wire,
    uint8_t address,
    Lsm6dsoOutputSample &sample)
{
    wire.beginTransmission(address);
    if (wire.write(LSM6DSO_OUTPUT_START_REGISTER) != 1)
        return false;
    if (wire.endTransmission(false) != 0)
        return false;

    const uint8_t received = wire.requestFrom(
        address,
        LSM6DSO_OUTPUT_SAMPLE_BYTES,
        static_cast<uint8_t>(true));
    if (received != LSM6DSO_OUTPUT_SAMPLE_BYTES)
        return false;

    uint8_t bytes[LSM6DSO_OUTPUT_SAMPLE_BYTES];
    for (uint8_t index = 0; index < LSM6DSO_OUTPUT_SAMPLE_BYTES; ++index)
    {
        if (wire.available() <= 0)
            return false;
        bytes[index] = static_cast<uint8_t>(wire.read());
    }

    decodeLsm6dsoOutputSample(bytes, sample);
    return true;
}
