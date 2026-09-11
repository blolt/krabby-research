# Task 3 measurement checkpoint

## Current driver: SparkFun INA2XX

SparkFun INA2XX 1.0.0 with Toolkit 1.2.0 replaces Adafruit. Each failed numeric
read becomes NaN independently; successful fields are preserved. Pack shunt
configuration, application calibration, and EEPROM layout are unchanged. Only
pack receives a shunt configuration; midpoint is used for voltage. Startup resets
and continuous conversion are explicit, while pack recovery preserves charge.
`isValid` replaces `wasInaAvailable` and is true only when all four vendor reads
succeed. Failed or unread fields are NaN. Calibration preserves this acquisition
result. Voltage consumers check the voltage fields independently, so failed
current, power or charge reads do not hide usable voltage readings. Recovery
scheduling is unchanged.

The migration notes below describe earlier checkpoints, including the former
Adafruit API's lack of read-status reporting.

Ina228Adapter returns voltage, current, power, charge and wasInaAvailable.
Calibration preserves that acquisition snapshot. Only pack configures its external
shunt; capture commands and EEPROM layout remain unchanged.

Voltage-plausibility checks and the split-plausibility helper are removed.
Polling passes acquisition availability to noteRead. Failed initialization still
retries, but numeric read values no longer mark an initialized adapter down.
Because the vendor numeric API exposes no individual read success, this cannot
detect a post-initialization disconnect by itself. No substitute checker was added.

BatterySplit uses Volts and calculates A, B and divergence once. Telemetry reports
current numeric values and divergence directly, without stale or sentinel fallback.
Flags report acquisition availability. Host split availability uses only those flags.
OLED availability uses pack for pack, midpoint for A, and both for B. The existing
numeric-format limits and bar-fill clamping remain rendering constraints.
Calibration input validation remains part of calibration persistence.

Scenario fixtures cover the new behavior: NaN/out-of-range reads do not trigger
recovery. Healthy fixtures remain unchanged; failed-initialization scenarios change
only their previously gated divergence bit. Each poll checks acquisition flags and
current numeric output. Adapter tests retain explicit recovery-policy coverage.
See M16-TASK3-UNITS-REVIEW.md for the earlier units audit; its references to split
plausibility predate removal of those checks.

BatteryTelemetryFrame is removed. appendBatteryTelemetry accepts the pack
measurement and BatterySplit directly, plus midpoint availability and region.
No metadata is added to the derived split. Wire order, precision and flags remain
unchanged; all 21 existing transcripts are retained without regeneration.

## Direct derived values and display inputs

BatterySplit and its helper are removed. The poll directly computes
inferredBattBVoltage and isDiverged. appendBatteryTelemetry accepts both monitor
measurements, inferred B, the divergence boolean and the region byte; it performs
formatting only. The OLED consumes the measurements and inferred B directly.
Duplicate latest-voltage/availability globals and lastGoodMidpointVoltage are
removed. The inferred B value is retained alongside the two measurements solely
for the deferred display render.

All 21 scenario outputs are byte-identical after removing test-record lines for
the deleted display/cache state. Exact inferred-B assertions and serializer tests
cover the new path. No firmware voltage-plausibility gating is introduced.

## Acquisition before serialization

readPowerMeasurements performs INA acquisition, calibration, recovery bookkeeping
and inferred-B calculation without printing. The leader calls it on the existing
telemetry tick before starting its output line. The later sensor-output block
computes divergence and calls appendBatteryTelemetry directly. Power reads now
precede actuator printing and the IMU read; wire field order is unchanged. Recovery
still uses one timestamp taken before the INA reads. Characterization compiles
both acquisition and serialization regions verbatim and invokes them separately.

## Adapter-owned recovery

INA measure() now follows the IMU ordering: when unavailable, consult its recovery
policy and attempt initialization when due; after successful recovery, read and
return a fresh measurement in the same call. noteRead is removed from the public
API and sketch. The adapter retains the TwoWire instance supplied to begin(),
returns unavailable before begin(), and never repeatedly initializes a healthy
device. Pack recovery preserves the existing accumulator-reset policy. Numeric
values still do not imply transaction failure or trigger recovery.

The application calibration helpers are preserved. Healthy transcripts change
only by removal of the sketch's timestamp call; failed-initialization scenarios
now acquire and publish during the successful recovery call. Each unavailable
adapter timestamps its own retry attempt, as the IMU does.

## Calibration functions

PowerCalibration applies its existing record directly through applyPackCalibration
and applyMidpointCalibration. The sketch passes each INA measurement directly to
its corresponding function. No separate calibrator objects or cached copies of
settings are retained. Pack uses typed voltage addition and shunt scaling; midpoint
changes only voltage. Availability is preserved. EEPROM layout and capture behavior
remain unchanged.

## Divergence on unavailable readings

The existing divergence bit is true for measured imbalance or assumed divergence
when either adapter is unavailable or either battery voltage is non-finite.
It remains a boolean in the same wire position. The existing DIVERGED GUI label
and DIVERGE compact-log label remain visible when a monitor is unavailable.
Numeric measurements are preserved without last-good substitution.
