#include <stdint.h>

#include "src/display/display.h"
#include "unity.h"

namespace
{
const char *VALID_LEFT =
    "LEFT ; A 0.1 0 0 1 1 0 30 0; B nan 0 0 0 0 0 0 0;"
    " C 0.2 0 0 1 1 40 0 0; D 0.3 0 0 0 0 0 0 0;"
    " E 0.4 0 0 0 0 0 0 0; F 0.5 0 0 0 0 0 0 0";
}

void setUp() {}
void tearDown() {}

static bool parseAndUpdateControllerDisplayState(
    ControllerDisplayState &state,
    const char *line,
    const char *expectedRole,
    int moveThreshold,
    uint32_t nowMilliseconds)
{
    ActuatorTelemetry actuators[CONTROLLER_ACTUATOR_COUNT];
    if (!parseActuatorTelemetry(line, expectedRole, actuators))
        return false;
    updateControllerDisplayState(
        state, actuators, moveThreshold, nowMilliseconds);
    return true;
}

// A follower running the previous firmware sends nine fields. Absence means the
// sender cannot report evidence, not that it has none, so the channel must not
// be pinned Unverified forever on an image that will never supply the field.
static void test_nine_field_segment_reads_as_verified()
{
    ActuatorTelemetry actuators[CONTROLLER_ACTUATOR_COUNT];
    TEST_ASSERT_TRUE(parseActuatorTelemetry(VALID_LEFT, "LEFT ", actuators));
    for (size_t i = 0; i < CONTROLLER_ACTUATOR_COUNT; ++i)
        TEST_ASSERT_TRUE(actuators[i].attachmentVerified);
}

static void test_tenth_field_carries_attachment_evidence()
{
    const char *line =
        "LEFT ; A 0.1 0 0 1 1 0 30 0 0; B 0.2 0 0 0 0 0 0 0 1;"
        " C 0.2 0 0 1 1 40 0 0 0; D 0.3 0 0 0 0 0 0 0 1;"
        " E 0.4 0 0 0 0 0 0 0 0; F 0.5 0 0 0 0 0 0 0 1";
    ActuatorTelemetry actuators[CONTROLLER_ACTUATOR_COUNT];
    TEST_ASSERT_TRUE(parseActuatorTelemetry(line, "LEFT ", actuators));
    TEST_ASSERT_FALSE(actuators[0].attachmentVerified);
    TEST_ASSERT_TRUE(actuators[1].attachmentVerified);
    TEST_ASSERT_FALSE(actuators[4].attachmentVerified);
    TEST_ASSERT_TRUE(actuators[5].attachmentVerified);
}

// A field of the wrong width would otherwise be read by its first character, so
// "10" would parse as unverified rather than as corruption.
static void test_multi_character_attachment_field_is_rejected()
{
    const char *line =
        "LEFT ; A 0.1 0 0 1 1 0 30 0 10; B 0.2 0 0 0 0 0 0 0 1;"
        " C 0.2 0 0 1 1 40 0 0 0; D 0.3 0 0 0 0 0 0 0 1;"
        " E 0.4 0 0 0 0 0 0 0 0; F 0.5 0 0 0 0 0 0 0 1";
    ActuatorTelemetry actuators[CONTROLLER_ACTUATOR_COUNT];
    TEST_ASSERT_FALSE(parseActuatorTelemetry(line, "LEFT ", actuators));
}

// Eleven fields is not a newer sender to be tolerated; it is a framing error,
// and accepting it would let a corrupted line set display state.
static void test_eleven_field_segment_is_rejected()
{
    const char *line =
        "LEFT ; A 0.1 0 0 1 1 0 30 0 1 9; B 0.2 0 0 0 0 0 0 0 1;"
        " C 0.2 0 0 1 1 40 0 0 0; D 0.3 0 0 0 0 0 0 0 1;"
        " E 0.4 0 0 0 0 0 0 0 0; F 0.5 0 0 0 0 0 0 0 1";
    ActuatorTelemetry actuators[CONTROLLER_ACTUATOR_COUNT];
    TEST_ASSERT_FALSE(parseActuatorTelemetry(line, "LEFT ", actuators));
}

