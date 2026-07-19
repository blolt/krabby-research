# M16 Power Bus & Battery Safety

In-repo reference for Milestone 16 Task 3 — **battery safety only**.
Source of record: `patina-foundation-grants/.../Milestone16-I2C-Sensors/TASK-3-POWER-BUS-INA228.md`
(this doc is safety-only; the octopus framing + bench-octopus fallback now live in
`hardware/Uno-v0.2/diagrams/BOM.md §6`, the topology in the WireViz source
`docs/M16-POWER-BUS-WIRING.yml`, and the constants in
`firmware/arduino/sensors_config.h` — that header is the single contract; if it
and this doc disagree, the header wins).

Closes **AC 3b** (battery-safety section present); AC 3a (octopus + bench-octopus
fallback) now lives in `diagrams/BOM.md §6`. §2 was hardened after an adversarial
safety review (2026-07 bench-safety critique); read §2 and §2.1 in full before wiring.

---

## 2. ⚠️ Battery safety — read fully before wiring (AC 3b)

The voltage (12–24 V) will not shock you through dry skin. **The hazard is the
fault current.** A large LiFePO4 pack can dump **hundreds to thousands of amps
into a short** — enough to vaporize a wrench, weld a ring to your finger, and
start a fire in the time it takes to flinch. Every rule below exists to keep a
short from ever happening and to make sure something opens the circuit *fast* if
one does. This is real high-amperage DC work; nothing here is optional.

### A. Before you touch anything — you, and the space

- **REMOVE ALL METAL FROM YOUR HANDS AND WRISTS** — rings, watch, bracelet, metal
  band. A ring across a terminal welds instantly and can deglove a finger. This
  is the single most common way people get hurt at these currents.
- **DO NOT ENERGIZE ALONE.** A second person stands clear of the lugs, near the
  disconnect. Before you start, confirm they know how to (1) open the breaker
  **and** (2) physically disconnect the battery, and that a hot / hissing /
  swelling / venting battery means **evacuate and call 911** — not "open the
  breaker and peek."
- **PPE:** face shield (not just safety glasses) and insulated gloves for
  handling lugs and the first energize; sleeves rolled.
- **Insulated tools** = VDE / 1000 V-rated (or genuinely insulated) — *not* a
  screwdriver with tape on the handle.
- **Workspace:** bare concrete, metal, or a fire blanket — **not wood or
  plastic.** A Class-ABC extinguisher **and** a bucket of dry sand within arm's
  reach. Flammables cleared, no drinks on the bench, decent ventilation, the
  battery sitting stable so it cannot slide or tip.

### B. The fuse — the one part you cannot improvise

- **A bare "150 A ANL" is not a complete spec.** The parameter that decides
  whether a fuse *clears* a short or *arcs over and keeps conducting* is its **DC
  interrupting rating (AIC)**. Commodity ANL fuses are ~2 kA AIC; a large
  low-resistance LiFePO4 can exceed that, in which case the fuse arcs, sprays
  molten metal, and can weld closed while the battery keeps dumping.
- **Use a Class-T fuse** (~20 kA AIC) **or** a fuse/breaker with a **datasheet DC
  AIC above your battery's short-circuit current** and a **DC voltage rating ≥
  your pack voltage.** Check the datasheet *before buying*. An AC-rated or
  automotive part may fail to interrupt DC.
- Keep the **150 A value** (it protects the 2 AWG battery lead). **Do not
  downsize it** because the bench draws less current — it is *wire* protection,
  not load protection. Any thinner branch (10 AWG to an H-bridge, a bench test
  load on small wire) needs **its own** branch fuse sized to that wire.
- **Your battery's internal BMS is NOT your fault protection.** The external
  terminal fuse is mandatory regardless of any BMS; do not rely on the BMS to
  clear a bench short.

### C. "De-energized" means the fuse is OUT — not just a breaker open

- For make/break isolation, **pull the fuse or disconnect at the battery
  terminal** — a *visible air gap*. A breaker can weld shut or get bumped; never
  trust one toggle as both the fault-interrupt device *and* the isolation for
  every wiring step.
- Everything **downstream** of the fuse is protected once it is in. The
  connection **at the battery terminal itself** (and the inter-battery series
  jumper, if any) is **upstream of the fuse and can never be protected.** Make
  those the *last* connections, one hand, with everything else already wired and
  the fuse out — never land a hot lead whose far end is loose on the bench.

### D. Build order (fuse OUT the entire time)

1. **Trace-cut the two onboard INA228 shunts now, with NO battery on the bench.**
   It is knife / soldering-iron work and has zero electrical dependency on the
   pack — do it during software prep, not next to a live battery.
2. **Mount the fuse holder / breaker on Pack+ FIRST**, in the open/pulled state:
   land its **downstream (dead) end first**, then the **battery-terminal end
   last**. Cap or cover the downstream stud.
3. Build the rest downstream (shunt → INA228 Pack 0x40 → bus) with the **fuse
   still out**.
4. **Fuse the midpoint sense lead (two-battery build only).** The Midpoint INA228
   (`0x41`) VBUS tap lands on the pack midpoint, which is **upstream of the 150 A
   pack fuse** and therefore never protected by it. Put a **low-amperage inline
   fuse (0.5–1 A, `FUSE_MID` in the WireViz source)** in that sense lead between
   the midpoint tap and the INA228 VBUS pin, so a chafed or shorted sense wire
   opens its own fuse instead of arcing an unfused tap off the live pack. Land it
   with the pack fuse still OUT, like every other connection.
