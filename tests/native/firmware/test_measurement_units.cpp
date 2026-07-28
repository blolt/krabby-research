#include <limits>
#include <type_traits>

#include "unity.h"

#include "measurement_units.h"

static_assert(!std::is_convertible<float, MilliAmps>::value,
              "raw floats must not implicitly become milliamps");
static_assert(!std::is_convertible<float, Ohms>::value,
              "raw floats must not implicitly become ohms");
static_assert(!std::is_convertible<Ohms, Amps>::value,
              "resistance must not implicitly become current");
static_assert(!std::is_convertible<float, Amps>::value,
              "raw floats must not implicitly become amps");
static_assert(!std::is_convertible<MilliAmps, Amps>::value,
              "milliamps must be explicitly converted to amps");
static_assert(!std::is_convertible<MilliWatts, Watts>::value,
              "milliwatts must be explicitly converted to watts");
static_assert(!std::is_convertible<float, Coulombs>::value,
              "raw floats must not implicitly become coulombs");
static_assert(!std::is_convertible<uint32_t, Milliseconds>::value,
              "raw integers must not implicitly become milliseconds");
static_assert(!std::is_convertible<Milliseconds, Amps>::value,
              "time must not implicitly become current");

void setUp() {}
void tearDown() {}

static void test_current_converts_in_both_directions()
{
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 1.5f, toAmps(MilliAmps(1500.0f)).value());
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, 1500.0f, toMilliAmps(Amps(1.5f)).value());
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 0.0f, toAmps(MilliAmps(0.0f)).value());
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, -2.5f, toAmps(MilliAmps(-2500.0f)).value());
}

static void test_power_converts_in_both_directions()
{
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 12.75f, toWatts(MilliWatts(12750.0f)).value());
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, 12750.0f, toMilliWatts(Watts(12.75f)).value());
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 0.0f, toWatts(MilliWatts(0.0f)).value());
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, -0.5f, toWatts(MilliWatts(-500.0f)).value());
}

static void test_shunt_trim_preserves_the_measurement_unit()
{
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, 2.04f, applyShuntTrim(Amps(2.0f), 1.02f).value());
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, 51.0f, applyShuntTrim(Watts(50.0f), 1.02f).value());
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, 306.0f, applyShuntTrim(Coulombs(300.0f), 1.02f).value());
}

static void test_non_finite_values_propagate_for_caller_validation()
{
    const float nan = std::numeric_limits<float>::quiet_NaN();
    const float inf = std::numeric_limits<float>::infinity();

    TEST_ASSERT_TRUE(isnan(toAmps(MilliAmps(nan)).value()));
    TEST_ASSERT_TRUE(isinf(toAmps(MilliAmps(inf)).value()));
    TEST_ASSERT_TRUE(isnan(toWatts(MilliWatts(nan)).value()));
    TEST_ASSERT_TRUE(isinf(toWatts(MilliWatts(inf)).value()));
    TEST_ASSERT_TRUE(isnan(applyShuntTrim(Coulombs(nan), 1.0f).value()));
    TEST_ASSERT_TRUE(isinf(applyShuntTrim(Coulombs(inf), 1.0f).value()));
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_current_converts_in_both_directions);
    RUN_TEST(test_power_converts_in_both_directions);
    RUN_TEST(test_shunt_trim_preserves_the_measurement_unit);
    RUN_TEST(test_non_finite_values_propagate_for_caller_validation);
    return UNITY_END();
}
