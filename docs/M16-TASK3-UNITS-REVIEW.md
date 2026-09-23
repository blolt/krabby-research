# Task 3 units review

BatterySplit now stores Volts for A and B. Calculation and plausibility APIs take
Volts, as do voltage bounds and the sketch's pack/midpoint locals. Same-unit <=
and >= operators extend LinearUnit; they use native comparisons directly so NaN
remains unordered. No implicit conversion or comparison with raw floats is added.

## Remaining avoidable exits

- PowerCalibration::applyPackCalibration/applyMidpointCalibration unwrap voltages
  for addition. Existing operator+ can preserve Volts throughout.
- correctPackCurrent/Power/Charge unwrap to multiply by a dimensionless gain.
  Existing scalarMultiply preserves Amps/Watts/Coulombs without rewrapping.
- Calibration reference and offset checks use raw numeric bounds. Type voltage
  limits as Volts and minimum current as Amps; retain typed subtraction and the
  same-unit comparison operators. Convert only when writing the EEPROM record.
- Ina228Adapter constructor/storage and PACK_SHUNT_* constants use floats. Ohms
  and Amps already exist; use them through configuration and unwrap at setShunt.
- Current calibration divides Amps by Amps to produce a dimensionless gain.
  A named same-unit ratio operation would make this intentional boundary explicit.
- DisplayFrame model sums unwrapped battery voltages and compares unwrapped
  angles. Typed addition is available; same-unit ==/!= could cover equality.
  Keep normalized bar fills, pixel coordinates and decivolt encoding numeric.

## Deliberate boundaries

Vendor APIs, Serial/telemetry formatting, CLI number parsing and EEPROM records
need raw representations. Convert immediately on input and only at the final
external call on output. EEPROM fields must retain their existing binary layout.
Calibration gains and normalized gauge fills are dimensionless floats.

isfinite/fabs currently require unwrapping at the math call. A named unit-aware
finite check and absolute-value method could contain those exits without changing
arithmetic. This remains in split validation/divergence today. Implement absolute
value with the appropriate floating-point operation, preserving signed-zero and
NaN behavior rather than inferring it from comparisons.

## Suggested migration order

1. Replace calibration addition/scaling with existing typed operations.
2. Type calibration limits and shunt configuration, preserving EEPROM layout and
   the exact values passed to the vendor.
3. Add only needed math/ratio/equality helpers with focused tests; migrate their
   consumers separately, including display calculations.

For each step, require unchanged polling transcripts and preserve NaN/infinity,
signed zero, comparison boundaries, and calibration order. This review covers
Task 3's power path and its shared units/display boundaries, not every raw numeric
operation in actuator control or the rest of the repository.
