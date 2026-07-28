# M16 INA228 Bench Calibration Procedure (AC 3i)

Per-board calibration of the two INA228 power monitors on the leader I2C bus:

| Role | I2C addr | What it measures | What we trim |
|------|----------|------------------|--------------|
| Pack     | `0x40` | Total pack V/I/P/charge across the external 200 A / 75 mV shunt | VBUS offset and shunt current trim |
| Midpoint | `0x41` | Lower-battery VBUS only (current channel grounded) | VBUS offset |

The upper battery is derived on-board as `battB = packV - battA`, so it inherits
both boards' VBUS trims — calibrate both monitors before trusting divergence.

Calibration values persist in EEPROM at `EEPROM_INA_CAL_ADDR` (byte 66, block
`PowerCalibrationData`, magic `0xC8`). They survive reflash and power-cycle and
load automatically at boot (`inaSetup` -> `loadPowerCalibration`). An uncalibrated board
runs identity trims (offset 0, shunt 1): its readings remain uncorrected rather
than being changed by invalid persisted calibration.

## Correction model

Applied live every telemetry tick in `battAppendTelemetry`:

```
packV = rawBusV_pack + packVoltageOffset
battA = rawBusV_mid  + midpointVoltageOffset
packI = rawCurrent_pack * packShuntCal
packW = rawPower_pack * packShuntCal
packCharge = rawCharge_pack * packShuntCal
```

- **VBUS offset** corrects each bus-voltage ADC path against a reference DMM.
- **packShuntCal** corrects Pack current, power, and accumulated charge against
  a known forced current.

## Invalid captures do not replace the active calibration

Every capture path validates *before* it writes EEPROM. A reference or a solved
trim outside the bounds in `sensors_config.h`
(`INA228_CAL_*`) is rejected with a `... aborting (no write)` message and the
prior calibration stays in force. Persistence uses a magic-last write:

- If power fails before the invalid marker is written, the prior valid block
  remains.
- After the invalid marker is written and before the final valid magic byte, the
  partial block is rejected on restart and identity calibration is used.
- After the final magic byte is written, the new complete block loads.

## Serial command reference (`P CAL`)

Leader board only (FRONT or the solo-on-USB bench board). Issue over the USB
serial console at 250000 baud. The command is **not** forwarded to followers.

| Command | Action |
|---------|--------|
| `P CAL VOLTAGE <packReferenceVolts> <midpointReferenceVolts>` | Capture both voltage offsets, save+apply |
| `P CAL CURRENT <knownAmps>` | Capture the Pack current/shunt scale, save+apply |
| `P CAL SHOW` | Print the currently loaded power-calibration values |
| `P CAL ?` | Print power-calibration command help |

`packReferenceVolts` and `midpointReferenceVolts` are the DMM-measured true
voltages at the two monitor sense points when the command is issued.
`midpointReferenceVolts` is the lower-battery voltage, not the total Pack
voltage. `knownAmps` is signed to match the Pack INA228 convention.

## Bench setup

You need:

- The leader board flashed and on USB. The boot log—not `P CAL SHOW`—must show
  `INA: Pack (0x40) online` and
  `INA: Midpoint (0x41) online`).
- A calibrated bench DMM.
- A known voltage source near the normal operating point, either the real 24 V
  Pack or a suitably rated bench supply connected to the Pack/Midpoint sense
  nodes.
- For the shunt step: an electronic load or bench supply that can force a known,
  steady DC current through the external Pack shunt, with a suitably rated and
  fused DMM in series (or a trusted current-limited source) to establish the
  true amperage.

Before connecting or changing wiring:

- Disable actuation and place the robot in a stable, unloaded condition.
- Remove Pack power before moving conductors.
- Confirm voltage/current ranges, polarity, lead placement, fuse rating, and
  equipment current rating before energizing.
- Do not use the INA228 `IN+`/`IN-` shunt differential pair as the two terminals
  of the Pack voltage-reference measurement.

Wire the DMM to read the same voltage nodes used by the monitors:

- Pack reference: Pack INA228 VBUS sense node to Pack ground.
- Midpoint reference: inter-battery midpoint to Pack ground (battery A).

Before capture, choose and record the engineering-approved voltage and current
accuracy tolerances. M16 does not specify numeric accuracy tolerances. The
`±2.0 V` offset bound is an input plausibility limit, not a passing accuracy
tolerance.

## Procedure A — VBUS offset capture

1. Apply a known voltage near the normal operating point and let it settle.
2. Record the DMM readings as `packReferenceVolts` and
   `midpointReferenceVolts`.
