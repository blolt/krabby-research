"""Pixel-accurate SSD1306 / SparkFun Qwiic OLED 1.3" (128x64) software simulator.

Mirrors the SparkFun_Qwiic_OLED_Arduino_Library primitive API and — critically —
reuses the library's OWN bundled bitmap fonts (parsed straight from its headers),
including its exact drawCharacter blit quirks (column-major bytes, the 5x7
1px margin, off-by-one width). So a frame drawn here is bit-identical to what the
physical panel shows, which is the whole point: we design/iterate/unit-test the
krab UI off-hardware and trust it.

Coordinate space matches the library: origin top-left, x right, y down, 128x64.
Color: 1 = lit pixel (COLOR_WHITE), 0 = off (COLOR_BLACK).

The render code (krab.py) draws against THIS class using the same method names the
firmware calls on Qwiic1in3OLED (erase, pixel, line, rectangle, rectangleFill,
text, setFont), so porting the render to C++ is mechanical.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

WIDTH = 128
HEIGHT = 64
COLOR_BLACK = 0
COLOR_WHITE = 1

# Locate the SparkFun library's font headers (res/), in priority order:
#   1. QWIIC_OLED_LIB_DIR env var (CI/dev override): <dir>/res
#   2. the repo's materialized libs, fetched by firmware/scripts/fetch_arduino_libs.py
#   3. the personal Arduino sketchbook install (~/Documents/...)
# The first candidate that actually holds the font headers wins. Falling back to
# the repo libs keeps the render tests runnable on a clean HOME (Docker `make
# test`, CI, fresh clone) instead of erroring on a missing ~/Documents install.
_LIB_ENV = os.environ.get("QWIIC_OLED_LIB_DIR")
_REPO_RES = (
    Path(__file__).resolve().parents[1]
    / "arduino/libraries/SparkFun_Qwiic_OLED_Arduino_Library/src/res"
)
_HOME_RES = Path.home() / (
    "Documents/Arduino/libraries/SparkFun_Qwiic_OLED_Arduino_Library/src/res"
)


def _resolve_res_dir() -> "Path | None":
    candidates = []
    if _LIB_ENV:
        candidates.append(Path(_LIB_ENV) / "res")
    candidates.append(_REPO_RES)
    candidates.append(_HOME_RES)
    for d in candidates:
        if (d / "_fnt_5x7.h").exists():
            return d
    return None


_RES_DIR = _resolve_res_dir()


class Font:
    """A SparkFun bitmap font parsed from its _fnt_*.h header.

    Font map layout (per qwiic_grbuffer.cpp drawCharacter): characters are laid
    out left-to-right in a strip `map_width` bytes wide; each glyph column is one
    byte whose bit j is pixel-row j (LSB = top). Tall fonts (8x16) span nRows =
    height/8 byte-rows, each row `map_width` bytes further into the data.
    """

    def __init__(self, name: str, width: int, height: int, start: int,
                 n_chars: int, map_width: int, data: list[int]):
        self.name = name
        self.width = width
        self.height = height
        self.start = start
        self.n_chars = n_chars
        self.map_width = map_width
        self.data = data
        self.margin = 1 if (height // 8 or 1) == 1 else 0  # 5x7 gets a 1px gap

    @property
    def advance(self) -> int:
        return self.width + self.margin

    @classmethod
    def from_header(cls, prefix: str, header: Path) -> "Font":
        txt = header.read_text()

        def _def(field: str) -> int:
            m = re.search(rf"#define\s+{prefix}_{field}\s+(\d+)", txt)
            if not m:
                raise ValueError(f"{prefix}_{field} not found in {header}")
            return int(m.group(1))

        # Grab every 0xNN after the data-array declaration.
        body = txt.split("_data[]", 1)[1]
        body = body.split("{", 1)[1]
        data = [int(h, 16) for h in re.findall(r"0x[0-9a-fA-F]{2}", body)]
        return cls(prefix, _def("WIDTH"), _def("HEIGHT"), _def("START"),
                   _def("NCHAR"), _def("MAP_WIDTH"), data)


def _load_fonts() -> dict[str, Font]:
    fonts = {}
    if _RES_DIR is None:
        return fonts
    for key, prefix, fname in (
        ("5x7", "FONT_5X7", "_fnt_5x7.h"),
        ("8x16", "FONT_8X16", "_fnt_8x16.h"),
    ):
        path = _RES_DIR / fname
        if path.exists():
            fonts[key] = Font.from_header(prefix, path)
    return fonts


_FONTS = _load_fonts()


class OLED:
    """128x64 1-bit framebuffer with the SparkFun primitive API."""

    def __init__(self):
        self.buf = bytearray(WIDTH * HEIGHT)  # one byte/pixel, 0/1
        self.font = _FONTS.get("5x7")

    # --- framebuffer ---
    def erase(self):
        for i in range(len(self.buf)):
            self.buf[i] = 0

    def display(self):
        # No-op in the sim: the buffer already reflects every draw call. Present
        # so the firmware port is line-for-line — on the panel THIS is the I2C
        # flush of the dirty page(s), and nothing appears until it is called
        # (full frame ~120ms; a single dirty 8px band ~5.8ms, measured on HW).
        return

    def pixel(self, x: int, y: int, clr: int = COLOR_WHITE):
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            self.buf[y * WIDTH + x] = 1 if clr else 0

    def get(self, x: int, y: int) -> int:
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            return self.buf[y * WIDTH + x]
        return 0

    # --- primitives (match Qwiic1in3OLED signatures) ---
    def line(self, x0, y0, x1, y1, clr: int = COLOR_WHITE):
        # EXACT port of QwGrBufferDevice::drawLine (steep-swap Bresenham,
        # err = dx//2). Reproduces the library's tie-breaking pixel-for-pixel,
        # so non-45° diagonals match hardware and not just an approximation.
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        if dx == 0 and dy == 0:
            self.pixel(x0, y0, clr)
            return
        steep = dy > dx
        if steep:
            x0, y0 = y0, x0
            x1, y1 = y1, x1
            dx, dy = dy, dx
        if x0 > x1:
            x0, x1 = x1, x0
            y0, y1 = y1, y0
        err = dx // 2
        ystep = 1 if y0 < y1 else -1
        y = y0
        for x in range(x0, x1 + 1):
            self.pixel(y, x, clr) if steep else self.pixel(x, y, clr)
            err -= dy
            if err < 0:
                y += ystep
                err += dx

    def rectangle(self, x, y, w, h, clr: int = COLOR_WHITE):
        # EXACT port of QwGrBufferDevice::rectangle + drawRect. The library
        # draws top+bottom always, but the vertical sides ONLY when height >= 4
        # (y1 - y0 >= 3). A box of height <= 3 renders open-ended on the panel.
        if w <= 1 or h <= 1:                              # library: this is a line
            self.line(x, y, x + w - 1, y + h - 1, clr)
            return
        x1, y1 = x + w - 1, y + h - 1
        self.line(x, y, x1, y, clr)                       # top
        self.line(x, y1, x1, y1, clr)                     # bottom
        if y1 - y < 3:                                    # height <= 3: no side walls
            return
        self.line(x, y + 1, x, y1, clr)                   # left  (y+1..y1, per drawRect)
        self.line(x1, y + 1, x1, y1, clr)                 # right

    def rectangleFill(self, x, y, w, h, clr: int = COLOR_WHITE):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.pixel(xx, yy, clr)

    def setFont(self, key: str):
        if key not in _FONTS:
            raise ValueError(f"font {key!r} not loaded (have {list(_FONTS)})")
        self.font = _FONTS[key]

    def text(self, x0: int, y0: int, s: str, clr: int = COLOR_WHITE):
        """Faithful port of QwGrBufferDevice::drawText/drawCharacter."""
        f = self.font
        n_rows = (f.height // 8) or 1
        margin = 1 if n_rows == 1 else 0
        n_row_len = f.map_width // f.width
        row_bytes = f.map_width * n_rows
        x = x0
        for ch in s:
            off = ord(ch) - f.start
            if 0 <= off < f.n_chars:
                font_index = (off // n_row_len) * row_bytes + (off % n_row_len) * f.width
                for row in range(n_rows):
                    row_offset = row * 8
                    for i in range(f.width + margin):
                        if margin and i == f.width:
                            continue
                        idx = font_index + i + row * f.map_width
                        col = f.data[idx] if idx < len(f.data) else 0
                        for j in range(8):
                            if col & (1 << j):
                                self.pixel(x + i, y0 + j + row_offset, clr)
            x += f.width + margin

    def text_width(self, s: str) -> int:
        return len(s) * (self.font.width + self.font.margin)

    # --- output ---
    def to_ascii(self, on="#", off=".") -> str:
        rows = []
        for y in range(HEIGHT):
            rows.append("".join(on if self.buf[y * WIDTH + x] else off
                                for x in range(WIDTH)))
        return "\n".join(rows)

    def to_rows(self) -> list[str]:
        return self.to_ascii().split("\n")


def fonts_available() -> list[str]:
    return list(_FONTS)
