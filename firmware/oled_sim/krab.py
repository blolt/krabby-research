"""Krab status-screen render (M16 Task 2) — pure state->draw-calls.

BASELINE = draft 1 (the liked version). We add features ONE AT A TIME from here,
reviewing each on hardware/sim before the next — no wholesale redraws.

Written against the OLED sim's SparkFun-mirrored API so it ports to C++ firmware
mechanically. State model:
  controllers: {"FRONT": bool, "MID": bool, "REAR": bool}  # present/detected
  actuators:   list of 6 glyph states [FL,FR,ML,MR,RL,RR], each of
               "extend"|"retract"|"hold"|"disc"
  batt:        (frac_a, frac_b) 0..1 bar levels; build them from per-battery
               VOLTAGES via KrabState.from_battery_voltages() (the same clamp
               the firmware OLED port runs on the BATT frame)
  role, roll, pitch, pack_volts
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ssd1306 import OLED, COLOR_WHITE, COLOR_BLACK


@dataclass
class KrabState:
    # v0.2 boards are grouped BY SIDE (firmware ACT_LIST): FRONT={FL,FR},
    # LEFT={ML,RL}, RIGHT={MR,RR}. (Fletcher 2026-07-15: front/mid/back is a
    # possible future, not v0.2.)
    controllers: dict = field(default_factory=lambda: {"FRONT": True, "LEFT": True, "RIGHT": True})
    # 6 legs [FL,FR,ML,MR,RL,RR]; each leg = (yaw, hip, knee) — the 3 actuators
    # per leg (hip-yaw, hip-lift, knee), so 18 joint glyphs total. Order from the
    # body outward: yaw (nearest), hip, knee (at the foot).
    legs: list = field(default_factory=lambda: [("hold", "hold", "hold")] * 6)
    batt: tuple = (0.8, 0.6)
    role: str = "FRONT"                              # firmware roleLabel(): FRONT/UNKWN/LEFT/RIGHT
    roll: int = 0
    pitch: int = 0
    pack_volts: float = 24.0

    @classmethod
    def from_battery_voltages(cls, *battery_voltages: float, **kwargs) -> "KrabState":
        """Build a state whose battery bars come from per-battery resting VOLTAGES,
        each mapped through battery_fraction() — the exact clamp the firmware OLED
        port runs on the BATT frame's per-battery volts (batt_a_v, batt_b_v). Pass
        one voltage per 4S battery; all other KrabState fields via kwargs. render()
        still consumes `batt` as fractions, so this only moves the volts->fraction
        step to the ONE place the firmware also does it."""
        return cls(batt=tuple(battery_fraction(v) for v in battery_voltages), **kwargs)


# --- battery state-of-charge gauge (voltage-window mapping) ---
# LiFePO4's discharge curve is flat (~3.2 V/cell from ~90% down to ~20%), so the
# bars are a coarse glance-gauge, not a coulomb-accurate SoC. Each 4S battery's
# resting voltage maps linearly over its usable window. A future state-of-charge
# design would need capacity, initialization/reconciliation, reset and brownout
# behavior, and a way to represent both batteries; that is outside this A/C.
BATT_EMPTY_V = 12.0                                    # ~3.0 V/cell resting -> 0% on the gauge
BATT_FULL_V = 13.4                                     # rested-full 4S LiFePO4 ~3.35 V/cell (Appendix C) -> 100%


def battery_fraction(voltage: float) -> float:
    """One 4S LiFePO4 battery's resting voltage -> 0..1 bar level, clamped."""
    return max(0.0, min(1.0, (voltage - BATT_EMPTY_V) / (BATT_FULL_V - BATT_EMPTY_V)))


# --- geometry (128x64): rectangular body, split by an upside-down T (⊥) ---
# Same rectangle + same legs as before; only the internal division changed. The
# ⊥ (horizontal bar above the bottom strip + a vertical stem up from its center)
# splits the body into the 3 by-side regions, which — with the legs where they
# already sit — line up exactly with the boards:
#   bottom strip (full width) = FRONT board (FL, FR legs at the bottom)
#   top-left  = LEFT board  (ML, RL legs on the left)
#   top-right = RIGHT board (MR, RR legs on the right)
TEXT_Y = 0
GLYPH = 9
BAND_H = GLYPH + 1                                     # 10 (leg row pitch, unchanged)
BODY_W, BODY_H = 32, BAND_H * 3 + 1                    # 32 x 31 (unchanged)
BODY_X, BODY_Y = (128 - BODY_W) // 2, 22               # centered (unchanged)
TBAR_Y = BODY_Y + 2 * BAND_H                           # 42: ⊥ horizontal bar
STEM_X = BODY_X + BODY_W // 2                          # 64: ⊥ vertical stem
REGION_OF_ACT = ["FRONT", "FRONT", "LEFT", "RIGHT", "LEFT", "RIGHT"]  # [FL,FR,ML,MR,RL,RR]
LEG_BAND = [2, 2, 1, 1, 0, 0]                          # leg row (0 top .. 2 bottom), unchanged

