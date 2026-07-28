#include <stdint.h>

#include "controller_freshness.h"
#include "unity.h"

static const uint32_t CONTROLLER_TIMEOUT_MS = 500;
static const char *LEFT_TELEMETRY =
    "LEFT ; A 0 0 0 0 0 0 0 0; B 0 0 0 0 0 0 0 0;"
    " C 0 0 0 0 0 0 0 0; D 0 0 0 0 0 0 0 0;"
    " E 0 0 0 0 0 0 0 0; F nan 0 0 0 0 0 0 0";
static const char *RIGHT_TELEMETRY =
    "RIGHT; A 0 0 0 0 0 0 0 0; B 0 0 0 0 0 0 0 0;"
    " C 0 0 0 0 0 0 0 0; D 0 0 0 0 0 0 0 0;"
    " E 0 0 0 0 0 0 0 0; F 0 0 0 0 0 0 0 0";

void setUp() {}
void tearDown() {}

static void test_never_seen_and_unassigned_controllers_are_not_fresh() {
    ControllerTelemetryFreshness freshness = {false, 0};
    TEST_ASSERT_FALSE(
        controllerTelemetryIsFresh(
            true, freshness, 0, CONTROLLER_TIMEOUT_MS
        )
    );

    noteControllerTelemetry(freshness, 1000);
    TEST_ASSERT_FALSE(
        controllerTelemetryIsFresh(
            false, freshness, 1000, CONTROLLER_TIMEOUT_MS
        )
    );
}

static void test_freshness_timeout_is_exclusive_at_500_ms() {
    ControllerTelemetryFreshness freshness = {false, 0};
    noteControllerTelemetry(freshness, 1000);

    TEST_ASSERT_TRUE(
        controllerTelemetryIsFresh(
            true, freshness, 1000, CONTROLLER_TIMEOUT_MS
        )
    );
    TEST_ASSERT_TRUE(
        controllerTelemetryIsFresh(
            true, freshness, 1499, CONTROLLER_TIMEOUT_MS
        )
    );
    TEST_ASSERT_FALSE(
        controllerTelemetryIsFresh(
            true, freshness, 1500, CONTROLLER_TIMEOUT_MS
        )
    );
    TEST_ASSERT_FALSE(
        controllerTelemetryIsFresh(
            true, freshness, 1501, CONTROLLER_TIMEOUT_MS
        )
    );
}

static void test_freshness_handles_unsigned_clock_rollover() {
    ControllerTelemetryFreshness freshness = {false, 0};
    noteControllerTelemetry(freshness, UINT32_MAX - 100);
    TEST_ASSERT_TRUE(
        controllerTelemetryIsFresh(
            true, freshness, 50, CONTROLLER_TIMEOUT_MS
        )
    );
    TEST_ASSERT_FALSE(
        controllerTelemetryIsFresh(
            true, freshness, 399, CONTROLLER_TIMEOUT_MS
        )
    );
}

static void test_complete_expected_telemetry_qualifies() {
    TEST_ASSERT_TRUE(
        isExpectedControllerTelemetry(LEFT_TELEMETRY, "LEFT ")
    );
    TEST_ASSERT_TRUE(
        isExpectedControllerTelemetry(RIGHT_TELEMETRY, "RIGHT")
    );
}

static void test_non_telemetry_and_wrong_role_lines_do_not_qualify() {
    TEST_ASSERT_FALSE(isExpectedControllerTelemetry("", "LEFT "));
    TEST_ASSERT_FALSE(isExpectedControllerTelemetry("LEFT ", "LEFT "));
    TEST_ASSERT_FALSE(
        isExpectedControllerTelemetry("LEFT diagnostic", "LEFT ")
    );
    TEST_ASSERT_FALSE(
        isExpectedControllerTelemetry(RIGHT_TELEMETRY, "LEFT ")
    );
    TEST_ASSERT_FALSE(
        isExpectedControllerTelemetry("VER 1.2.3", "LEFT ")
    );
    TEST_ASSERT_FALSE(
        isExpectedControllerTelemetry("ROLE_HINT: LEFT", "LEFT ")
    );
    TEST_ASSERT_FALSE(
        isExpectedControllerTelemetry("J FLHY 50", "LEFT ")
    );
    TEST_ASSERT_FALSE(isExpectedControllerTelemetry(nullptr, "LEFT "));
    TEST_ASSERT_FALSE(
        isExpectedControllerTelemetry("LEFT ; data", nullptr)
    );
}

static void test_incomplete_joint_or_field_sets_do_not_qualify() {
    TEST_ASSERT_FALSE(isExpectedControllerTelemetry(
        "LEFT ; A 0 0 0 0 0 0 0 0", "LEFT "
    ));
    TEST_ASSERT_FALSE(isExpectedControllerTelemetry(
        "LEFT ; A 0 0 0 0 0 0 0; B 0 0 0 0 0 0 0 0;"
        " C 0 0 0 0 0 0 0 0; D 0 0 0 0 0 0 0 0;"
        " E 0 0 0 0 0 0 0 0; F 0 0 0 0 0 0 0 0",
        "LEFT "
    ));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_never_seen_and_unassigned_controllers_are_not_fresh);
    RUN_TEST(test_freshness_timeout_is_exclusive_at_500_ms);
    RUN_TEST(test_freshness_handles_unsigned_clock_rollover);
    RUN_TEST(test_complete_expected_telemetry_qualifies);
    RUN_TEST(test_non_telemetry_and_wrong_role_lines_do_not_qualify);
    RUN_TEST(test_incomplete_joint_or_field_sets_do_not_qualify);
    return UNITY_END();
}