// The wire field has to reach the glyph, not just the struct: a follower with no
// evidence must render the hollow ring the leader would render for itself.
static void test_unverified_follower_channel_renders_unverified()
{
    const char *line =
        "LEFT ; A 0.1 0 0 0 0 0 0 0 0; B 0.2 0 0 0 0 0 0 0 1;"
        " C 0.2 0 0 0 0 0 0 0 0; D 0.3 0 0 0 0 0 0 0 1;"
        " E 0.4 0 0 0 0 0 0 0 0; F 0.5 0 0 0 0 0 0 0 1";
    ControllerDisplayState state;
    TEST_ASSERT_TRUE(parseAndUpdateControllerDisplayState(
        state, line, "LEFT ", 20, 1000));
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Unverified, (int)state.glyphs[0]);
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Hold, (int)state.glyphs[1]);
}

static void test_glyph_boundaries_and_disconnection()
{
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Disconnected,
        (int)actuatorGlyphForCommandedDrive(false, 255, 20, true));
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Hold,
        (int)actuatorGlyphForCommandedDrive(true, 19, 20, true));
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Extend,
        (int)actuatorGlyphForCommandedDrive(true, 20, 20, true));
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Retract,
        (int)actuatorGlyphForCommandedDrive(true, -20, 20, true));
}

static void test_unverified_attachment_is_distinct_from_hold()
{
    // Idle with no evidence yet: not disconnected, but not a confirmed hold.
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Unverified,
        (int)actuatorGlyphForCommandedDrive(true, 0, 20, false));
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Unverified,
        (int)actuatorGlyphForCommandedDrive(true, 19, 20, false));

    // Driving is what produces the evidence, so motion still wins while pending.
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Extend,
        (int)actuatorGlyphForCommandedDrive(true, 20, 20, false));
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Retract,
        (int)actuatorGlyphForCommandedDrive(true, -20, 20, false));

    // A disconnected verdict outranks a missing one.
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Disconnected,
        (int)actuatorGlyphForCommandedDrive(false, 0, 20, false));
}

static void test_controller_update_is_transactional_and_decodes_all_states()
{
    ControllerDisplayState state;
    TEST_ASSERT_TRUE(parseAndUpdateControllerDisplayState(
        state, VALID_LEFT, "LEFT ", 20, 1000));
    TEST_ASSERT_TRUE(state.seen);
    TEST_ASSERT_EQUAL_UINT32(1000, state.lastTelemetryMilliseconds);
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Extend, (int)state.glyphs[0]);
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Disconnected, (int)state.glyphs[1]);
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Retract, (int)state.glyphs[2]);
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Hold, (int)state.glyphs[3]);

    TEST_ASSERT_FALSE(parseAndUpdateControllerDisplayState(
        state, "LEFT ; A 0 0", "LEFT ", 20, 2000));
    TEST_ASSERT_EQUAL_UINT32(1000, state.lastTelemetryMilliseconds);
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Extend, (int)state.glyphs[0]);
}

static void test_invalid_pwm_and_conflicting_directions_are_rejected()
{
    ControllerDisplayState state;
    const char *outOfRange =
        "LEFT ; A 0 0 0 0 0 0 256 0; B 0 0 0 0 0 0 0 0;"
        " C 0 0 0 0 0 0 0 0; D 0 0 0 0 0 0 0 0;"
        " E 0 0 0 0 0 0 0 0; F 0 0 0 0 0 0 0 0";
    const char *bothDirections =
        "LEFT ; A 0 0 0 0 0 1 1 0; B 0 0 0 0 0 0 0 0;"
        " C 0 0 0 0 0 0 0 0; D 0 0 0 0 0 0 0 0;"
        " E 0 0 0 0 0 0 0 0; F 0 0 0 0 0 0 0 0";
    TEST_ASSERT_FALSE(parseAndUpdateControllerDisplayState(
        state, outOfRange, "LEFT ", 20, 1));
    TEST_ASSERT_FALSE(parseAndUpdateControllerDisplayState(
        state, bothDirections, "LEFT ", 20, 1));
    TEST_ASSERT_FALSE(state.seen);
}

