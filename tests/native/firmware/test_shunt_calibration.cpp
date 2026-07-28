#include <limits>

#include "unity.h"

#include "sensors_config.h"
#include "shunt_calibration.h"

namespace {

const Amps MINIMUM_CURRENT(INA228_CAL_MIN_SHUNT_TRIM_A);

bool calculate(Amps knownCurrent, Amps measuredCurrent, float& result)
{
    return calculateShuntTrim(
        knownCurrent,
        measuredCurrent,
        MINIMUM_CURRENT,
        INA228_CAL_MIN_GAIN,
        INA228_CAL_MAX_GAIN,
        result);
}

void test_positive_and_negative_current_produce_same_trim()
{
    float positiveResult = 0.0f;
    float negativeResult = 0.0f;

    TEST_ASSERT_TRUE(calculate(Amps(10.0f), Amps(8.0f), positiveResult));
    TEST_ASSERT_TRUE(calculate(Amps(-10.0f), Amps(-8.0f), negativeResult));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 1.25f, positiveResult);
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, positiveResult, negativeResult);
}

void test_trim_bounds_are_inclusive()
{
    float lowerResult = 0.0f;
    float upperResult = 0.0f;

    TEST_ASSERT_TRUE(calculate(Amps(5.0f), Amps(10.0f), lowerResult));
    TEST_ASSERT_TRUE(calculate(Amps(10.0f), Amps(5.0f), upperResult));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, INA228_CAL_MIN_GAIN, lowerResult);
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, INA228_CAL_MAX_GAIN, upperResult);
}

void test_current_below_minimum_is_rejected_without_mutating_result()
{
    const float tooSmall = INA228_CAL_MIN_SHUNT_TRIM_A - 0.001f;
    float result = 7.0f;

    TEST_ASSERT_FALSE(calculate(Amps(tooSmall), Amps(1.0f), result));
    TEST_ASSERT_EQUAL_FLOAT(7.0f, result);
    TEST_ASSERT_FALSE(calculate(Amps(1.0f), Amps(-tooSmall), result));
    TEST_ASSERT_EQUAL_FLOAT(7.0f, result);
    TEST_ASSERT_FALSE(calculate(Amps(0.0f), Amps(1.0f), result));
    TEST_ASSERT_EQUAL_FLOAT(7.0f, result);
    TEST_ASSERT_FALSE(calculate(Amps(1.0f), Amps(0.0f), result));
    TEST_ASSERT_EQUAL_FLOAT(7.0f, result);

    TEST_ASSERT_TRUE(calculate(
        Amps(INA228_CAL_MIN_SHUNT_TRIM_A),
        Amps(INA228_CAL_MIN_SHUNT_TRIM_A),
        result));
    TEST_ASSERT_EQUAL_FLOAT(1.0f, result);
}

void test_opposite_signs_and_out_of_band_trim_are_rejected()
{
    float result = 7.0f;

    TEST_ASSERT_FALSE(calculate(Amps(1.0f), Amps(-1.0f), result));
    TEST_ASSERT_EQUAL_FLOAT(7.0f, result);
    TEST_ASSERT_FALSE(calculate(Amps(4.9f), Amps(10.0f), result));
    TEST_ASSERT_EQUAL_FLOAT(7.0f, result);
    TEST_ASSERT_FALSE(calculate(Amps(10.1f), Amps(5.0f), result));
    TEST_ASSERT_EQUAL_FLOAT(7.0f, result);
}

void test_nonfinite_currents_are_rejected_without_mutating_result()
{
    const float nonfinite[] = {
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity(),
    };

    for (size_t index = 0; index < 3; ++index)
    {
        float result = 7.0f;
        TEST_ASSERT_FALSE(
            calculate(Amps(nonfinite[index]), Amps(1.0f), result));
        TEST_ASSERT_EQUAL_FLOAT(7.0f, result);
        TEST_ASSERT_FALSE(
            calculate(Amps(1.0f), Amps(nonfinite[index]), result));
        TEST_ASSERT_EQUAL_FLOAT(7.0f, result);
    }
}

void test_invalid_limits_are_rejected_without_mutating_result()
{
    const float nan = std::numeric_limits<float>::quiet_NaN();
    const float inf = std::numeric_limits<float>::infinity();
    const float invalidLimits[][3] = {
        {-0.1f, 0.5f, 2.0f},
        {nan, 0.5f, 2.0f},
        {inf, 0.5f, 2.0f},
        {0.1f, nan, 2.0f},
        {0.1f, inf, 2.0f},
        {0.1f, 0.0f, 2.0f},
        {0.1f, -0.1f, 2.0f},
        {0.1f, 0.5f, nan},
        {0.1f, 0.5f, inf},
        {0.1f, 2.0f, 0.5f},
    };

    for (size_t index = 0; index < 10; ++index)
    {
        float result = 7.0f;
        TEST_ASSERT_FALSE(calculateShuntTrim(
            Amps(1.0f),
            Amps(1.0f),
            Amps(invalidLimits[index][0]),
            invalidLimits[index][1],
            invalidLimits[index][2],
            result));
        TEST_ASSERT_EQUAL_FLOAT(7.0f, result);
    }
}

}  // namespace

void setUp() {}
void tearDown() {}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_positive_and_negative_current_produce_same_trim);
    RUN_TEST(test_trim_bounds_are_inclusive);
    RUN_TEST(test_current_below_minimum_is_rejected_without_mutating_result);
    RUN_TEST(test_opposite_signs_and_out_of_band_trim_are_rejected);
    RUN_TEST(test_nonfinite_currents_are_rejected_without_mutating_result);
    RUN_TEST(test_invalid_limits_are_rejected_without_mutating_result);
    return UNITY_END();
}
