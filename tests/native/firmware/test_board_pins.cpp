#include "unity.h"

#include "board_pins.h"

void setUp() {}
void tearDown() {}

static void test_default_status_led_pin_is_free_d30()
{
    TEST_ASSERT_EQUAL_INT(30, STATUS_LED_PIN);
    TEST_ASSERT_FALSE(boardPinIsReserved(STATUS_LED_PIN));
}

static void test_serial_pwm_uart_and_i2c_pins_are_reserved()
{
    for (int pin = 0; pin <= 21; ++pin)
        TEST_ASSERT_TRUE(boardPinIsReserved(pin));
}

static void test_all_active_revision_enable_pins_are_reserved()
{
    const int enablePins[] = {
        PIN_S0_EN, PIN_S1_EN, PIN_S2_EN,
        PIN_S3_EN, PIN_S4_EN, PIN_S5_EN
    };
    for (size_t index = 0; index < 6; ++index)
        TEST_ASSERT_TRUE(boardPinIsReserved(enablePins[index]));
}

static void test_orin_gate_and_actuator_analog_aliases_are_reserved()
{
    TEST_ASSERT_TRUE(boardPinIsReserved(38));
    for (int pin = 54; pin <= 65; ++pin)
        TEST_ASSERT_TRUE(boardPinIsReserved(pin));
}

static void test_active_revision_hall_pins_are_reserved()
{
#if KRABBY_PIN_REV == 1
    for (int pin = 32; pin <= 37; ++pin)
        TEST_ASSERT_TRUE(boardPinIsReserved(pin));
#elif KRABBY_PIN_REV == 3
    for (int pin = 50; pin <= 52; ++pin)
        TEST_ASSERT_TRUE(boardPinIsReserved(pin));
    for (int pin = 66; pin <= 68; ++pin)
        TEST_ASSERT_TRUE(boardPinIsReserved(pin));
#endif
}

static void test_representative_unassigned_gpio_remains_available()
{
    const int freePins[] = {29, 30, 31, 39, 40, 49, 53};
    for (size_t index = 0; index < 7; ++index)
        TEST_ASSERT_FALSE(boardPinIsReserved(freePins[index]));
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_default_status_led_pin_is_free_d30);
    RUN_TEST(test_serial_pwm_uart_and_i2c_pins_are_reserved);
    RUN_TEST(test_all_active_revision_enable_pins_are_reserved);
    RUN_TEST(test_orin_gate_and_actuator_analog_aliases_are_reserved);
    RUN_TEST(test_active_revision_hall_pins_are_reserved);
    RUN_TEST(test_representative_unassigned_gpio_remains_available);
    return UNITY_END();
}
