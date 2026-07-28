#include <stdio.h>

#include <string>
#include <type_traits>

#include "unity.h"

#include "battery_telemetry.h"

static_assert(
    std::is_same<decltype(BatteryTelemetryFrame::packVoltage), Volts>::value,
    "pack voltage must remain strongly typed");
static_assert(
    std::is_same<decltype(BatteryTelemetryFrame::packCurrent), Amps>::value,
    "pack current must remain strongly typed");
static_assert(
    std::is_same<decltype(BatteryTelemetryFrame::packPower), Watts>::value,
    "pack power must remain strongly typed");
static_assert(
    std::is_same<decltype(BatteryTelemetryFrame::packCharge), Coulombs>::value,
    "pack charge must remain strongly typed");

void setUp() {}
void tearDown() {}

class StringOutput
{
public:
    void print(char value)
    {
        text_ += value;
    }

    void print(const char* value)
    {
        text_ += value;
    }

    void print(float value, int precision)
    {
        char buffer[40];
        snprintf(buffer, sizeof(buffer), "%.*f", precision, value);
        text_ += buffer;
    }

    void print(int value)
    {
        char buffer[16];
        snprintf(buffer, sizeof(buffer), "%d", value);
        text_ += buffer;
    }

    void print(uint8_t value)
    {
        char buffer[16];
        snprintf(buffer, sizeof(buffer), "%u", static_cast<unsigned>(value));
        text_ += buffer;
    }

    const std::string& text() const
    {
        return text_;
    }

private:
    std::string text_;
};

static BatteryTelemetryFrame distinctiveFrame(bool diverged, uint8_t powerState)
{
    const BatteryTelemetryFrame frame = {
        Volts(26.55f),
        Amps(-12.34f),
        Watts(327.6f),
        Coulombs(1450.2f),
        Volts(13.35f),
        Volts(13.20f),
        diverged,
        powerState
    };
    return frame;
}

static BatteryTelemetryFrame frameWithCurrent(float amps)
{
    BatteryTelemetryFrame frame = distinctiveFrame(false, 0);
    frame.packCurrent = Amps(amps);
    return frame;
}

static BatteryTelemetryFrame frameWithPower(float watts)
{
    BatteryTelemetryFrame frame = distinctiveFrame(false, 0);
    frame.packPower = Watts(watts);
    return frame;
}

static BatteryTelemetryFrame frameWithCharge(float coulombs)
{
    BatteryTelemetryFrame frame = distinctiveFrame(false, 0);
    frame.packCharge = Coulombs(coulombs);
    return frame;
}

static BatteryTelemetryFrame frameWithBatteryA(float volts)
{
    BatteryTelemetryFrame frame = distinctiveFrame(false, 0);
    frame.batteryAVoltage = Volts(volts);
    return frame;
}

static BatteryTelemetryFrame frameWithBatteryB(float volts)
{
    BatteryTelemetryFrame frame = distinctiveFrame(false, 0);
    frame.batteryBVoltage = Volts(volts);
    return frame;
}

static void test_serializes_exact_tag_delimiters_order_units_and_precision()
{
    StringOutput out;

    appendBatteryTelemetry(out, distinctiveFrame(false, 0));

    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 0",
        out.text().c_str());
}

static void test_serializes_divergence_and_full_byte_power_state()
{
    StringOutput out;

    appendBatteryTelemetry(out, distinctiveFrame(true, 255));

    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 1 255",
        out.text().c_str());
}

static void test_serializes_positive_zero_and_negative_pack_current_without_sign_change()
{
    StringOutput positive;
    StringOutput zero;
    StringOutput negative;

    appendBatteryTelemetry(positive, frameWithCurrent(12.34f));
    appendBatteryTelemetry(zero, frameWithCurrent(0.0f));
    appendBatteryTelemetry(negative, frameWithCurrent(-12.34f));

    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 12.34 327.6 1450.2 13.35 13.20 0 0",
        positive.text().c_str());
    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 0.00 327.6 1450.2 13.35 13.20 0 0",
        zero.text().c_str());
    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 0",
        negative.text().c_str());
}

