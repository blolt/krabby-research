// Throwaway: invalidates only the IMU calibration magic byte so the next boot of
// the real firmware performs a fresh capture. Leaves joint calibration (0-25)
// and role (32-33) untouched.
#include <EEPROM.h>
static const int EEPROM_IMU_CAL_ADDR = 40;
void setup() {
  Serial.begin(250000);
  delay(300);
  EEPROM.update(EEPROM_IMU_CAL_ADDR, 0x00);
  Serial.print("IMU cal magic at ");
  Serial.print(EEPROM_IMU_CAL_ADDR);
  Serial.print(" now 0x");
  Serial.println(EEPROM.read(EEPROM_IMU_CAL_ADDR), HEX);
}
void loop() {}
