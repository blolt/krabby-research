#include "unity.h"
#include "src/actuator/actuator_attachment.h"

constexpr ActuatorAttachmentState ATTACHMENT_UNKNOWN = ActuatorAttachmentState::Unknown;
constexpr ActuatorAttachmentState ATTACHMENT_ATTACHED = ActuatorAttachmentState::Attached;
constexpr ActuatorAttachmentState ATTACHMENT_DISCONNECTED = ActuatorAttachmentState::Disconnected;

namespace
{
// Taken from the shipped limits so the test cannot drift from them.
constexpr ActuatorAttachmentLimits LIMITS = ACTUATOR_ATTACHMENT_DEFAULT_LIMITS;
constexpr int CURRENT_PRESENT_FLOOR = LIMITS.currentPresentFloor;
constexpr uint8_t REQUIRED_SAMPLES = LIMITS.debounceSamples;

void update(
    ActuatorAttachmentTracker &tracker,
    bool usable,
    int current)
{
    tracker.update(usable, current, LIMITS);
}
}

void setUp() {}
void tearDown() {}

static void test_boot_unknown_does_not_false_disconnect()
{
    ActuatorAttachmentTracker tracker;

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state());
    TEST_ASSERT_TRUE(tracker.isAttachedOrUnknown());
    TEST_ASSERT_TRUE(actuatorConnectionIsValid(true, tracker));
    TEST_ASSERT_FALSE(actuatorConnectionIsValid(false, tracker));
}

static void test_idle_current_is_never_attachment_evidence()
{
    ActuatorAttachmentTracker tracker;

    for (int sample = 0; sample < 10; ++sample)
        update(tracker, false, 0);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state());

    // Idle contributed nothing, so the whole run of three is still needed.
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state());
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state());
}

static void test_consecutive_low_driven_current_latches_disconnected()
{
    ActuatorAttachmentTracker tracker;

    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state());
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state());
    TEST_ASSERT_FALSE(tracker.isAttachedOrUnknown());
}

static void test_present_threshold_is_inclusive_and_debounced()
{
    ActuatorAttachmentTracker tracker;

    update(tracker, true, CURRENT_PRESENT_FLOOR);
    update(tracker, true, CURRENT_PRESENT_FLOOR);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state());
    update(tracker, true, CURRENT_PRESENT_FLOOR);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_ATTACHED, tracker.state());
}

static void test_opposite_evidence_breaks_consecutive_run()
{
    ActuatorAttachmentTracker tracker;

    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);

    // The at-floor sample broke the run, so two have accumulated since: one
    // more latches, which would not be true had the run never reset.
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state());
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state());
}

static void test_idle_breaks_pending_evidence_but_retains_latched_state()
{
    ActuatorAttachmentTracker tracker;

    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, false, 1023);
    // Idle cleared the pending pair: two more must not be enough on their own.
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state());

    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state());

    for (int sample = 0; sample < 10; ++sample)
        update(tracker, false, 1023);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state());
}

static void test_consecutive_present_current_recovers_disconnected_channel()
{
    ActuatorAttachmentTracker tracker;
    for (int sample = 0; sample < REQUIRED_SAMPLES; ++sample)
        update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state());

    update(tracker, true, CURRENT_PRESENT_FLOOR);
    update(tracker, true, CURRENT_PRESENT_FLOOR);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state());
    update(tracker, true, CURRENT_PRESENT_FLOOR);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_ATTACHED, tracker.state());
    TEST_ASSERT_TRUE(tracker.isAttachedOrUnknown());
}

static void test_position_and_current_evidence_both_gate_connection()
{
    ActuatorAttachmentTracker tracker;
    for (int sample = 0; sample < REQUIRED_SAMPLES; ++sample)
        update(tracker, true, CURRENT_PRESENT_FLOOR);

    TEST_ASSERT_TRUE(actuatorConnectionIsValid(true, tracker));
    TEST_ASSERT_FALSE(actuatorConnectionIsValid(false, tracker));

    for (int sample = 0; sample < REQUIRED_SAMPLES; ++sample)
        update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_FALSE(actuatorConnectionIsValid(true, tracker));
    TEST_ASSERT_FALSE(actuatorConnectionIsValid(false, tracker));
}

static void test_zero_required_samples_never_changes_state()
{
    ActuatorAttachmentTracker tracker;
    constexpr ActuatorAttachmentLimits noDebounce = {CURRENT_PRESENT_FLOOR, 0, 0};
    tracker.update(true, 0, noDebounce);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state());
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_boot_unknown_does_not_false_disconnect);
    RUN_TEST(test_idle_current_is_never_attachment_evidence);
    RUN_TEST(test_consecutive_low_driven_current_latches_disconnected);
    RUN_TEST(test_present_threshold_is_inclusive_and_debounced);
    RUN_TEST(test_opposite_evidence_breaks_consecutive_run);
    RUN_TEST(test_idle_breaks_pending_evidence_but_retains_latched_state);
    RUN_TEST(test_consecutive_present_current_recovers_disconnected_channel);
    RUN_TEST(test_position_and_current_evidence_both_gate_connection);
    RUN_TEST(test_zero_required_samples_never_changes_state);
    return UNITY_END();
}
