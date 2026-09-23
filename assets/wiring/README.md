# M16 wiring

The Task 2 Schemdraw sheet records the leader Mega's I²C chain: Qwiic adapter →
LSM6DSO IMU → SSD1306 OLED. The OLED uses address `0x3D`.

The [Task 3 sheet](generated/sheets/task3_wiring.html) adds the series batteries,
150 A fuse, external shunt, SparkFun INA228 monitors, leader MCU, actuator driver
and feedback connections, explicit octopus-to-MCU power branches, and UART links to both followers. It is a connection
overview: signal bundles represent repeated channels, and matching net names
connect the sense inputs and power distribution without crossing the control wiring.

SparkFun jumper settings follow the [manufacturer hardware reference](https://docs.sparkfun.com/SparkFun_Qwiic_Current_Sensor_INA2XX/hardware/hardware%20overview):
open SHUNT and leave VBUS open on both boards; keep A0/A1 closed for the pack
(`0x40`), and open A0 with A1 closed for the midpoint (`0x41`). These address
settings differ from the earlier Adafruit boards.

Render and validate the documentation with:

```sh
make -C assets/wiring render
```

Open the HTML output under `generated/sheets/` for the interactive schematic.
Each diagram module's filename is its canonical name and the basename of every
generated format.

The MCU supply block records the power routing only. Converter arrangement,
output voltage and MCU power connectors remain to be confirmed.