5. **Insulate every exposed live junction** before energizing — boots/covers on
   the fuse studs and on the shunt's two power lugs. The shunt carries full fault
   current until the fuse clears; its lugs are a live short target, not just a
   measurement point.

### E. Pre-energize verification gate (fuse still OUT, breaker open)

Do all of this *before* the fuse goes in. **Set the DMM to DC-VOLTS (not amps,
not continuity) whenever you are near a live terminal** — a meter left in amps or
continuity placed across the pack is itself a dead short.

- **No dead short:** DMM in resistance/continuity, probes on the **load-side
  (downstream) Pack+ rail ↔ Pack−** — *never across the battery terminal itself,
  which stays live upstream of the OUT fuse* → must read **high / no continuity**
  (let it settle if the load has input caps). The open fuse isolates the
  downstream circuit, so probing the load side is what actually exercises this
  check. A **beep = dead short = STOP** and find it.
- **Polarity:** the load-side Pack+ rail reads *positive* vs Pack−.
- **Ground bond:** each INA228 board GND is bonded to Pack− and reads ≈ 0 V vs
  Pack− (single-point star ground). A floating sense ground can push VBUS / IN
  outside their 0–85 V window and **silently fry the chip** — no arc, no warning.
- **Sense orientation:** with the fuse OUT, only the **Midpoint VBUS** is live (it
  taps the pack midpoint *upstream* of the fuse) — confirm it reads its expected
  ~half-pack magnitude vs ground. The **Pack VBUS and IN+/IN− taps sit downstream
  of the OUT fuse and read ~0 V now** — confirm their polarity/magnitude under load
  during first energize (§F), not here. **Single battery** (§2.1): no midpoint tap
  exists, so defer this whole check to first energize.
- **Walk every connection** against the topology diagram; all power lugs torqued;
  **no tools, DMM leads, or wire offcuts bridging anything.**

### F. First energize (buddy present, everyone clear of the lugs)

- Insert the fuse / close the breaker.
- Watch for **arcing, heat, smell, hiss, swelling.** Expected: pack reads your
  battery's nominal (see §2.1 for your single-battery number).
- **Any anomaly → open the breaker immediately AND STOP. Do not re-energize to
  "try again."** Diagnose with the fuse OUT (battery physically disconnected for
  anything upstream of the fuse). Re-close only after the specific cause is found
  and fixed.
- **Hot / hissing / swelling / venting battery → thermal event: EVACUATE, call
  911.** Opening the breaker does *not* stop a runaway cell.

### Reference — reading a DMM safely, and terms

- **Continuity mode beeps when connected.** With the fuse OUT you want **NO beep**
  across the **load-side Pack+ rail ↔ Pack−** (not the battery terminal, which is
  live upstream of the fuse). Use **DC-volts** to read voltage. Hold both probes in
  one hand (or land one at a time) so your hands never bridge two nodes.
- **Kelvin sense terminals** = the small separate sense screws on the shunt,
  distinct from its two big current lugs. Wire IN+/IN− to the *sense screws*,
  never the power lugs.
- **Calibration is live work.** `K S` / Procedure C in
  `docs/M16-INA228-CALIBRATION.md` force real current through the shunt on an
  energized pack — same PPE, buddy, and fuse discipline apply. **De-energize
  (fuse out) before connecting any electronic load or current source, then
  re-energize to run the capture.**

---

## 2.1 ⚠️ Single-battery variant — READ THIS if you have one battery

If you have **one battery** (not two 12 V in series), **there is no midpoint
node.** The Midpoint monitor exists only to measure the junction *between* two
series batteries. So:

- **SKIP** the series link, the **Midpoint INA228 (`0x41`)**, its VBUS-to-midpoint
  tap, and its sense-lead fuse — entirely.
- **SKIP** the per-battery / divergence checks. `batt_a`, `batt_b`, and the
  divergence flag are **meaningless with one battery** — ignore them; do **not**
  treat the mismatch as a wiring fault to hunt down while the pack is live.
- **NEVER open the battery case to fabricate a midpoint.** Tapping an internal
  cell or BMS node is a live, unfused, fire-prone short path. If any instruction
  says "tap the middle," it does not apply to you — don't.
- **Everything else is unchanged:** Pack INA228 (`0x40`), the external shunt, the
  fuse, the firmware, and pack V / I / P calibration all work exactly the same on
  a single battery.
- **Expected readings:** `pack_v` ≈ **your battery's nominal** — a 12 V box reads
  ~13 V, a 24 V box reads ~26 V. Use *your* number, not the two-battery "24–26 V"
  in older step text. `pack_i` / `pack_w` are valid; `batt_a` / `batt_b` /
  divergence are N/A.
- **Fault current can be higher, not lower.** A single large low-resistance cell
  can source *more* prompt short-circuit current than the two-in-series case.
  Read your battery's datasheet max-continuous and short-circuit current and
  confirm your fuse's DC AIC (§2B) and wire gauge are rated above it.

---

## 3. Topology

Topology and INA228 wiring are the WireViz source `docs/M16-POWER-BUS-WIRING.yml`
(rendered to `assets/M16-power-bus-wiring.svg`).

## 4. Constants

Constants are the contract in `firmware/arduino/sensors_config.h`.
