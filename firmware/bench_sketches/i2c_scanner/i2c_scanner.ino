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

static const unsigned long SCANNER_BAUD = 250000UL;
// Standalone Arduino sketches are copied to a temporary build directory, so
// this sketch cannot include the production adapter translation unit. Host
// contract tests require these named values to match its bus constants.
static const unsigned long SCANNER_I2C_CLOCK_HZ = 100000UL;
static const unsigned long SCANNER_I2C_TIMEOUT_US = 10000UL;
static const unsigned long STARTUP_SETTLE_MS = 50UL;
static const unsigned long SCAN_INTERVAL_MS = 3000UL;
static const byte FIRST_I2C_ADDRESS = 1;
static const byte LAST_I2C_ADDRESS = 126;

void setup() {
  Serial.begin(SCANNER_BAUD);
  pinMode(SDA, INPUT_PULLUP); pinMode(SCL, INPUT_PULLUP);
  delay(STARTUP_SETTLE_MS);
  Serial.print("idle SDA(D20)="); Serial.print(digitalRead(SDA));
  Serial.print(" SCL(D21)="); Serial.println(digitalRead(SCL));
  Wire.begin();
  Wire.setClock(SCANNER_I2C_CLOCK_HZ);
  Wire.setWireTimeout(SCANNER_I2C_TIMEOUT_US, true);
}

void loop() {
  byte n = 0;
  for (byte a = FIRST_I2C_ADDRESS; a <= LAST_I2C_ADDRESS; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) { Serial.print("FOUND 0x"); Serial.println(a, HEX); n++; }
    if (Wire.getWireTimeoutFlag()) { Serial.println("BUS TIMEOUT"); Wire.clearWireTimeoutFlag(); }
  }
  Serial.print("scan done, devices: "); Serial.println(n);
  delay(SCAN_INTERVAL_MS);
}
