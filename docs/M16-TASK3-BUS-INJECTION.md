# Explicit IMU and OLED bus dependencies

The IMU and OLED adapters now require a `TwoWire&` at construction. The sketch
passes `Wire`. Initialization, measurement reads, probes, driver configuration,
OLED transfer clocks, and recovery use the supplied instance. `ArduinoI2cBus`
also receives that instance and restarts it after bus clearing.

Recovery still uses the Mega SDA/SCL pins and the existing GPIO/time functions.
This does not add alternative physical bus pin mappings or runtime driver
substitution on the MCU. Device configuration, retry policy, calibration and
redraw behavior are unchanged. INA production code is unchanged.

The existing 14 IMU and 13 OLED tests now run against a non-global bus. Its scripts,
device state and events are separate from global Wire, which must remain unused.
Clock and GPIO state remain shared physical-environment inputs. The vendor
drivers retain the supplied bus for subsequent configuration, reads and transfers.
OLED recovery tests start from a failed initialize, because the real library needs
a bound bus before its reset can succeed.

Shared Wire-fake consolidation and combined sensor/display replay remain separate
follow-up work. No commits or pushes were made.

## Validation

All 25 native suites, 266 Python firmware/OLED tests, and GCC coverage gates
pass. The direct adapter/helper report has 149/149 branches and 220/222 lines
covered. The two uncovered IMU
assignment lines are the same GCC reporting gaps documented at the original
checkpoint. OLED coverage is 77/77 lines; the bus helper is 36/36.

The Mega build uses 56,494 bytes of flash and 5,945 bytes of static RAM, increases
of 90 and 6 bytes respectively. Before/after firmware hashes limit this pass to
the sketch construction sites, IMU adapter, OLED adapter/canvas, and bus helper.

## Subsequent shared Wire consolidation

All four native Wire substitutes now use one `wire_native_support` library.
See the [shared Wire support notes](../tests/native/firmware/fakes/wire/README.md).
Driver-specific state remains outside the bus implementation; the clock/GPIO
substitutes and separate INA driver implementations have not been consolidated.
This subsequent test-support change leaves production firmware and replay fixtures
byte-identical to the bus-injection checkpoint.

The shared-Wire checkpoint passes all 26 native suites. GCC coverage gates pass;
the shared
transport implementation has 75/75 lines, 15/15 functions and 55/59 branches
covered. Clock/GPIO behavior and power-poll replay fixtures are unchanged.

All 266 Python firmware/OLED tests also pass. The installed SparkFun font file
blocked during reading, so that run used the pinned OLED library v1.0.9 downloaded
into `/tmp`, selected through `QWIIC_OLED_LIB_DIR`. No repository or installed
library files were changed for that workaround.
