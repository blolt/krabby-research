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
Arduino and Wire substitutes. The suite compiles the pinned SparkFun Qwiic OLED
library (v1.0.9). An SSD1306 device fake at 0x3D answers it on the test bus,
decoding setup commands, page and column addressing and display data into a
128x64 frame that tests inspect pixel by pixel.

One ordered event log records bus lifecycle, clock and timeout-flag changes, GPIO
activity and panel events: each probe or library ping with its status, each setup
sequence, and each run of display data with the bus clock active when it was sent.
Ping and probe outcomes (ACK, NACK or timeout) are scripted in bus order, and
leftover scripts fail the tests. Virtual delays advance time without sleeping;
millis wraps at 32 bits.

The library's 1.3" device inherits a constructor that skips its own member
initializers. Production is unaffected because the adapter is a zero-initialized
global; the tests place adapters and canvases in zeroed storage for the same reason.

## Covered behavior

The tests cover:

- Canvas begin/reset results, begin doing nothing once initialized, erase and
  display, and uint8 coordinate and colour conversion shown in the pixels sent.
- Adapter initialization success/failure and initialization state.
- First-frame drawing, unchanged-frame probing without drawing/transfers,
  single-element partial redraw and explicit invalidation.
- Drawing before transfer, 400 kHz transfer clock and restoration to 100 kHz.
- Disconnect detection even for an unchanged frame, suppressed drawing while
  unavailable, failed reset and exact retry boundaries including clock rollover.
- Recovery resetting the panel and forcing a full redraw of the same frame; the
  frame sent matches a fresh adapter's.
- Ordinary NACKs versus timeouts, clearing stale timeout flags, free-bus restart,
  pulse-based recovery, open-drain STOP, stuck-bus latching and release.
- Failed post-clear probe, failed post-clear reset, and failed final probe before
  rendering, with no display transfer on any of those paths.
- Explicit initialization clearing cached frame, retry timing and stuck-bus state.
- A NACK during display leaving the panel stale while the adapter treats the frame
  as drawn, until an invalidation sends it again.

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

- All 14 direct tests pass (`ctest -R test_ssd1306_adapter`), including 25
  repeated runs.
- Adapter/canvas coverage from the `test-native-coverage` build: 84/84 lines,
  23/23 functions, 27/30 branches. The three uncovered branches are on the
  constructor's member-initializer line; every adapter decision is covered.
- All 26 native suites and 266 Python firmware/OLED tests pass.
- Existing aggregate coverage gates pass: 97.0% lines, 89.7% branches. The separately
  measured extracted sketch regions remain at 100% lines and branches.
- Mega build passes: 56,358 bytes flash and 5,939 bytes static RAM.

The library's display() returns no transfer status. The tests show what reaches
the panel over the bus, including a stale panel after a NACK; electrical bus
behavior remains outside the device fake. The status font is the library's default,
so selecting it changes nothing on the panel. Existing renderer and simulator tests
remain responsible for their own rendering behavior.

No production fix was introduced. This completes the OLED review checkpoint.
