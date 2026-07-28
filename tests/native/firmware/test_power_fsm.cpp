#include <cstring>
#include <limits>
#include <type_traits>

#include "unity.h"

#include "power_fsm.h"

static_assert(!std::is_convertible<float, Volts>::value,
              "raw floats must not implicitly become volts");
static_assert(sizeof(PowerMessageType) == sizeof(uint8_t),
              "the internal power-message discriminant must remain one byte");

void setUp() {}
void tearDown() {}

static PowerFsmResult step(
    PowerState state,
    float voltage,
    bool valid = true,
    uint16_t belowSoft = 0,
    uint16_t belowHard = 0)
{
    return powerFsmStep(
        state, voltage, valid, belowSoft, belowHard);
}

static PowerFsmResult repeat(
    PowerState state,
    float voltage,
    int count,
    bool valid = true)
{
    PowerFsmResult result = {state, 0, 0};
    for (int tick = 0; tick < count; ++tick)
    {
        result = powerFsmStep(
            result.state,
            voltage,
            valid,
            result.belowSoftTicks,
            result.belowHardTicks);
    }
    return result;
}

static void test_warn_named_threshold_and_exact_boundaries()
{
    TEST_ASSERT_EQUAL_FLOAT(
        24.8f, PACK_WARNING_THRESHOLD.value());
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::Normal,
        step(PowerState::Normal, PACK_WARNING_THRESHOLD.value()).state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::Warn,
        step(PowerState::Normal, PACK_WARNING_THRESHOLD.value() - 0.01f).state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::Normal,
        step(PowerState::Warn, PACK_WARNING_THRESHOLD.value()).state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::Warn,
        step(PowerState::Resuming, PACK_WARNING_THRESHOLD.value() - 0.01f).state);
}

static void test_warn_is_telemetry_only_and_does_not_accumulate_soft_cut()
{
    PowerController controller;
    controller.step(PACK_WARNING_THRESHOLD.value() - 0.01f, true);
    TEST_ASSERT_EQUAL_UINT8(PowerState::Warn, controller.state);
    TEST_ASSERT_FALSE(controller.actuatorsParked());
    TEST_ASSERT_EQUAL_UINT16(0, controller.belowSoftTicks);
    TEST_ASSERT_EQUAL_UINT16(0, controller.belowHardTicks);
}

static void test_soft_cut_requires_consecutive_strictly_below_ticks()
{
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::Warn,
        repeat(PowerState::Normal, 23.9f, POWER_CUT_DEBOUNCE_TICKS - 1).state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::SoftCut,
        repeat(PowerState::Normal, 23.9f, POWER_CUT_DEBOUNCE_TICKS).state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::Warn,
        repeat(PowerState::Normal, PACK_SOFT_CUT_THRESHOLD.value(),
               POWER_CUT_DEBOUNCE_TICKS + 1).state);

    PowerFsmResult result =
        repeat(PowerState::Normal, 23.9f, POWER_CUT_DEBOUNCE_TICKS - 1);
    result = powerFsmStep(
        result.state, 24.2f, true,
        result.belowSoftTicks, result.belowHardTicks);
    TEST_ASSERT_EQUAL_UINT16(0, result.belowSoftTicks);
}

static void test_hard_cut_is_inclusive_and_wins_over_soft_cut()
{
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::HardCut,
        repeat(PowerState::Normal, PACK_HARD_CUT_THRESHOLD.value(),
               POWER_CUT_DEBOUNCE_TICKS).state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::SoftCut,
        repeat(PowerState::Normal, PACK_HARD_CUT_THRESHOLD.value() + 0.01f,
               POWER_CUT_DEBOUNCE_TICKS).state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::HardCut,
        repeat(PowerState::Normal, 21.0f, POWER_CUT_DEBOUNCE_TICKS).state);
}

static void test_cut_counters_saturate_and_soft_escalates_but_never_recovers()
{
    PowerFsmResult soft =
        repeat(PowerState::Normal, 23.0f, POWER_CUT_DEBOUNCE_TICKS + 20);
    TEST_ASSERT_EQUAL_UINT16(
        POWER_CUT_DEBOUNCE_TICKS, soft.belowSoftTicks);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::SoftCut,
        step(PowerState::SoftCut, 27.0f).state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::HardCut,
        repeat(PowerState::SoftCut, 21.0f, POWER_CUT_DEBOUNCE_TICKS).state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::HardCut,
        step(PowerState::HardCut, 27.0f).state);
}

