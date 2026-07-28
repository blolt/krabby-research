#pragma once

#include <errno.h>
#include <math.h>
#include <stdlib.h>

static const char POWER_COMMAND_PREFIX = 'P';
static const char POWER_CALIBRATION_NAMESPACE[] = "CAL";
static const char POWER_CALIBRATION_VOLTAGE_OPERATION[] = "VOLTAGE";
static const char POWER_CALIBRATION_CURRENT_OPERATION[] = "CURRENT";
static const char POWER_CALIBRATION_SHOW_OPERATION[] = "SHOW";
static const char POWER_CALIBRATION_HELP_OPERATION[] = "?";

enum class PowerCalibrationOperation {
    Invalid,
    Voltage,
    Current,
    Show,
    Help,
};

struct PowerCalibrationCommand {
    PowerCalibrationOperation operation;
    float firstReference;
    float secondReference;
};

inline char powerCalibrationAsciiUpper(char value)
{
    return value >= 'a' && value <= 'z' ? value - ('a' - 'A') : value;
}

inline bool powerCalibrationTokenEquals(
    const char* actual,
    const char* expected)
{
    if (actual == nullptr || expected == nullptr)
        return false;

    while (*actual != '\0' && *expected != '\0')
    {
        if (powerCalibrationAsciiUpper(*actual) != *expected)
            return false;
        ++actual;
        ++expected;
    }
    return *actual == '\0' && *expected == '\0';
}

inline PowerCalibrationOperation parsePowerCalibrationOperation(
    const char* namespaceToken,
    const char* operationToken)
{
    if (!powerCalibrationTokenEquals(
            namespaceToken, POWER_CALIBRATION_NAMESPACE))
        return PowerCalibrationOperation::Invalid;
    if (powerCalibrationTokenEquals(
            operationToken, POWER_CALIBRATION_VOLTAGE_OPERATION))
        return PowerCalibrationOperation::Voltage;
    if (powerCalibrationTokenEquals(
            operationToken, POWER_CALIBRATION_CURRENT_OPERATION))
        return PowerCalibrationOperation::Current;
    if (powerCalibrationTokenEquals(
            operationToken, POWER_CALIBRATION_SHOW_OPERATION))
        return PowerCalibrationOperation::Show;
    if (powerCalibrationTokenEquals(
            operationToken, POWER_CALIBRATION_HELP_OPERATION))
        return PowerCalibrationOperation::Help;
    return PowerCalibrationOperation::Invalid;
}

inline bool parsePowerCalibrationNumber(const char* token, float& result)
{
    if (token == nullptr || *token == '\0')
        return false;

    errno = 0;
    char* end = nullptr;
    const double parsed = strtod(token, &end);
    if (end == token ||
        *end != '\0' ||
        errno == ERANGE ||
        !isfinite(parsed))
        return false;

    const float value = static_cast<float>(parsed);
    if (!isfinite(value))
        return false;

    result = value;
    return true;
}

inline bool parsePowerCalibrationCommand(
    size_t tokenCount,
    const char* const* tokens,
    PowerCalibrationCommand& result)
{
    if (tokens == nullptr || tokenCount < 2)
        return false;

    const PowerCalibrationOperation operation =
        parsePowerCalibrationOperation(tokens[0], tokens[1]);
    PowerCalibrationCommand parsed = {
        operation, 0.0f, 0.0f};

    switch (operation)
    {
        case PowerCalibrationOperation::Voltage:
            if (tokenCount != 4 ||
                !parsePowerCalibrationNumber(tokens[2], parsed.firstReference) ||
                !parsePowerCalibrationNumber(tokens[3], parsed.secondReference))
                return false;
            break;
        case PowerCalibrationOperation::Current:
            if (tokenCount != 3 ||
                !parsePowerCalibrationNumber(tokens[2], parsed.firstReference))
                return false;
            break;
        case PowerCalibrationOperation::Show:
        case PowerCalibrationOperation::Help:
            if (tokenCount != 2)
                return false;
            break;
        case PowerCalibrationOperation::Invalid:
            return false;
    }

    result = parsed;
    return true;
}
