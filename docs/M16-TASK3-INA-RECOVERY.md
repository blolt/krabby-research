# INA acquisition and recovery

INA recovery now uses the SparkFun driver exclusively. Its begin() performs the
address acknowledgment and INA228 identity check; the adapter no longer performs
an additional Wire probe. The configured bus and address are unchanged.

## Acquisition and retry behavior

All four fields are attempted while the adapter is up. Each failed driver read
produces NaN for that field, preserving the other readings. A sample is valid only
when all four calls succeed. Numeric NaN/infinity with a successful driver status
still counts as acquisition success; no plausibility checks were added.

One failed sample counts once toward recovery. A fully successful sample clears
consecutive failures. Reads continue during transient failures and cooldown while
the adapter is up. Three consecutive failed samples qualify a restart, subject to
the existing two-second retry interval.

The sample that triggers a restart is returned unchanged, even when restarting
succeeds. There is no immediate reread to conceal the failed acquisition. If
restarting fails, the adapter becomes unavailable and returns default unavailable
measurements until a retry is permitted.

A successful retry from the unavailable state reads a sample in that same call.
That call has already counted toward the retry: if its new reading fails, it does
not count a second failure or schedule another restart. Following calls continue
the normal acquisition policy. Raw diagnostic/calibration accessors do not update
recovery state.

## Configuration and charge

After every successful driver begin, the adapter restores conversion-ready alert
configuration and continuous ADC mode, retains the two-millisecond configuration
delay, and reapplies shunt calibration when explicitly configured.

Charge-preserving recovery skips device reset and accumulator reset. It no longer
skips alert/mode configuration. Explicit initialization retains the previous reset
behavior. Recovery after failed startup also avoids accumulator reset; only an
explicit begin configured to reset charge requests that operation.

A real power loss may erase accumulated charge. This change prevents software
recovery from requesting that erasure; it cannot recover charge lost in hardware.

## Tests and fixture review

The 16 direct adapter tests cover transient failures followed by success, partial
samples at the recovery threshold, failed restart, cooldown boundaries/rollover,
failed reads after successful reinitialization, and independent monitor histories.
All required configuration failures during charge-preserving recovery are tested.

The power-poll substitute now returns errors when a device is absent and supports
per-field read-status injection. Successful numeric NaN scenarios remain separate.
A new partial-current failure replay verifies that voltage still reaches telemetry
and the display while acquisition validity is false, recovery qualifies, and the
other monitor stays live.

Existing healthy fixtures are unchanged. Changes to eight startup/disconnect
fixtures remove redundant probe events, reflect driver begin attempts and changed
failure transitions. Two additional fixtures now exercise actual staggered and
repeated acquisition failures, including charge retention. Non-disconnect startup
fixture changes were checked to affect only event sequences and adapter counters.

To run the suite:

```sh
make -C firmware test-native
```

## Boundaries

Validation passed: all 25 native suites, 266 Python tests, and the GCC coverage
gates. Direct INA adapter coverage is 75/75 lines, 92/92 branches, and 13/13
functions. The Mega build uses 56,404 bytes of flash and
5,939 bytes of static RAM: 46 additional flash bytes and unchanged static RAM.

Only `firmware/arduino/src/power_monitor/ina228_adapter.h` changed in the production
firmware tree, verified against a before/after SHA-256 snapshot. The sketch, IMU,
OLED, display model, simulator, retry-policy implementation, and thresholds are
unchanged. Shared physical bus recovery remains deferred: an INA alone still
cannot clear a stuck Qwiic bus through this recovery path.

The power-poll harness uses its existing extracted sketch regions and simplified
host timing. It is not a complete sketch or electrical simulation. Driver setup
arguments/delays are checked by the direct adapter tests; the Mega build checks
compilation with the real SparkFun library.
