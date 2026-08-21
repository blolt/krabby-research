#pragma once

#include <stddef.h>
#include <stdint.h>

static constexpr size_t STATUS_DISPLAY_JOINTS_PER_LEG = 3;
static constexpr uint32_t CONTROLLER_DISPLAY_TIMEOUT_MILLISECONDS = 500;

// A full frame is ~1.25 kB, so ~29 ms on the wire here and ~115 ms at the
// 100 kHz sensor clock, which would not fit TELEMETRY_INTERVAL_MS.
static constexpr uint32_t SSD1306_TRANSFER_BUS_CLOCK_HZ = 400000UL;

// Header fields are positioned separately rather than composed into one string,
// so a tilt change does not dirty the role and voltage cells. The 5x7 font
// advances 6 px per character.
static constexpr int SSD1306_CHAR_WIDTH = 6;
static constexpr int SSD1306_TEXT_HEIGHT = 8;
static constexpr int SSD1306_HEADER_Y = 0;
static constexpr int SSD1306_HEADER_RULE_Y = 9;
static constexpr int SSD1306_HEADER_ROLE_X = 0;
static constexpr int SSD1306_HEADER_ROLE_CHARS = 5;   // "UNKWN"
static constexpr int SSD1306_HEADER_TILT_X = 36;
static constexpr int SSD1306_HEADER_TILT_CHARS = 7;   // "+00/+00"
static constexpr int SSD1306_HEADER_VOLTS_X = 92;
static constexpr int SSD1306_HEADER_VOLTS_CHARS = 6;  // "24.8V"

static_assert(
    SSD1306_HEADER_ROLE_X + SSD1306_HEADER_ROLE_CHARS * SSD1306_CHAR_WIDTH <=
        SSD1306_HEADER_TILT_X,
    "role field overlaps the tilt field");
static_assert(
    SSD1306_HEADER_TILT_X + SSD1306_HEADER_TILT_CHARS * SSD1306_CHAR_WIDTH <=
        SSD1306_HEADER_VOLTS_X,
    "tilt field overlaps the voltage field");
static_assert(
    SSD1306_HEADER_VOLTS_X + SSD1306_HEADER_VOLTS_CHARS * SSD1306_CHAR_WIDTH <= 128,
    "voltage field runs off the panel");

static constexpr int SSD1306_GLYPH_SIZE = 9;
// Measured on the panel: ~120 ms for a full frame against ~5.8 ms for a single
// 8px band, so the renderer redraws only the bands that changed.
static constexpr int SSD1306_BAND_HEIGHT = SSD1306_GLYPH_SIZE + 1;
static constexpr int SSD1306_BODY_WIDTH = 32;
static constexpr int SSD1306_BODY_HEIGHT = SSD1306_BAND_HEIGHT * 3 + 1;
static constexpr int SSD1306_BODY_X = (128 - SSD1306_BODY_WIDTH) / 2;
static constexpr int SSD1306_BODY_Y = 22;
static constexpr int SSD1306_T_BAR_Y =
    SSD1306_BODY_Y + 2 * SSD1306_BAND_HEIGHT;
static constexpr int SSD1306_STEM_X =
    SSD1306_BODY_X + SSD1306_BODY_WIDTH / 2;
static constexpr int SSD1306_LEG_BAND[6] = {2, 2, 1, 1, 0, 0};
// Joint spacing along a leg, from the body edge outward.
static constexpr int SSD1306_LEG_FIRST_OFFSET = 7;
static constexpr int SSD1306_LEG_JOINT_PITCH = 11;

static_assert(
    SSD1306_LEG_JOINT_PITCH > SSD1306_GLYPH_SIZE,
    "leg joints are pitched closer than a glyph is wide, so they would overlap");
static_assert(
    SSD1306_BODY_X - (SSD1306_LEG_FIRST_OFFSET +
                      (STATUS_DISPLAY_JOINTS_PER_LEG - 1) * SSD1306_LEG_JOINT_PITCH +
                      SSD1306_GLYPH_SIZE / 2) >= 0,
    "outermost leg joint runs off the left of the panel");
static_assert(
    SSD1306_BODY_X + SSD1306_BODY_WIDTH +
        (SSD1306_LEG_FIRST_OFFSET +
         (STATUS_DISPLAY_JOINTS_PER_LEG - 1) * SSD1306_LEG_JOINT_PITCH +
         SSD1306_GLYPH_SIZE / 2) < 128,
    "outermost leg joint runs off the right of the panel");

// Face on the body's front (bottom) edge: two eyes on stalks over a smile.
static constexpr int SSD1306_FACE_CENTER_X =
    SSD1306_BODY_X + SSD1306_BODY_WIDTH / 2;
static constexpr int SSD1306_FACE_TOP_Y =
    SSD1306_BODY_Y + SSD1306_BODY_HEIGHT - 1;
static constexpr int SSD1306_FACE_EYE_OFFSET_X = 6;
static constexpr int SSD1306_FACE_STALK_HEIGHT = 2;
static constexpr int SSD1306_FACE_EYE_Y =
    SSD1306_FACE_TOP_Y + SSD1306_FACE_STALK_HEIGHT + 1;
static constexpr int SSD1306_FACE_BOTTOM_Y = SSD1306_FACE_TOP_Y + 5;

static_assert(SSD1306_FACE_BOTTOM_Y < 64, "krab face runs off the bottom of the panel");
static_assert(
    SSD1306_FACE_CENTER_X + SSD1306_FACE_EYE_OFFSET_X + 1 <
        SSD1306_BODY_X + SSD1306_BODY_WIDTH,
    "krab face is wider than the body it sits on");

static constexpr int SSD1306_BATTERY_WIDTH = 18;
static constexpr int SSD1306_BATTERY_HEIGHT = 7;
static constexpr int SSD1306_BATTERY_GAP = 4;
static constexpr int SSD1306_BATTERY_X = 2;
static constexpr int SSD1306_BATTERY_Y = 11;
// Interior fill span: the outline's two side walls are not fillable.
static constexpr int SSD1306_BATTERY_FILL_WIDTH = SSD1306_BATTERY_WIDTH - 2;
// "No signal" draws every other pixel along the bar's centre line, so the gauge
// still reads as a battery that has lost its source rather than an empty one.
static constexpr int SSD1306_BATTERY_NO_SIGNAL_STEP = 2;

static constexpr int SSD1306_BATTERY_NUB_WIDTH = 2;
static constexpr int SSD1306_BATTERY_NUB_HEIGHT = 3;
static constexpr int SSD1306_BATTERY_PITCH =
    SSD1306_BATTERY_WIDTH + SSD1306_BATTERY_NUB_WIDTH +
    SSD1306_BATTERY_GAP;
