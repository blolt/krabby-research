#pragma once

#include <math.h>
#include <stddef.h>
#include <stdint.h>

#pragma pack(push, 1)
struct PowerCalibrationData
{
    uint8_t magic;
    uint8_t schema;
    float packVoltageOffset;
    float midpointVoltageOffset;
    float packShuntCal;
};
#pragma pack(pop)

static_assert(sizeof(PowerCalibrationData) == 14,
              "power-calibration EEPROM layout must remain 14 bytes");

struct PowerCalibrationStorageRules
{
    uint8_t magic;
    uint8_t schema;
    float maximumVoltageOffsetMagnitude;
    float minimumShuntScale;
    float maximumShuntScale;
};

inline PowerCalibrationData identityPowerCalibration()
{
    const PowerCalibrationData identity = {
        0, 0, 0.0f, 0.0f, 1.0f};
    return identity;
}

inline bool powerCalibrationIsPlausible(
    const PowerCalibrationData& calibration,
    const PowerCalibrationStorageRules& rules)
{
    if (calibration.magic != rules.magic ||
        calibration.schema != rules.schema)
        return false;

    const float values[] = {
        calibration.packVoltageOffset,
        calibration.midpointVoltageOffset,
        calibration.packShuntCal};
    for (size_t index = 0; index < sizeof(values) / sizeof(values[0]); ++index)
        if (!isfinite(values[index]))
            return false;

    if (!isfinite(rules.maximumVoltageOffsetMagnitude) ||
        rules.maximumVoltageOffsetMagnitude < 0.0f ||
        fabs(calibration.packVoltageOffset) >
            rules.maximumVoltageOffsetMagnitude ||
        fabs(calibration.midpointVoltageOffset) >
            rules.maximumVoltageOffsetMagnitude)
        return false;

    if (!isfinite(rules.minimumShuntScale) ||
        !isfinite(rules.maximumShuntScale) ||
        rules.minimumShuntScale > rules.maximumShuntScale ||
        calibration.packShuntCal < rules.minimumShuntScale ||
        calibration.packShuntCal > rules.maximumShuntScale)
        return false;

    return true;
}

template <typename Storage>
inline bool loadPowerCalibration(
    Storage& storage,
    int address,
    const PowerCalibrationStorageRules& rules,
    PowerCalibrationData& result)
{
    PowerCalibrationData stored = identityPowerCalibration();
    storage.get(address, stored);
    if (!powerCalibrationIsPlausible(stored, rules))
    {
        result = identityPowerCalibration();
        return false;
    }

    result = stored;
    return true;
}

template <typename Storage>
inline void persistPowerCalibration(
    Storage& storage,
    int address,
    const PowerCalibrationStorageRules& rules,
    PowerCalibrationData& calibration)
{
    // Work on a copy so the active calibration never temporarily carries the
    // invalid marker used to protect the EEPROM transaction.
    PowerCalibrationData stored = calibration;
    stored.schema = rules.schema;
    stored.magic = 0;
    storage.put(address, stored);

    // The valid marker is the final byte written. An interruption after the
    // invalid marker lands therefore leaves a block that load rejects.
    storage.update(address, rules.magic);

    calibration.schema = rules.schema;
    calibration.magic = rules.magic;
}
