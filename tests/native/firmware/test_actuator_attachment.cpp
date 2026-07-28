#include "unity.h"

#include "actuator_attachment.h"

namespace
{
const int CURRENT_PRESENT_FLOOR = 50;
const uint8_t REQUIRED_SAMPLES = 3;

void update(
    ActuatorAttachmentTracker &tracker,
    bool usable,
    int current)
{
    tracker.update(
        usable,
        current,
        CURRENT_PRESENT_FLOOR,
        REQUIRED_SAMPLES);
}
}

void setUp() {}
void tearDown() {}

static void test_boot_unknown_does_not_false_disconnect()
{
    ActuatorAttachmentTracker tracker;

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state);
    TEST_ASSERT_TRUE(tracker.isAttachedOrUnknown());
    TEST_ASSERT_TRUE(actuatorConnectionIsValid(true, tracker));
    TEST_ASSERT_FALSE(actuatorConnectionIsValid(false, tracker));
}

static void test_idle_current_is_never_attachment_evidence()
{
    ActuatorAttachmentTracker tracker;

    for (int sample = 0; sample < 10; ++sample)
        update(tracker, false, 0);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state);
    TEST_ASSERT_EQUAL_UINT8(0, tracker.disconnectedEvidenceCount);
}

static void test_consecutive_low_driven_current_latches_disconnected()
{
    ActuatorAttachmentTracker tracker;

    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state);
    TEST_ASSERT_FALSE(tracker.isAttachedOrUnknown());
}

static void test_present_threshold_is_inclusive_and_debounced()
{
    ActuatorAttachmentTracker tracker;

    update(tracker, true, CURRENT_PRESENT_FLOOR);
    update(tracker, true, CURRENT_PRESENT_FLOOR);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state);
    update(tracker, true, CURRENT_PRESENT_FLOOR);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_ATTACHED, tracker.state);
}

static void test_opposite_evidence_breaks_consecutive_run()
{
    ActuatorAttachmentTracker tracker;

    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state);
    TEST_ASSERT_EQUAL_UINT8(2, tracker.disconnectedEvidenceCount);
}

static void test_idle_breaks_pending_evidence_but_retains_latched_state()
{
    ActuatorAttachmentTracker tracker;

    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, false, 1023);
    TEST_ASSERT_EQUAL_UINT8(0, tracker.disconnectedEvidenceCount);

    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state);

    for (int sample = 0; sample < 10; ++sample)
        update(tracker, false, 1023);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state);
}

static void test_consecutive_present_current_recovers_disconnected_channel()
{
    ActuatorAttachmentTracker tracker;
    for (int sample = 0; sample < REQUIRED_SAMPLES; ++sample)
        update(tracker, true, CURRENT_PRESENT_FLOOR - 1);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state);

    update(tracker, true, CURRENT_PRESENT_FLOOR);
    update(tracker, true, CURRENT_PRESENT_FLOOR);
    TEST_ASSERT_EQUAL_INT(ATTACHMENT_DISCONNECTED, tracker.state);
    update(tracker, true, CURRENT_PRESENT_FLOOR);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_ATTACHED, tracker.state);
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
    tracker.update(true, 0, CURRENT_PRESENT_FLOOR, 0);

    TEST_ASSERT_EQUAL_INT(ATTACHMENT_UNKNOWN, tracker.state);
    TEST_ASSERT_EQUAL_UINT8(0, tracker.attachedEvidenceCount);
    TEST_ASSERT_EQUAL_UINT8(0, tracker.disconnectedEvidenceCount);
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
