# Task 3 power migration baseline

Historical checkpoint: the cached battery-split behavior below has subsequently
been intentionally removed. See [the current measurement checkpoint](M16-TASK3-MEASUREMENT-CHECKPOINT.md)
for the revised contract and fixture changes.

This is the first review checkpoint before introducing a measurement structure.
The reference firmware is commit `810a647` on rebased `pr/m16-task3`. This change
adds tests and documentation only; firmware behavior is unchanged.

## Test boundary

`tests/native/firmware/arduino/test_power_poll.cpp` executes the actual
`battAppendTelemetry` function and the battery-to-display mapping from
`arduino.ino`. CMake extracts those regions verbatim at configure time, along
with their state declarations. Missing, ambiguous or reversed boundary markers fail the
configuration. Changes to the sketch trigger reconfiguration. This temporary
seam avoids editing production code just to establish its baseline; remove it
when the polling responsibilities have migrated into independently compilable
production components.

The suite uses the production INA228 adapter, recovery policy, calibration,
battery splitting, telemetry serializer, display model, and renderer. Dedicated
fakes supply vendor readings, clock, Wire presence probes, storage, and Print.
They record calls rather than model the INA228 registers or electrical behavior.

Every scenario compares against a checked-in transcript in
`tests/native/firmware/fixtures/power_poll/`. Each poll records:

- BATT output, including field order, requested precision, cached values and validity.
- Ordered clock, vendor read, recovery, configuration and telemetry-start calls.
- Last-good caches and the separate display values and validity flags.
- The resulting display model and incremental drawing calls.
- Calibration values, adapter state, failure counts and initialization/reset counts.

Fake vendor inputs use V, mA, mW and C. Cache output uses V, A, W and C.
`model` contains pack volts, A/B decivolts, and A/B normalized fills. Calibration
save results are the production enum values: 0 saved, 1 invalid input, 2 storage
verification failed. Tests restore snapshots of the production declaration-initialized state between
scenarios; polls within a scenario
share caches, adapters and renderer state.

## Scenarios for review

| Fixture | Behavior recorded |
| --- | --- |
| `healthy` | Healthy readings, identical frames, sub-display-resolution changes, exact and exceeded divergence threshold, full bars with changing voltage labels. |
| `startup` | Neither monitor available; absent probe, retry deadline, recovery tick, first fresh sample. |
| `midpoint_only_startup` | A remains displayable while pack and B are unavailable; pack initializes later. |
| `pack_only_startup` | Pack is independently displayable without midpoint. |
| `pack_disconnect` | Invalid pack voltage, retained caches, live midpoint, suppressed reads while down, recovery without accumulator reset. |
| `midpoint_disconnect` | Pack keeps updating while midpoint is down, followed by split recovery. |
| `both_disconnect` | Both fail after a valid sample; cached telemetry remains while voltage labels become unavailable. |
| `current_behavior_impossible_split` | Independently plausible voltages imply a negative or excessive B voltage; telemetry and display validity differ. |
| `voltage_boundaries` | Inclusive zero and upper bounds, out-of-range, negative, infinity and NaN voltages. |
| `current_behavior_unchecked_pack_fields` | NaN current/charge, infinite power and a small finite current remain accepted with valid pack voltage. |
| `retry_rollover` | Retry interval across uint32 clock wrap, including elapsed 1999 and 2000 ms. |
| `read_order_and_clock` | A delayed midpoint read crosses the retry deadline; eligibility uses the timestamp captured before reads. |
| `failed_begin` | Acknowledged device whose initialization fails, then successful retry and subsequent fresh sample. |
| `calibration` | Offsets and gain, rejected references, persistence/reload, failed verification retaining RAM calibration and invalidating storage. |
| `midpoint_failed_begin` | Midpoint initialization fails despite ACK, then recovers at its retry deadline. |
| `staggered_recovery` | Both monitors fail; pack recovers first and remains independently displayable. |
| `repeated_disconnect` | A second outage preserves the retry interval after a successful sample, without resetting charge. |
| `calibration_while_unavailable` | Calibration changes while pack is down; pack/split caches stay unchanged while the live midpoint uses the new offset. |
| `divergence_A_higher` | Exact, exceeded and below-threshold divergence with A higher than B. |
| `calibrated_validity` | Voltage validity is evaluated after correction, including raw negative values corrected into range. |

