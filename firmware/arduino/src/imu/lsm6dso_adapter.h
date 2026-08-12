#pragma once

#include <SparkFunLSM6DSO.h>
#include <Wire.h>
#include <stdint.h>

#include "../../byte_order.h"
#include "imu_calibrator.h"
#include "imu_constants.h"

enum class Lsm6dsoInitializationResult : uint8_t
{
    Ok,
    NotDetected,
    ConfigurationFailed,
};

class Lsm6dsoAdapter
{
public:
    Lsm6dsoAdapter()
        : calibrator_{},
          consecutiveBadReads_(0),
          initialized_(false),
          address_(0)
    {
    }

    Lsm6dsoInitializationResult initialize()
    {
        calibrator_ = ImuCalibrator{};
        consecutiveBadReads_ = 0;
        initialized_ = false;
        Wire.begin();
        Wire.setClock(I2C_DEFAULT_BUS_CLOCK_HZ);
        Wire.setWireTimeout(LSM6DSO_BUS_TIMEOUT_MICROSECONDS, true);

        address_ = LSM6DSO_PRIMARY_ADDRESS;
        if (!driver_.begin(address_))
        {
            address_ = LSM6DSO_ALTERNATE_ADDRESS;
            if (!driver_.begin(address_))
            {
                address_ = 0;
                return Lsm6dsoInitializationResult::NotDetected;
            }
        }

        const bool configured =
            driver_.setIncrement(LSM6DSO_AUTO_INCREMENT) &&
            driver_.setAccelRange(LSM6DSO_ACCELERATION_RANGE_G) &&
            driver_.setAccelDataRate(LSM6DSO_ACCELERATION_DATA_RATE_HZ) &&
            driver_.setGyroRange(LSM6DSO_ANGULAR_RATE_RANGE_DEGREES_PER_SECOND) &&
            driver_.setGyroDataRate(LSM6DSO_ANGULAR_RATE_DATA_RATE_HZ) &&
            driver_.setBlockDataUpdate(LSM6DSO_BLOCK_DATA_UPDATE);

        if (!configured)
        {
            address_ = 0;
            return Lsm6dsoInitializationResult::ConfigurationFailed;
        }

        delay(LSM6DSO_TURN_ON_TIME_MS);

        initialized_ = true;
        return Lsm6dsoInitializationResult::Ok;
    }

    template <typename Storage>
    ImuCalibrationResult calibrate(
        Storage &storage,
        void (*delayMilliseconds)(unsigned long))
    {
        return calibrator_.calibrate(
            [this]() { return readSensorMeasurement(); },
            storage,
            delayMilliseconds);
    }
    
    ImuMeasurement measure()
    {
        const ImuMeasurement bodyMeasurement = readSensorMeasurement();
        return calibrator_.applyImuCalibration(bodyMeasurement);
    }

private:
    ImuMeasurement readSensorMeasurement()
    {
        if (address_ == 0)
            return ImuMeasurement{false};

        Wire.beginTransmission(address_);
        if (Wire.write(LSM6DSO_OUTPUT_START_REGISTER) != 1)
            return ImuMeasurement{false};

        if (Wire.endTransmission(false) != 0)
            return ImuMeasurement{false};

        if (Wire.requestFrom(
                address_,
                LSM6DSO_NUM_SAMPLE_BYTES,
                static_cast<uint8_t>(true)) != LSM6DSO_NUM_SAMPLE_BYTES)
        {
            return ImuMeasurement{false};
        }

        uint8_t bytes[LSM6DSO_NUM_SAMPLE_BYTES];
        for (uint8_t index = 0; index < LSM6DSO_NUM_SAMPLE_BYTES; ++index)
        {
            if (Wire.available() <= 0)
                return ImuMeasurement{false};
            bytes[index] = static_cast<uint8_t>(Wire.read());
        }

        ImuMeasurement measurement{true};
        const int16_t rawTemperature = decodeInt16LittleEndian(&bytes[0]);
        measurement.temperature = Celsius(
            rawTemperature * LSM6DSO_TEMPERATURE_CELSIUS_PER_LSB +
            LSM6DSO_TEMPERATURE_OFFSET_CELSIUS);

        for (uint8_t axis = 0; axis < 3; ++axis)
        {
            const int16_t rawAngularRate =
                decodeInt16LittleEndian(&bytes[2 + axis * 2]);
            const int16_t rawAcceleration =
                decodeInt16LittleEndian(&bytes[8 + axis * 2]);

            measurement.angularRate[axis] = RadiansPerSecond(
                rawAngularRate * LSM6DSO_ANGULAR_RATE_RADIANS_PER_SECOND_PER_LSB);
            measurement.acceleration[axis] = MetersPerSecondSquared(
                rawAcceleration *
                LSM6DSO_ACCELERATION_METERS_PER_SECOND_SQUARED_PER_LSB);
        }

        if (!measurement.succeeded())
        {
            consecutiveBadReads_++;
        }

        if (consecutiveBadReads_ >= IMU_BAD_TICKS_BEFORE_INVALID)
        {
            initialized_ = false;
        }

        return transformImuMeasurementToBodyFrame(measurement);
    }

    LSM6DSO driver_;
    ImuCalibrator calibrator_;
    uint8_t consecutiveBadReads_;
    bool initialized_;
    uint8_t address_;
};