static void test_over_voltage_latches_immediately_from_every_nonterminal_state()
{
    const PowerState origins[] = {
        PowerState::Normal, PowerState::Warn, PowerState::SoftCut, PowerState::HardCut,
        PowerState::Sleep, PowerState::Resuming};
    for (size_t index = 0; index < sizeof(origins) / sizeof(origins[0]); ++index)
    {
        TEST_ASSERT_EQUAL_UINT8(
            PowerState::OverVolt,
            step(origins[index], PACK_OVER_VOLT_THRESHOLD.value()).state);
        TEST_ASSERT_NOT_EQUAL(
            PowerState::OverVolt,
            step(origins[index], PACK_OVER_VOLT_THRESHOLD.value() - 0.01f).state);
    }

    TEST_ASSERT_EQUAL_UINT8(
        PowerState::OverVolt,
        step(PowerState::OverVolt, 25.0f, false, 4, 4).state);
}

static void test_sleep_recovery_is_strict_and_routes_through_resuming()
{
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::Sleep, step(PowerState::Sleep, PACK_RECOVERY_THRESHOLD.value()).state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::OverVolt,
        step(PowerState::Sleep, PACK_OVER_VOLT_THRESHOLD.value()).state);
    PowerFsmResult resumed =
        step(PowerState::Sleep, PACK_RECOVERY_THRESHOLD.value() + 0.01f);
    TEST_ASSERT_EQUAL_UINT8(PowerState::Resuming, resumed.state);
    TEST_ASSERT_EQUAL_UINT8(
        PowerState::Normal, step(resumed.state, 27.0f).state);
}

static void test_every_invalid_reading_holds_state_and_resets_all_counters()
{
    const float invalidVoltages[] = {
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity(),
        -0.01f,
        40.01f};
    const PowerState states[] = {
        PowerState::Normal, PowerState::Warn, PowerState::SoftCut, PowerState::HardCut,
        PowerState::Sleep, PowerState::Resuming};

    for (size_t stateIndex = 0;
         stateIndex < sizeof(states) / sizeof(states[0]);
         ++stateIndex)
    {
        for (size_t valueIndex = 0;
             valueIndex < sizeof(invalidVoltages) / sizeof(invalidVoltages[0]);
             ++valueIndex)
        {
            const PowerFsmResult result =
                step(states[stateIndex], invalidVoltages[valueIndex],
                     true, 3, 3);
            TEST_ASSERT_EQUAL_UINT8(states[stateIndex], result.state);
            TEST_ASSERT_EQUAL_UINT16(0, result.belowSoftTicks);
            TEST_ASSERT_EQUAL_UINT16(0, result.belowHardTicks);
        }

        const PowerFsmResult offline =
            step(states[stateIndex], 23.0f, false, 3, 3);
        TEST_ASSERT_EQUAL_UINT8(states[stateIndex], offline.state);
        TEST_ASSERT_EQUAL_UINT16(0, offline.belowSoftTicks);
        TEST_ASSERT_EQUAL_UINT16(0, offline.belowHardTicks);
    }
}