static void test_freshness_boundary_assignment_and_rollover()
{
    ControllerDisplayState state;
    TEST_ASSERT_FALSE(isControllerDisplayStateFresh(state, true, 0));
    TEST_ASSERT_TRUE(parseAndUpdateControllerDisplayState(
        state, VALID_LEFT, "LEFT ", 20, UINT32_MAX - 100));
    TEST_ASSERT_TRUE(isControllerDisplayStateFresh(state, true, 398));
    TEST_ASSERT_FALSE(isControllerDisplayStateFresh(state, true, 399));
    TEST_ASSERT_FALSE(isControllerDisplayStateFresh(state, false, UINT32_MAX - 100));
}

static void test_leg_mapping_disconnect_scan_and_model_equality()
{
    StatusDisplayModel model;
    ActuatorGlyph glyphs[6] = {
        ActuatorGlyph::Hold, ActuatorGlyph::Extend, ActuatorGlyph::Retract,
        ActuatorGlyph::Disconnected, ActuatorGlyph::Hold, ActuatorGlyph::Extend};
    setControllerDisplayLegs(model, 4, 2, glyphs);
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Hold, (int)model.legs[4][0]);
    TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Disconnected, (int)model.legs[2][0]);

    bool connected[6] = {true, true, true, true, true, true};
    TEST_ASSERT_FALSE(hasDisconnectedActuator(connected));
    connected[5] = false;
    TEST_ASSERT_TRUE(hasDisconnectedActuator(connected));

    StatusDisplayModel sameModel = model;
    TEST_ASSERT_TRUE(statusDisplayModelsEqual(model, sameModel));
    model.pitch = Degrees(1.0f);
    TEST_ASSERT_FALSE(statusDisplayModelsEqual(model, sameModel));

    // Battery is a Task 3 placeholder, so a change to it is the one difference
    // that could otherwise pass the redraw check unnoticed.
    StatusDisplayModel batteryChanged = sameModel;
    batteryChanged.batteryLevel[1] = 0.5f;
    TEST_ASSERT_FALSE(statusDisplayModelsEqual(sameModel, batteryChanged));
}

static ImuMeasurement accelerationSample(float ax, float ay, float az)
{
    ImuMeasurement measurement{true};
    measurement.acceleration[0] = MetersPerSecondSquared(ax);
    measurement.acceleration[1] = MetersPerSecondSquared(ay);
    measurement.acceleration[2] = MetersPerSecondSquared(az);
    return measurement;
}

static ControllerDisplayState peerState(
    ActuatorGlyph glyph, bool connected, uint32_t atMilliseconds)
{
    ControllerDisplayState state;
    for (size_t actuator = 0; actuator < CONTROLLER_ACTUATOR_COUNT; ++actuator)
    {
        state.glyphs[actuator] = glyph;
        state.connected[actuator] = connected;
    }
    state.seen = true;
    state.lastTelemetryMilliseconds = atMilliseconds;
    return state;
}

