#include "unity.h"

#include "pot_validity.h"

namespace
{
const float IDLE_JITTER_MAX = 6.0f;

bool update(PotValidityTracker &tracker, int rawPot, bool driving)
{
    return tracker.update(rawPot, driving, IDLE_JITTER_MAX);
}

void applyBadSamples(
    PotValidityTracker &tracker,
    int rawPot,
    bool driving,
    uint8_t count)
{
    for (uint8_t sample = 0; sample < count; ++sample)
        update(tracker, rawPot, driving);
}
}

void setUp() {}
void tearDown() {}

static void test_reset_seeds_previous_sample_and_valid_state()
{
    PotValidityTracker tracker;
    tracker.reset(500);

    TEST_ASSERT_EQUAL_INT(500, tracker.previousRawPot);
    TEST_ASSERT_EQUAL_UINT8(0, tracker.badSampleCount);
    TEST_ASSERT_TRUE(tracker.valid);
    TEST_ASSERT_TRUE(update(tracker, 500, false));
}

static void test_sane_band_boundaries_are_exclusive()
{
    const int rejected[] = {0, POT_BAND_LO, POT_BAND_HI, 1023};
    for (size_t value = 0; value < 4; ++value)
    {
        PotValidityTracker tracker;
        tracker.reset(rejected[value]);
        applyBadSamples(tracker, rejected[value], false, POS_DEBOUNCE);
        TEST_ASSERT_FALSE(tracker.valid);
    }

    PotValidityTracker lowInside;
    lowInside.reset(POT_BAND_LO + 1);
    TEST_ASSERT_TRUE(update(lowInside, POT_BAND_LO + 1, false));
    PotValidityTracker highInside;
    highInside.reset(POT_BAND_HI - 1);
    TEST_ASSERT_TRUE(update(highInside, POT_BAND_HI - 1, false));
}

static void test_three_consecutive_bad_idle_samples_invalidate()
{
    PotValidityTracker tracker;
    tracker.reset(500);

    TEST_ASSERT_TRUE(update(tracker, 507, false));
    TEST_ASSERT_TRUE(update(tracker, 500, false));
    TEST_ASSERT_FALSE(update(tracker, 507, false));
    TEST_ASSERT_EQUAL_UINT8(POS_DEBOUNCE, tracker.badSampleCount);
}

static void test_good_sample_breaks_bad_run_and_immediately_recovers()
{
    PotValidityTracker tracker;
    tracker.reset(500);
    update(tracker, 507, false);
    update(tracker, 500, false);
    TEST_ASSERT_TRUE(update(tracker, 503, false));
    TEST_ASSERT_EQUAL_UINT8(0, tracker.badSampleCount);

    update(tracker, 600, false);
    update(tracker, 500, false);
    update(tracker, 600, false);
    TEST_ASSERT_FALSE(tracker.valid);
    TEST_ASSERT_TRUE(update(tracker, 602, false));
    TEST_ASSERT_EQUAL_UINT8(0, tracker.badSampleCount);
}

static void test_idle_slew_boundary_is_inclusive()
{
    PotValidityTracker tracker;
    tracker.reset(500);

    TEST_ASSERT_TRUE(update(
        tracker, 500 + (int)IDLE_JITTER_MAX, false));
    TEST_ASSERT_EQUAL_UINT8(0, tracker.badSampleCount);
}

static void test_driving_suppresses_slew_check_for_real_motion()
{
    PotValidityTracker tracker;
    tracker.reset(300);

    TEST_ASSERT_TRUE(update(tracker, 700, true));
    TEST_ASSERT_TRUE(update(tracker, 200, true));
    TEST_ASSERT_EQUAL_UINT8(0, tracker.badSampleCount);
}

static void test_driving_never_suppresses_rail_check()
{
    PotValidityTracker tracker;
    tracker.reset(500);

    applyBadSamples(tracker, 1023, true, POS_DEBOUNCE);

    TEST_ASSERT_FALSE(tracker.valid);
}

static void test_bad_counter_saturates_at_debounce_limit()
{
    PotValidityTracker tracker;
    tracker.reset(500);

    applyBadSamples(tracker, 1023, false, 20);

    TEST_ASSERT_EQUAL_UINT8(POS_DEBOUNCE, tracker.badSampleCount);
    TEST_ASSERT_FALSE(tracker.valid);
}

static void test_position_reporting_filters_only_normalized_position()
{
    const float normalizedPosition = 0.625f;

    TEST_ASSERT_FLOAT_WITHIN(
        0.0001f,
        normalizedPosition,
        filteredActuatorPosition(true, normalizedPosition));
    TEST_ASSERT_TRUE(isnan(
        filteredActuatorPosition(false, normalizedPosition)));
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_reset_seeds_previous_sample_and_valid_state);
    RUN_TEST(test_sane_band_boundaries_are_exclusive);
    RUN_TEST(test_three_consecutive_bad_idle_samples_invalidate);
    RUN_TEST(test_good_sample_breaks_bad_run_and_immediately_recovers);
    RUN_TEST(test_idle_slew_boundary_is_inclusive);
    RUN_TEST(test_driving_suppresses_slew_check_for_real_motion);
    RUN_TEST(test_driving_never_suppresses_rail_check);
    RUN_TEST(test_bad_counter_saturates_at_debounce_limit);
    RUN_TEST(test_position_reporting_filters_only_normalized_position);
    return UNITY_END();
}
