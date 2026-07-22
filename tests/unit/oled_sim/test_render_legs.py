"""Leg-glyph coverage & geometry tests for the M16 Task 2 OLED render.

Each of the 6 legs draws body -> YAW -> HIP -> KNEE = 3 glyphs, 18 total. Legs sit
at 3 rows per side (LEG_BAND), left legs to the -x of the body, right legs to +x.
These tests assert region-level pixel invariants (lit-count in a window around a
glyph center, apex/corner silhouette signatures) rather than exact bitmaps, so
small pixel shifts don't cause false failures.
"""
from __future__ import annotations

from krab import (
    KrabState,
    render,
    BODY_X,
    BODY_Y,
    BODY_W,
    LEG_BAND,
    BAND_H,
    GLYPH,
)
from ssd1306 import OLED

# Reproduce render()'s per-joint layout math (all internal to render's loop):
#   r = GLYPH//2, GAP=5, step=2r+GAP; joint j sits at edge + sign*(r+GAP+j*step).
R = GLYPH // 2          # 4  (glyph half-box)
GAP = 5
STEP = 2 * R + GAP      # 13 (center-to-center pitch along a leg)


def _leg_centers(i: int):
    """(list of 3 (cx,cy) joint centers [yaw,hip,knee], sign) for leg i."""
    by = BODY_Y + LEG_BAND[i] * BAND_H + BAND_H // 2
    sign = -1 if (i % 2) == 0 else 1                       # even=left(-x), odd=right(+x)
    edge = BODY_X if sign < 0 else BODY_X + BODY_W
    centers = [(edge + sign * (R + GAP + j * STEP), by) for j in range(3)]
    return centers, sign


def _count(d: OLED, cx: int, cy: int, rad: int = R, drop_row=None) -> int:
    """Lit pixels in the [cx±rad, cy±rad] box; optionally skip one y row."""
    n = 0
    for y in range(cy - rad, cy + rad + 1):
        if y == drop_row:
            continue
        for x in range(cx - rad, cx + rad + 1):
            n += d.get(x, y)
    return n


def _changed(a: OLED, b: OLED):
    """Set of (x,y) pixels that differ between two frames."""
    return {
        (x, y)
        for y in range(64)
        for x in range(128)
        if a.get(x, y) != b.get(x, y)
    }


def _all_hold():
    return [("hold", "hold", "hold")] * 6


# --------------------------------------------------------------------------- #
# 1. Each leg draws exactly 3 glyphs (yaw, hip, knee) as separate clusters.    #
# --------------------------------------------------------------------------- #
def test_leg_renders_three_separated_glyphs():
    # Distinct states per joint so a single blob can't masquerade as three.
    legs = _all_hold()
    legs[0] = ("extend", "retract", "hold")
    d = render(KrabState(legs=legs))
    centers, _ = _leg_centers(0)

    # Every joint window has lit pixels ABOVE the connector row (connectors are
    # horizontal at cy, so excluding cy isolates the glyph body itself).
    for (cx, cy) in centers:
        above = sum(d.get(x, y) for y in range(cy - R, cy) for x in range(cx - R, cx + R + 1))
        assert above > 0, f"no glyph pixels above connector at {(cx, cy)}"

    # The three clusters are SEPARATE: the midpoint between adjacent centers has
    # no glyph pixels off the connector row.
    cy = centers[0][1]
    for a, b in ((0, 1), (1, 2)):
        mx = (centers[a][0] + centers[b][0]) // 2
        gap = sum(d.get(x, y) for y in range(cy - R, cy) for x in range(mx - 1, mx + 2))
        assert gap == 0, f"clusters {a}/{b} bleed together at x~{mx}"


# --------------------------------------------------------------------------- #
# 2. Six legs, 3 per side, at the expected LEG_BAND rows.                      #
# --------------------------------------------------------------------------- #
def test_six_legs_three_per_side_expected_rows():
    d = render(KrabState())  # default: all 18 joints "hold"

    left_rows, right_rows = [], []
    for i in range(6):
        centers, sign = _leg_centers(i)
        for (cx, cy) in centers:
            assert _count(d, cx, cy) > 0, f"leg {i} joint at {(cx, cy)} is blank"
        # side placement: left legs outside the left body edge, right outside right.
        cx0 = centers[0][0]
        if sign < 0:
            assert cx0 < BODY_X
            left_rows.append(centers[0][1])
        else:
            assert cx0 > BODY_X + BODY_W
            right_rows.append(centers[0][1])

    assert len(left_rows) == 3 and len(right_rows) == 3        # 3 legs per side
    # 3 distinct rows, each shared by exactly one left + one right leg.
    assert sorted(set(left_rows)) == sorted(set(right_rows))
    assert len(set(left_rows)) == 3


