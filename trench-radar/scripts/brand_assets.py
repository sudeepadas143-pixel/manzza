"""TRENCH//RADAR brand assets, generated from one geometric definition (docs/BRAND.md).

The mark: three time slices of a signal (a waterfall display) cut by a drifting double channel,
the trench, whose two cuts are the // of the name, with the signal (house pink) running through it.
The wordmark: condensed, chamfered capitals drawn as polygons, not set in a font, so every file is
self-contained. Every shape is a flat polygon: no gradients, filters or effects.

Writes SVGs to web/brand/, raster icons to web/icons/, and the inline masthead lockup into
web/index.html between the brand markers. Uses only Pillow (already an app dependency).

Usage: python scripts/brand_assets.py
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BRAND, ICONS = ROOT / "web" / "brand", ROOT / "web" / "icons"
SLANT = math.tan(math.radians(20))           # one angle for the cuts and the slashes

# Signal Press colours (docs/DESIGN.md)
INK, PINK, PAPER = "#16130e", "#e0247f", "#eee8da"
NIGHT_INK, NIGHT_PINK, NIGHT = "#efe8d8", "#ff4fa3", "#121926"


# ------------------------------------------------------------------ geometry
def mark(box: float = 512, inset: float = 64, heights=(0.6, 0.85, 1.25), row_gap: float = 0.074, cut: float = 0.12,
         signal: float = 0.098) -> list[tuple[str, list]]:
    """The symbol in a square of side `box`: (role, polygon) pairs, role "ink" or "signal".
    Slices thin toward the top (the newest), which also keeps it from reading as a #. Fractions
    are of the drawn width. The channel is centred and leans right going up."""
    w = box - 2 * inset
    g = w * row_gap
    rows = len(heights)
    hs = [(w - (rows - 1) * g) * x / sum(heights) for x in heights]
    cw, sw = w * cut, w * signal
    band = 2 * cw + sw
    mid = box / 2
    lean = lambda y: (mid - y) * SLANT                        # noqa: E731
    x0 = lambda y: mid - band / 2 + lean(y)                   # noqa: E731
    out = []
    a = inset
    for h in hs:
        b = a + h
        e = [lambda y, k=k: x0(y) + k for k in (0, cw, cw + sw, band)]
        out.append(("ink", [(inset, a), (e[0](a), a), (e[0](b), b), (inset, b)]))
        out.append(("signal", [(e[1](a), a), (e[2](a), a), (e[2](b), b), (e[1](b), b)]))
        out.append(("ink", [(e[3](a), a), (box - inset, a), (box - inset, b), (e[3](b), b)]))
        a = b + g
    return out


# Wordmark letters on a 100-unit cap height, stroke 20, chamfer 14: (outline, holes, width)
LETTERS = {
    "T": ([(0, 0), (48, 0), (48, 20), (34, 20), (34, 100), (14, 100), (14, 20), (0, 20)], [], 48),
    "R": ([(0, 0), (36, 0), (50, 14), (50, 44), (41, 53), (50, 100), (30, 100), (22, 60), (20, 60), (20, 100), (0, 100)],
          [[(20, 20), (30, 20), (30, 40), (20, 40)]], 50),
    "E": ([(0, 0), (40, 0), (40, 20), (20, 20), (20, 40), (34, 40), (34, 60), (20, 60), (20, 80), (40, 80), (40, 100), (0, 100)], [], 40),
    "N": ([(0, 0), (19, 0), (31, 52), (31, 0), (50, 0), (50, 100), (31, 100), (19, 48), (19, 100), (0, 100)], [], 50),
    "C": ([(14, 0), (46, 0), (46, 20), (20, 20), (20, 80), (46, 80), (46, 100), (14, 100), (0, 86), (0, 14)], [], 46),
    "H": ([(0, 0), (20, 0), (20, 40), (30, 40), (30, 0), (50, 0), (50, 100), (30, 100), (30, 60), (20, 60), (20, 100), (0, 100)], [], 50),
    "A": ([(14, 0), (36, 0), (50, 14), (50, 100), (30, 100), (30, 64), (20, 64), (20, 100), (0, 100), (0, 14)],
          [[(20, 20), (30, 20), (30, 44), (20, 44)]], 50),
    "D": ([(0, 0), (36, 0), (50, 14), (50, 86), (36, 100), (0, 100)], [[(20, 20), (30, 20), (30, 80), (20, 80)]], 50),
}
TRACK, SLASH_W, SLASH_GAP = 10, 15, 9


def wordmark() -> tuple[list[tuple[str, list, list]], float]:
    """(role, outline, holes) per glyph, laid out on the 100-unit cap height; and the total width."""
    out, x = [], 0.0
    for part in ("TRENCH", "//", "RADAR"):
        if part == "//":
            x += 2
            run = 100 * SLANT
            for k in range(2):
                sx = x + k * (SLASH_W + SLASH_GAP)
                out.append(("signal", [(sx + run, 0), (sx + run + SLASH_W, 0), (sx + SLASH_W, 100), (sx, 100)], []))
            x += run + 2 * SLASH_W + SLASH_GAP + TRACK + 2
            continue
        for ch in part:
            poly, holes, w = LETTERS[ch]
            out.append(("ink", [(x + px, py) for px, py in poly], [[(x + px, py) for px, py in h] for h in holes]))
            x += w + TRACK
    return out, x - TRACK


# ------------------------------------------------------------------ SVG
def _d(poly, k=1.0, dx=0.0, dy=0.0) -> str:
    return "M" + "L".join(f"{_n(x * k + dx)} {_n(y * k + dy)}" for x, y in poly) + "Z"


def _n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _paths(glyphs, colors: dict, k=1.0, dx=0.0, dy=0.0, cls=False) -> str:
    """One path per role; holes cut with even-odd (no glyph overlaps another)."""
    by: dict[str, list[str]] = {}
    for g in glyphs:
        role, poly, holes = g if len(g) == 3 else (g[0], g[1], [])
        by.setdefault(role, []).append(_d(poly, k, dx, dy) + "".join(_d(h, k, dx, dy) for h in holes))
    out = []
    for role, ds in by.items():
        paint = f'class="{role}"' if cls else f'fill="{colors[role]}"'
        out.append(f'<path {paint} fill-rule="evenodd" d="{"".join(ds)}"/>')
    return "".join(out)


def _svg(w, h, body, title, bg=None) -> str:
    rect = f'<rect width="{_n(w)}" height="{_n(h)}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(w)} {_n(h)}" role="img" aria-label="{title}">'
            f'<title>{title}</title>{rect}{body}</svg>\n')


PALETTES = {
    "": {"ink": INK, "signal": PINK},
    "-night": {"ink": NIGHT_INK, "signal": NIGHT_PINK},
    "-mono-black": {"ink": "#000000", "signal": "#000000"},
    "-mono-white": {"ink": "#ffffff", "signal": "#ffffff"},
}


def lockup_geometry(cap=100.0):
    """Mark and wordmark side by side: the mark is 1.36 caps tall, aligned to the cap's centre."""
    wm, ww = wordmark()
    side = cap * 1.36
    gap = cap * 0.34
    m = mark(box=side, inset=0)
    dy = (side - cap) / 2
    glyphs = [(r, p, []) for r, p in m] + [(r, [(x + side + gap, y + dy) for x, y in p],
                                             [[(x + side + gap, y + dy) for x, y in h] for h in hs]) for r, p, hs in wm]
    return glyphs, side + gap + ww, side


