#include "unity.h"
#include "src/actuator/pot_validity.h"

// Taken from the shipped limits so the test cannot drift from them.
constexpr PotValidityLimits LIMITS = POT_VALIDITY_DEFAULT_LIMITS;
constexpr int POT_BAND_LO = LIMITS.minimumRaw;
constexpr int POT_BAND_HI = LIMITS.maximumRaw;
constexpr uint8_t POS_DEBOUNCE = LIMITS.invalidSampleLimit;
constexpr int IDLE_JITTER_MAX = LIMITS.idleJitterMax;

namespace
{
bool update(PotValidityTracker &tracker, int rawPot, bool driving)
{
    return tracker.update(rawPot, driving, LIMITS);
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

// The probe is held apart from the sampled verdict: a channel whose samples are
// all fine is still invalid if the pin proves open, and vice versa.
static void test_open_probe_invalidates_independently_of_samples()
{
    PotValidityTracker tracker;
    tracker.reset(500);
    TEST_ASSERT_TRUE(tracker.update(500, false, LIMITS));
    TEST_ASSERT_TRUE(tracker.isValid());

    tracker.notePositionProbe(1020, LIMITS.openProbeMinimum);
    TEST_ASSERT_TRUE(tracker.positionOpen());
    TEST_ASSERT_FALSE(tracker.isValid());

    // Samples keep passing; the probe alone is holding it invalid.
    TEST_ASSERT_FALSE(tracker.update(500, false, LIMITS));
    TEST_ASSERT_FALSE(tracker.isValid());
}

static void test_open_probe_boundary_is_inclusive_and_clears()
{
    PotValidityTracker tracker;
    tracker.reset(500);

    tracker.notePositionProbe(LIMITS.openProbeMinimum - 1, LIMITS.openProbeMinimum);
    TEST_ASSERT_FALSE(tracker.positionOpen());
    tracker.notePositionProbe(LIMITS.openProbeMinimum, LIMITS.openProbeMinimum);
    TEST_ASSERT_TRUE(tracker.positionOpen());

    // A later good probe clears it without needing a reset.
    tracker.notePositionProbe(964, LIMITS.openProbeMinimum);
    TEST_ASSERT_FALSE(tracker.positionOpen());
    TEST_ASSERT_TRUE(tracker.isValid());
}

static void test_reset_clears_a_latched_open_probe()
{
    PotValidityTracker tracker;
    tracker.notePositionProbe(1023, LIMITS.openProbeMinimum);
    TEST_ASSERT_FALSE(tracker.isValid());
    tracker.reset(500);
    TEST_ASSERT_TRUE(tracker.isValid());
    TEST_ASSERT_FALSE(tracker.positionOpen());
}

// An uncalibrated channel takes the fixed default; a calibrated one derives from
// its own stroke, and is allowed to end up higher than the default rather than
// calling a genuinely high-reading pot open.
static void test_probe_threshold_follows_calibrated_stroke()
{
    TEST_ASSERT_EQUAL_INT(LIMITS.openProbeMinimum,
        potOpenProbeMinimum(POT_STROKE_MAX_RAW, LIMITS));
    TEST_ASSERT_EQUAL_INT(985 + LIMITS.openProbeMargin,
        potOpenProbeMinimum(985, LIMITS));
    TEST_ASSERT_EQUAL_INT(1010 + LIMITS.openProbeMargin,
        potOpenProbeMinimum(1010, LIMITS));
}

static void test_reset_seeds_previous_sample_and_valid_state()
{
    PotValidityTracker tracker;
    tracker.reset(500);

    TEST_ASSERT_TRUE(tracker.isValid());
    // Seeded at 500, so an identical sample is no slew at all.
    TEST_ASSERT_TRUE(update(tracker, 500, false));
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
        TEST_ASSERT_FALSE(tracker.isValid());
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
}

static void test_good_sample_breaks_bad_run_and_immediately_recovers()
{
    PotValidityTracker tracker;
    tracker.reset(500);
    update(tracker, 507, false);
    update(tracker, 500, false);
    // One good sample clears the pending run outright: two more bad samples are
    // then needed again, so the third is where validity drops.
    TEST_ASSERT_TRUE(update(tracker, 503, false));
    TEST_ASSERT_TRUE(update(tracker, 600, false));
    TEST_ASSERT_TRUE(update(tracker, 500, false));

    update(tracker, 600, false);
    update(tracker, 500, false);
    update(tracker, 600, false);
    TEST_ASSERT_FALSE(tracker.isValid());
    TEST_ASSERT_TRUE(update(tracker, 602, false));
}

static void test_idle_slew_boundary_is_inclusive()
{
    PotValidityTracker tracker;
    tracker.reset(500);

    TEST_ASSERT_TRUE(update(tracker, 500 + IDLE_JITTER_MAX, false));

    // A sample exactly on the boundary counts as good, so the full run of three
    // is still required afterwards rather than the remainder of a partial one.
    TEST_ASSERT_TRUE(update(tracker, 1023, false));
    TEST_ASSERT_TRUE(update(tracker, 1023, false));
    TEST_ASSERT_FALSE(update(tracker, 1023, false));
}

static void test_driving_suppresses_slew_check_for_real_motion()
{
    PotValidityTracker tracker;
    tracker.reset(300);

    TEST_ASSERT_TRUE(update(tracker, 700, true));
    TEST_ASSERT_TRUE(update(tracker, 200, true));
}

static void test_driving_never_suppresses_rail_check()
{
    PotValidityTracker tracker;
    tracker.reset(500);

    applyBadSamples(tracker, 1023, true, POS_DEBOUNCE);

    TEST_ASSERT_FALSE(tracker.isValid());
}

static void test_bad_counter_saturates_at_debounce_limit()
{
    PotValidityTracker tracker;
    tracker.reset(500);

    applyBadSamples(tracker, 1023, false, 20);
    TEST_ASSERT_FALSE(tracker.isValid());

    // Saturation is observable as immediate recovery: had the counter kept
    // climbing to 20, one good sample could not restore validity. The sample
    // must be driven -- an idle jump back from the rail is itself a slew
    // violation, so it would not qualify as good.
    TEST_ASSERT_TRUE(update(tracker, 500, true));
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
    RUN_TEST(test_open_probe_invalidates_independently_of_samples);
    RUN_TEST(test_open_probe_boundary_is_inclusive_and_clears);
    RUN_TEST(test_reset_clears_a_latched_open_probe);
    RUN_TEST(test_probe_threshold_follows_calibrated_stroke);
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