def test_eighteen_joint_glyphs_total_have_ink():
    d = render(KrabState())
    total = 0
    for i in range(6):
        centers, _ = _leg_centers(i)
        for c in centers:
            assert _count(d, *c) > 0
            total += 1
    assert total == 18


# --------------------------------------------------------------------------- #
# 3. A disconnected joint (disc) renders the ✕ cross, not a live glyph.        #
# --------------------------------------------------------------------------- #
def test_disc_renders_x_cross_not_live_glyph():
    legs = _all_hold()
    legs[0] = ("disc", "hold", "hold")
    d = render(KrabState(legs=legs))
    (cx, cy), *_ = _leg_centers(0)[0]

    # ✕ signature: all four diagonal corners lit; edge-midpoints dark (bare cross,
    # no box). This is the exact inverse of a filled dot, so it can't be a "hold".
    corners = [d.get(cx - 3, cy - 3), d.get(cx + 3, cy + 3),
               d.get(cx - 3, cy + 3), d.get(cx + 3, cy - 3)]
    mids = [d.get(cx - 3, cy), d.get(cx + 3, cy),
            d.get(cx, cy - 3), d.get(cx, cy + 3)]
    assert all(corners), "disc must light all 4 diagonal corners (✕)"
    assert not any(mids), "disc must NOT fill edge-midpoints (no box, not a dot)"

    # Contrast: the same position with a live 'hold' has the opposite silhouette.
    legs[0] = ("hold", "hold", "hold")
    h = render(KrabState(legs=legs))
    assert not any([h.get(cx - 3, cy - 3), h.get(cx + 3, cy + 3),
                    h.get(cx - 3, cy + 3), h.get(cx + 3, cy - 3)])
    assert any([h.get(cx - 3, cy), h.get(cx + 3, cy)])


# --------------------------------------------------------------------------- #
# 4. Changing only YAW changes only the innermost (nearest-body) glyph.        #
# --------------------------------------------------------------------------- #
def test_yaw_change_touches_only_innermost_glyph():
    base = render(KrabState(legs=_all_hold()))
    legs = _all_hold()
    legs[2] = ("disc", "hold", "hold")   # flip only leg 2's yaw (idx 0)
    mod = render(KrabState(legs=legs))

    centers, _ = _leg_centers(2)
    (yx, yy), (hx, hy), (kx, ky) = centers

    diff = _changed(base, mod)
    assert diff, "changing yaw must change some pixels"
    # Every changed pixel lies within the yaw glyph box (radius R of its center).
    for (x, y) in diff:
        assert abs(x - yx) <= R and abs(y - yy) <= R, \
            f"yaw change leaked to {(x, y)} outside innermost glyph"

    # Hip and knee windows are pixel-identical between the two frames.
    for (cx, cy) in ((hx, hy), (kx, ky)):
        for y in range(cy - R, cy + R + 1):
            for x in range(cx - R, cx + R + 1):
                assert base.get(x, y) == mod.get(x, y), \
                    f"non-yaw glyph at {(cx, cy)} changed at {(x, y)}"


# --------------------------------------------------------------------------- #
# 5. apex-direction regression guard on a leg glyph: extend=UP, retract=DOWN.  #
# --------------------------------------------------------------------------- #
def _row_width(d: OLED, cx: int, y: int, rad: int = R) -> int:
    return sum(d.get(x, y) for x in range(cx - rad, cx + rad + 1))


def test_extend_apex_up_retract_apex_down_on_leg():
    legs = _all_hold()
    legs[0] = ("extend", "retract", "hold")
    d = render(KrabState(legs=legs))
    (ex, ey), (rx, ry), _ = _leg_centers(0)[0]

    # extend ▲: bottom row wider than top row (apex points UP). The historical bug
    # rendered it inverted, so this is the guard.
    assert _row_width(d, ex, ey + (R - 1)) > _row_width(d, ex, ey - (R - 1)), \
        "extend must be apex-UP (wide at bottom)"
    # retract ▼: top row wider than bottom (apex points DOWN).
    assert _row_width(d, rx, ry - (R - 1)) > _row_width(d, rx, ry + (R - 1)), \
        "retract must be apex-DOWN (wide at top)"
