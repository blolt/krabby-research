# Krab OLED Status Render — Specification (M16 Task 2)

Authoritative contract for the krab status screen. The Python sim
(`krab.py` + `ssd1306.py`) is written to be a **line-for-line mirror of the AVR
firmware** so the port is mechanical and the panel matches the sim pixel-for-pixel.
This file records the rendering contract and the hardware limits that shape it.

- **Target panel:** SparkFun Qwiic OLED 1.3" (`Qwiic1in3OLED`), 128×64, 1-bit.
- **Library:** SparkFun Qwiic OLED, pinned **v1.0.9** (newer versions pull in
  C++ `<map>` and break the AVR build).
- **MCU:** ATmega2560 (Arduino Mega), AVR, Harvard architecture.

## 1. The 1:1 contract

The sim renders the exact logical framebuffer the library composes before it
ships pixels over I2C. Every sim primitive in `ssd1306.py` is a verified port of
its `qwiic_grbuffer.cpp` counterpart, so "looks right in the sim" == "looks right
on the panel." Two fidelity gaps were found and closed (see §3); the goldens in
`tests/unit/oled_sim/test_render_golden.py` are pinned to hardware-faithful output.

**Nothing here is aesthetic license.** If the sim and panel ever disagree, the
sim has a bug — fix the sim, do not paper over it in firmware.

## 2. State model (`KrabState`)

| field         | type            | meaning / units                                             | range enforced        |
|---------------|-----------------|-------------------------------------------------------------|-----------------------|
| `controllers` | `{str: bool}`   | board present/detected: `FRONT`, `LEFT`, `RIGHT` (v0.2 by-side) | —                  |
| `legs`        | `[(y,h,k)]×6`   | 6 legs `[FL,FR,ML,MR,RL,RR]`, each = (yaw, hip, knee) glyph state | `extend/retract/hold/disc` |
| `batt`        | `(float,float)` | 2 cell fill fractions, 0..1, from `battery_fraction(V)` (§7) | clamped 0..1 at draw  |
| `role`        | `str`           | `roleLabel()`: `FRONT`/`LEFT`/`RIGHT`/`UNKWN`               | keep ≤5 glyphs        |
| `roll,pitch`  | `int`           | degrees from IMU                                             | **clamped ±99** for display |
| `pack_v`      | `float`         | pack voltage; firmware holds it as an **integer** (see §4)  | formatted from decivolts |

## 3. Primitive semantics that constrain the design

These are the library behaviors the design must respect. All are now replicated
exactly in `ssd1306.py`.

- **`pixel(x,y)`** clips at `x≥128 || y≥64` (and, in the sim, `x<0 || y<0`). On
  AVR the args are `uint8_t`, so a negative coordinate must never reach the API
  (§4).
- **`line()`** is the library's steep-swap Bresenham (`err = dx/2`). Horizontal,
  vertical, and exact-45° lines are unambiguous; **other slopes depend on this
  exact tie-breaking**, so the sim ports the algorithm verbatim rather than
  approximating. Every line in the current render is H/V/45°, but bent legs or
  any angled element rely on this.
- **`rectangle(x,y,w,h)` — the sharp edge.** The library draws top+bottom always,
  but the **vertical side walls only when height ≥ 4** (`y1-y0 ≥ 3`); `w≤1 || h≤1`
  degenerates to a line. **A closed outline ≤3px tall is impossible via
  `rectangle()`** — it renders open-ended. Consequences in this render:
  - Body (32×31) and battery cells (`18×7` each, horizontal, laid **end-to-end**
    in a row — not stacked — with a 4px gap and a 2×3 terminal nub on each cell's
    right edge): closed, both sides drawn. ✅ The batteries are deliberately ≥4px
    tall so `rectangle()` gives a closed cell (Fletcher found the earlier 3px
    rails unreadable). **Placement (AC-2b): top-left corner** (`BAT_X, BAT_Y =
    2, 11`), in the strip between the text separator (y=9) and the body (y=22) —
    deliberately off the body, not stacked on its rear. This departs from AC-2b's
    "two stacked bars on the rear"; the top-left placement is an intentional,
    Fletcher-approved deviation (legible cells beat rear-stacked on a 1-bit 128×64
    panel). Geometry is the shipped layout in `krab.py` (`BAT_W, BAT_H, BAT_HGAP,
    BAT_NUB_W, BAT_NUB_H`).
  - Eyes (`3×3`): closed hollow boxes, drawn as **4 explicit `line()` walls**,
    NOT via `rectangle()` (which would strip the side walls on a 3px box and
    render them open on the panel). This is the canonical pattern for any small
    closed box: draw the walls yourself.
- **`rectangleFill(x,y,w,h)`** fills `w×h` pixels inclusive (`x..x+w-1`,
  `y..y+h-1`). Used for the solid body regions and battery fill.
- **`text(x,y,s)`** uses `QW_FONT_5X7`: 6px advance (5 wide + 1), origin top-left,
  clips at the right edge. Budget ≈ **21 glyphs / 128px** per line.

## 4. Firmware limits (why the code looks the way it does)

The sim executes these the firmware way so the constraints are exercised, not
just documented:

