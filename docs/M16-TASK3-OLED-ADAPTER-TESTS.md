# OLED adapter test checkpoint

This records the original tests-only checkpoint. See [bus injection](M16-TASK3-BUS-INJECTION.md)
for the subsequent production refactor and supplied-bus tests.

This stage adds tests, native support, CMake test registration and documentation.
SHA-256 snapshots of the firmware tree before and after the work match, excluding
Python bytecode caches. Production firmware, display model, renderer and OLED
simulator remain unchanged. Nothing was committed or pushed.

## Build integration

`test_ssd1306_adapter` runs in the native CMake manifest, CTest and the existing
firmware CI job. It compiles the production adapter/canvas and links the production
display model and telemetry implementation.

`oled_native_support` is a Unity-independent static library with target-scoped
Arduino, Wire, SparkFun OLED and font substitute headers. It does not alter the
INA or IMU support. The vendor surface was checked against the installed pinned
SparkFun library; the font substitute is only an identity token, not bitmap data.

One ordered event log records drawing arguments, font selection, resets, transfers,
bus operations and GPIO activity. Probe ACK and timeout results are independent.
Begin/reset/probe responses are scripted, and unexpected operations or leftover
scripts fail the tests. Virtual delays advance time without sleeping; millis wraps
at 32 bits. A transfer records the bus clock actually active at that moment.

## Covered behavior

Thirteen tests cover:

- Canvas begin/reset return values, reset's clear-display argument, font selection,
  erase/display forwarding, all drawing arguments and uint8 coordinate conversion.
- Adapter initialization success/failure, initialization state and font selection.
- First-frame drawing, unchanged-frame probing without drawing/transfers,
  single-element partial redraw and explicit invalidation.
- Drawing before transfer, 400 kHz transfer clock and restoration to 100 kHz.
- Disconnect detection even for an unchanged frame, suppressed drawing while
  unavailable, failed reset and exact retry boundaries including clock rollover.
- Recovery restoring font and forcing a full redraw of the same frame. Drawing
  calls match a fresh adapter's rendering, with explicit erase/transfer assertions.
- Ordinary NACKs versus timeouts, clearing stale timeout flags, free-bus restart,
  pulse-based recovery, open-drain STOP, stuck-bus latching and release.
- Failed post-clear probe, failed post-clear reset, and failed final probe before
  rendering, with no display transfer on any of those paths.
- Explicit initialization clearing cached frame, retry timing and stuck-bus state.

## Reproduce

```sh
make -C firmware test-native
```

After the native coverage build, report the adapter/canvas independently:

```sh
gcovr --root . build/native-firmware-coverage \
  --filter 'firmware/arduino/src/display/ssd1306_adapter\.h$' \
  --exclude-unreachable-branches --exclude-throw-branches --txt --print-summary
```

Use the actual coverage directory and matching gcov executable for an alternate
compiler. No production coverage exclusions or thresholds were changed.

## Results and limits

- All 13 direct tests pass (`ctest -R test_ssd1306_adapter`).
- GCC 15 adapter/canvas coverage: 76/76 lines, 20/20 functions, 45/45 branches.
- All 25 native suites and 266 Python firmware/OLED tests pass.
- Existing aggregate coverage gates pass: 96.0% lines, 91.8% branches. The separately
  measured extracted sketch regions remain at 100% lines and branches.
- Mega build passes: 56,358 bytes flash and 5,939 bytes static RAM.

The driver display() method returns no transfer status. These tests establish
when the adapter requests a transfer and restores the clock; they cannot establish
that the physical panel received it. Driver framebuffer rendering and electrical
bus behavior are outside this substitute. Existing renderer and simulator tests
remain responsible for their own rendering behavior.

No production fix was introduced. This completes the OLED review checkpoint.