# battery gauge: two HORIZONTAL cells laid END-TO-END in a row ("in series"),
# top-left corner. Each: closed body (H>=4 so rectangle() draws the side walls —
# RENDER_SPEC §3, short boxes render open-ended) + terminal nub on the right +
# left-to-right charge fill. The earlier 3px rails weren't readable (Fletcher),
# so the cells are taller and the nub is chunkier.
BAT_W, BAT_H = 18, 7                                   # each cell body (wide, closed, stout)
BAT_HGAP = 4                                           # horizontal gap between the two cells
BAT_X, BAT_Y = 2, 11                                   # top-left of the first (left) cell
BAT_NUB_W, BAT_NUB_H = 2, 3                            # terminal nub (right side, vertically centered)
BAT_PITCH = BAT_W + BAT_NUB_W + BAT_HGAP              # left-edge spacing between cells (incl. nub)


def _lround(x: float) -> int:
    """Round half away from zero, mirroring C's lround() (which the firmware uses
    to format decivolts and size the battery fill). Python's built-in round() is
    banker's rounding (half to even) -- e.g. round(242.5)==242 but lround==243 --
    which would make the sim string diverge from the panel at exact-half boundaries
    (pack_volts 24.25 -> "24.2V" in the sim vs "24.3V" on hardware). Keep them equal."""
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def _glyph(d: OLED, cx: int, cy: int, state: str):
    """State glyph centered at (cx, cy), all filling the same 9px box (spec §1):
    extend/+PWM = ▲ filled triangle apex-UP; retract/-PWM = ▼ filled triangle
    apex-DOWN; hold/~0PWM = ● filled dot; disc = ✕ cross. Four distinct silhouettes."""
    r = GLYPH // 2
    t = r - 1                                                  # triangles + X are 1px smaller
    if state == "extend":                                      # ▲ apex up
        for i in range(2 * t + 1):
            hw = i * t // (2 * t)                              # 0 (top) -> t (bottom)
            d.line(cx - hw, cy - t + i, cx + hw, cy - t + i)
    elif state == "retract":                                   # ▼ apex down
        for i in range(2 * t + 1):
            hw = (2 * t - i) * t // (2 * t)                    # t (top) -> 0 (bottom)
            d.line(cx - hw, cy - t + i, cx + hw, cy - t + i)
    elif state == "hold":                                      # ● filled dot (unchanged)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    d.pixel(cx + dx, cy + dy)
    else:  # disc                                              # ✕ cross (bare, no box)
        d.line(cx - t, cy - t, cx + t, cy + t)
        d.line(cx - t, cy + t, cx + t, cy - t)