3. Issue `P CAL VOLTAGE <packReferenceVolts> <midpointReferenceVolts>`.
   Firmware solves both offsets, commits neither unless both are valid, then
   saves and applies both together.
4. Record the values returned by `P CAL SHOW`.
5. Verify both reported voltages at the capture point against the recorded
   tolerance.
6. Without recalibrating, verify at one or more independent representative
   operating voltages and record the results.

## Future improvement — two-point gain calibration

A two-point VBUS procedure could solve both gain and offset if bench evidence
shows that offset-only calibration is insufficient across the operating range.
It is intentionally not implemented in M16: the acceptance criterion requires
per-board offset trim, and shipping gain state and commands without that evidence
would expand the calibration workflow and EEPROM schema unnecessarily.

## Procedure B — Pack shunt current trim

Corrects Pack current, power, and accumulated charge against a known forced
current. `packShuntCal`
is a proportional trim (`packI = raw * packShuntCal`), so calibrate at a current
in the normal operating band for the best fit.

1. Force a known, steady DC current through the external pack shunt, in the
   normal sense direction. Record the series-DMM value as `knownAmps`, signed to
   match the monitor convention.
2. Issue `P CAL CURRENT <knownAmps>`. Firmware reads raw Pack current and saves
   `packShuntCal = knownAmps / measured`, then applies it live.
3. **Verify:** hold the same current, watch the `BATT` telemetry `pack_i` field
   and confirm it matches `knownAmps` within the recorded tolerance.
4. Repeat verification at a second representative current without recalibrating.
   Record both reference and reported values so the trim is not accepted merely
   because it fits its capture point.

A near-zero measured or requested current is rejected
(`INA228_CAL_MIN_SHUNT_TRIM_A`) since dividing by it is meaningless.

## Verifying against a DMM

After any VBUS capture, watch the leader telemetry `BATT` segment:

```
;BATT <pack_v> <pack_i> <pack_w> <pack_charge> <batt_a> <batt_b> <divergence> <power_state>
```

- `pack_v` should match the DMM pack reading within your DMM tolerance.
- `batt_a` should match the DMM lower-battery reading.
- `batt_b` (= `pack_v - batt_a`) should match the DMM upper-battery reading.
- With both batteries healthy and balanced, `divergence` should read `0`.

`P CAL SHOW` at any time prints the stored trims for a record of what a board
carries. `P CAL ?` prints help without mixing help text into the state output.

## Persistence verification

1. Record `P CAL SHOW` after both capture procedures.
2. Remove power from the Mega, restore power, and confirm the boot log reports
   `POWER CAL: loaded from EEPROM.`
3. Run `P CAL SHOW` and confirm all values exactly match the recorded block.
4. Confirm corrected telemetry remains within the recorded tolerances.
5. If EEPROM retention across firmware upload is a project requirement, reflash
   using the intended uploader and repeat steps 2–4. Reflash retention depends on
   uploader behavior and is not established by the EEPROM implementation alone.

## Calibration record

Retain this information with the bench evidence:

| Field | Recorded value |
|---|---|
| Board identity / role | |
| Date and operator | |
| DMM identifier and calibration status | |
| Voltage/current source and load | |
| Approved voltage tolerance | |
| Approved current tolerance | |
| Pack reference / reported / absolute error / pass-fail | |
| Midpoint reference / reported / absolute error / pass-fail | |
| Independent voltage point(s), errors, and pass-fail | |
| Known current / reported current / absolute error / pass-fail | |
| Independent current point(s), errors, and pass-fail | |
| `P CAL SHOW` before restart | |
| `P CAL SHOW` after restart | |
| Reflash-retention result, if required | |

## `packShuntCal` status

`packShuntCal` is **active**, not reserved: it multiplies live Pack current,
power, and accumulated charge in `battAppendTelemetry` and is captured by
`P CAL CURRENT`. Identity (1.0) until a current calibration is run, so an
uncalibrated board's shunt-derived measurements remain uncorrected rather than
being scaled by invalid persisted data. It is bounded to
`[INA228_CAL_MIN_GAIN, INA228_CAL_MAX_GAIN]` on both capture and EEPROM load,
so a garbage value can never scale the readings wildly.

## EEPROM layout

See `sensors_config.h`. The INA block is 14 bytes at address 66-79:
`magic(0xC8) + schema(1) + packVoltageOffset + midpointVoltageOffset + packShuntCal`
(three floats). `static_assert`s pin
`sizeof(PowerCalibrationData) == EEPROM_INA_CAL_SIZE`, so a layout change that forgets the
size constant fails to compile rather than corrupting a neighbor block. Bump
`EEPROM_INA_CAL_SCHEMA` on any field reshuffle.
