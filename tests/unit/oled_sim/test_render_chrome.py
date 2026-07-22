"""Render chrome tests: battery cells, top text strip, and the krab face.

These are the non-body "chrome" elements of the M16 Task 2 status screen. The
render is pure state -> pixels, so every assertion below is a deterministic pixel
/ region check against the framebuffer (via .get), not a golden-image compare —
they survive small pixel shifts by asserting *where* lit pixels are and *that*
fill width tracks the battery fraction, rather than exact coordinates.
"""
from krab import (KrabState, render, BODY_X, BODY_Y, BODY_W, BODY_H,
                  BAT_X, BAT_Y, BAT_W, BAT_H, BAT_PITCH)
from ssd1306 import OLED, WIDTH, HEIGHT


def _lit(d: OLED, x0: int, x1: int, y0: int, y1: int) -> int:
    """Count lit pixels in the half-open rect [x0,x1) x [y0,y1)."""
    return sum(d.get(x, y) for x in range(x0, x1) for y in range(y0, y1))


# --- battery -----------------------------------------------------------------
# Two horizontal cells laid end-to-end in a row in the top-left corner. Each cell
# has a closed body and a left-to-right fill proportional to its fraction. We
# assert on total lit pixels inside each cell's interior (the fill), not exact
# coords, so the tests survive small geometry tweaks. Interior of cell j is the
# body minus its 1px walls.
def _cell_interior_lit(d: OLED, j: int) -> int:
    bx = BAT_X + j * BAT_PITCH
    return _lit(d, bx + 1, bx + BAT_W - 1, BAT_Y + 1, BAT_Y + BAT_H - 1)


def test_battery_fill_tracks_fraction():
    """A fuller cell must have strictly more lit fill pixels than an emptier one,
    and swapping the fractions must swap which cell is fuller."""
    d_hi_lo = render(KrabState(batt=(0.9, 0.1)))
    d_lo_hi = render(KrabState(batt=(0.1, 0.9)))

    a_hi = _cell_interior_lit(d_hi_lo, 0)
    b_lo = _cell_interior_lit(d_hi_lo, 1)
    a_lo = _cell_interior_lit(d_lo_hi, 0)
    b_hi = _cell_interior_lit(d_lo_hi, 1)

    # within a frame, the fuller cell wins
    assert a_hi > b_lo
    assert b_hi > a_lo
    # the same physical cell responds to its own fraction across frames
    assert a_hi > a_lo
    assert b_hi > b_lo


def test_battery_fill_monotonic_with_fraction():
    """Higher fraction -> more fill, checked across a monotone sweep on cell A."""
    fills = [
        _cell_interior_lit(render(KrabState(batt=(f, 0.0))), 0)
        for f in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]
    assert fills == sorted(fills)        # non-decreasing
    assert fills[0] < fills[-1]          # and actually grows
    assert fills[0] == 0                 # empty draws no fill
    assert fills[-1] > 0                 # full draws some fill


def test_battery_cells_in_top_left_corner():
    """Both battery cells live in the top-left corner (below the text separator at
    y=9, above the body at y=22) and don't leak to the right."""
    d = render(KrabState(batt=(0.7, 0.7)))
    band_lo, band_hi = BAT_Y, BAT_Y + BAT_H              # single row of cells
    # genuine battery pixels in the corner, left of the body
    assert _lit(d, 0, BODY_X, band_lo, band_hi) > 0, "expected battery pixels top-left"
    # the band sits entirely above the body, so it is body-free by construction
    assert band_hi <= BODY_Y
    # the gauge stays left of the body's column span
    assert _lit(d, BODY_X, WIDTH, band_lo, band_hi) == 0


# --- top text strip ----------------------------------------------------------
def test_text_strip_renders():
    """role + roll/pitch + pack_v draws lit pixels in the top strip (rows 0-8)."""
    d = render(KrabState())
    assert _lit(d, 0, WIDTH, 0, 9) > 0
    # the separator line at y=9 spans the full width
    assert _lit(d, 0, WIDTH, 9, 10) == WIDTH