def render(state: KrabState, bend=(0, 0, 0)) -> OLED:
    """bend = per-joint vertical offset (yaw, hip, knee) in px, applied as the leg
    goes outward — 0 = straight horizontal legs; positive = each joint droops
    lower (bent/jointed legs). Lets us compare leg styles without a redraw."""
    d = OLED()
    d.erase()

    # top status strip. Everything here is written the way the AVR firmware MUST
    # write it, so the port is mechanical (see RENDER_SPEC.md "Firmware limits"):
    #   - NO %f: AVR snprintf omits float unless you link -lprintf_flt (flash
    #     cost). Format the pack voltage from integer decivolts as two %d fields.
    #     The INA228 already yields an integer reading; pack_volts is the float stand-in.
    #   - roll/pitch clamped to +/-99 so the 3-char (incl. sign) fields can't
    #     widen the line past its 128px / ~21-glyph budget at 5x7.
    d.setFont("5x7")                                     # firmware: setFont(&QW_FONT_5X7)
    dv = _lround(state.pack_volts * 10)                  # decivolts (C lround, half away from 0)
    roll = max(-99, min(99, state.roll))
    pitch = max(-99, min(99, state.pitch))
    top = f"{state.role} {roll:+03d}/{pitch:+03d} {dv // 10:d}.{dv % 10:d}V"
    d.text(TEXT_Y, 0, top)
    d.line(0, 9, 127, 9)

    # two horizontal battery cells laid END-TO-END in a row top-left. Each fraction
    # is the BATT frame's per-battery voltage run through battery_fraction() (see
    # KrabState.from_battery_voltages / §7). Each cell: closed body + right-side
    # terminal nub + L->R charge fill.
    fill_h = BAT_H - 2                                   # interior height (between the walls)
    nub_dy = (BAT_H - BAT_NUB_H) // 2                    # center the nub on the right edge
    for j, frac in enumerate(state.batt):
        bx = BAT_X + j * BAT_PITCH                       # cells laid left -> right (in series)
        d.rectangle(bx, BAT_Y, BAT_W, BAT_H)            # closed body (H>=4 -> side walls drawn)
        d.rectangleFill(bx + BAT_W, BAT_Y + nub_dy, BAT_NUB_W, BAT_NUB_H)  # terminal nub (right)
        fw = _lround((BAT_W - 2) * max(0.0, min(1.0, frac)))
        if fw > 0:                                       # fill grows left -> right
            d.rectangleFill(bx + 1, BAT_Y + 1, fw, fill_h)

    # rectangular body, conceptually split by an upside-down T (⊥) into 3 regions
    # that TILE the interior. Present = filled; adjacent present regions merge into
    # a solid body (no visible seam — no beetle line). The ⊥ split only shows up
    # where a region is empty (a dead board), which is the only time it matters.
    d.rectangle(BODY_X, BODY_Y, BODY_W, BODY_H)                    # outer frame
    if state.controllers.get("LEFT", False):                      # top-left tile
        d.rectangleFill(BODY_X + 1, BODY_Y + 1, STEM_X - BODY_X - 1, TBAR_Y - BODY_Y - 1)
    if state.controllers.get("RIGHT", False):                     # top-right tile (incl. stem col)
        d.rectangleFill(STEM_X, BODY_Y + 1, BODY_X + BODY_W - 1 - STEM_X, TBAR_Y - BODY_Y - 1)
    if state.controllers.get("FRONT", False):                     # bottom tile (incl. bar row)
        d.rectangleFill(BODY_X + 1, TBAR_Y, BODY_W - 2, BODY_Y + BODY_H - 1 - TBAR_Y)

    # 18 leg glyphs — each leg is body -> YAW -> HIP -> KNEE, equal stubs between.
    # Extending the leg to 3 joints also lengthens it (more spider-like).
    # PORT NOTE: cx/gy/sign math goes negative for left-side legs. Firmware MUST
    # keep these as signed int; a negative stored in uint8_t wraps to ~200 and
    # draws across the panel instead of clipping. Only pass to the (uint8_t) API
    # once on-panel. Python ints are unbounded, so the sim can't catch this — the
    # spec calls it out instead.
    r = GLYPH // 2
    GAP = 5
    step = 2 * r + GAP
    for i, joints in enumerate(state.legs):                       # (yaw, hip, knee)
        by = BODY_Y + LEG_BAND[i] * BAND_H + BAND_H // 2
        sign = -1 if (i % 2) == 0 else 1                          # left -> -x, right -> +x
        edge = BODY_X if sign < 0 else BODY_X + BODY_W
        px, py = edge, by
        for j, st in enumerate(joints):
            cx = edge + sign * (r + GAP + j * step)
            gy = by + bend[j]                                     # this joint's y (bent leg)
            d.line(px, py, cx - sign * r, gy)                    # angled connector
            _glyph(d, cx, gy, st)
            px, py = cx + sign * r, gy

    # --- handsome krab face on the FRONT (bottom edge): eyes on stalks + smile ---
    fcx = BODY_X + BODY_W // 2
    fy = BODY_Y + BODY_H - 1
    for ex in (fcx - 6, fcx + 6):
        d.line(ex, fy + 1, ex, fy + 2)                           # eyestalk
        # hollow 3x3 eye drawn as 4 EXPLICIT walls. rectangle() drops the side
        # walls on a <=3px box (RENDER_SPEC §3), which would render the eyes open
        # on the panel; drawing the walls with line() keeps them closed on HW too.
        ey = fy + 3
        d.line(ex - 1, ey, ex + 1, ey)                          # top
        d.line(ex - 1, ey + 2, ex + 1, ey + 2)                  # bottom
        d.line(ex - 1, ey, ex - 1, ey + 2)                      # left wall
        d.line(ex + 1, ey, ex + 1, ey + 2)                      # right wall
    d.pixel(fcx - 2, fy + 4); d.pixel(fcx + 2, fy + 4)
    d.line(fcx - 1, fy + 5, fcx + 1, fy + 5)                     # smile

    d.display()                                                  # firmware: oled.display() — the I2C flush; nothing shows until here
    return d
