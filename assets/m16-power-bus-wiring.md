# M16 Power Bus — Wiring Diagram (AC 3j)

The 24 V pack, the external shunt, and the two INA228 monitors, as built and
verified on the bench. This is the rebuild reference: it records not just what
connects to what, but the several places where the obvious wiring is wrong.

M12 is not finished, so this is the **bench octopus** configuration §1 sanctions —
batteries on a table with the shunt and sense taps wired into the bus exactly as
they will sit on the robot. Only the chassis is missing; the electrical order is
the same.

## Power path

```
  batt+ ──[150 A fuse]── ⊙═══════ SHUNT ═══════⊙ ─────► octopus ──► MCU + 6 H-bridges
  (upper)                 │    200 A / 75 mV   │
                          │    0.000375 Ω      │
                        small                small
                        screw                screw
                          │                    │
                         IN+                  IN−
                          └──── Pack INA228 ───┘         VBUS ──┘ (load-side stud)
                                   0x41
                                onboard shunt REMOVED

  midpoint ●──────────────────────────────────────────► Midpoint INA228 (0x40) VBUS
  (junction)                                              IN+ / IN− ──► batt−

  batt−  ●────────────────── single point ─────────────► Mega GND
  (lower)
```

The fuse is the **first** element on Pack+, closest to the battery post — nothing
between it and the terminal (3b). The shunt is inline downstream of it, so every
octopus load is measured and nothing bypasses it (3c).

## Sense taps — the parts that are easy to get wrong

**Kelvin, not the studs.** IN+ and IN− land on the shunt's two *small* sense
screws, never the large current-carrying studs. The small screws sample the
potential at the ends of the resistive element; the studs would fold the bolt
joints' contact resistance into the measurement and drift as they loosen.

**IN+ is the fuse side, IN− the load side.** The INA228 measures `V(IN+) − V(IN−)`,
so with current flowing battery → load, the upstream tap sits higher and
**discharge reads positive**. Reversed leads give a correctly-scaled negative
current — which the shunt trim cannot fix, because it is a multiplier.

**Pack VBUS on the load side.** A second wire from the shunt's *load-side* large
stud, the same node as IN−. On the fuse side it would read high by the shunt drop
(`I × 0.000375 Ω`, ~37 mV at 100 A) — small enough to look like a calibration
offset, but scaling with current, so a single-point voltage trim would absorb it
at one load and be wrong at every other.

The Adafruit **VBUS-to-IN+ solder jumper stays open** on both boards. Bridged, it
would tie VBUS to the fuse side and defeat the above.

**Midpoint VBUS on the series junction**, measuring the lower battery against
batt−. The upper battery is derived in firmware as `batt_b = pack_v − batt_a`, so
it inherits both boards' trims.

**Midpoint IN+/IN− tied to batt−.** Its current channel is unused; tying both to
Pack− gives it a defined 0 V common mode instead of floating (3d.4). Electrically
this also makes its onboard shunt inert, which is why removing that one is
insurance rather than function.

## Ground — required, not optional

**One wire from batt− to Mega GND.** Both INA228s take their ground reference
through Qwiic from the Mega. If the Mega runs on USB and batt− is unreferenced,
IN+/IN− float at an undefined common-mode potential and the current channel reads
drift rather than current — on this bench it read −2.3 A of nothing, which fell
to −0.30 A the moment the reference was made.

**Single point.** Do not also ground the bench supply separately to batt−. At 2 A
the shunt drops 0.75 mV and the part resolves microvolts, so a second path is a
loop whose circulating current appears as differential offset. Make this
connection with the pack protection **open**, then close it.

Once the robot runs off the octopus normally, the Mega's own supply provides the
reference and this wire comes out.

## I2C chain

Four dupont jumpers from the Mega — **SDA D20, SCL D21, 3V3, GND** — into the
first Qwiic connector, then daisy-chained:

```
  Mega ──4× dupont──► Qwiic ──► LSM6DSO ──► OLED ──► Pack INA228 ──► Midpoint INA228
                               0x6B/0x6A    0x3D        0x41              0x40
```

Bus runs at **100 kHz** (`I2C_DEFAULT_BUS_CLOCK_HZ`); the OLED raises it to 400 kHz
for its own transfers and puts it back. Daisy-chain order is electrically
irrelevant — it is a bus — but this is the physical order as built.

The INA228s are powered from Qwiic (the Mega's 3.3 V), **not** from the pack they
measure. That is what lets a monitor stay alive and answering while its sense
wire is disconnected, and why the ground wire above is necessary.

## Addresses — swapped from spec §3

| Role | Address | A0 jumper |
|---|---|---|
| **Pack** | `0x41` | **bridged** |
| **Midpoint** | `0x40` | default, unmodified |

Spec §3 assigns Pack `0x40` on the reasoning that Pack should be the unmodified
board. This build is the other way round: **Pack is defined by carrying the
external shunt's Kelvin taps**, and the onboard-shunt desolder was done on the
board that already had A0 bridged. Electrically identical — only the labels move.

Recorded as a deviation against 3c, 3d, 3h.1 and 3h.2. The constants live in
`firmware/arduino/src/power_bus/power_bus_constants.h`.

## What the firmware reports

The leader appends a `BATT` segment to its telemetry line every tick:

```
;BATT <pack_v> <pack_i> <pack_w> <pack_charge> <batt_a_v> <batt_b_v> \
      <divergence_flag> <pack_region> <pack_valid> <midpoint_valid>
```

`batt_a_v` and `batt_b_v` are the two measured batteries — visible in the serial
stream, on the GUI's BATT row, and as the two OLED bars. `divergence_flag` trips
when `|batt_a − batt_b| > 0.5 V`.

`pack_valid` / `midpoint_valid` are per-monitor liveness. When one reads `0`, that
monitor's fields carry its **last trustworthy reading** — plausible-looking and
not current. Check them before trusting any value, and before calibrating against
one.

## Bench-verified

- Divergence trips at both edges, within 0.1 V of `2·batt_a ± 0.5`
- OLED `batt_b` bar sweeps its full range while `batt_a` holds fixed
- Pack bus voltage agrees with a DMM to **0.2 mV** before any trim
- VBUS offsets captured and persisted: `+0.0002 V` pack, `−0.0039 V` midpoint

Calibration procedure: `docs/M16-INA228-CALIBRATION.md`.

## Not yet built

Assembled-harness photos (3j) wait on M12 — there is no chassis to secure the
loom to, so the bench configuration above is the current state.
