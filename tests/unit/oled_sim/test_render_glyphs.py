"""Unit tests for the 4 leg-state glyph shapes (M16 Task 2, spec §1).

Each glyph is rendered in isolation via `_glyph(OLED(), cx, cy, state)` and its
lit pixels inspected directly. The glyphs are pure state->pixels, so these are
exact silhouette assertions (with small tolerances where sensible).

Ground truth (krab.py, GLYPH=9 -> r=4, t=3):
  extend  = filled triangle apex-UP   (narrow top row, wide bottom row), ~7px
  retract = filled triangle apex-DOWN (wide top row, narrow bottom row), ~7px
  hold    = filled round dot, ~9px box, corners dark, ~circular
  disc    = ✕ cross, two 45° diagonals, ~7px box, NO box edges, sparse center

CRITICAL regression guard (a real bug once shipped): `extend` must be apex-UP
and `retract` apex-DOWN — never inverted.
"""
import pytest

from krab import _glyph
from ssd1306 import OLED

# Draw well inside the 128x64 buffer so nothing clips.
CX, CY = 40, 32
RAD = 6  # search radius covering the largest glyph (9px dot -> half 4)


def draw(state):
    d = OLED()
    _glyph(d, CX, CY, state)
    return d


def lit_cells(d):
    """All lit (x, y) within the glyph's neighborhood."""
    return [
        (x, y)
        for y in range(CY - RAD, CY + RAD + 1)
        for x in range(CX - RAD, CX + RAD + 1)
        if d.get(x, y)
    ]


def bbox(cells):
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    return min(xs), max(xs), min(ys), max(ys)


def row_width(d, y):
    """Number of lit pixels in row y within the glyph neighborhood."""
    return sum(d.get(x, y) for x in range(CX - RAD, CX + RAD + 1))


# --------------------------------------------------------------------------
# extend: filled triangle apex-UP  (narrow at top, wide at bottom)
# --------------------------------------------------------------------------
def test_extend_is_apex_up():
    d = draw("extend")
    cells = lit_cells(d)
    assert cells, "extend drew nothing"
    _, _, ymin, ymax = bbox(cells)

    top_w = row_width(d, ymin)
    bot_w = row_width(d, ymax)

    # REGRESSION GUARD: apex-up means the single-pixel apex is at the TOP and the
    # wide base is at the BOTTOM. If this were apex-down (the inversion bug), the
    # inequality would flip.
    assert top_w < bot_w, f"extend not apex-up: top={top_w} bot={bot_w}"
    assert top_w <= 2, f"extend apex (top) should be a narrow point, got {top_w}"
    assert bot_w >= 5, f"extend base (bottom) should be wide, got {bot_w}"


def test_extend_fills_downward_monotonically():
    # Row widths should be non-decreasing from top to bottom for a filled ▲.
    d = draw("extend")
    cells = lit_cells(d)
    _, _, ymin, ymax = bbox(cells)
    widths = [row_width(d, y) for y in range(ymin, ymax + 1)]
    assert all(b >= a for a, b in zip(widths, widths[1:])), widths
    assert widths[0] < widths[-1]


# --------------------------------------------------------------------------
# retract: filled triangle apex-DOWN  (wide at top, narrow at bottom)
# --------------------------------------------------------------------------
def test_retract_is_apex_down():
    d = draw("retract")
    cells = lit_cells(d)
    assert cells, "retract drew nothing"
    _, _, ymin, ymax = bbox(cells)

    top_w = row_width(d, ymin)
    bot_w = row_width(d, ymax)

    # REGRESSION GUARD: apex-down is the mirror of extend.
    assert top_w > bot_w, f"retract not apex-down: top={top_w} bot={bot_w}"
    assert bot_w <= 2, f"retract apex (bottom) should be a narrow point, got {bot_w}"
    assert top_w >= 5, f"retract base (top) should be wide, got {top_w}"