# ------------------------------------------------------------------ raster
def raster(glyphs, w, h, px_w, colors, bg=None, ss=8) -> Image.Image:
    """Supersampled polygon rendering; holes punched per glyph."""
    W, Hh = px_w * ss, round(px_w * h / w) * ss
    k = W / w
    im = Image.new("RGBA", (W, Hh), bg or (0, 0, 0, 0))
    for role in ("ink", "signal"):
        mask = Image.new("L", (W, Hh), 0)
        d = ImageDraw.Draw(mask)
        for g in glyphs:
            r, poly, holes = g if len(g) == 3 else (g[0], g[1], [])
            if r != role:
                continue
            d.polygon([(x * k, y * k) for x, y in poly], fill=255)
            for hp in holes:
                d.polygon([(x * k, y * k) for x, y in hp], fill=0)
        im.paste(Image.new("RGBA", (W, Hh), colors[role]), (0, 0), mask)
    return im.resize((W // ss, Hh // ss), Image.LANCZOS)


# ------------------------------------------------------------------ files
def main() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    ICONS.mkdir(parents=True, exist_ok=True)
    big = mark()                                  # the mark at display sizes
    small = mark(inset=24, heights=(0.8, 0.95, 1.15), row_gap=0.1, cut=0.15, signal=0.13)   # optical size for 16-48 px
    wm, ww = wordmark()
    lock, lw, lh = lockup_geometry()
    files = {}
    for suf, col in PALETTES.items():
        files[f"mark{suf}.svg"] = _svg(512, 512, _paths(big, col), "TRENCH//RADAR")
        files[f"wordmark{suf}.svg"] = _svg(ww, 100, _paths(wm, col), "TRENCH//RADAR")
        files[f"lockup{suf}.svg"] = _svg(lw, lh, _paths(lock, col), "TRENCH//RADAR")
    # on their editions' paper, for places that need a background
    files["mark-on-paper.svg"] = _svg(512, 512, _paths(big, PALETTES[""]), "TRENCH//RADAR", PAPER)
    files["mark-on-night.svg"] = _svg(512, 512, _paths(big, PALETTES["-night"]), "TRENCH//RADAR", NIGHT)
    for name, text in files.items():
        (BRAND / name).write_text(text)
    # favicon: the small drawing, following the browser's light or dark theme
    fav = (f'<style>.ink{{fill:{INK}}}.signal{{fill:{PINK}}}@media (prefers-color-scheme:dark)'
           f'{{.ink{{fill:{NIGHT_INK}}}.signal{{fill:{NIGHT_PINK}}}}}</style>' + _paths(small, {}, cls=True))
    (ICONS / "favicon.svg").write_text(_svg(512, 512, fav, "TRENCH//RADAR"))
    # raster icons: favicons from the small drawing, app icons from the large one on paper
    pal = PALETTES[""]
    ico = [raster(small, 512, 512, s, pal) for s in (16, 32, 48)]
    ico[2].save(ICONS / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=ico[:2])
    for s in (180, 192, 512):
        raster(big, 512, 512, s, pal, bg=PAPER).save(ICONS / f"icon-{s}.png", optimize=True)
    # maskable: launchers crop to a circle or squircle; keep the mark inside the central 80%
    raster(mark(inset=118), 512, 512, 512, pal, bg=PAPER).save(ICONS / "icon-maskable-512.png", optimize=True)
    # Windows exe: every size the shell asks for, small ones from the small drawing
    ex = [raster(small if s <= 48 else big, 512, 512, s, pal, bg=None if s <= 48 else PAPER) for s in (16, 24, 32, 48, 64, 128, 256)]
    ex[-1].save(ICONS / "trench-radar.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)], append_images=ex[:-1])
    _masthead(lock, lw, lh)
    print("wrote", len(files) + 6, "brand files")


def _masthead(lock, lw, lh) -> None:
    """The inline lockup in the masthead, painted by the edition's own ink tokens."""
    k = 28 / lh                               # 28 px tall
    body = _paths(lock, {}, k=k, cls=True)
    svg = (f'<svg class="brand" viewBox="0 0 {_n(lw * k)} {_n(lh * k)}" aria-hidden="true" focusable="false">'
           f'{body.replace('class="', 'class="b-')}</svg>')
    html = (ROOT / "web" / "index.html").read_text()
    new = re.sub(r"<!-- brand:start -->.*?<!-- brand:end -->", f"<!-- brand:start -->{svg}<!-- brand:end -->", html, flags=re.S)
    if new == html and "<!-- brand:start -->" not in html:
        raise SystemExit("index.html has no brand markers")
    (ROOT / "web" / "index.html").write_text(new)


if __name__ == "__main__":
    main()
