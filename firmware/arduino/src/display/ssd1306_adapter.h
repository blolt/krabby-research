#pragma once

#include <Arduino.h>
#include <SparkFun_Qwiic_OLED.h>
#include <Wire.h>
#include <math.h>
#include <res/qw_fnt_5x7.h>

#include "../imu/imu_constants.h"
#include "display_constants.h"
#include "display.h"

class Ssd1306Adapter
{
public:
    Ssd1306Adapter()
        : driver_(), previousModel_(), hasPreviousModel_(false), initialized_(false)
    {
    }

    bool isInitialized() const { return initialized_; }

    bool initialize()
    {
        initialized_ = driver_.begin();
        if (initialized_)
            driver_.setFont(QW_FONT_5X7);
        invalidate();
        return initialized_;
    }

    // Redraws only the elements whose model fields changed. The driver tracks a
    // dirty range per page and sends only those bytes
    bool render(const StatusDisplayModel &model)
    {
        if (!initialized_)
            return false;

        const bool full = !hasPreviousModel_;
        if (!full && statusDisplayModelsEqual(previousModel_, model))
            return false;

        driver_.setFont(QW_FONT_5X7);
        if (full)
        {
            driver_.erase();
            driver_.line(0, SSD1306_HEADER_RULE_Y, 127, SSD1306_HEADER_RULE_Y);
        }

        if (full || model.role != previousModel_.role)
            drawRole(model);
        if (full || model.roll.value != previousModel_.roll.value ||
            model.pitch.value != previousModel_.pitch.value)
            drawTilt(model);
        if (full || model.packVoltage.value != previousModel_.packVoltage.value)
            drawVolts(model);

        for (int battery = 0; battery < 2; ++battery)
            if (full || model.batteryLevel[battery] != previousModel_.batteryLevel[battery])
                drawBattery(model, battery);

        if (full || model.frontPresent != previousModel_.frontPresent ||
            model.leftPresent != previousModel_.leftPresent ||
            model.rightPresent != previousModel_.rightPresent)
            drawBody(model);

        for (int leg = 0; leg < 6; ++leg)
            for (int joint = 0; joint < 3; ++joint)
                if (full || model.legs[leg][joint] != previousModel_.legs[leg][joint])
                    drawLegJoint(model, leg, joint);

        previousModel_ = model;
        hasPreviousModel_ = true;

        Wire.setClock(SSD1306_TRANSFER_BUS_CLOCK_HZ);
        driver_.display();
        Wire.setClock(I2C_DEFAULT_BUS_CLOCK_HZ);
        return true;
    }

    void invalidate()
    {
        previousModel_ = StatusDisplayModel{};
        hasPreviousModel_ = false;
    }

private:

    void clear(int x, int y, int width, int height)
    {
        driver_.rectangleFill(x, y, width, height, COLOR_BLACK);
    }

    void drawTextField(int x, int chars, const char *text)
    {
        clear(x, SSD1306_HEADER_Y, chars * SSD1306_CHAR_WIDTH, SSD1306_TEXT_HEIGHT);
        driver_.text(x, SSD1306_HEADER_Y, text);
    }

    void drawRole(const StatusDisplayModel &model)
    {
        drawTextField(SSD1306_HEADER_ROLE_X, SSD1306_HEADER_ROLE_CHARS,
                      statusDisplayRoleLabel(model.role));
    }

    void drawTilt(const StatusDisplayModel &model)
    {
        char text[12];
        snprintf(text, sizeof(text), "%+03d/%+03d",
                 clampTilt(static_cast<int>(model.roll.value)),
                 clampTilt(static_cast<int>(model.pitch.value)));
        drawTextField(SSD1306_HEADER_TILT_X, SSD1306_HEADER_TILT_CHARS, text);
    }

    void drawVolts(const StatusDisplayModel &model)
    {
        const int decivolts =
            static_cast<int>(lround(model.packVoltage.value * 10.0f));
        char text[10];
        snprintf(text, sizeof(text), "%d.%dV", decivolts / 10, abs(decivolts % 10));
        drawTextField(SSD1306_HEADER_VOLTS_X, SSD1306_HEADER_VOLTS_CHARS, text);
    }

    void drawBattery(const StatusDisplayModel &model, int battery)
    {
        const int x = SSD1306_BATTERY_X + battery * SSD1306_BATTERY_PITCH;
        const int nubY = (SSD1306_BATTERY_HEIGHT - SSD1306_BATTERY_NUB_HEIGHT) / 2;

        clear(x, SSD1306_BATTERY_Y,
              SSD1306_BATTERY_WIDTH + SSD1306_BATTERY_NUB_WIDTH,
              SSD1306_BATTERY_HEIGHT);
        driver_.rectangle(x, SSD1306_BATTERY_Y, SSD1306_BATTERY_WIDTH, SSD1306_BATTERY_HEIGHT);
        driver_.rectangleFill(x + SSD1306_BATTERY_WIDTH, SSD1306_BATTERY_Y + nubY,
                              SSD1306_BATTERY_NUB_WIDTH, SSD1306_BATTERY_NUB_HEIGHT);

        const float raw = model.batteryLevel[battery];
        const float level = raw < 0.0f ? 0.0f : (raw > 1.0f ? 1.0f : raw);
        const int fillWidth =
            static_cast<int>(lround((SSD1306_BATTERY_WIDTH - 2) * level));
        if (fillWidth > 0)
            driver_.rectangleFill(x + 1, SSD1306_BATTERY_Y + 1, fillWidth,
                                  SSD1306_BATTERY_HEIGHT - 2);
    }