def test_extend_and_retract_are_inverses():
    # The two triangles must be genuinely opposite, not the same shape.
    e = draw("extend")
    r = draw("retract")
    ce, cr = lit_cells(e), lit_cells(r)
    _, _, eymin, eymax = bbox(ce)
    _, _, rymin, rymax = bbox(cr)
    # extend widest at bottom; retract widest at top.
    assert row_width(e, eymax) > row_width(e, eymin)
    assert row_width(r, rymin) > row_width(r, rymax)


def test_triangles_fit_seven_px():
    for state in ("extend", "retract"):
        cells = lit_cells(draw(state))
        xmin, xmax, ymin, ymax = bbox(cells)
        w, h = xmax - xmin + 1, ymax - ymin + 1
        assert 6 <= w <= 8, f"{state} width {w} not ~7px"
        assert 6 <= h <= 8, f"{state} height {h} not ~7px"


# --------------------------------------------------------------------------
# hold: filled round dot, ~9px box, corners dark, roughly circular
# --------------------------------------------------------------------------
def test_hold_is_filled_circular_blob():
    d = draw("hold")
    cells = lit_cells(d)
    assert cells, "hold drew nothing"

    # Solid center.
    assert d.get(CX, CY)
    assert d.get(CX - 1, CY) and d.get(CX + 1, CY)
    assert d.get(CX, CY - 1) and d.get(CX, CY + 1)

    # Round, not square: the four corners of the 9px box must be dark.
    for dx, dy in ((-4, -4), (4, -4), (-4, 4), (4, 4)):
        assert not d.get(CX + dx, CY + dy), f"corner ({dx},{dy}) lit -> not circular"

    # Filled blob: far more lit pixels than a stroke-only glyph (X ~ 13).
    assert 45 <= len(cells) <= 55, f"dot fill count {len(cells)} out of range"


def test_hold_fits_nine_px():
    d = draw("hold")
    xmin, xmax, ymin, ymax = bbox(lit_cells(d))
    assert (xmax - xmin + 1) == 9, "dot width should span the full 9px box"
    assert (ymax - ymin + 1) == 9, "dot height should span the full 9px box"


# --------------------------------------------------------------------------
# disc: ✕ cross, two 45° diagonals, NO surrounding box, sparse center
# --------------------------------------------------------------------------
def test_disc_diagonals_lit():
    d = draw("disc")
    # Both diagonals pass through their four corners of the 7px box.
    for dx, dy in ((-3, -3), (3, 3), (-3, 3), (3, -3)):
        assert d.get(CX + dx, CY + dy), f"diagonal endpoint ({dx},{dy}) not lit"
    # Interior diagonal samples (both strokes present near center).
    assert d.get(CX - 1, CY - 1) and d.get(CX + 1, CY + 1)   # ↘ stroke
    assert d.get(CX - 1, CY + 1) and d.get(CX + 1, CY - 1)   # ↗ stroke
    # Crossing point.
    assert d.get(CX, CY)


def test_disc_has_no_box_edges():
    d = draw("disc")
    # The midpoints of the 7px bounding box's four edges must be DARK — proving
    # it is a bare ✕, not a boxed/framed glyph.
    assert not d.get(CX, CY - 3), "top edge midpoint lit -> spurious box"
    assert not d.get(CX, CY + 3), "bottom edge midpoint lit -> spurious box"
    assert not d.get(CX - 3, CY), "left edge midpoint lit -> spurious box"
    assert not d.get(CX + 3, CY), "right edge midpoint lit -> spurious box"


def test_disc_is_sparse_and_seven_px():
    d = draw("disc")
    cells = lit_cells(d)
    xmin, xmax, ymin, ymax = bbox(cells)
    assert (xmax - xmin + 1) == 7, "X width should be ~7px"
    assert (ymax - ymin + 1) == 7, "X height should be ~7px"
    # Two 7px diagonals sharing one center pixel -> ~13 lit; far sparser than a
    # filled triangle/dot.
    assert len(cells) <= 16, f"X should be sparse, got {len(cells)} lit"
    assert len(cells) >= 10


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
