"""By-side topology tests for the M16 Task 2 OLED render.

v0.2 boards are grouped BY SIDE (firmware ACT_LIST): FRONT={FL,FR}, LEFT={ML,RL},
RIGHT={MR,RR}. The body rectangle is split by an upside-down T (⊥) into three
tiles that line up with those boards. A present board fills its tile; a missing
board leaves its tile empty (that is the only time the ⊥ seam is visible). This
module asserts the mapping and the present/missing fill behavior at the pixel
level: each single missing board darkens EXACTLY its one region, nothing else.
"""
from krab import (
    KrabState, render, BODY_X, BODY_Y, BODY_W, BODY_H, TBAR_Y, STEM_X,
    REGION_OF_ACT,
)


# Interior fill rects for the three tiles, derived from the render's own geometry
# constants (so they track any deliberate geometry change). Each is the strictly
# interior region — one pixel inside the outer frame — so the always-drawn frame
# never contaminates a lit/dark count. Rects are half-open: [x0, x1) x [y0, y1).
LEFT_RECT = (BODY_X + 1, STEM_X, BODY_Y + 1, TBAR_Y)
RIGHT_RECT = (STEM_X, BODY_X + BODY_W - 1, BODY_Y + 1, TBAR_Y)
FRONT_RECT = (BODY_X + 1, BODY_X + BODY_W - 1, TBAR_Y, BODY_Y + BODY_H - 1)
REGION_RECTS = {"LEFT": LEFT_RECT, "RIGHT": RIGHT_RECT, "FRONT": FRONT_RECT}


def _count_lit(d, rect):
    x0, x1, y0, y1 = rect
    return sum(d.get(x, y) for y in range(y0, y1) for x in range(x0, x1))


def _area(rect):
    x0, x1, y0, y1 = rect
    return (x1 - x0) * (y1 - y0)


def _state(**controllers):
    """Default all-present state, overriding named boards to the given bools."""
    s = KrabState()
    s.controllers = {"FRONT": True, "LEFT": True, "RIGHT": True, **controllers}
    return s


def test_region_of_act_is_byside_mapping():
    # [FL, FR, ML, MR, RL, RR] -> board owning each leg.
    assert REGION_OF_ACT == ["FRONT", "FRONT", "LEFT", "RIGHT", "LEFT", "RIGHT"]
    # Same fact stated as board -> leg indices (the BY-SIDE grouping).
    groups = {}
    for idx, board in enumerate(REGION_OF_ACT):
        groups.setdefault(board, []).append(idx)
    assert groups["FRONT"] == [0, 1]   # FL, FR
    assert groups["LEFT"] == [2, 4]    # ML, RL
    assert groups["RIGHT"] == [3, 5]   # MR, RR


def test_three_tiles_are_disjoint_and_tile_the_interior():
    # The three interior rects must not overlap and must exactly cover the full
    # body interior (no gap, no double-count) — a precondition for the counts
    # below to mean "this board and only this board".
    total = _area(LEFT_RECT) + _area(RIGHT_RECT) + _area(FRONT_RECT)
    interior = (BODY_W - 2) * (BODY_H - 2)
    assert total == interior


def test_all_present_body_is_fully_solid():
    d = render(_state())
    # Every interior pixel of every tile is lit — merged into one solid body.
    for name, rect in REGION_RECTS.items():
        lit = _count_lit(d, rect)
        assert lit == _area(rect), f"{name} tile not fully solid: {lit}/{_area(rect)}"


def test_left_missing_darkens_only_left():
    d = render(_state(LEFT=False))
    assert _count_lit(d, LEFT_RECT) == 0                     # dead board -> empty tile
    assert _count_lit(d, RIGHT_RECT) == _area(RIGHT_RECT)    # neighbors untouched
    assert _count_lit(d, FRONT_RECT) == _area(FRONT_RECT)


def test_right_missing_darkens_only_right():
    d = render(_state(RIGHT=False))
    assert _count_lit(d, RIGHT_RECT) == 0
    assert _count_lit(d, LEFT_RECT) == _area(LEFT_RECT)
    assert _count_lit(d, FRONT_RECT) == _area(FRONT_RECT)


def test_front_missing_darkens_only_front():
    d = render(_state(FRONT=False))
    assert _count_lit(d, FRONT_RECT) == 0
    assert _count_lit(d, LEFT_RECT) == _area(LEFT_RECT)
    assert _count_lit(d, RIGHT_RECT) == _area(RIGHT_RECT)


def test_each_single_missing_board_darkens_exactly_its_region():
    # Sweep all three: the missing tile is empty, the other two stay full.
    for missing in ("FRONT", "LEFT", "RIGHT"):
        d = render(_state(**{missing: False}))
        for name, rect in REGION_RECTS.items():
            lit = _count_lit(d, rect)
            expected = 0 if name == missing else _area(rect)
            assert lit == expected, (
                f"with {missing} missing, {name} tile lit={lit}, expected {expected}"
            )
