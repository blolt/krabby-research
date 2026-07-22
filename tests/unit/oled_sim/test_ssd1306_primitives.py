"""Primitive-level tests for the OLED sim's load-bearing quirks (ssd1306.py).

krab.py and the render goldens exercise the primitives only in combination; these
pin the individual behaviors the render RELIES ON but nothing else currently
reaches:
  * rectangle() drops the side walls on a <=3px-tall box (open-ended on the
    panel) but closes a >=4px box -- RENDER_SPEC §3, the reason the eyes and the
    tall battery cells are drawn the way they are.
  * a w=1 rectangle() degenerates to a line().
  * line() is the library's exact steep-swap Bresenham; a non-45 slope has one
    specific pixel set, not an approximation.
  * pixel() clips out-of-range coordinates to a no-op.
Pure Python, no hardware.
"""
from ssd1306 import OLED, WIDTH, HEIGHT


def _lit_pixels(d: OLED) -> set:
    return {(x, y) for y in range(HEIGHT) for x in range(WIDTH) if d.get(x, y)}


class TestRectangleSideWalls:
    def test_short_box_is_open_ended(self):
        # h=3 -> y1-y0 = 2 < 3, so rectangle() draws top+bottom but NO side
        # walls; the interior row has no lit pixels even at the box's edge
        # columns. This is why small closed boxes (eyes) draw explicit walls.
        d = OLED()
        d.rectangle(10, 10, 6, 3)
        assert all(d.get(x, 10) for x in range(10, 16))   # top row drawn
        assert all(d.get(x, 12) for x in range(10, 16))   # bottom row drawn
        assert all(d.get(x, 11) == 0 for x in range(10, 16))  # open-ended: no walls

    def test_tall_box_is_closed(self):
        # h=4 -> y1-y0 = 3, side walls ARE drawn: the interior row has lit pixels
        # at exactly the left and right columns, and nothing between (not filled).
        d = OLED()
        d.rectangle(10, 20, 6, 4)
        assert d.get(10, 21) == 1          # left wall
        assert d.get(15, 21) == 1          # right wall
        assert all(d.get(x, 21) == 0 for x in range(11, 15))  # hollow interior


class TestRectangleDegenerate:
    def test_width_1_rectangle_equals_a_line(self):
        # w<=1 -> rectangle() degenerates to a single line() call.
        r = OLED()
        r.rectangle(5, 5, 1, 5)
        line = OLED()
        line.line(5, 5, 5, 9)
        assert _lit_pixels(r) == _lit_pixels(line)
        assert _lit_pixels(r)              # and it is a real (non-empty) vertical line


class TestLineBresenham:
    def test_non_45_slope_pixel_set_is_pinned(self):
        # line(0,0 -> 4,2): dx=4, dy=2, err=dx//2=2. The library's tie-breaking
        # yields exactly this set; any drift in the port changes angled elements
        # (bent legs) invisibly to the golden frames, which are all H/V/45deg.
        d = OLED()
        d.line(0, 0, 4, 2)
        assert _lit_pixels(d) == {(0, 0), (1, 0), (2, 1), (3, 1), (4, 2)}


class TestPixelClipping:
    def test_out_of_range_pixel_is_a_noop(self):
        d = OLED()
        d.pixel(WIDTH + 5, 5)     # x >= 128
        d.pixel(5, HEIGHT + 5)    # y >= 64
        d.pixel(-1, 5)            # x < 0
        d.pixel(5, -1)            # y < 0
        assert _lit_pixels(d) == set()
