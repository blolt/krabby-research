#include "unity.h"

#include "oled_actuator_glyphs.h"

namespace
{
const int MOVE_THRESHOLD = 5;
const int GLYPH_SIZE = 9;

struct RecordedLine
{
    int x0;
    int y0;
    int x1;
    int y1;
};

struct RecordingDisplay
{
    RecordedLine lines[16];
    struct RecordedPixel
    {
        int x;
        int y;
    } pixels[96];
    size_t lineCount;
    size_t pixelCount;

    RecordingDisplay() : lineCount(0), pixelCount(0) {}

    void line(int x0, int y0, int x1, int y1)
    {
        TEST_ASSERT_LESS_THAN(16, lineCount);
        lines[lineCount++] = {x0, y0, x1, y1};
    }

    void pixel(int x, int y)
    {
        TEST_ASSERT_LESS_THAN(96, pixelCount);
        pixels[pixelCount] = {x, y};
        ++pixelCount;
    }

    bool hasPixel(int x, int y) const
    {
        for (size_t index = 0; index < pixelCount; ++index)
            if (pixels[index].x == x && pixels[index].y == y)
                return true;
        return false;
    }

    bool isLit(int x, int y) const
    {
        if (hasPixel(x, y))
            return true;

        for (size_t index = 0; index < lineCount; ++index)
        {
            const RecordedLine &candidate = lines[index];
            const int dx = candidate.x1 - candidate.x0;
            const int dy = candidate.y1 - candidate.y0;
            const int pointDx = x - candidate.x0;
            const int pointDy = y - candidate.y0;
            const bool collinear = pointDx * dy == pointDy * dx;
            const bool inX =
                x >= (candidate.x0 < candidate.x1 ? candidate.x0 : candidate.x1) &&
                x <= (candidate.x0 > candidate.x1 ? candidate.x0 : candidate.x1);
            const bool inY =
                y >= (candidate.y0 < candidate.y1 ? candidate.y0 : candidate.y1) &&
                y <= (candidate.y0 > candidate.y1 ? candidate.y0 : candidate.y1);
            if (collinear && inX && inY)
                return true;
        }
        return false;
    }
};

const char *const SIX_STATE_LINE =
    "LEFT ;"
    " RLHY 0.100 100 1 1 1 0 5 0;"
    " RLHL 0.200 200 2 1 1 5 0 0;"
    " RLKL 0.300 300 3 1 1 0 0 0;"
    " MLHY nan 400 4 1 1 0 255 0;"
    " MLHL 0.500 500 5 1 1 0 4 0;"
    " MLKL 0.600 600 6 1 1 4 0 0";

void assertGlyphs(
    const OledGlyph (&actual)[6],
    const OledGlyph (&expected)[6])
{
    for (size_t index = 0; index < 6; ++index)
        TEST_ASSERT_EQUAL_INT(expected[index], actual[index]);
}
}

void setUp() {}
void tearDown() {}

static void assertTriangleRows(
    OledGlyph glyph,
    const int (&expectedHalfWidths)[7])
{
    const int centerX = 20;
    const int centerY = 10;
    RecordingDisplay display;

    drawOledActuatorGlyph(
        display, centerX, centerY, glyph, GLYPH_SIZE);

    TEST_ASSERT_EQUAL_UINT(7, display.lineCount);
    TEST_ASSERT_EQUAL_UINT(0, display.pixelCount);
    for (size_t row = 0; row < display.lineCount; ++row)
    {
        TEST_ASSERT_EQUAL_INT(centerX - expectedHalfWidths[row], display.lines[row].x0);
        TEST_ASSERT_EQUAL_INT(centerY - 3 + (int)row, display.lines[row].y0);
        TEST_ASSERT_EQUAL_INT(centerX + expectedHalfWidths[row], display.lines[row].x1);
        TEST_ASSERT_EQUAL_INT(centerY - 3 + (int)row, display.lines[row].y1);
    }
}

static void test_production_extend_renderer_draws_apex_up_triangle()
{
    const int expectedHalfWidths[7] = {0, 0, 1, 1, 2, 2, 3};
    assertTriangleRows(OG_EXTEND, expectedHalfWidths);
}

static void test_production_retract_renderer_draws_apex_down_triangle()
{
    const int expectedHalfWidths[7] = {3, 2, 2, 1, 1, 0, 0};
    assertTriangleRows(OG_RETRACT, expectedHalfWidths);
}

