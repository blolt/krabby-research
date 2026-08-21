#include <stdint.h>

#include "src/power_bus/ina_recovery.h"
#include "unity.h"

namespace
{
constexpr InaRecoveryLimits LIMITS = {3, 2000};
}

void setUp() {}
void tearDown() {}

// A shared I2C bus makes an isolated failure ordinary: the IMU and the display
// are on the same wires. Retrying on the first one would spend bus time on a
// device that is already answering.
static void test_isolated_failures_do_not_trigger_a_retry()
{
    InaRecoveryPolicy policy;
    TEST_ASSERT_FALSE(policy.noteFailure(1000, LIMITS));
    TEST_ASSERT_FALSE(policy.noteFailure(1050, LIMITS));
    TEST_ASSERT_EQUAL_UINT8(2, policy.badTicks());

    policy.noteSuccess();
    TEST_ASSERT_EQUAL_UINT8(0, policy.badTicks());
    // The run was broken, so the next failure starts counting again.
    TEST_ASSERT_FALSE(policy.noteFailure(1100, LIMITS));
}

static void test_consecutive_failures_reach_the_threshold()
{
    InaRecoveryPolicy policy;
    TEST_ASSERT_FALSE(policy.noteFailure(1000, LIMITS));
    TEST_ASSERT_FALSE(policy.noteFailure(1001, LIMITS));
    TEST_ASSERT_TRUE(policy.noteFailure(1002, LIMITS));
}

// A true return means the caller re-initialises, so returning true again for the
// same run of failures would retry twice for one piece of evidence.
static void test_a_triggered_retry_consumes_its_evidence()
{
    InaRecoveryPolicy policy;
    policy.noteFailure(0, LIMITS);
    policy.noteFailure(1, LIMITS);
    TEST_ASSERT_TRUE(policy.noteFailure(2, LIMITS));
    TEST_ASSERT_EQUAL_UINT8(0, policy.badTicks());
}

// The interval brake: a device that is genuinely absent must not be retried on
// every poll once its failure count keeps reaching the threshold.
static void test_interval_holds_off_a_second_attempt()
{
    InaRecoveryPolicy policy;
    policy.noteFailure(1000, LIMITS);
    policy.noteFailure(1000, LIMITS);
    TEST_ASSERT_TRUE(policy.noteFailure(1000, LIMITS));   // first attempt at t=1000

    policy.noteFailure(2999, LIMITS);
    policy.noteFailure(2999, LIMITS);
    // Threshold reached again, but only 1999 ms have passed.
    TEST_ASSERT_FALSE(policy.noteFailure(2999, LIMITS));

    // One more failure, now exactly 2000 ms after the last attempt.
    TEST_ASSERT_TRUE(policy.noteFailure(3000, LIMITS));
}

// millis() wraps every ~49 days. Comparing timestamps directly rather than
// subtracting would compute a vast elapsed time and disable the brake forever.
static void test_elapsed_time_survives_the_millis_rollover()
{
    InaRecoveryPolicy policy;
    const uint32_t beforeWrap = 0xFFFFFF00u;      // 4294967040
    policy.noteFailure(beforeWrap, LIMITS);
    policy.noteFailure(beforeWrap, LIMITS);
    TEST_ASSERT_TRUE(policy.noteFailure(beforeWrap, LIMITS));

    // Wrapped through zero; unsigned subtraction gives 512 ms, not ~4.29e9.
    policy.noteFailure(0x100u, LIMITS);
    policy.noteFailure(0x100u, LIMITS);
    TEST_ASSERT_FALSE(policy.noteFailure(0x100u, LIMITS));

    // beforeWrap + 2000 wraps to 1744, so elapsed is exactly the interval.
    TEST_ASSERT_TRUE(policy.noteFailure(1744u, LIMITS));
}

// Without a "never attempted" flag, a first failure run at millis() near zero
// would look like one that had just retried.
static void test_first_attempt_is_not_blocked_at_boot()
{
    InaRecoveryPolicy policy;
    policy.noteFailure(0, LIMITS);
    policy.noteFailure(0, LIMITS);
    TEST_ASSERT_TRUE(policy.noteFailure(0, LIMITS));
}

// The counter is uint8_t. Without the guard it would wrap 255 -> 0, which reads
// as "the device just started failing" on a device that never came back.
static void test_bad_tick_counter_saturates()
{
    // Threshold at the type's maximum and an interval that never elapses, so
    // after the first attempt nothing can reset the counter.
    const InaRecoveryLimits blocked = {255, 0xFFFFFFFFu};
    InaRecoveryPolicy policy;
    for (int i = 0; i < 255; ++i)
        policy.noteFailure(0, blocked);           // 255th attempt fires, resets
    for (int i = 0; i < 400; ++i)
        policy.noteFailure(1, blocked);           // climbs, then holds
    TEST_ASSERT_EQUAL_UINT8(255, policy.badTicks());
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_isolated_failures_do_not_trigger_a_retry);
    RUN_TEST(test_consecutive_failures_reach_the_threshold);
    RUN_TEST(test_a_triggered_retry_consumes_its_evidence);
    RUN_TEST(test_interval_holds_off_a_second_attempt);
    RUN_TEST(test_elapsed_time_survives_the_millis_rollover);
    RUN_TEST(test_first_attempt_is_not_blocked_at_boot);
    RUN_TEST(test_bad_tick_counter_saturates);
    return UNITY_END();
}
