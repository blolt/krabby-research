#include <limits>

#include "unity.h"

#include "power_calibration_protocol.h"

void setUp() {}
void tearDown() {}

static void test_top_level_command_prefix_is_power()
{
    TEST_ASSERT_EQUAL_CHAR('P', POWER_COMMAND_PREFIX);
}

static void test_complete_tokens_select_each_operation_case_insensitively()
{
    TEST_ASSERT_EQUAL_INT(
        static_cast<int>(PowerCalibrationOperation::Voltage),
        static_cast<int>(parsePowerCalibrationOperation("CAL", "VOLTAGE")));
    TEST_ASSERT_EQUAL_INT(
        static_cast<int>(PowerCalibrationOperation::Current),
        static_cast<int>(parsePowerCalibrationOperation("cal", "current")));
    TEST_ASSERT_EQUAL_INT(
        static_cast<int>(PowerCalibrationOperation::Show),
        static_cast<int>(parsePowerCalibrationOperation("Cal", "Show")));
    TEST_ASSERT_EQUAL_INT(
        static_cast<int>(PowerCalibrationOperation::Help),
        static_cast<int>(parsePowerCalibrationOperation("CAL", "?")));
}

static void test_missing_wrong_and_partial_tokens_are_invalid()
{
    const char* invalid[][2] = {
        {"", "VOLTAGE"},
        {"POWER", "VOLTAGE"},
        {"CAL", ""},
        {"CAL", "V"},
        {"CAL", "CURRENTLY"},
        {"CAL", "SHUNT"},
        {"CAL", "LIST"},
        {nullptr, "SHOW"},
        {"CAL", nullptr},
    };

    for (size_t index = 0; index < 9; ++index)
    {
        TEST_ASSERT_EQUAL_INT(
            static_cast<int>(PowerCalibrationOperation::Invalid),
            static_cast<int>(parsePowerCalibrationOperation(
                invalid[index][0], invalid[index][1])));
    }
}

static void test_valid_numbers_are_parsed_exactly()
{
    const char* tokens[] = {
        "0", "10", "-10", "+10.25", "25.84", "1e-2", "-3.5E+1",
    };
    const float expected[] = {
        0.0f, 10.0f, -10.0f, 10.25f, 25.84f, 0.01f, -35.0f,
    };

    for (size_t index = 0; index < 7; ++index)
    {
        float result = 99.0f;
        TEST_ASSERT_TRUE(parsePowerCalibrationNumber(tokens[index], result));
        TEST_ASSERT_FLOAT_WITHIN(0.00001f, expected[index], result);
    }
}

static void test_invalid_numbers_do_not_mutate_result()
{
    const char* invalid[] = {
        "",
        " ",
        "abc",
        "1abc",
        "1 2",
        "nan",
        "NaN",
        "inf",
        "-inf",
        "1e999",
        nullptr,
    };

    for (size_t index = 0; index < 11; ++index)
    {
        float result = 99.0f;
        TEST_ASSERT_FALSE(
            parsePowerCalibrationNumber(invalid[index], result));
        TEST_ASSERT_EQUAL_FLOAT(99.0f, result);
    }
}

static void test_complete_commands_require_exact_argument_counts()
{
    const char* voltage[] = {"CAL", "VOLTAGE", "25.84", "12.91"};
    const char* current[] = {"CAL", "CURRENT", "-10.0"};
    const char* show[] = {"CAL", "SHOW"};
    const char* help[] = {"CAL", "?"};
    PowerCalibrationCommand result = {
        PowerCalibrationOperation::Invalid, 99.0f, 98.0f};

    TEST_ASSERT_TRUE(parsePowerCalibrationCommand(4, voltage, result));
    TEST_ASSERT_EQUAL_INT(
        static_cast<int>(PowerCalibrationOperation::Voltage),
        static_cast<int>(result.operation));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 25.84f, result.firstReference);
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 12.91f, result.secondReference);

    TEST_ASSERT_TRUE(parsePowerCalibrationCommand(3, current, result));
    TEST_ASSERT_EQUAL_INT(
        static_cast<int>(PowerCalibrationOperation::Current),
        static_cast<int>(result.operation));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, -10.0f, result.firstReference);

    TEST_ASSERT_TRUE(parsePowerCalibrationCommand(2, show, result));
    TEST_ASSERT_EQUAL_INT(
        static_cast<int>(PowerCalibrationOperation::Show),
        static_cast<int>(result.operation));
    TEST_ASSERT_TRUE(parsePowerCalibrationCommand(2, help, result));
    TEST_ASSERT_EQUAL_INT(
        static_cast<int>(PowerCalibrationOperation::Help),
        static_cast<int>(result.operation));
}

static void test_invalid_complete_commands_preserve_prior_result()
{
    const char* missingVoltage[] = {"CAL", "VOLTAGE", "25.84"};
    const char* extraVoltage[] = {
        "CAL", "VOLTAGE", "25.84", "12.91", "extra"};
    const char* missingCurrent[] = {"CAL", "CURRENT"};
    const char* extraCurrent[] = {"CAL", "CURRENT", "10", "extra"};
    const char* extraShow[] = {"CAL", "SHOW", "extra"};
    const char* badNumber[] = {"CAL", "CURRENT", "10A"};
    const char** invalid[] = {
        missingVoltage,
        extraVoltage,
        missingCurrent,
        extraCurrent,
        extraShow,
        badNumber,
    };
    const size_t counts[] = {3, 5, 2, 4, 3, 3};

    for (size_t index = 0; index < 6; ++index)
    {
        PowerCalibrationCommand result = {
            PowerCalibrationOperation::Show, 99.0f, 98.0f};
        TEST_ASSERT_FALSE(parsePowerCalibrationCommand(
            counts[index], invalid[index], result));
        TEST_ASSERT_EQUAL_INT(
            static_cast<int>(PowerCalibrationOperation::Show),
            static_cast<int>(result.operation));
        TEST_ASSERT_EQUAL_FLOAT(99.0f, result.firstReference);
        TEST_ASSERT_EQUAL_FLOAT(98.0f, result.secondReference);
    }

    PowerCalibrationCommand result = {
        PowerCalibrationOperation::Show, 99.0f, 98.0f};
    TEST_ASSERT_FALSE(parsePowerCalibrationCommand(0, nullptr, result));
    TEST_ASSERT_EQUAL_FLOAT(99.0f, result.firstReference);
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_top_level_command_prefix_is_power);
    RUN_TEST(test_complete_tokens_select_each_operation_case_insensitively);
    RUN_TEST(test_missing_wrong_and_partial_tokens_are_invalid);
    RUN_TEST(test_valid_numbers_are_parsed_exactly);
    RUN_TEST(test_invalid_numbers_do_not_mutate_result);
    RUN_TEST(test_complete_commands_require_exact_argument_counts);
    RUN_TEST(test_invalid_complete_commands_preserve_prior_result);
    return UNITY_END();
}
