# INA228 adapter test checkpoint

## Current task 3 scope

Task 3 retains the real SparkFun INA2XX/Toolkit host builds, register-level INA228
fake, direct INA adapter suite, power-poll replay fixtures, and shared Wire fake.
The IMU/OLED driver suites and their production bus-injection refactors are
preserved on `test/m16-deferred-imu-oled` at `09d199d9` for later integration into
tasks 1 and 2. The IMU adapter, OLED adapter, and Arduino I2C recovery helper in
this branch match the integrated upstream main (`e50bb6d8`). Existing IMU logic,
display-model, renderer, and simulator tests remain in task 3.

The following sections record an earlier substitute-driver checkpoint; their
suite counts and coverage results are historical, not the current test manifest.


This records the tests-only checkpoint before the recovery changes. See
[INA acquisition and recovery](M16-TASK3-INA-RECOVERY.md) for current behavior.

The native suite compiles the production `Ina228Adapter` against small substitutes
for SparkFun INA2XX 1.0.0 and Arduino/Wire. It does not emulate INA registers or
implement the vendor driver. Device scripts and call logs belong to each Wire
instance and I²C address. The firmware API and production code are unchanged by
this testing stage.

## Covered behavior

- Unbound and null-bus measurements, explicit address/shunt configuration, all
  six setup failure points, configuration arguments, and the startup delay.
- All 16 combinations of read success/failure, with both negative and positive
  error codes. Failed calls may write a value or leave the output untouched.
  Every field is still attempted, errors produce NaN, and successful fields survive.
- Signed SI values, raw accessors, snapshot independence, and successful read
  statuses accompanied by NaN or infinity.
- Recovery qualification, exact 2,000 ms retry boundaries, clock rollover,
  failed probing/configuration, and measurement in the successful recovery call.
- Accumulator/reset calls for pack recovery and reconfiguration for adapters
  without charge preservation.
- Independent pack/midpoint readings, failures, configuration and recovery; the
  same address on different buses; rebinding and clearing an adapter's bus.

The fake's read and setup signatures were checked against the installed pinned
SparkFun headers. The Mega build additionally compiles against the real libraries.

## Reproduce

The suite is already registered in the native manifest and runs in firmware CI:

```sh
make -C firmware test-native
```

To report the direct suite's adapter coverage after `test-native-coverage`:

```sh
gcovr --root . build/native-firmware-coverage \
  --filter 'firmware/arduino/src/power_monitor/ina228_adapter\.h$' \
  --gcov-exclude-directory '.*/CMakeFiles/test_power_poll\.dir/.*' \
  --exclude-unreachable-branches --exclude-throw-branches --txt --print-summary
```

Use the configured coverage build directory and matching `--gcov-executable` when
using an alternate compiler. The direct report excludes the power-poll target
because it compiles the same header with a different substitute. The ordinary
coverage gate still includes that target.

## Results

- 13 direct adapter tests pass; 14 deliberately altered adapters are detected.
- Direct adapter coverage (GCC 15): 76/76 lines, 14/14 functions, 85/85 branches.
- Combined adapter coverage with the power-poll harness: 100% lines, 87/88 branches.
  The additional uncovered branch is in the alert/mode setup expression compiled
  against that harness's substitute; both errors are exercised by the direct suite.
- All 23 native suites and 266 Python firmware/OLED tests pass.
- Existing overall coverage gates pass: 96.9% lines, 92.9% branches. The separately
  measured extracted sketch regions remain at 100% lines and branches.
- Mega build: 56,358 bytes flash, 5,939 bytes static RAM.

## Behavior retained for review

Read errors clear measurement validity but leave `isUp()` true and do not trigger
reinitialization. The driver decodes integer registers, so a successful read is
always finite; validity remains an acquisition-status result. These tests preserve
those policies.

For a pack adapter configured to preserve charge, recovery skips device reset,
alert/mode setup and accumulator reset, even if the initial begin failed. It
reapplies shunt calibration. This existing behavior is characterized, not changed.

This checkpoint covers adapter software behavior, not physical bus recovery or
vendor-driver correctness. IMU and OLED adapter expansion awaits review.
