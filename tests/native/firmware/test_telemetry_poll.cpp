#include <limits>
#include <type_traits>

#include "unity.h"

#include "telemetry_poll.h"

static_assert(
    std::is_same<decltype(TELEMETRY_POLL_INTERVAL), const Milliseconds>::value,
    "telemetry poll interval must retain its unit");

void setUp() {}
void tearDown() {}

static void test_configured_interval_is_50_milliseconds_and_20_hertz()
{
    TEST_ASSERT_EQUAL_UINT32(50U, TELEMETRY_POLL_INTERVAL.value());
    TEST_ASSERT_EQUAL_UINT32(
        20U, 1000U / TELEMETRY_POLL_INTERVAL.value());
}

static void test_initial_poll_obeys_exact_interval_boundary()
{
    TEST_ASSERT_FALSE(telemetryPollDue(0U, 0U));
    TEST_ASSERT_FALSE(telemetryPollDue(49U, 0U));
    TEST_ASSERT_TRUE(telemetryPollDue(50U, 0U));
    TEST_ASSERT_TRUE(telemetryPollDue(51U, 0U));
}

static void test_later_poll_obeys_exact_interval_boundary()
{
    TEST_ASSERT_FALSE(telemetryPollDue(1049U, 1000U));
    TEST_ASSERT_TRUE(telemetryPollDue(1050U, 1000U));
    TEST_ASSERT_TRUE(telemetryPollDue(1051U, 1000U));
}

static void test_poll_interval_is_preserved_across_millis_rollover()
{
    const uint32_t previous = std::numeric_limits<uint32_t>::max() - 24U;

    TEST_ASSERT_FALSE(telemetryPollDue(24U, previous));
    TEST_ASSERT_TRUE(telemetryPollDue(25U, previous));
    TEST_ASSERT_TRUE(telemetryPollDue(26U, previous));
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_configured_interval_is_50_milliseconds_and_20_hertz);
    RUN_TEST(test_initial_poll_obeys_exact_interval_boundary);
    RUN_TEST(test_later_poll_obeys_exact_interval_boundary);
    RUN_TEST(test_poll_interval_is_preserved_across_millis_rollover);
    return UNITY_END();
}
