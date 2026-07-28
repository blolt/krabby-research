#pragma once

#include <stdint.h>

template <typename Lsm6dso>
bool configureLsm6dso(
    Lsm6dso &device,
    bool autoIncrement,
    uint8_t accelRangeG,
    uint16_t accelDataRateHz,
    uint16_t gyroRangeDps,
    uint16_t gyroDataRateHz,
    bool blockDataUpdate)
{
    // Preserve the register-write order recommended by the library's default
    // setup, but retain each result instead of silently discarding failures.
    if (!device.setIncrement(autoIncrement)) return false;
    if (!device.setAccelRange(accelRangeG)) return false;
    if (!device.setAccelDataRate(accelDataRateHz)) return false;
    if (!device.setGyroRange(gyroRangeDps)) return false;
    if (!device.setGyroDataRate(gyroDataRateHz)) return false;
    if (!device.setBlockDataUpdate(blockDataUpdate)) return false;
    return true;
}

// Hardware-boundary contract for IMU startup. The concrete Arduino adapter
// supplies begin() and configure(); keeping the decision logic here makes every
// address/configuration failure path testable without an I2C bus.
enum ImuInitResult
{
    IMU_INIT_OK,
    IMU_INIT_NOT_DETECTED,
    IMU_INIT_CONFIGURATION_FAILED
};

template <typename ImuDevice>
ImuInitResult initializeImu(
    ImuDevice &device,
    uint8_t primaryAddress,
    uint8_t alternateAddress,
    uint8_t &selectedAddress)
{
    uint8_t detectedAddress = primaryAddress;
    if (!device.begin(detectedAddress))
    {
        detectedAddress = alternateAddress;
        if (!device.begin(detectedAddress))
            return IMU_INIT_NOT_DETECTED;
    }

    // A device that answers WHO_AM_I but rejects configuration is unhealthy.
    // Do not probe the alternate address: it cannot be the same responding
    // sensor, and doing so would hide the register-write failure.
    if (!device.configure())
        return IMU_INIT_CONFIGURATION_FAILED;

    // Do not expose an address until initialization is wholly successful.
    selectedAddress = detectedAddress;
    return IMU_INIT_OK;
}
