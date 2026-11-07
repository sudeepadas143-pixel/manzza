"""Same picture, different name: perceptual hashes of token images.

Many metas are an image rather than a word (the same frog under ten names). A 64-bit
difference hash (dHash: shrink to 9x8 greyscale, compare neighbouring pixels) stays nearly
identical when an image is re-encoded, resized or lightly edited, so two tokens whose hashes
differ in <= 6 bits almost certainly use the same picture. Written here on Pillow alone rather
than pulling in imagehash (which adds SciPy and PyWavelets) for this one function.

Bandwidth: only tokens that people are buying (a stored hourly snapshot, i.e. 5+ buyers) get
their image fetched, once, capped at 2 MB. Images are creator-supplied and untrusted: they are
decoded with a pixel limit, hashed, and discarded; nothing is stored or shown.
"""
from __future__ import annotations

import io
from collections import defaultdict

MAX_BYTES = 2_000_000
MAX_PIXELS = 25_000_000
NEAR = 6


def dhash(data: bytes) -> int:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with Image.open(io.BytesIO(data)) as im:
        im.draft("L", (64, 64))                      # cheap downscale for JPEGs
        g = im.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        px = list(g.tobytes())                      # one byte per pixel in mode "L"
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits


def to_signed(h: int) -> int:
    """SQLite integers are signed 64-bit."""
    return h - (1 << 64) if h >= 1 << 63 else h


def distance(a: int, b: int) -> int:
    return bin((a ^ b) & ((1 << 64) - 1)).count("1")


def groups(items: list[dict], near: int = NEAR) -> list[list[dict]]:
    """Cluster tokens whose image hashes are within `near` bits (single linkage). Only
    groups with 2+ different names are returned: the same name reusing its image is a clone,
    which the launch tape already flags."""
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(items)):
        for j in range(i):
            if distance(items[i]["hash"], items[j]["hash"]) <= near:
                parent[find(i)] = find(j)
    by = defaultdict(list)
    for i, it in enumerate(items):
        by[find(i)].append(it)
    out = [g for g in by.values() if len({(x.get("name") or "").strip().lower() for x in g}) >= 2]
    return sorted(out, key=len, reverse=True)
