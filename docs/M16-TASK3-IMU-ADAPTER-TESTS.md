# IMU adapter test checkpoint

This records the original tests-only checkpoint. See [bus injection](M16-TASK3-BUS-INJECTION.md)
for the subsequent production refactor and supplied-bus tests.

`test_lsm6dso_adapter` compiles the production adapter, calibrator, measurement
conversions, recovery policy and Arduino I²C wrapper. Production behavior and APIs
are unchanged by this stage. OLED adapter testing remains a separate review step.

## Build and support

The suite is registered in the native CMake manifest and runs through CTest,
`make -C firmware test-native`, and the existing firmware CI coverage job.

`imu_native_support` is a separate static-library target with its substitute
headers scoped to consumers. It does not link Unity. Its environment attaches
register-level LSM6DSO fakes to the test bus and supplies SDA inputs and virtual
microsecond time. Arduino delays advance that clock without sleeping; `millis()`
wraps at 32 bits.

The suite compiles the pinned SparkFun LSM6DSO driver. The device fake answers it
register by register: identification, read-modify-write configuration, the
adapter's 14-byte burst read, address and register NACKs, and short reads. The
merged event log records bus lifecycle, GPIO, clock, identification reads and
register writes; transfer-level Wire events stay in the bus log. Teardown rejects
bus and environment errors and unconsumed samples or SDA scripts.

A requestFrom count that differs from the bytes available, and a write that fails
on an acknowledged byte, are not modelled: no AVR Wire produces them, so the
adapter's checks for those cases are not exercised. The device fake does not
model sensor physics or electrical bus behavior.

## Coverage and behavioral checks

The tests cover:

- Primary/alternate discovery, absent devices, a device answering with another
  WHO_AM_I (accepted by the driver), every configuration failure, the resulting
  register values, timeout/clock settings, and startup delay.
- Raw burst protocol, signed sample decoding, independent expected SI values,
  temperature, extreme signed inputs, and the current identity body-axis mapping.
- Register-selection and transmission errors, and every short response length.
- All-zero motion versus nonzero channels; each configuration-register read error;
  every bit of the three configuration registers, including ignored bits.
- Loaded and captured calibration through public adapter methods, failed reads,
  motion rejection, persistence verification, and application to later samples.
- Calibration retention across automatic recovery and clearing on initialize.
- Failure qualification, exact retry boundaries, rollover, failed configuration,
  same-call recovery reads, and explicit initialization resetting recovery state.
- Free/stuck/released buses; nine-pulse recovery limit, stuck-bus latch, GPIO release,
  open-drain STOP sequence, restored clock/timeout, and the minimum half-bit delay.

The current axis mapping is identity. This suite verifies that mounting; it does
not claim to distinguish an omitted identity transform from applying it.

## Reproduce

```sh
make -C firmware test-native
```

After a GCC coverage build, report the adapter and wrapper specifically:

```sh
gcovr --root . build/native-firmware-coverage \
  --filter 'firmware/arduino/src/imu/lsm6dso_adapter\.h$' \
  --filter 'firmware/arduino/src/i2c/arduino_i2c_bus\.h$' \
  --exclude-unreachable-branches --exclude-throw-branches --txt --print-summary
```

Use the actual coverage build directory and matching gcov executable when using
an alternate toolchain. No production exclusions or coverage thresholds were
changed for this suite.

## Results

- 14 direct tests pass (`ctest -R test_lsm6dso_adapter`).
- Direct GCC 15 adapter report: 107/109 lines and all 102 branches covered.
- Arduino I²C wrapper: 36/36 lines and both branches covered.
- GCC attributes zero-count blocks to the first lines of the Celsius and
  RadiansPerSecond assignments (adapter lines 181 and 192). The continuation
  lines and constructor calls execute, and the tests assert their numeric results;
  the report also contains untaken exception branches there. These two reported
  line gaps remain visible.
- All 24 native suites, 266 Python firmware/OLED tests, and existing coverage gates pass.
- Mega build: 56,358 bytes flash, 5,939 bytes static RAM.

The tests characterize existing behavior. They do not change polling cadence,
recover devices through actual electrical faults, or establish sensor settling time.