Additional harness checks reject unknown device addresses and incorrect Wire
instances. Internal floating-point snapshots use `max_digits10` round-trip
precision (including signed zero and non-finite values); telemetry retains the
serializer's requested precision. Fixture failures report the first differing
scenario and line. Trace and fixture I/O errors fail the test.

## Existing behavior to preserve during migration

These fixtures describe current behavior, including shortcomings. They are not
endorsements of the following policies:

- An impossible split retains the previous A/B telemetry values while both
  monitor-valid flags can remain set. The OLED independently hides pack and B.
- Pack validity checks voltage; current, power and charge can subsequently be
  non-finite without clearing that flag.
- Successful recovery changes adapter availability on that poll, but fresh
  measurements and valid telemetry wait until the next poll.
- Missing readings preserve cached numbers; validity is separate from value.
- Both voltage reads precede recovery decisions, and pack current, power and
  charge reads follow them. Recovery does not reset an initialized pack's charge.

Any intentional correction belongs in a separate change with explicitly revised
expectations after the structural migration.

## Running and maintaining the baseline

From the repository root:

```sh
make -C firmware test-native
python -m pytest -q tests/unit/oled_sim tests/unit/firmware
```

For a focused rerun after building:

```sh
ctest --test-dir build/native-firmware-tests -R '^test_power_poll$' --output-on-failure
```

Normal tests never rewrite fixtures. To inspect new observations separately:

```sh
baseline_dir=$(mktemp -d /tmp/krabby-power-observations.XXXXXX)
build/native-firmware-tests/test_power_poll --record "$baseline_dir"
diff -ru tests/native/firmware/fixtures/power_poll "$baseline_dir"
```

Review every difference before updating a fixture. A behavior-preserving
migration should pass the original fixtures. Recording alone is not validation.
`KRABBY_POWER_POLL_SKETCH` can point CMake at a temporary sketch copy, leaving
repository firmware intact.

## Validation of this checkpoint

- All 24 native suites pass under Clang and GCC, including 20 characterization scenarios.
- All 261 Python firmware/simulator tests pass.
- The broader GCC 15 coverage gate passes; a separate gate requires 100% lines
  and branches for the extracted sketch regions (41 lines and 42 branches).
- Existing fixtures retain identical telemetry, events and drawing commands;
  internal numeric changes only expose the original values at greater precision.
- Mega build against real vendor libraries passes: 56,270 bytes flash, 5,871 bytes RAM.
- `git diff --exit-code HEAD -- firmware/arduino firmware/oled_sim` confirms
  production source files are unchanged. The Makefile change adds the test coverage gate.

## Limits and subsequent checkpoints

The Print fake uses host formatting with the production serializer's precision;
it is not an AVR rounding/overflow emulator. Draw-call transcripts verify renderer
requests, not OLED hardware. Vendor begin/reset events record requested operations,
not chip internals. Clock advances are scripted; these tests do not establish
I2C transaction timing, analog accuracy or accumulator continuity on real devices.
Calibration storage is in-memory here; existing EEPROM layout tests remain needed.
This suite does not execute the whole Arduino setup/loop or command dispatcher.
The broader coverage gate excludes the sketch. The separate sketch gate covers
only the extracted regions, not the entire sketch or hardware integration.

After baseline review, introduce a data-only measurement assembled from the
existing values. Then migrate telemetry and display consumers separately, extract
state composition/caching, and only then change acquisition boundaries. Preserve
these outputs and call ordering at each checkpoint. Bring the simulator onto the
production input path afterward; keep behavioral fixes separate. Hardware checks
remain necessary before claiming equivalence of acquisition on the device.
