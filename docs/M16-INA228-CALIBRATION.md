# M16 INA228 Bench Calibration Procedure (AC 3i)

Per-board calibration of the two INA228 power monitors on the leader I2C bus:

| Role | I2C addr | What it measures | What we trim |
|------|----------|------------------|--------------|
| Pack     | `0x40` | Total pack V/I/P/charge across the external 200 A / 75 mV shunt | VBUS gain+offset, **and** shunt current trim |
| Midpoint | `0x41` | Lower-battery VBUS only (current channel grounded) | VBUS gain+offset |

The upper battery is derived on-board as `battB = packV - battA`, so it inherits
both boards' VBUS trims — calibrate both monitors before trusting divergence.

Calibration values persist in EEPROM at `EEPROM_INA_CAL_ADDR` (byte 66, block
`InaCalData`, magic `0xC8`). They survive reflash and power-cycle and load
automatically at boot (`inaSetup` -> `inaCalPlausible`). An uncalibrated board
runs identity trims (gain 1, offset 0, shunt 1): the reading is uncorrected, but
never wrong.

## Correction model

Applied live every telemetry tick in `battAppendTelemetry`:

```
packV = rawBusV_pack * packVGain + packVOffset
battA = rawBusV_mid  * midVGain  + midVOffset
packI = rawCurrent_pack * packShuntCal      (and packW likewise)
```

- **VBUS offset+gain** correct the bus-voltage ADC path against a reference DMM.
- **packShuntCal** corrects the pack current/power against a known forced current.

## Safety: no capture can brick a board

Every capture path validates *before* it writes EEPROM. A reference or a solved
trim outside the bounds in `sensors_config.h`
(`INA228_CAL_*`) is rejected with a `... aborting (no write)` message and the
prior calibration stays in force. Writes are torn-write-safe: the block is
streamed with `magic=0x00` first and the real magic byte is flipped in last, so a
power loss mid-write fails the magic check on reload and falls back to identity
(same scheme as `imuCaptureGyroBias`).

## Serial command reference (`K`)

Leader board only (FRONT or the solo-on-USB bench board). Issue over the USB
serial console at 250000 baud. The command is **not** forwarded to followers.

| Command | Action |
|---------|--------|
| `K ?` | Print current calibration + usage |
| `K L <packRefV> <midRefV>` | Capture the **LOW** point of a two-point VBUS cal (held in RAM) |
| `K H <packRefV> <midRefV>` | Capture the **HIGH** point, solve gain+offset for both boards, save+apply |
| `K Z <packRefV> <midRefV>` | Single-point VBUS **offset** trim (gain unchanged), save+apply |
| `K S <knownAmps>` | Pack **shunt** current trim, save+apply |

`packRefV` / `midRefV` are the DMM-measured true voltages at the two monitor
sense points at the instant you issue the command. `<midRefV>` is the *lower*
battery voltage (the Midpoint monitor's VBUS), not the pack.

## Bench setup

You need:

- The leader board flashed and on USB, both INA228s enumerated (`K ?` prints;
  boot log shows `INA: Pack (0x40) online` and `INA: Midpoint (0x41) online`).
- A calibrated bench DMM.
- A variable/known voltage source for the VBUS points (either the real 24 V pack
  plus a partially-drained state to get a second point, or a bench PSU wired to
  the pack/midpoint sense nodes).
- For the shunt step: an electronic load or bench supply that can force a known,
  steady DC current through the external pack shunt, with the DMM in series (or a
  trusted current-limited source) to establish the true amperage.

Wire the DMM to read the *same* node the monitor senses:
- Pack VBUS: across the pack terminals (IN+/IN- bus side of the Pack INA228).
- Midpoint VBUS: from the battery midpoint tap to pack ground (the lower battery).

## Procedure A — VBUS gain+offset (two-point, preferred)

Two points fully solve the line `corrected = raw*gain + offset`; use points as
far apart as practical (e.g. ~20 V and ~26 V on the pack) for the best gain fit.

1. Apply the LOW voltage. Let it settle.
2. Read the DMM at both sense points -> `packLo`, `midLo`.
3. Issue: `K L <packLo> <midLo>`. Firmware snapshots the raw monitor readings.
   Confirm the `LOW point captured` reply.
4. Apply the HIGH voltage. Let it settle.
5. Read the DMM again -> `packHi`, `midHi`.
6. Issue: `K H <packHi> <midHi>`. Firmware reads raw again, solves and saves
   `packVGain/packVOffset` and `midVGain/midVOffset`, and echoes the new block.
7. **Verify** (see below).

If the two points are too close (`packDenom < 0.5 V` / `midDenom < 0.25 V`) the
solve is rejected — spread the points further apart and retry from step 1.

## Procedure B — VBUS offset-only (single-point, quick field re-trim)

Use when the gain is already trusted (from a prior two-point cal) and you only
need to null a small offset drift at the operating point.

1. Apply a known voltage near the normal operating point. Let it settle.
2. Read the DMM -> `packRef`, `midRef`.
3. Issue: `K Z <packRef> <midRef>`. Firmware holds the current gains and solves
   the offsets so the corrected reading equals the reference, then saves+applies.
4. **Verify.**

## Procedure C — Pack shunt current trim

Corrects the pack current/power against a known forced current. `packShuntCal`
is a proportional trim (`packI = raw * packShuntCal`), so calibrate at a current
in the normal operating band for the best fit.

1. Force a known, steady DC current through the external pack shunt, in the
   normal sense direction. Establish the true value on the series DMM -> `Aknown`
   (signed to match the monitor's sign convention).
2. Issue: `K S <Aknown>`. Firmware reads the raw pack current and saves
   `packShuntCal = Aknown / measured`, then applies it live.
3. **Verify:** hold the same current, watch the `BATT` telemetry `pack_i` field
   — it should now read `Aknown` within tolerance.

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

`K ?` at any time prints the stored trims for a record of what a board carries.

## `packShuntCal` status

`packShuntCal` is **active**, not reserved: it multiplies the live Pack current
and power in `battAppendTelemetry` and is captured by `K S`. Identity (1.0) until
a shunt trim is run, so an uncalibrated board's current is uncorrected but never
wrong. It is bounded to `[INA228_CAL_MIN_GAIN, INA228_CAL_MAX_GAIN]` on both
capture and EEPROM load, so a garbage value can never scale the reading wildly.

## EEPROM layout

See `sensors_config.h`. The INA block is 22 bytes at address 66-87:
`magic(0xC8) + schema(1) + packVOffset + packVGain + midVOffset + midVGain +
packShuntCal` (five floats). A `static_assert` in `arduino.ino` pins
`sizeof(InaCalData) == EEPROM_INA_CAL_SIZE`, so a layout change that forgets the
size constant fails to compile rather than corrupting a neighbor block. Bump
`EEPROM_INA_CAL_SCHEMA` on any field reshuffle.