static void test_tilt_matches_known_orientations()
{
    const float g = METERS_PER_SECOND_SQUARED_PER_G;

    TEST_ASSERT_EQUAL_FLOAT(0.0f, tiltRoll(accelerationSample(0, 0, g)).value);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, tiltPitch(accelerationSample(0, 0, g)).value);

    TEST_ASSERT_EQUAL_FLOAT(90.0f, tiltRoll(accelerationSample(0, g, 0)).value);
    TEST_ASSERT_EQUAL_FLOAT(-90.0f, tiltRoll(accelerationSample(0, -g, 0)).value);
    TEST_ASSERT_EQUAL_FLOAT(180.0f, tiltRoll(accelerationSample(0, 0, -g)).value);

    TEST_ASSERT_EQUAL_FLOAT(90.0f, tiltPitch(accelerationSample(-g, 0, 0)).value);
    TEST_ASSERT_EQUAL_FLOAT(-90.0f, tiltPitch(accelerationSample(g, 0, 0)).value);

    // Pitch uses the magnitude of the y/z pair, so rolling does not tilt it.
    TEST_ASSERT_EQUAL_FLOAT(0.0f, tiltPitch(accelerationSample(0, g, 0)).value);

    const float diagonal = g * 0.70710678f;
    TEST_ASSERT_EQUAL_FLOAT(
        45.0f, tiltRoll(accelerationSample(0, diagonal, diagonal)).value);
}

static void test_tilt_is_rounded_to_whole_degrees()
{
    // atan2(0.1, 1.0) is 5.71 degrees; halves round away from zero.
    const Degrees positive = tiltRoll(accelerationSample(0, 0.1f, 1.0f));
    const Degrees negative = tiltRoll(accelerationSample(0, -0.1f, 1.0f));
    TEST_ASSERT_EQUAL_FLOAT(6.0f, positive.value);
    TEST_ASSERT_EQUAL_FLOAT(-6.0f, negative.value);

    // statusDisplayModelsEqual() compares angles exactly, so the value must
    // carry no fractional part at all.
    TEST_ASSERT_EQUAL_FLOAT(positive.value, (float)(long)positive.value);
    TEST_ASSERT_EQUAL_FLOAT(negative.value, (float)(long)negative.value);
}

static void test_every_role_has_a_label()
{
    TEST_ASSERT_EQUAL_STRING("FRONT", statusDisplayRoleLabel(StatusDisplayRole::Front));
    TEST_ASSERT_EQUAL_STRING("LEFT", statusDisplayRoleLabel(StatusDisplayRole::Left));
    TEST_ASSERT_EQUAL_STRING("RIGHT", statusDisplayRoleLabel(StatusDisplayRole::Right));
    TEST_ASSERT_EQUAL_STRING("UNKWN", statusDisplayRoleLabel(StatusDisplayRole::Unknown));
}

static void test_disconnect_scan_ignores_stale_peers()
{
    bool localConnected[CONTROLLER_ACTUATOR_COUNT] = {
        true, true, true, true, true, true};
    const ControllerDisplayState wired = peerState(ActuatorGlyph::Hold, true, 0);
    const ControllerDisplayState unplugged =
        peerState(ActuatorGlyph::Disconnected, false, 0);

    TEST_ASSERT_FALSE(
        anyActuatorDisconnected(localConnected, wired, true, wired, true));

    // A peer reporting a disconnect only counts while its telemetry is fresh.
    TEST_ASSERT_FALSE(
        anyActuatorDisconnected(localConnected, unplugged, false, wired, true));
    TEST_ASSERT_TRUE(
        anyActuatorDisconnected(localConnected, unplugged, true, wired, true));
    TEST_ASSERT_FALSE(
        anyActuatorDisconnected(localConnected, wired, true, unplugged, false));
    TEST_ASSERT_TRUE(
        anyActuatorDisconnected(localConnected, wired, true, unplugged, true));

    // A local disconnect stands on its own, with no peer assigned.
    localConnected[3] = false;
    TEST_ASSERT_TRUE(
        anyActuatorDisconnected(localConnected, wired, false, wired, false));
}

