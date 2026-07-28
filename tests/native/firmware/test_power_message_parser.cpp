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

int main()
{
    UNITY_BEGIN();
    RUN_TEST(accepts_only_the_exact_shutdown_ack_line);
    return UNITY_END();
}
