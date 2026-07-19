/*
 * Dual INA228 bring-up — M16 Task 3 bench tool (low-voltage, battery-free).
 *
 * Initializes the Pack monitor (0x40) and Midpoint monitor (0x41, A0 jumper
 * strapped) and prints bus voltage / current / power / die temp at 2 Hz.
 * Each device inits independently — one missing board must not block the
 * other (mirrors Task 3's per-device error handling).
 *
 * SAFE BENCH SETUP (no batteries, no shunt, no safety sign-off needed):
 * the Qwiic connector powers the chip logic only; the measured bus is the
 * VBUS input, which is SINGLE-ENDED (measured against common GND — there is
 * no VBUS- pin). On the Adafruit breakout VBUS is tied to VIN- by a default
 * solder jumper, so just jumper the VIN- terminal to the shield's 5V (or
 * 3.3V) and share GND. Current will read ~0 mA because nothing flows
 * through the (absent) shunt inputs — that is expected; this sketch
 * validates addresses, comms, calibration constants, and units, NOT the
 * shunt. The 200A/75mV shunt work is gated on the battery-safety checklist
 * (Task 3 §2) and does not happen with this sketch.
 *
 * Units (verified in Adafruit_INA2xx.cpp v3.0.0 — they are MIXED):
 * readBusVoltage() -> V, readCurrent() -> mA, readPower() -> mW,
 * readDieTemp() -> degC. Task 3 must convert to SI (V/A/W) for telemetry.
 *
 * Pack calibration matches the spec (§4): setShunt(0.000375, 200.0) —
 * 75 mV / 200 A external shunt = 375 uOhm.
 *
 * Flash:  arduino-cli compile --fqbn arduino:avr:mega firmware/bench_sketches/ina228_read
 *         arduino-cli upload -p PORT --fqbn arduino:avr:mega firmware/bench_sketches/ina228_read
 * Read:   serial monitor at 250000 baud. Reflash the real firmware afterwards
 *         with `make -C firmware upload-firmware PORT=...`.
 *
 * Library: "Adafruit INA228 Library" (arduino-cli lib install).
 */
#include <Wire.h>
#include <Adafruit_INA228.h>

Adafruit_INA228 pack;
Adafruit_INA228 mid;

bool packUp = false;
bool midUp = false;

void setup() {
  Serial.begin(250000);
  Wire.begin();
  Wire.setClock(100000);
  Wire.setWireTimeout(10000, true);

  packUp = pack.begin(0x40, &Wire);
  if (packUp) {
    pack.setShunt(0.000375, 200.0); // spec §4: 75 mV / 200 A external shunt
    Serial.println("PACK  (0x40): online, setShunt(0.000375, 200.0)");
  } else {
    Serial.println("PACK  (0x40): init FAILED");
  }

  midUp = mid.begin(0x41, &Wire);
  if (midUp) {
    Serial.println("MID   (0x41): online (VBUS only; current channel unused)");
  } else {
    Serial.println("MID   (0x41): init FAILED (A0 jumper strapped? scanner sees 0x41?)");
  }
}

void loop() {
  if (packUp) {
    // Library units are mixed (see header comment): V / mA / mW / degC.
    Serial.print("PACK V(V)=");   Serial.print(pack.readBusVoltage(), 3);
    Serial.print(" I(mA)=");      Serial.print(pack.readCurrent(), 3);
    Serial.print(" P(mW)=");      Serial.print(pack.readPower(), 3);
    Serial.print(" die(C)=");     Serial.print(pack.readDieTemp(), 1);
  } else {
    Serial.print("PACK absent");
  }
  Serial.print("  |  ");
  if (midUp) {
    Serial.print("MID V(V)="); Serial.print(mid.readBusVoltage(), 3);
  } else {
    Serial.print("MID absent");
  }
  Serial.println();
  delay(500);
}