static void test_production_hold_renderer_draws_filled_dot()
{
    const int centerX = 20;
    const int centerY = 10;
    RecordingDisplay display;

    drawOledActuatorGlyph(
        display, centerX, centerY, OG_HOLD, GLYPH_SIZE);

    TEST_ASSERT_EQUAL_UINT(0, display.lineCount);
    TEST_ASSERT_EQUAL_UINT(49, display.pixelCount);
    TEST_ASSERT_TRUE(display.hasPixel(centerX, centerY));
    TEST_ASSERT_TRUE(display.hasPixel(centerX - 4, centerY));
    TEST_ASSERT_TRUE(display.hasPixel(centerX + 4, centerY));
    TEST_ASSERT_TRUE(display.hasPixel(centerX, centerY - 4));
    TEST_ASSERT_TRUE(display.hasPixel(centerX, centerY + 4));
    TEST_ASSERT_FALSE(display.hasPixel(centerX - 4, centerY - 4));
    TEST_ASSERT_FALSE(display.hasPixel(centerX + 4, centerY + 4));
}

static void test_production_disconnected_renderer_draws_diagonal_cross()
{
    const int centerX = 20;
    const int centerY = 10;
    RecordingDisplay display;

    drawOledActuatorGlyph(
        display, centerX, centerY, OG_DISC, GLYPH_SIZE);

    TEST_ASSERT_EQUAL_UINT(2, display.lineCount);
    TEST_ASSERT_EQUAL_UINT(0, display.pixelCount);
    TEST_ASSERT_EQUAL_INT(centerX - 3, display.lines[0].x0);
    TEST_ASSERT_EQUAL_INT(centerY - 3, display.lines[0].y0);
    TEST_ASSERT_EQUAL_INT(centerX + 3, display.lines[0].x1);
    TEST_ASSERT_EQUAL_INT(centerY + 3, display.lines[0].y1);
    TEST_ASSERT_EQUAL_INT(centerX - 3, display.lines[1].x0);
    TEST_ASSERT_EQUAL_INT(centerY + 3, display.lines[1].y0);
    TEST_ASSERT_EQUAL_INT(centerX + 3, display.lines[1].x1);
    TEST_ASSERT_EQUAL_INT(centerY - 3, display.lines[1].y1);
}

static bool drawingsAreEqual(
    const RecordingDisplay &left,
    const RecordingDisplay &right)
{
    for (int y = 0; y < 32; ++y)
        for (int x = 0; x < 40; ++x)
            if (left.isLit(x, y) != right.isLit(x, y))
                return false;
    return true;
}

static void test_all_production_glyph_pairs_are_visually_distinct()
{
    const OledGlyph glyphs[] = {
        OG_EXTEND, OG_RETRACT, OG_HOLD, OG_DISC
    };
    RecordingDisplay drawings[4];
    for (size_t glyph = 0; glyph < 4; ++glyph)
        drawOledActuatorGlyph(
            drawings[glyph], 20, 10, glyphs[glyph], GLYPH_SIZE);

    for (size_t left = 0; left < 4; ++left)
        for (size_t right = left + 1; right < 4; ++right)
            TEST_ASSERT_FALSE(drawingsAreEqual(
                drawings[left], drawings[right]));
}

static void test_shared_state_mapping_covers_boundaries_and_disconnect()
{
    TEST_ASSERT_EQUAL_INT(OG_DISC, actuatorGlyph(false, -255, MOVE_THRESHOLD));
    TEST_ASSERT_EQUAL_INT(OG_DISC, actuatorGlyph(false, 0, MOVE_THRESHOLD));
    TEST_ASSERT_EQUAL_INT(OG_DISC, actuatorGlyph(false, 255, MOVE_THRESHOLD));
    TEST_ASSERT_EQUAL_INT(OG_HOLD, actuatorGlyph(true, 0, MOVE_THRESHOLD));
    TEST_ASSERT_EQUAL_INT(OG_HOLD, actuatorGlyph(true, MOVE_THRESHOLD - 1, MOVE_THRESHOLD));
    TEST_ASSERT_EQUAL_INT(OG_HOLD, actuatorGlyph(true, -MOVE_THRESHOLD + 1, MOVE_THRESHOLD));
    TEST_ASSERT_EQUAL_INT(OG_EXTEND, actuatorGlyph(true, MOVE_THRESHOLD, MOVE_THRESHOLD));
    TEST_ASSERT_EQUAL_INT(OG_EXTEND, actuatorGlyph(true, 255, MOVE_THRESHOLD));
    TEST_ASSERT_EQUAL_INT(OG_RETRACT, actuatorGlyph(true, -MOVE_THRESHOLD, MOVE_THRESHOLD));
    TEST_ASSERT_EQUAL_INT(OG_RETRACT, actuatorGlyph(true, -255, MOVE_THRESHOLD));
}