    void drawBody(const StatusDisplayModel &model)
    {
        clear(SSD1306_BODY_X, SSD1306_BODY_Y, SSD1306_BODY_WIDTH,
              SSD1306_FACE_BOTTOM_Y - SSD1306_BODY_Y + 1);
        driver_.rectangle(SSD1306_BODY_X, SSD1306_BODY_Y, SSD1306_BODY_WIDTH, SSD1306_BODY_HEIGHT);
        if (model.leftPresent)
            driver_.rectangleFill(SSD1306_BODY_X + 1, SSD1306_BODY_Y + 1,
                                  SSD1306_STEM_X - SSD1306_BODY_X - 1,
                                  SSD1306_T_BAR_Y - SSD1306_BODY_Y - 1);
        if (model.rightPresent)
            driver_.rectangleFill(SSD1306_STEM_X, SSD1306_BODY_Y + 1,
                                  SSD1306_BODY_X + SSD1306_BODY_WIDTH - 1 - SSD1306_STEM_X,
                                  SSD1306_T_BAR_Y - SSD1306_BODY_Y - 1);
        if (model.frontPresent)
            driver_.rectangleFill(SSD1306_BODY_X + 1, SSD1306_T_BAR_Y, SSD1306_BODY_WIDTH - 2,
                                  SSD1306_BODY_Y + SSD1306_BODY_HEIGHT - 1 - SSD1306_T_BAR_Y);
        drawFace();
    }

    void drawFace()
    {
        const int centerX = SSD1306_FACE_CENTER_X;
        const int top = SSD1306_FACE_TOP_Y;
        const int eyeY = SSD1306_FACE_EYE_Y;
        for (int side = -1; side <= 1; side += 2)
        {
            const int eyeX = centerX + side * SSD1306_FACE_EYE_OFFSET_X;
            driver_.line(eyeX, top + 1, eyeX, top + SSD1306_FACE_STALK_HEIGHT);
            driver_.line(eyeX - 1, eyeY, eyeX + 1, eyeY);
            driver_.line(eyeX - 1, eyeY + 2, eyeX + 1, eyeY + 2);
            driver_.line(eyeX - 1, eyeY, eyeX - 1, eyeY + 2);
            driver_.line(eyeX + 1, eyeY, eyeX + 1, eyeY + 2);
        }
        driver_.pixel(centerX - 2, top + 4);
        driver_.pixel(centerX + 2, top + 4);
        driver_.line(centerX - 1, SSD1306_FACE_BOTTOM_Y, centerX + 1,
                     SSD1306_FACE_BOTTOM_Y);
    }

    void drawLegJoint(const StatusDisplayModel &model, int leg, int joint)
    {
        const int radius = SSD1306_GLYPH_SIZE / 2;
        const int sign = leg % 2 == 0 ? -1 : 1;
        const int y = SSD1306_BODY_Y + SSD1306_LEG_BAND[leg] * SSD1306_BAND_HEIGHT +
                      SSD1306_BAND_HEIGHT / 2;
        const int edge = sign < 0 ? SSD1306_BODY_X : SSD1306_BODY_X + SSD1306_BODY_WIDTH;
        const int centerX = edge + sign * (SSD1306_LEG_FIRST_OFFSET +
                                           joint * SSD1306_LEG_JOINT_PITCH);
        // The body edge anchors the innermost joint; the rest hang off their neighbour.
        const int inner = joint == 0
            ? edge
            : edge + sign * (SSD1306_LEG_FIRST_OFFSET +
                             (joint - 1) * SSD1306_LEG_JOINT_PITCH + radius);

        const int outer = centerX + sign * radius;
        const int left = sign < 0 ? outer : inner + 1;
        const int right = sign < 0 ? inner - 1 : outer;
        clear(left, y - radius, right - left + 1, SSD1306_GLYPH_SIZE);

        driver_.line(inner, y, centerX - sign * radius, y);
        drawGlyph(centerX, y, model.legs[leg][joint]);
    }

    void drawGlyph(
        int centerX,
        int centerY,
        ActuatorGlyph glyph)
    {
        const int radius = SSD1306_GLYPH_SIZE / 2;
        const int triangleRadius = radius - 1;
        if (glyph == ActuatorGlyph::Extend ||
            glyph == ActuatorGlyph::Retract)
        {
            const int diameter = 2 * triangleRadius;
            for (int row = 0; row <= diameter; ++row)
            {
                const int widthRow =
                    glyph == ActuatorGlyph::Extend
                    ? row
                    : diameter - row;
                const int halfWidth = widthRow * triangleRadius / diameter;
                const int y = centerY - triangleRadius + row;
                driver_.line(centerX - halfWidth, y, centerX + halfWidth, y);
            }
            return;
        }

        if (glyph == ActuatorGlyph::Hold || glyph == ActuatorGlyph::Unverified)
        {
            const int inner = glyph == ActuatorGlyph::Hold
                ? 0
                : (radius - 1) * (radius - 1);
            for (int dy = -radius; dy <= radius; ++dy)
                for (int dx = -radius; dx <= radius; ++dx)
                {
                    const int distance = dx * dx + dy * dy;
                    if (distance <= radius * radius && distance >= inner)
                        driver_.pixel(centerX + dx, centerY + dy);
                }
            return;
        }

        driver_.line(centerX - triangleRadius, centerY - triangleRadius,
                     centerX + triangleRadius, centerY + triangleRadius);
        driver_.line(centerX - triangleRadius, centerY + triangleRadius,
                     centerX + triangleRadius, centerY - triangleRadius);
    }

    static int clampTilt(int value)
    {
        return value < -99 ? -99 : (value > 99 ? 99 : value);
    }

    Qwiic1in3OLED driver_;
    StatusDisplayModel previousModel_;
    bool hasPreviousModel_;
    bool initialized_;
};
