#include <limits>

#include "unity.h"

#include "src/power_bus/battery_split.h"
#include "src/power_bus/power_bus_constants.h"

void setUp() {}
void tearDown() {}

static void assertSplit(
    float packVoltage,
    float midpointVoltage,
    float expectedA,
    float expectedB,
    bool expectedDivergence)
{
    BatterySplit result = {-1.0f, -1.0f, false};
    TEST_ASSERT_TRUE(calculateBatterySplit(
        packVoltage,
        midpointVoltage,
        INA228_DIVERGENCE_THRESHOLD,
        result));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, expectedA, result.batteryA);
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, expectedB, result.batteryB);
    TEST_ASSERT_EQUAL(expectedDivergence, result.diverged);
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, packVoltage, result.batteryA + result.batteryB);
}

static void test_exact_and_fractional_splits_use_pack_minus_midpoint()
{
    assertSplit(24.0f, 12.0f, 12.0f, 12.0f, false);
    assertSplit(26.55f, 13.35f, 13.35f, 13.20f, false);
    assertSplit(24.13f, 11.50f, 11.50f, 12.63f, true);
}

static void test_voltage_boundaries_are_inclusive()
{
    assertSplit(0.0f, 0.0f, 0.0f, 0.0f, false);
    assertSplit(20.0f, 0.0f, 0.0f, 20.0f, true);
    assertSplit(20.0f, 20.0f, 20.0f, 0.0f, true);
    assertSplit(40.0f, 20.0f, 20.0f, 20.0f, false);
}

static void test_divergence_threshold_is_strict()
{
    assertSplit(24.0f, 12.25f, 12.25f, 11.75f, false);
    assertSplit(24.0f, 12.25001f, 12.25001f, 11.74999f, true);
    assertSplit(24.0f, 11.75f, 11.75f, 12.25f, false);
    assertSplit(24.0f, 11.74999f, 11.74999f, 12.25001f, true);
}

static void test_non_finite_inputs_are_rejected_without_mutating_result()
{
    const float nan = std::numeric_limits<float>::quiet_NaN();
    const float inf = std::numeric_limits<float>::infinity();
    const float invalidInputs[][3] = {
        {nan, 12.0f, INA228_DIVERGENCE_THRESHOLD.value},
        {inf, 12.0f, INA228_DIVERGENCE_THRESHOLD.value},
        {24.0f, nan, INA228_DIVERGENCE_THRESHOLD.value},
        {24.0f, inf, INA228_DIVERGENCE_THRESHOLD.value},
        {24.0f, 12.0f, nan},
        {24.0f, 12.0f, inf},
    };

    for (size_t index = 0; index < 6; ++index)
    {
        BatterySplit result = {1.0f, 2.0f, true};
        TEST_ASSERT_FALSE(calculateBatterySplit(
            invalidInputs[index][0],
            invalidInputs[index][1],
            Volts(invalidInputs[index][2]),
            result));
        TEST_ASSERT_EQUAL_FLOAT(1.0f, result.batteryA);
        TEST_ASSERT_EQUAL_FLOAT(2.0f, result.batteryB);
        TEST_ASSERT_TRUE(result.diverged);
    }
}

static void test_out_of_range_inputs_and_impossible_pairs_are_rejected()
{
    const float invalidInputs[][3] = {
        {-0.001f, 0.0f, INA228_DIVERGENCE_THRESHOLD.value},
        {40.001f, 20.0f, INA228_DIVERGENCE_THRESHOLD.value},
        {24.0f, -0.001f, INA228_DIVERGENCE_THRESHOLD.value},
        {24.0f, 20.001f, INA228_DIVERGENCE_THRESHOLD.value},
        {10.0f, 10.001f, INA228_DIVERGENCE_THRESHOLD.value},
        {40.0f, 19.999f, INA228_DIVERGENCE_THRESHOLD.value},
        {24.0f, 12.0f, -0.001f},
    };

    for (size_t index = 0; index < 7; ++index)
    {
        BatterySplit result = {};
        TEST_ASSERT_FALSE(calculateBatterySplit(
            invalidInputs[index][0],
            invalidInputs[index][1],
            Volts(invalidInputs[index][2]),
            result));
    }
}

// The bug this replaced had two halves. The poll returned as soon as the Pack
// read failed, so the Midpoint was never judged - its liveness froze and its
// retry schedule stopped advancing. And it read the Midpoint's verdict off
// calculateBatterySplit, which also fails when the Pack is the wrong one.
//
// The sequencing half is call-site ordering and cannot be asserted here. The
// attribution half is these two functions being separate, which can.
static void test_a_bad_pack_does_not_condemn_the_midpoint()
{
    TEST_ASSERT_FALSE(batteryPackVoltageIsValid(NAN));
    TEST_ASSERT_TRUE(batteryCellVoltageIsValid(6.6f));
}

static void test_a_bad_midpoint_does_not_condemn_the_pack()
{
    TEST_ASSERT_TRUE(batteryPackVoltageIsValid(13.2f));
    TEST_ASSERT_FALSE(batteryCellVoltageIsValid(NAN));
}

// An implausible *pair* is not a Midpoint fault. The Midpoint reports an
// ordinary 6.6 V while the Pack reads 3 V, so batteryB would be negative and no
// frame can be emitted - but the wrong monitor is the Pack, and judging the
// Midpoint on the pair would retry a device that is answering correctly.
static void test_an_implausible_pair_is_not_a_midpoint_fault()
{
    TEST_ASSERT_TRUE(batteryCellVoltageIsValid(6.6f));

    BatterySplit split;
    TEST_ASSERT_FALSE(calculateBatterySplit(3.0f, 6.6f, Volts(0.5f), split));
}

static void test_cell_voltage_validity_bounds()
{
    TEST_ASSERT_TRUE(batteryCellVoltageIsValid(0.0f));
    TEST_ASSERT_TRUE(batteryCellVoltageIsValid(20.0f));
    TEST_ASSERT_FALSE(batteryCellVoltageIsValid(-0.1f));
    TEST_ASSERT_FALSE(batteryCellVoltageIsValid(20.1f));
    TEST_ASSERT_FALSE(batteryCellVoltageIsValid(NAN));
    TEST_ASSERT_FALSE(batteryCellVoltageIsValid(INFINITY));
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_a_bad_pack_does_not_condemn_the_midpoint);
    RUN_TEST(test_a_bad_midpoint_does_not_condemn_the_pack);
    RUN_TEST(test_an_implausible_pair_is_not_a_midpoint_fault);
    RUN_TEST(test_cell_voltage_validity_bounds);
    RUN_TEST(test_exact_and_fractional_splits_use_pack_minus_midpoint);
    RUN_TEST(test_voltage_boundaries_are_inclusive);
    RUN_TEST(test_divergence_threshold_is_strict);
    RUN_TEST(test_non_finite_inputs_are_rejected_without_mutating_result);
    RUN_TEST(test_out_of_range_inputs_and_impossible_pairs_are_rejected);
    return UNITY_END();
}
