#include <unity.h>

#include "power_message_parser.h"

void setUp() {}
void tearDown() {}

static void accepts_only_the_exact_shutdown_ack_line()
{
    TEST_ASSERT_TRUE(powerIsShutdownAckLine("PWR 1 SHUTDOWN_ACK"));
    TEST_ASSERT_TRUE(powerIsShutdownAckLine("PWR 1 SHUTDOWN_ACK\r"));

    TEST_ASSERT_FALSE(powerIsShutdownAckLine(nullptr));
    TEST_ASSERT_FALSE(powerIsShutdownAckLine(""));
    TEST_ASSERT_FALSE(powerIsShutdownAckLine("PWR 2 SHUTDOWN_ACK"));
    TEST_ASSERT_FALSE(powerIsShutdownAckLine("PWR 1 SHUTDOWN_ACK extra"));
    TEST_ASSERT_FALSE(powerIsShutdownAckLine("PWR 1 POWERING_DOWN SHUTDOWN_ACK"));
    TEST_ASSERT_FALSE(powerIsShutdownAckLine("XPWR 1 SHUTDOWN_ACK"));
    TEST_ASSERT_FALSE(powerIsShutdownAckLine("PWR 1 SHUTDOWN_ACKNOWLEDGED"));
}

static void accepts_only_the_exact_payload_after_prefix_dispatch()
{
    TEST_ASSERT_TRUE(powerIsShutdownAckPayload("WR 1 SHUTDOWN_ACK"));
    TEST_ASSERT_TRUE(powerIsShutdownAckPayload("WR 1 SHUTDOWN_ACK\r"));

    TEST_ASSERT_FALSE(powerIsShutdownAckPayload(nullptr));
    TEST_ASSERT_FALSE(powerIsShutdownAckPayload("PWR 1 SHUTDOWN_ACK"));
    TEST_ASSERT_FALSE(powerIsShutdownAckPayload("WR 2 SHUTDOWN_ACK"));
    TEST_ASSERT_FALSE(powerIsShutdownAckPayload("WR 1 SHUTDOWN_ACK extra"));
    TEST_ASSERT_FALSE(powerIsShutdownAckPayload(" CAL SHOW"));
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(accepts_only_the_exact_shutdown_ack_line);
    RUN_TEST(accepts_only_the_exact_payload_after_prefix_dispatch);
    return UNITY_END();
}