static void test_serializes_zero_fractional_and_positive_pack_power_in_watts()
{
    StringOutput zero;
    StringOutput fractional;
    StringOutput positive;

    appendBatteryTelemetry(zero, frameWithPower(0.0f));
    appendBatteryTelemetry(fractional, frameWithPower(0.26f));
    appendBatteryTelemetry(positive, frameWithPower(327.64f));

    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 0.0 1450.2 13.35 13.20 0 0",
        zero.text().c_str());
    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 0.3 1450.2 13.35 13.20 0 0",
        fractional.text().c_str());
    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 0",
        positive.text().c_str());
}

static void test_serializes_positive_zero_and_negative_accumulated_charge()
{
    StringOutput positive;
    StringOutput zero;
    StringOutput negative;

    appendBatteryTelemetry(positive, frameWithCharge(1450.24f));
    appendBatteryTelemetry(zero, frameWithCharge(0.0f));
    appendBatteryTelemetry(negative, frameWithCharge(-1450.24f));

    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 0",
        positive.text().c_str());
    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 0.0 13.35 13.20 0 0",
        zero.text().c_str());
    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 -1450.2 13.35 13.20 0 0",
        negative.text().c_str());
}

static void test_serializes_distinct_battery_a_voltages_as_the_fifth_payload()
{
    StringOutput low;
    StringOutput intermediate;
    StringOutput high;

    appendBatteryTelemetry(low, frameWithBatteryA(12.0f));
    appendBatteryTelemetry(intermediate, frameWithBatteryA(12.73f));
    appendBatteryTelemetry(high, frameWithBatteryA(13.4f));

    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 12.00 13.20 0 0",
        low.text().c_str());
    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 12.73 13.20 0 0",
        intermediate.text().c_str());
    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 13.40 13.20 0 0",
        high.text().c_str());
}

static void test_serializes_distinct_battery_b_voltages_as_the_sixth_payload()
{
    StringOutput low;
    StringOutput intermediate;
    StringOutput high;

    appendBatteryTelemetry(low, frameWithBatteryB(12.0f));
    appendBatteryTelemetry(intermediate, frameWithBatteryB(12.68f));
    appendBatteryTelemetry(high, frameWithBatteryB(13.4f));

    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 12.00 0 0",
        low.text().c_str());
    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 12.68 0 0",
        intermediate.text().c_str());
    TEST_ASSERT_EQUAL_STRING(
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.40 0 0",
        high.text().c_str());
}

static void assertPowerStateSerializes(uint8_t state, const char* expected)
{
    StringOutput out;
    appendBatteryTelemetry(out, distinctiveFrame(false, state));
    TEST_ASSERT_EQUAL_STRING(expected, out.text().c_str());
}

static void test_serializes_every_defined_power_state_as_the_eighth_payload()
{
    assertPowerStateSerializes(
        BATTERY_POWER_NORMAL,
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 0"
    );
    assertPowerStateSerializes(
        BATTERY_POWER_WARN,
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 1"
    );
    assertPowerStateSerializes(
        BATTERY_POWER_SOFT_CUT,
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 2"
    );
    assertPowerStateSerializes(
        BATTERY_POWER_HARD_CUT,
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 3"
    );
    assertPowerStateSerializes(
        BATTERY_POWER_OVER_VOLT,
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 4"
    );
    assertPowerStateSerializes(
        BATTERY_POWER_SLEEP,
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 5"
    );
    assertPowerStateSerializes(
        BATTERY_POWER_RESUMING,
        ";BATT 26.55 -12.34 327.6 1450.2 13.35 13.20 0 6"
    );
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_serializes_exact_tag_delimiters_order_units_and_precision);
    RUN_TEST(test_serializes_divergence_and_full_byte_power_state);
    RUN_TEST(test_serializes_positive_zero_and_negative_pack_current_without_sign_change);
    RUN_TEST(test_serializes_zero_fractional_and_positive_pack_power_in_watts);
    RUN_TEST(test_serializes_positive_zero_and_negative_accumulated_charge);
    RUN_TEST(test_serializes_distinct_battery_a_voltages_as_the_fifth_payload);
    RUN_TEST(test_serializes_distinct_battery_b_voltages_as_the_sixth_payload);
    RUN_TEST(test_serializes_every_defined_power_state_as_the_eighth_payload);
    return UNITY_END();
}