static void test_forwarded_line_decodes_all_six_actuators_atomically()
{
    OledGlyph glyphs[6] = {
        OG_DISC, OG_DISC, OG_DISC, OG_DISC, OG_DISC, OG_DISC
    };
    bool connected[6] = {false, false, false, false, false, false};
    const OledGlyph expected[6] = {
        OG_EXTEND, OG_RETRACT, OG_HOLD, OG_DISC, OG_HOLD, OG_HOLD
    };

    TEST_ASSERT_TRUE(parseControllerActuatorStates(
        SIX_STATE_LINE, "LEFT ", MOVE_THRESHOLD, glyphs, connected));
    assertGlyphs(glyphs, expected);
    TEST_ASSERT_TRUE(connected[0]);
    TEST_ASSERT_FALSE(connected[3]);
}

static void assertNonFinitePositionDecodesDisconnected(
    const char *position,
    int retractPwm,
    int extendPwm)
{
    char line[512];
    const int written = snprintf(
        line,
        sizeof(line),
        "LEFT ; RLHY %s 100 1 1 1 %d %d 0;"
        " RLHL 0.200 200 2 1 1 5 0 0;"
        " RLKL 0.300 300 3 1 1 0 0 0;"
        " MLHY 0.400 400 4 1 1 0 255 0;"
        " MLHL 0.500 500 5 1 1 0 4 0;"
        " MLKL 0.600 600 6 1 1 4 0 0",
        position,
        retractPwm,
        extendPwm);
    TEST_ASSERT_GREATER_THAN(0, written);
    TEST_ASSERT_LESS_THAN((int)sizeof(line), written);

    OledGlyph glyphs[6] = {
        OG_HOLD, OG_HOLD, OG_HOLD, OG_HOLD, OG_HOLD, OG_HOLD
    };
    bool connected[6] = {true, true, true, true, true, true};
    TEST_ASSERT_TRUE(parseControllerActuatorStates(
        line, "LEFT ", MOVE_THRESHOLD, glyphs, connected));
    TEST_ASSERT_EQUAL_INT(OG_DISC, glyphs[0]);
    TEST_ASSERT_FALSE(connected[0]);
}

static void test_forwarded_nonfinite_position_overrides_motion_pwm()
{
    assertNonFinitePositionDecodesDisconnected("nan", 0, 255);
    assertNonFinitePositionDecodesDisconnected("inf", 255, 0);
    assertNonFinitePositionDecodesDisconnected("-inf", 0, 255);
}

static void test_role_label_is_data_not_special_case()
{
    const char *roles[] = {"FRONT", "LEFT ", "RIGHT"};
    for (size_t role = 0; role < 3; ++role)
    {
        char line[512];
        const int written = snprintf(
            line, sizeof(line), "%s%s", roles[role], SIX_STATE_LINE + 5);
        TEST_ASSERT_GREATER_THAN(0, written);
        TEST_ASSERT_LESS_THAN((int)sizeof(line), written);

        OledGlyph glyphs[6] = {
            OG_DISC, OG_DISC, OG_DISC, OG_DISC, OG_DISC, OG_DISC
        };
        bool connected[6] = {false, false, false, false, false, false};
        TEST_ASSERT_TRUE(parseControllerActuatorStates(
            line, roles[role], MOVE_THRESHOLD, glyphs, connected));
        TEST_ASSERT_EQUAL_INT(OG_EXTEND, glyphs[0]);
        TEST_ASSERT_EQUAL_INT(OG_DISC, glyphs[3]);
    }
}

static void test_rejected_line_leaves_previous_complete_sample_untouched()
{
    const char *const malformed =
        "LEFT ;"
        " RLHY 0.100 100 1 1 1 0 bad 0;"
        " RLHL 0.200 200 2 1 1 5 0 0;"
        " RLKL 0.300 300 3 1 1 0 0 0;"
        " MLHY nan 400 4 1 1 0 255 0;"
        " MLHL 0.500 500 5 1 1 0 4 0;"
        " MLKL 0.600 600 6 1 1 4 0 0";
    OledGlyph glyphs[6] = {
        OG_HOLD, OG_EXTEND, OG_RETRACT, OG_DISC, OG_EXTEND, OG_RETRACT
    };
    const OledGlyph previous[6] = {
        OG_HOLD, OG_EXTEND, OG_RETRACT, OG_DISC, OG_EXTEND, OG_RETRACT
    };
    bool connected[6] = {true, false, true, false, true, false};
    const bool previousConnected[6] = {true, false, true, false, true, false};

    TEST_ASSERT_FALSE(parseControllerActuatorStates(
        malformed, "LEFT ", MOVE_THRESHOLD, glyphs, connected));
    assertGlyphs(glyphs, previous);
    for (size_t actuator = 0; actuator < 6; ++actuator)
        TEST_ASSERT_EQUAL(previousConnected[actuator], connected[actuator]);
}

