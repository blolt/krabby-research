#pragma once
#include "Wire.h"

enum status_t { IMU_SUCCESS, IMU_HW_ERROR, IMU_NOT_SUPPORTED, IMU_OUT_OF_BOUNDS, IMU_ALL_ONES_WARNING, IMU_GENERIC_ERROR = 0xFF };
class LSM6DSO
{
public:
    bool begin(uint8_t address = 0x6B, TwoWire &wire = Wire);
    bool setIncrement(bool enabled = true);
    bool setAccelRange(uint8_t);
    bool setAccelDataRate(uint16_t);
    bool setGyroRange(uint16_t);
    bool setGyroDataRate(uint16_t);
    bool setBlockDataUpdate(bool);
    status_t readRegister(uint8_t *, uint8_t);
private:
    TwoWire *wire_ = nullptr;
    uint8_t address_ = 0;
    bool configure(unsigned index, const char *name, long value);
};
