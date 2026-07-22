/*
 * Krab status render on the Qwiic OLED 1.3" — M16 Task 2/3 bench tool.
 *
 * The first FIRMWARE port of the Python render (firmware/oled_sim/krab.py). It is
 * a mechanical 1:1 translation per RENDER_SPEC.md §5 (the sim was written against
 * the SparkFun primitives precisely so this port is boring): same geometry
 * constants, same draw-call order, integer voltage formatting (no %f), signed int
 * for the leg math, and one oled.display() flush. What you see here should match
 * the sim's nominal frame pixel-for-pixel.
 *
 * Draws a static NOMINAL krab (all boards present, all joints holding, two healthy
 * battery bars, a handsome face). Not driven by live telemetry — a bench demo.
 *
 * Wiring: Qwiic chain, OLED at 0x3D (SDA=D20, SCL=D21, 3.3V/GND).
 * Flash:  arduino-cli compile --fqbn arduino:avr:mega firmware/bench_sketches/oled_krab
 *         arduino-cli upload -p PORT --fqbn arduino:avr:mega firmware/bench_sketches/oled_krab
 * Reflash the real firmware afterwards with `make -C firmware upload-firmware PORT=...`.
 * Library: "SparkFun Qwiic OLED Arduino Library" PIN 1.0.9 (>=1.0.14 breaks AVR).
 */
#include <Wire.h>
#include <SparkFun_Qwiic_OLED.h>
#include <res/qw_fnt_5x7.h>

Qwiic1in3OLED oled; // 1.3" = 128x64, address 0x3D
bool oledUp = false;

// --- geometry (mirrors krab.py; keep in lockstep) ---
static const int GLYPH = 9;
static const int BAND_H = GLYPH + 1;                 // 10
static const int BODY_W = 32, BODY_H = BAND_H * 3 + 1; // 32 x 31
static const int BODY_X = (128 - BODY_W) / 2;        // 48
static const int BODY_Y = 22;
static const int TBAR_Y = BODY_Y + 2 * BAND_H;       // 42
static const int STEM_X = BODY_X + BODY_W / 2;       // 64
static const int LEG_BAND[6] = {2, 2, 1, 1, 0, 0};
// battery gauge
static const int BAT_W = 18, BAT_H = 7, BAT_HGAP = 4;
static const int BAT_X = 2, BAT_Y = 11;
static const int BAT_NUB_W = 2, BAT_NUB_H = 3;
static const int BAT_PITCH = BAT_W + BAT_NUB_W + BAT_HGAP;
static const float BATT_EMPTY_V = 12.0f, BATT_FULL_V = 13.6f;

enum Glyph { HOLD, EXTEND, RETRACT, DISC };

struct KrabState {
  bool front, left, right;   // controllers present
  Glyph legs[6][3];          // [leg FL,FR,ML,MR,RL,RR][yaw,hip,knee]
  float batt[2];             // 0..1 bar fractions
  const char *role;
  int roll, pitch;
  float pack_v;
};

static float batteryFraction(float v) {
  float f = (v - BATT_EMPTY_V) / (BATT_FULL_V - BATT_EMPTY_V);
  if (f < 0.0f) f = 0.0f;
  if (f > 1.0f) f = 1.0f;
  return f;
}

// State glyph centered at (cx, cy) in the same 9px box (RENDER_SPEC §1).
static void glyph(int cx, int cy, Glyph st) {
  int r = GLYPH / 2;   // 4
  int t = r - 1;       // 3
  if (st == EXTEND) {                                  // filled triangle, apex up
    for (int i = 0; i <= 2 * t; i++) {
      int hw = i * t / (2 * t);
      oled.line(cx - hw, cy - t + i, cx + hw, cy - t + i);
    }
  } else if (st == RETRACT) {                          // filled triangle, apex down
    for (int i = 0; i <= 2 * t; i++) {
      int hw = (2 * t - i) * t / (2 * t);
      oled.line(cx - hw, cy - t + i, cx + hw, cy - t + i);
    }
  } else if (st == HOLD) {                             // filled dot
    for (int dy = -r; dy <= r; dy++)
      for (int dx = -r; dx <= r; dx++)
        if (dx * dx + dy * dy <= r * r) oled.pixel(cx + dx, cy + dy);
  } else {                                             // DISC: bare X
    oled.line(cx - t, cy - t, cx + t, cy + t);
    oled.line(cx - t, cy + t, cx + t, cy - t);
  }
}

