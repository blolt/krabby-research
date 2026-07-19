/*
 * I2C bus scanner + health check — M16 bench tool.
 *
 * Reports idle SDA/SCL levels (both must read 1; a stuck-low line means a
 * wiring short or a device holding the bus) then sweeps addresses 1-126.
 * Expected on the Krabby-Uno leader bus: LSM6DSO at 0x6B or 0x6A (ADR jumper),
 * Qwiic OLED 0x3D (Task 2), INA228 pack 0x40 / midpoint 0x41 (Task 3).
 *
 * Flash:  arduino-cli compile --fqbn arduino:avr:mega firmware/bench_sketches/i2c_scanner
 *         arduino-cli upload -p PORT --fqbn arduino:avr:mega firmware/bench_sketches/i2c_scanner
 * Read:   serial monitor at 250000 baud. Reflash the real firmware afterwards
 *         with `make -C firmware upload-firmware PORT=...`.
 */
#include <Wire.h>

void setup() {
  Serial.begin(250000);
  pinMode(20, INPUT_PULLUP); pinMode(21, INPUT_PULLUP);
  delay(50);
  Serial.print("idle SDA(D20)="); Serial.print(digitalRead(20));
  Serial.print(" SCL(D21)="); Serial.println(digitalRead(21));
  Wire.begin();
  Wire.setClock(100000);
  Wire.setWireTimeout(10000, true);
}

void loop() {
  byte n = 0;
  for (byte a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) { Serial.print("FOUND 0x"); Serial.println(a, HEX); n++; }
    if (Wire.getWireTimeoutFlag()) { Serial.println("BUS TIMEOUT"); Wire.clearWireTimeoutFlag(); }
  }
  Serial.print("scan done, devices: "); Serial.println(n);
  delay(3000);
}