static void assertInvalidPwmSampleIsRejected(const char *firstSegment)
{
    char line[512];
    const int written = snprintf(
        line,
        sizeof(line),
        "LEFT ; %s;"
        " RLHL 0.200 200 2 1 1 5 0 0;"
        " RLKL 0.300 300 3 1 1 0 0 0;"
        " MLHY nan 400 4 1 1 0 255 0;"
        " MLHL 0.500 500 5 1 1 0 4 0;"
        " MLKL 0.600 600 6 1 1 4 0 0",
        firstSegment);
    TEST_ASSERT_GREATER_THAN(0, written);
    TEST_ASSERT_LESS_THAN((int)sizeof(line), written);

    OledGlyph glyphs[6] = {
        OG_HOLD, OG_EXTEND, OG_RETRACT, OG_DISC, OG_EXTEND, OG_RETRACT
    };
    const OledGlyph previous[6] = {
        OG_HOLD, OG_EXTEND, OG_RETRACT, OG_DISC, OG_EXTEND, OG_RETRACT
    };
    bool connected[6] = {true, false, true, false, true, false};
    TEST_ASSERT_FALSE(parseControllerActuatorStates(
        line, "LEFT ", MOVE_THRESHOLD, glyphs, connected));
    assertGlyphs(glyphs, previous);
}

static void test_forwarded_pwm_fields_enforce_firmware_wire_invariants()
{
    assertInvalidPwmSampleIsRejected("RLHY 0.100 100 1 1 1 -1 0 0");
    assertInvalidPwmSampleIsRejected("RLHY 0.100 100 1 1 1 0 -1 0");
    assertInvalidPwmSampleIsRejected("RLHY 0.100 100 1 1 1 256 0 0");
    assertInvalidPwmSampleIsRejected("RLHY 0.100 100 1 1 1 0 256 0");
    assertInvalidPwmSampleIsRejected("RLHY 0.100 100 1 1 1 5 5 0");
}

static void test_controller_mapping_covers_each_position_without_overlap()
{
    OledGlyph legs[6][3];
    const OledGlyph front[6] = {
        OG_HOLD, OG_EXTEND, OG_RETRACT, OG_DISC, OG_HOLD, OG_EXTEND
    };
    const OledGlyph left[6] = {
        OG_RETRACT, OG_DISC, OG_HOLD, OG_EXTEND, OG_RETRACT, OG_DISC
    };
    const OledGlyph right[6] = {
        OG_EXTEND, OG_HOLD, OG_DISC, OG_RETRACT, OG_EXTEND, OG_HOLD
    };

    setControllerLegGlyphs(legs, 0, 1, front);
    setControllerLegGlyphs(legs, 4, 2, left);
    setControllerLegGlyphs(legs, 5, 3, right);

    for (size_t joint = 0; joint < 3; ++joint)
    {
        TEST_ASSERT_EQUAL_INT(front[joint], legs[0][joint]);
        TEST_ASSERT_EQUAL_INT(front[joint + 3], legs[1][joint]);
        TEST_ASSERT_EQUAL_INT(left[joint], legs[4][joint]);
        TEST_ASSERT_EQUAL_INT(left[joint + 3], legs[2][joint]);
        TEST_ASSERT_EQUAL_INT(right[joint], legs[5][joint]);
        TEST_ASSERT_EQUAL_INT(right[joint + 3], legs[3][joint]);
    }
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_production_extend_renderer_draws_apex_up_triangle);
    RUN_TEST(test_production_retract_renderer_draws_apex_down_triangle);
    RUN_TEST(test_production_hold_renderer_draws_filled_dot);
    RUN_TEST(test_production_disconnected_renderer_draws_diagonal_cross);
    RUN_TEST(test_all_production_glyph_pairs_are_visually_distinct);
    RUN_TEST(test_shared_state_mapping_covers_boundaries_and_disconnect);
    RUN_TEST(test_forwarded_line_decodes_all_six_actuators_atomically);
    RUN_TEST(test_forwarded_nonfinite_position_overrides_motion_pwm);
    RUN_TEST(test_role_label_is_data_not_special_case);
    RUN_TEST(test_rejected_line_leaves_previous_complete_sample_untouched);
    RUN_TEST(test_forwarded_pwm_fields_enforce_firmware_wire_invariants);
    RUN_TEST(test_controller_mapping_covers_each_position_without_overlap);
    return UNITY_END();
}
