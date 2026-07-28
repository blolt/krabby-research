#include "unity.h"

#include "disconnect_status.h"

namespace
{
void setAll(bool (&connected)[ACTUATORS_PER_CONTROLLER], bool value)
{
    for (size_t actuator = 0;
         actuator < ACTUATORS_PER_CONTROLLER;
         ++actuator)
        connected[actuator] = value;
}
}

void setUp() {}
void tearDown() {}

static void test_all_eighteen_connected_keeps_led_off()
{
    bool front[6], left[6], right[6];
    setAll(front, true);
    setAll(left, true);
    setAll(right, true);

    TEST_ASSERT_FALSE(disconnectStatusLedActive(
        front, true, left, true, right));
}

static void test_each_of_eighteen_positions_independently_lights_led()
{
    bool front[6], left[6], right[6];
    bool *controllers[] = {front, left, right};
    for (size_t controller = 0; controller < 3; ++controller)
        for (size_t actuator = 0;
             actuator < ACTUATORS_PER_CONTROLLER;
             ++actuator)
        {
            setAll(front, true);
            setAll(left, true);
            setAll(right, true);
            controllers[controller][actuator] = false;
            TEST_ASSERT_TRUE(disconnectStatusLedActive(
                front, true, left, true, right));
        }
}

static void test_multiple_disconnects_remain_active_until_final_recovery()
{
    bool front[6], left[6], right[6];
    setAll(front, true);
    setAll(left, true);
    setAll(right, true);
    front[0] = false;
    right[5] = false;

    TEST_ASSERT_TRUE(disconnectStatusLedActive(
        front, true, left, true, right));
    front[0] = true;
    TEST_ASSERT_TRUE(disconnectStatusLedActive(
        front, true, left, true, right));
    right[5] = true;
    TEST_ASSERT_FALSE(disconnectStatusLedActive(
        front, true, left, true, right));
}

static void test_stale_remote_snapshot_does_not_fabricate_motor_disconnect()
{
    bool front[6], left[6], right[6];
    setAll(front, true);
    setAll(left, false);
    setAll(right, false);

    TEST_ASSERT_FALSE(disconnectStatusLedActive(
        front, false, left, false, right));
    TEST_ASSERT_TRUE(disconnectStatusLedActive(
        front, true, left, false, right));
    TEST_ASSERT_TRUE(disconnectStatusLedActive(
        front, false, left, true, right));
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_all_eighteen_connected_keeps_led_off);
    RUN_TEST(test_each_of_eighteen_positions_independently_lights_led);
    RUN_TEST(test_multiple_disconnects_remain_active_until_final_recovery);
    RUN_TEST(test_stale_remote_snapshot_does_not_fabricate_motor_disconnect);
    return UNITY_END();
}