1. **No `%f`.** AVR `snprintf` drops float support unless you link
   `-lprintf_flt` (flash cost). The pack voltage is formatted from **integer
   decivolts** as two `%d` fields (`dv/10`, `dv%10`) — see `krab.py` top strip.
   The sim does the same integer round-trip so the rendered string is identical.
2. **Signed coordinate math.** Leg/glyph offsets go negative before clipping.
   Firmware must compute them in signed `int` and only pass on-panel values to
   the `uint8_t` API; a negative stored in `uint8_t` wraps to ~200 and streaks
   across the panel. Python ints are unbounded, so the sim can't catch this —
   the port note in `krab.py` and this line are the guard.
3. **Explicit flush.** Nothing appears until `oled.display()`. The sim's
   `OLED.display()` is a no-op called at the end of `render()` to mark the point.
4. **Draw mode = copy (default).** The render assumes set-pixel semantics. Do
   **not** switch to XOR mode — glyphs drawn over a filled body region would
   invert instead of set.
5. **Font in PROGMEM.** The library keeps font tables in flash; use
   `QW_FONT_5X7`. A different font = different glyph bytes = sim mismatch.
6. **Update timing (appearance-neutral).** Full frame ≈ **120 ms**; a single
   dirty 8px band ≈ **5.8 ms** (measured, `bench_sketches/oled_dirty`). This
   affects refresh cost, not the image, so the sim does not model dirty regions.
   Firmware should redraw only changed bands.

## 5. Mechanical port map (sim → firmware)

| sim (`ssd1306.py` / `krab.py`)      | firmware (SparkFun C++)                    |
|-------------------------------------|--------------------------------------------|
| `d = OLED(); d.erase()`             | `oled.begin(); oled.erase();`              |
| `d.setFont("5x7")`                  | `oled.setFont(QW_FONT_5X7);`               |
| `d.text(x, y, s)`                   | `oled.text(x, y, s);`                      |
| `d.line/rectangle/rectangleFill(…)` | `oled.line/rectangle/rectangleFill(…);`    |
| f-string with `dv//10`, `dv%10`     | `snprintf(buf, n, "%d.%dV", dv/10, dv%10);`|
| `d.display()`                       | `oled.display();`                          |

Coordinate constants (`GLYPH`, `BAND_H`, `BODY_*`, `TBAR_Y`, `STEM_X`,
`REGION_OF_ACT`, `LEG_BAND`) transfer as-is — keep them as named `const` so the
two implementations stay in lockstep.

## 6. Verification

- `tests/unit/oled_sim/` — glyph shapes + inversion guard, by-side topology,
  disjoint region tiling, chrome (incl. the battery voltage→fraction mapping),
  and 4 golden full-frame snapshots.
- Text fidelity confirmed on the physical panel ("KRABBY").
- Run: `testenv/bin/python -m pytest tests/unit/oled_sim/ -q`
- Live preview: `firmware/oled_sim/serve.py` → http://127.0.0.1:8080 (edit
  `krab.py`, browser auto-reloads).

## 7. Battery bars: voltage → fill (Task 3 AC 3g)

The `batt` fractions are produced by `battery_fraction(voltage)` from each 4S
LiFePO4 battery's voltage in the `BATT` telemetry frame (`batt_a_v`, `batt_b_v`):

- **On the render path now, not just in tests.** The sim builds a state's `batt`
  via `KrabState.from_battery_voltages(a_v, b_v, …)`, which runs each per-battery
  voltage through `battery_fraction()`; `viewer.py`'s scenes pass real volts (a
  healthy ~13.4 V pack, a low ~12.1 V pack) through that factory — there are no
  hand-picked fraction literals left. `render()` still **consumes** `batt` as
  fractions (the goldens are unchanged), so the volts→fraction step lives in the
  ONE place the firmware OLED port **also** does it. NB: the firmware OLED port
  **exists in-tree** — `arduino.ino`'s `oledRenderLive()` reads the live pack /
  per-battery volts and `oledBatteryFraction()` applies the identical
  `(v-12.0)/(13.4-12.0)` clamp (`OLED_BATT_EMPTY_V`/`OLED_BATT_FULL_V`) before
  driving each bar, via `oledRenderKrab()`. This is a real C++ port of this Python
  path, not future work; the two must stay in **lockstep** — the volts→fraction
  window here (`krab.py`'s `battery_fraction()` / `BATT_EMPTY_V` / `BATT_FULL_V`)
  and the firmware's `OLED_BATT_*` constants are duplicated on purpose and pinned
  by a parity test (`tests/unit/firmware/test_oled_port_parity.py`); change one and
  the other must move with it.
- Linear over a usable **resting** window: `BATT_EMPTY_V = 12.0` (~3.0 V/cell) →
  0%, `BATT_FULL_V = 13.4` (~3.35 V/cell, rested-full) → 100%, clamped.
- **Coarse by design.** LiFePO4's curve is flat (~3.2 V/cell from ~90% to ~20%),
  so this is a glance-gauge, not a precise SoC, and it reads low under load (sag).
  Coulomb counting off the INA228 charge register is the accurate upgrade (Task 4).
- Ports to firmware verbatim: `frac = clamp((v - 12.0) / (13.4 - 12.0), 0, 1)`.
- Per-battery imbalance is surfaced separately by the frame's `divergence` flag,
  not by the bars.