static void test_model_maps_legs_by_peer_freshness()
{
    ActuatorGlyph localGlyphs[CONTROLLER_ACTUATOR_COUNT];
    for (size_t actuator = 0; actuator < CONTROLLER_ACTUATOR_COUNT; ++actuator)
        localGlyphs[actuator] = ActuatorGlyph::Hold;

    const uint32_t now = 1000;
    const ControllerDisplayState left =
        peerState(ActuatorGlyph::Extend, true, now - 100);
    const ControllerDisplayState right =
        peerState(ActuatorGlyph::Retract, true, now - 900);

    const StatusDisplayModel model = buildStatusDisplayModel(
        StatusDisplayRole::Front, true, localGlyphs,
        left, true, right, true,
        accelerationSample(0, 0, METERS_PER_SECOND_SQUARED_PER_G), now);

    TEST_ASSERT_EQUAL_INT((int)StatusDisplayRole::Front, (int)model.role);
    TEST_ASSERT_TRUE(model.frontPresent);
    TEST_ASSERT_TRUE(model.leftPresent);
    TEST_ASSERT_FALSE(model.rightPresent);

    for (size_t joint = 0; joint < STATUS_DISPLAY_JOINTS_PER_LEG; ++joint)
    {
        TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Hold, (int)model.legs[0][joint]);
        TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Hold, (int)model.legs[1][joint]);
        // Fresh peer supplies its own glyphs.
        TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Extend, (int)model.legs[4][joint]);
        TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Extend, (int)model.legs[2][joint]);
        // Stale peer is drawn disconnected, not with its last known glyphs.
        TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Disconnected, (int)model.legs[5][joint]);
        TEST_ASSERT_EQUAL_INT((int)ActuatorGlyph::Disconnected, (int)model.legs[3][joint]);
    }
}

static void test_model_keeps_last_tilt_when_the_sample_is_invalid()
{
    ActuatorGlyph localGlyphs[CONTROLLER_ACTUATOR_COUNT];
    for (size_t actuator = 0; actuator < CONTROLLER_ACTUATOR_COUNT; ++actuator)
        localGlyphs[actuator] = ActuatorGlyph::Hold;
    const ControllerDisplayState peer = peerState(ActuatorGlyph::Hold, true, 0);

    // Rolled 90 degrees, but the read failed, so the angle must not be used.
    ImuMeasurement failed =
        accelerationSample(0, METERS_PER_SECOND_SQUARED_PER_G, 0);
    failed.valid = false;
    TEST_ASSERT_FALSE(failed.succeeded());

    const StatusDisplayModel model = buildStatusDisplayModel(
        StatusDisplayRole::Left, false, localGlyphs,
        peer, false, peer, false, failed, 0);

    TEST_ASSERT_EQUAL_FLOAT(0.0f, model.roll.value);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, model.pitch.value);
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_nine_field_segment_reads_as_verified);
    RUN_TEST(test_tenth_field_carries_attachment_evidence);
    RUN_TEST(test_multi_character_attachment_field_is_rejected);
    RUN_TEST(test_eleven_field_segment_is_rejected);
    RUN_TEST(test_unverified_follower_channel_renders_unverified);
    RUN_TEST(test_glyph_boundaries_and_disconnection);
    RUN_TEST(test_unverified_attachment_is_distinct_from_hold);
    RUN_TEST(test_controller_update_is_transactional_and_decodes_all_states);
    RUN_TEST(test_invalid_pwm_and_conflicting_directions_are_rejected);
    RUN_TEST(test_freshness_boundary_assignment_and_rollover);
    RUN_TEST(test_leg_mapping_disconnect_scan_and_model_equality);
    RUN_TEST(test_tilt_matches_known_orientations);
    RUN_TEST(test_tilt_is_rounded_to_whole_degrees);
    RUN_TEST(test_every_role_has_a_label);
    RUN_TEST(test_disconnect_scan_ignores_stale_peers);
    RUN_TEST(test_model_maps_legs_by_peer_freshness);
    RUN_TEST(test_model_keeps_last_tilt_when_the_sample_is_invalid);
    return UNITY_END();
}