static void test_park_gate_state_codes_and_power_message_tokens()
{
    TEST_ASSERT_EQUAL_UINT8(0, static_cast<uint8_t>(PowerState::Normal));
    TEST_ASSERT_EQUAL_UINT8(1, static_cast<uint8_t>(PowerState::Warn));
    TEST_ASSERT_EQUAL_UINT8(2, static_cast<uint8_t>(PowerState::SoftCut));
    TEST_ASSERT_EQUAL_UINT8(3, static_cast<uint8_t>(PowerState::HardCut));
    TEST_ASSERT_EQUAL_UINT8(4, static_cast<uint8_t>(PowerState::OverVolt));
    TEST_ASSERT_EQUAL_UINT8(5, static_cast<uint8_t>(PowerState::Sleep));
    TEST_ASSERT_EQUAL_UINT8(6, static_cast<uint8_t>(PowerState::Resuming));

    PowerController controller;
    const PowerState states[] = {
        PowerState::Normal,
        PowerState::Warn,
        PowerState::SoftCut,
        PowerState::HardCut,
        PowerState::OverVolt,
        PowerState::Sleep,
        PowerState::Resuming,
    };
    for (size_t index = 0; index < sizeof(states) / sizeof(states[0]); ++index)
    {
        const PowerState state = states[index];
        controller.state = state;
        const bool expected =
            state == PowerState::SoftCut || state == PowerState::HardCut ||
            state == PowerState::OverVolt || state == PowerState::Sleep;
        TEST_ASSERT_EQUAL(expected, controller.actuatorsParked());
    }

    TEST_ASSERT_EQUAL_UINT8(1, POWER_MSG_SCHEMA);
    TEST_ASSERT_EQUAL_STRING(
        "POWERING_DOWN",
        powerMessageTypeToken(PowerMessageType::PoweringDown));
    TEST_ASSERT_EQUAL_STRING(
        "SHUTDOWN_ACK",
        powerMessageTypeToken(PowerMessageType::ShutdownAck));
    TEST_ASSERT_EQUAL_STRING(
        "RESUMING",
        powerMessageTypeToken(PowerMessageType::Resuming));
    TEST_ASSERT_EQUAL_STRING(
        "EMERGENCY_SHUTDOWN",
        powerMessageTypeToken(PowerMessageType::EmergencyShutdown));
    TEST_ASSERT_EQUAL_STRING(
        "under_voltage_soft",
        powerReasonToken(PoweringDownReason::UnderVoltageSoft));
    TEST_ASSERT_EQUAL_STRING(
        "manual",
        powerReasonToken(PoweringDownReason::Manual));
    TEST_ASSERT_EQUAL_STRING(
        "hard_cut",
        powerReasonToken(EmergencyShutdownReason::HardCut));
    TEST_ASSERT_EQUAL_STRING(
        "over_voltage",
        powerReasonToken(EmergencyShutdownReason::OverVoltage));
    TEST_ASSERT_EQUAL_STRING(
        "voltage_recovered",
        powerReasonToken(ResumingReason::VoltageRecovered));
}

static void test_shutdown_ack_is_scoped_to_an_active_graceful_transaction()
{
    PowerController controller;

    const PowerState rejectedStates[] = {
        PowerState::Normal,
        PowerState::Warn,
        PowerState::HardCut,
        PowerState::OverVolt,
        PowerState::Sleep,
        PowerState::Resuming,
    };
    for (size_t index = 0;
         index < sizeof(rejectedStates) / sizeof(rejectedStates[0]);
         ++index)
    {
        controller.state = rejectedStates[index];
        controller.orinCutArmed = true;
        controller.orinPowered = true;
        controller.shutdownAcked = false;
        TEST_ASSERT_FALSE(controller.acceptShutdownAckIfExpected());
        TEST_ASSERT_FALSE(controller.shutdownAcked);
    }

    controller.state = PowerState::SoftCut;
    controller.orinCutArmed = false;
    controller.orinPowered = true;
    TEST_ASSERT_FALSE(controller.acceptShutdownAckIfExpected());

    controller.orinCutArmed = true;
    controller.orinPowered = false;
    TEST_ASSERT_FALSE(controller.acceptShutdownAckIfExpected());

    controller.orinPowered = true;
    TEST_ASSERT_TRUE(controller.acceptShutdownAckIfExpected());
    TEST_ASSERT_TRUE(controller.shutdownAcked);

    // A repeated exact ACK is harmless and remains accepted while the same
    // graceful transaction is active.
    TEST_ASSERT_TRUE(controller.acceptShutdownAckIfExpected());
    TEST_ASSERT_TRUE(controller.shutdownAcked);
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_warn_named_threshold_and_exact_boundaries);
    RUN_TEST(test_warn_is_telemetry_only_and_does_not_accumulate_soft_cut);
    RUN_TEST(test_soft_cut_requires_consecutive_strictly_below_ticks);
    RUN_TEST(test_hard_cut_is_inclusive_and_wins_over_soft_cut);
    RUN_TEST(test_cut_counters_saturate_and_soft_escalates_but_never_recovers);
    RUN_TEST(test_over_voltage_latches_immediately_from_every_nonterminal_state);
    RUN_TEST(test_sleep_recovery_is_strict_and_routes_through_resuming);
    RUN_TEST(test_every_invalid_reading_holds_state_and_resets_all_counters);
    RUN_TEST(test_park_gate_state_codes_and_power_message_tokens);
    RUN_TEST(test_shutdown_ack_is_scoped_to_an_active_graceful_transaction);
    return UNITY_END();
}