def test_text_strip_reflects_role():
    """Different role strings must produce different top-strip pixels (the strip
    is the only place role is drawn, so only rows 0-8 need differ)."""
    front = render(KrabState(role="FRONT")).to_rows()[0:9]
    left = render(KrabState(role="LEFT")).to_rows()[0:9]
    right = render(KrabState(role="RIGHT")).to_rows()[0:9]
    assert front != left
    assert front != right
    assert left != right


def test_text_strip_reflects_orientation_and_voltage():
    """roll/pitch/pack_v values change the rendered text (rows 0-8)."""
    base = render(KrabState(roll=0, pitch=0, pack_v=24.0)).to_rows()[0:9]
    tilted = render(KrabState(roll=15, pitch=-9, pack_v=24.0)).to_rows()[0:9]
    drained = render(KrabState(roll=0, pitch=0, pack_v=19.7)).to_rows()[0:9]
    assert base != tilted
    assert base != drained


def test_pack_voltage_rounds_half_away_from_zero():
    """pack_v 24.25 is exactly 242.5 decivolts. The firmware uses C lround()
    (half away from zero -> 243 -> "24.3V"), NOT banker's rounding (242 ->
    "24.2V"), so the sim must too (krab._lround) or the sim string diverges from
    the panel at exact-half boundaries. Asserted via the rendered top strip:
    24.25 must render like 24.3, not like 24.2."""
    at_boundary = render(KrabState(pack_v=24.25)).to_rows()[0:9]
    rounds_up = render(KrabState(pack_v=24.3)).to_rows()[0:9]
    rounds_down = render(KrabState(pack_v=24.2)).to_rows()[0:9]
    assert at_boundary == rounds_up
    assert at_boundary != rounds_down


# --- clamp boundaries --------------------------------------------------------
def test_roll_pitch_clamped_to_plus_minus_99():
    """roll/pitch clamp to +/-99 for display so the 3-char (incl. sign) fields
    can't widen the top line past its 128px / ~21-glyph budget. Out-of-range
    values must render identically to the clamp endpoints."""
    clamped = render(KrabState(roll=150, pitch=-150)).to_rows()[0:9]
    at_limit = render(KrabState(roll=99, pitch=-99)).to_rows()[0:9]
    assert clamped == at_limit


def test_battery_fraction_clamped_0_to_1():
    """Battery cell fractions clamp to 0..1 at draw. An over-full / negative pair
    (1.5, -0.3) must render pixel-identically to the clamp endpoints (1.0, 0.0)."""
    over_under = render(KrabState(batt=(1.5, -0.3)))
    at_limits = render(KrabState(batt=(1.0, 0.0)))
    assert over_under.to_rows() == at_limits.to_rows()


# --- krab face ---------------------------------------------------------------
# The face (eyestalks + hollow eyes + smile) is drawn just BELOW the body's
# bottom edge, centered on the front. Body bottom row is BODY_Y+BODY_H-1.
def test_face_below_body_front():
    """Lit pixels exist below the body in the centered front area (the face)."""
    d = render(KrabState())
    body_bottom = BODY_Y + BODY_H - 1          # 52
    fcx = BODY_X + BODY_W // 2                  # 64
    # face band: strictly below the body, a few rows tall, around the center
    face = _lit(d, fcx - 10, fcx + 10, body_bottom + 1, body_bottom + 6)
    assert face > 0, "expected krab face pixels below the body front edge"


def test_face_has_two_eyes():
    """Two eyes -> lit pixels on BOTH sides of the face center, below the body."""
    d = render(KrabState())
    body_bottom = BODY_Y + BODY_H - 1
    fcx = BODY_X + BODY_W // 2
    y0, y1 = body_bottom + 1, body_bottom + 6
    left_eye = _lit(d, fcx - 10, fcx - 2, y0, y1)
    right_eye = _lit(d, fcx + 3, fcx + 11, y0, y1)
    assert left_eye > 0 and right_eye > 0


def test_face_does_not_bleed_off_panel():
    """Sanity: the whole render stays inside the 128x64 framebuffer, so the face
    (drawn near the bottom) never silently clips off-screen into nothing."""
    d = render(KrabState())
    assert _lit(d, 0, WIDTH, 0, HEIGHT) > 0
    # bottom-most face row must still be within the panel
    body_bottom = BODY_Y + BODY_H - 1
    assert body_bottom + 6 <= HEIGHT