static void renderKrab(const KrabState &s) {
  oled.erase();

  // top status strip (integer voltage: no %f). roll/pitch clamped to +/-99.
  oled.setFont(QW_FONT_5X7);
  int dv = (int)lround(s.pack_v * 10.0f);              // decivolts
  int roll = s.roll < -99 ? -99 : (s.roll > 99 ? 99 : s.roll);
  int pitch = s.pitch < -99 ? -99 : (s.pitch > 99 ? 99 : s.pitch);
  char top[24];
  snprintf(top, sizeof(top), "%s %+03d/%+03d %d.%dV", s.role, roll, pitch, dv / 10, dv % 10);
  oled.text(0, 0, top);
  oled.line(0, 9, 127, 9);

  // two horizontal battery cells laid end-to-end
  int fill_h = BAT_H - 2;
  int nub_dy = (BAT_H - BAT_NUB_H) / 2;
  for (int j = 0; j < 2; j++) {
    int bx = BAT_X + j * BAT_PITCH;
    oled.rectangle(bx, BAT_Y, BAT_W, BAT_H);
    oled.rectangleFill(bx + BAT_W, BAT_Y + nub_dy, BAT_NUB_W, BAT_NUB_H);
    float frac = s.batt[j] < 0 ? 0 : (s.batt[j] > 1 ? 1 : s.batt[j]);
    int fw = (int)lround((BAT_W - 2) * frac);
    if (fw > 0) oled.rectangleFill(bx + 1, BAT_Y + 1, fw, fill_h);
  }

  // rectangular body split into 3 by-side region tiles
  oled.rectangle(BODY_X, BODY_Y, BODY_W, BODY_H);
  if (s.left)  oled.rectangleFill(BODY_X + 1, BODY_Y + 1, STEM_X - BODY_X - 1, TBAR_Y - BODY_Y - 1);
  if (s.right) oled.rectangleFill(STEM_X, BODY_Y + 1, BODY_X + BODY_W - 1 - STEM_X, TBAR_Y - BODY_Y - 1);
  if (s.front) oled.rectangleFill(BODY_X + 1, TBAR_Y, BODY_W - 2, BODY_Y + BODY_H - 1 - TBAR_Y);

  // 18 leg glyphs. int (not uint8_t) math: intermediates go negative before
  // landing on-panel (RENDER_SPEC §4 signed-coordinate trap).
  int r = GLYPH / 2;
  int GAP = 5;
  int step = 2 * r + GAP;   // 13
  for (int i = 0; i < 6; i++) {
    int by = BODY_Y + LEG_BAND[i] * BAND_H + BAND_H / 2;
    int sign = (i % 2 == 0) ? -1 : 1;               // left -> -x, right -> +x
    int edge = (sign < 0) ? BODY_X : BODY_X + BODY_W;
    int px = edge, py = by;
    for (int j = 0; j < 3; j++) {
      int cx = edge + sign * (r + GAP + j * step);
      int gy = by;                                  // straight legs (bend = 0)
      oled.line(px, py, cx - sign * r, gy);
      glyph(cx, gy, s.legs[i][j]);
      px = cx + sign * r;
      py = gy;
    }
  }

  // handsome krab face: eyes on stalks + smile
  int fcx = BODY_X + BODY_W / 2;
  int fy = BODY_Y + BODY_H - 1;
  int exs[2] = {fcx - 6, fcx + 6};
  for (int k = 0; k < 2; k++) {
    int ex = exs[k];
    oled.line(ex, fy + 1, ex, fy + 2);              // eyestalk
    int ey = fy + 3;                                // hollow 3x3 eye, explicit walls
    oled.line(ex - 1, ey, ex + 1, ey);
    oled.line(ex - 1, ey + 2, ex + 1, ey + 2);
    oled.line(ex - 1, ey, ex - 1, ey + 2);
    oled.line(ex + 1, ey, ex + 1, ey + 2);
  }
  oled.pixel(fcx - 2, fy + 4);
  oled.pixel(fcx + 2, fy + 4);
  oled.line(fcx - 1, fy + 5, fcx + 1, fy + 5);      // smile

  oled.display();                                   // flush — nothing shows until here
}

void setup() {
  Serial.begin(250000);
  Wire.begin();
  Wire.setClock(100000);
  Wire.setWireTimeout(10000, true);

  oledUp = oled.begin();
  if (!oledUp) {
    Serial.println("OLED: init FAILED (check 0x3D on i2c_scanner, Qwiic cable seating)");
    return;
  }
  Serial.println("OLED: online at 0x3D — drawing nominal krab.");

  KrabState s;
  s.front = s.left = s.right = true;
  for (int i = 0; i < 6; i++)
    for (int j = 0; j < 3; j++) s.legs[i][j] = HOLD;   // all joints holding
  s.batt[0] = batteryFraction(13.4f);                  // healthy
  s.batt[1] = batteryFraction(13.2f);
  s.role = "FRONT";
  s.roll = 2;
  s.pitch = -1;
  s.pack_v = 26.6f;                                    // 13.4 + 13.2

  renderKrab(s);
}

void loop() {
  // Static frame; SSD1306 holds its RAM. Heartbeat so a missing OLED is visible.
  static uint32_t last = 0;
  if (millis() - last >= 1000) {
    last = millis();
    if (!oledUp) Serial.println("OLED: absent; loop alive (graceful-failure path)");
  }
}
