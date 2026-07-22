/*
 * Qwiic OLED 1.3" bring-up — M16 Task 2 bench tool (AC 2a groundwork).
 *
 * Initializes the SparkFun Qwiic OLED 1.3" (SSD1306, 128x64) at 0x3D and
 * draws a heartbeat counter. Exercises BOTH paths of AC 2a: successful init
 * and the graceful-failure path (init failure is reported over serial once
 * per second and the sketch keeps running — it must never hang the loop,
 * matching how the real firmware treats a missing display).
 *
 * Wiring: Qwiic chain off the Task 1 Qwiic->Dupont adapter (3.3V / GND /
 * SDA=D20 / SCL=D21). The OLED is address 0x3D fixed.
 *
 * Flash:  arduino-cli compile --fqbn arduino:avr:mega firmware/bench_sketches/oled_hello
 *         arduino-cli upload -p PORT --fqbn arduino:avr:mega firmware/bench_sketches/oled_hello
 * Read:   serial monitor at 250000 baud. Expect "OLED: online" then a live
 *         counter on the panel. Reflash the real firmware afterwards with
 *         `make -C firmware upload-firmware PORT=...`.
 *
 * Library: "SparkFun Qwiic OLED Arduino Library" — PIN 1.0.9. Versions
 * >= 1.0.14 add a grch1120 driver that includes C++ <map> and no longer
 * compiles on AVR (same architectures=* overclaim pattern as the BMI270 lib):
 *   arduino-cli lib install "SparkFun Qwiic OLED Arduino Library@1.0.9"
 */
#include <Wire.h>
#include <SparkFun_Qwiic_OLED.h>
#include <res/qw_fnt_8x16.h>

Qwiic1in3OLED oled; // 1.3" = 128x64, default address 0x3D

bool oledUp = false;
uint32_t ticks = 0;

void setup() {
  Serial.begin(250000);
  Wire.begin();
  Wire.setClock(100000);
  Wire.setWireTimeout(10000, true);

  oledUp = oled.begin();
  if (oledUp) {
    Serial.println("OLED: online at 0x3D");
    oled.setFont(QW_FONT_8X16);
  } else {
    Serial.println("OLED: init FAILED (check 0x3D on i2c_scanner, Qwiic cable seating)");
  }
}

void loop() {
  if (oledUp) {
    // Library 1.0.9 sends only DIRTY pages, so a text-only frame measures a
    // PARTIAL refresh. The Task 2 krab UI redraws most of the screen, so we
    // alternate: even ticks draw text (partial-refresh cost), odd ticks fill
    // the whole panel (all 8 pages dirty = true worst-case full-frame cost).
    // Budget AC 2h against the FULLFRAME number, not the partial one.
    bool fullFrame = (ticks % 2) != 0;
    oled.erase();
    if (fullFrame) {
      oled.rectangleFill(0, 0, oled.getWidth(), oled.getHeight());
    } else {
      oled.text(0, 0, "KRABBY BENCH");
      char buf[16];
      snprintf(buf, sizeof(buf), "tick %lu", (unsigned long)ticks);
      oled.text(0, 24, buf);
    }
    uint32_t t0 = micros();
    oled.display();
    uint32_t dt = micros() - t0;
    if (ticks % 10 < 2) { // print one partial + one fullframe pair every 10 ticks
      Serial.print("tick "); Serial.print(ticks);
      Serial.print(fullFrame ? "  FULLFRAME display() us=" : "  partial display() us=");
      Serial.println(dt);
    }
  } else if (ticks % 10 == 0) {
    Serial.println("OLED: absent; loop still alive (graceful-failure path)");
  }
  ticks++;
  delay(100);
}
