#include "unity.h"

#include "units.h"

void setUp() {}
void tearDown() {}

// The rounding conversions are exercised through tiltRoll/tiltPitch; this covers
// the default, which no caller uses at runtime today.
static void test_to_degrees_defaults_to_exact()
{
    const Radians tenth(0.1f);  // 5.729577... degrees

    const float exact = tenth.toDegrees().value;
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 5.729578f, exact);
    TEST_ASSERT_TRUE(exact != static_cast<float>(static_cast<long>(exact)));

    TEST_ASSERT_EQUAL_FLOAT(
        exact, tenth.toDegrees(Rounding::Exact).value);
    TEST_ASSERT_EQUAL_FLOAT(
        6.0f, tenth.toDegrees(Rounding::HalfAwayFromZero).value);
}

static void test_degrees_and_radians_round_trip()
{
    const Degrees ninety(90.0f);
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 90.0f, ninety.toRadians().toDegrees().value);
    TEST_ASSERT_FLOAT_WITHIN(
        0.0001f, 1.5707963f, ninety.toRadians().value);
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_to_degrees_defaults_to_exact);
    RUN_TEST(test_degrees_and_radians_round_trip);
    return UNITY_END();
}
