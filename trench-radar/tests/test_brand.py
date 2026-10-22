"""Brand assets (scripts/brand_assets.py, docs/BRAND.md): present, referenced correctly, flat, and in
sync with the generator."""
import json
import re
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT / "scripts"))
import brand_assets as B  # noqa: E402

SVGS = sorted((WEB / "brand").glob("*.svg")) + [WEB / "icons" / "favicon.svg"]


def test_every_variant_exists():
    names = {p.name for p in SVGS}
    for base in ("mark", "wordmark", "lockup"):
        for suf in ("", "-night", "-mono-black", "-mono-white"):
            assert f"{base}{suf}.svg" in names
    assert {"mark-on-paper.svg", "mark-on-night.svg", "favicon.svg"} <= names


@pytest.mark.parametrize("path", SVGS, ids=lambda p: p.name)
def test_svgs_are_flat_and_self_contained(path):
    s = path.read_text()
    assert s.startswith("<svg") and 'viewBox="' in s and "<title>TRENCH//RADAR</title>" in s
    assert not re.search(r"<(linearGradient|radialGradient|filter|image|text|use|mask|clipPath)\b|font-family|href=", s)
    if "mono" in path.name:
        assert len(set(re.findall(r'fill="(#[0-9a-f]{6})"', s))) == 1


def test_references_resolve_and_the_old_icon_is_gone():
    html = (WEB / "index.html").read_text()
    sw = (WEB / "sw.js").read_text()
    man = json.loads((WEB / "manifest.webmanifest").read_text())
    refs = re.findall(r'/static/([\w/.-]+\.(?:svg|png|ico))', html + sw) + [i["src"].removeprefix("/static/") for i in man["icons"]]
    assert refs
    for r in refs:
        assert (WEB / r).is_file(), r
    assert any(i.get("purpose") == "maskable" for i in man["icons"])
    assert not (WEB / "icons" / "icon.svg").exists() and "icons/icon.svg" not in html + sw


def test_raster_icons_have_their_sizes():
    for name, size in (("icon-180.png", 180), ("icon-192.png", 192), ("icon-512.png", 512), ("icon-maskable-512.png", 512)):
        assert Image.open(WEB / "icons" / name).size == (size, size)
    assert {(16, 16), (32, 32), (48, 48)} <= Image.open(WEB / "icons" / "favicon.ico").info["sizes"]
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= Image.open(WEB / "icons" / "trench-radar.ico").info["sizes"]
    assert 'icon="web/icons/trench-radar.ico"' in (ROOT / "TrenchRadar.spec").read_text()


def test_masthead_lockup_matches_the_generator():
    html = (WEB / "index.html").read_text()
    inline = re.search(r"<!-- brand:start -->(.*?)<!-- brand:end -->", html, re.S).group(1)
    lock, lw, lh = B.lockup_geometry()
    k = 28 / lh
    assert B._paths(lock, {}, k=k, cls=True).replace('class="', 'class="b-') in inline
    assert 'class="b-ink"' in inline and 'class="b-signal"' in inline and "fill=" not in inline


def test_the_mark_stays_legible_small():
    """At 16 px the trench (two cuts) and the signal must still be there: count the pink pixels and
    the paper-coloured gaps along the middle slice."""
    im = B.raster(B.mark(inset=24, heights=(0.8, 0.95, 1.15), row_gap=0.1, cut=0.15, signal=0.13), 512, 512, 16,
                  B.PALETTES[""], bg=B.PAPER).convert("RGB")
    pink = sum(1 for x in range(16) for y in range(16) if (lambda p: p[0] > 150 and p[1] < 120)(im.getpixel((x, y))))
    assert pink >= 6


def test_app_serves_the_favicon(tmp_path):
    from fastapi.testclient import TestClient

    from radar import api

    from .conftest import make_settings
    with TestClient(api.create_app(make_settings(tmp_path), with_scheduler=False)) as client:
        r = client.get("/favicon.ico")
        assert r.status_code == 200 and r.headers["content-type"] == "image/x-icon"
        assert client.get("/static/brand/lockup.svg").status_code == 200
