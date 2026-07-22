/*
 * OLED dirty-page probe — settles whether SparkFun Qwiic OLED 1.0.9 only
 * transfers changed pages on display(), or pushes the full framebuffer every
 * time. This decides the Task 2 render architecture (AC 2h) and must be
 * MEASURED, not assumed.
 *
 * Method: draw a full frame ONCE in setup (no erase() in loop). Each loop
 * iteration toggles only a small 16x16 region and times display(). If the
 * library is dirty-page-aware, this is a fraction of a full-frame push
 * (~120 ms measured by oled_hello); if it still costs ~120 ms, dirty-page is
 * NOT available and the render must chunk the transfer or raise the bus clock.
 * Also times an explicit full-frame (erase+fill) every 20th tick as the
 * reference ceiling.
 *
 * Flash: arduino-cli compile --fqbn arduino:avr:mega firmware/bench_sketches/oled_dirty
 *        arduino-cli upload -p PORT --fqbn arduino:avr:mega firmware/bench_sketches/oled_dirty
 * Read:  serial monitor @ 250000. Library pinned 1.0.9 (see oled_hello header).
 */
#include <Wire.h>
#include <SparkFun_Qwiic_OLED.h>
#include <res/qw_fnt_8x16.h>

Qwiic1in3OLED oled;
bool oledUp = false;
uint32_t ticks = 0;

void setup() {
  Serial.begin(250000);
  Wire.begin();
  Wire.setClock(100000);
  Wire.setWireTimeout(10000, true);
  oledUp = oled.begin();
  if (!oledUp) { Serial.println("OLED: init FAILED"); return; }
  oled.setFont(QW_FONT_8X16);

  // Draw a full static frame ONCE, like the real krab would be.
  oled.erase();
  oled.text(0, 0, "KRABBY STATIC");
  oled.line(0, 20, 127, 20);
  oled.rectangle(0, 24, 100, 30);
  oled.text(0, 48, "dirty probe");
  uint32_t t0 = micros();
  oled.display();
  Serial.print("initial full frame us="); Serial.println(micros() - t0);
}

void loop() {
  if (!oledUp) { delay(1000); return; }

  if (ticks % 20 == 19) {
    // Reference ceiling: force a whole-screen change.
    oled.erase();
    oled.rectangleFill(0, 0, oled.getWidth(), oled.getHeight());
    uint32_t t0 = micros();
    oled.display();
    Serial.print("tick "); Serial.print(ticks);
    Serial.print("  FULLFRAME us="); Serial.println(micros() - t0);
  } else {
    // Dirty-page candidate: change ONLY a 16x16 corner, no erase().
    uint8_t c = (ticks & 1) ? COLOR_WHITE : COLOR_BLACK;
    oled.rectangleFill(108, 0, 16, 16, c);
    uint32_t t0 = micros();
    oled.display();
    uint32_t dt = micros() - t0;
    if (ticks % 20 < 4) {
      Serial.print("tick "); Serial.print(ticks);
      Serial.print("  dirty16x16 us="); Serial.println(dt);
    }
  }
  ticks++;
  delay(100);
}
