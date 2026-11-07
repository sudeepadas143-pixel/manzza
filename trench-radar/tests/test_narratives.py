"""Narrative intelligence with a deterministic stand-in for the embedding model.

Concept words map to fixed directions (an animal concept, a gaming concept, an unseen
concept); every other word adds a little noise. That is enough to check the logic: grouping by
meaning, hard links, factory exclusion, categories (including a new one), tracking across runs
and point-in-time loading. All rows are fabricated test data."""
import hashlib

import numpy as np
import pytest

from radar import embed
from radar.analytics import narratives as N
from radar.db import connect, insert, rows

T0 = 1_790_000_000
CONCEPTS = {0: {"kimchi", "shiba", "dog", "animal", "cat", "frog", "creature", "mascot", "pet", "monkey"},
            1: {"gta", "game", "video", "anime", "leaked"},
            6: {"zorblax", "quuxian", "blorp"}}


class Fake:
    np = np

    def embed(self, texts):
        out = []
        for t in texts:
            v = np.zeros(64)
            for w in "".join(ch if ch.isalnum() else " " for ch in t.lower()).split():
                hit = [d for d, ws in CONCEPTS.items() if w in ws]
                if hit:
                    v[hit[0]] += 1.0
                else:
                    v[8 + int(hashlib.md5(w.encode()).hexdigest(), 16) % 56] += 0.12
            out.append(v / (np.linalg.norm(v) or 1))
        return np.array(out, dtype=np.float32)

    embed_many = embed


@pytest.fixture
def fake_model(monkeypatch):
    monkeypatch.setattr(embed.Embedder, "_inst", Fake())


def tok(con, mint, name, creator, t, **kw):
    insert(con, "tokens", {"mint": mint, "name": name, "symbol": name.split()[0].upper()[:6], "creator": creator,
                           "launchpad": "pump-fun", "created_at": t, "first_seen_at": t + 1, "source": "chain", **kw})


def obs(con, mint, t, buyers, net=1.0):
    insert(con, "token_obs", {"mint": mint, "observed_at": t, "source": "chain", "buyers_h1": buyers,
                              "organic_buyers_h1": buyers, "sellers_h1": 2, "net_sol_h1": net})


def world(con, t=T0):
    for i, nm in enumerate(["Kimchi the Shiba", "Kimchi Dog", "KIMCHI", "Shiba Kimchi pet"]):
        tok(con, f"K{i}", nm, f"ck{i}", t - 3000 + i * 600)
        obs(con, f"K{i}", t - 60, 30 - i * 5)
    insert(con, "x_posts", {"post": "leaker/status/1", "author": "leaker", "text": "GTA 6 leaked their bank, the game is real",
                            "followers": 5000, "fetched_at": t - 500, "status": "ok"})
    for i, nm in enumerate(["Piker Financial", "Maze Bank", "Leaked Bank"]):
        tok(con, f"G{i}", nm, f"cg{i}", t - 1500 + i * 60, x_post="leaker/status/1")
        obs(con, f"G{i}", t - 60, 8)
    for i, nm in enumerate(["Foo", "Bar", "Baz"]):                      # unrelated names, one picture
        tok(con, f"P{i}", nm, f"cp{i}", t - 2000 + i * 60)
        insert(con, "token_images", {"mint": f"P{i}", "hash": 0x0F0F0F0F0F0F0F0F, "fetched_at": t - 100, "status": "ok"})
    for i, nm in enumerate(["Zorblax", "Quuxian Zorblax", "Blorp Zorblax"]):   # a concept no category knows
        tok(con, f"Z{i}", nm, f"cz{i}", t - 1000 + i * 60)
    for i in range(12):                                                     # a launch factory
        tok(con, f"F{i}", f"Kimchi spam {i}", "factory", t - 3000 + i * 100)
    tok(con, "LATE", "Kimchi later", "ck9", t + 100)                        # not seen yet at T0


def test_narratives_are_read_by_meaning_and_hard_links(tmp_path, fake_model):
    con = connect(tmp_path / "n.db")
    world(con)
    r = N.build(con, T0)
    assert r["factory_launches_excluded"] == 12
    by = {n["title"]: n for n in r["narratives"]}
    kim = next(n for n in r["narratives"] if any(e["mint"].startswith("K") for e in n["represents"]["examples"]))
    assert {e["mint"] for e in kim["represents"]["examples"]} == {"K0", "K1", "K2", "K3"}      # no factory, no LATE
    assert kim["category"]["primary"] == "Characters & creatures"
    assert kim["traction"]["buyers_h1"] == 30 + 25 + 20 + 15
    gta = next(n for n in r["narratives"] if any(e["mint"].startswith("G") for e in n["represents"]["examples"]))
    assert gta["represents"]["post"]["author"] == "leaker" and any("leaker" in d for d in gta["drivers"])
    assert gta["category"]["primary"] == "Gaming, anime & entertainment"
    pic = next(n for n in r["narratives"] if any(e["mint"].startswith("P") for e in n["represents"]["examples"]))
    assert pic["grouping"]["links"].get("same picture", 0) >= 1
    zor = next(n for n in r["narratives"] if any(e["mint"].startswith("Z") for e in n["represents"]["examples"]))
    assert zor["category"]["primary"] is None and zor["category"]["novel"]
    assert all(n["explanation"] and n["state"] in N_STATES for n in r["narratives"])
    assert by  # titles present


N_STATES = {"new", "accelerating", "heating", "bought", "saturating", "steady", "fading"}


def test_tracking_keeps_ids_and_novel_narratives_become_categories(tmp_path, fake_model):
    con = connect(tmp_path / "t.db")
    world(con)
    r1 = N.build(con, T0, persist=True)
    ids1 = {n["label"]: n["id"] for n in r1["narratives"]}
    assert all(ids1.values())
    assert rows(con, "SELECT COUNT(*) n FROM narrative_categories")[0]["n"] == 0     # Zorblax has 3 launches: not enough
    for i, nm in enumerate(["Zorblax King", "Zorblax Moon"]):                         # more evidence arrives
        tok(con, f"Z{i + 3}", nm, f"cz{i + 3}", T0 + 60 + i)
    r2 = N.build(con, T0 + 300, persist=True)
    zor = next(n for n in r2["narratives"] if any(e["mint"].startswith("Z") for e in n["represents"]["examples"]))
    assert zor["category"].get("created_now")
    assert rows(con, "SELECT COUNT(*) n FROM narrative_categories")[0]["n"] == 1
    kim = next(n for n in r2["narratives"] if any(e["mint"].startswith("K") for e in n["represents"]["examples"]))
    assert kim["id"] in ids1.values() and kim["history_hours"] > 0
    r3 = N.build(con, T0 + 600, persist=True)                                          # the new category is reused
    zor3 = next(n for n in r3["narratives"] if any(e["mint"].startswith("Z") for e in n["represents"]["examples"]))
    assert zor3["category"]["emergent"] and zor3["category"]["primary"] == zor["category"]["primary"]
    assert rows(con, "SELECT COUNT(*) n FROM narrative_obs")[0]["n"] >= 3 * 3


def test_without_the_model_it_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(embed.Embedder, "_inst", None)
    con = connect(tmp_path / "e.db")
    world(con)
    r = N.build(con, T0)
    assert r["narratives"] == [] and not r["semantic"] and "model" in r["note"]


def test_boilerplate_descriptions_carry_no_narrative():
    assert N.meaningful_description("Deployed using https://j7tracker.io") == ""
    assert N.meaningful_description("Launched on discord.gg/uxento") == ""
    assert N.meaningful_description("Fees to @nima_owji via UsePaid") == ""
    assert "aura" in N.meaningful_description("A meme coin built around aura, confidence and main-character vibes")
    assert "9E51XMWG" not in N.clean("CA: 9E51XMWGbUCrgiLu7PrYrBa4TWo88GByvvmUMQfYpump the coin")


def test_token_cluster_shows_how_members_connect(tmp_path, fake_model):
    con = connect(tmp_path / "n.db")
    world(con)
    r = N.build(con, T0)
    pic = next(n for n in r["narratives"] if any(e["mint"].startswith("P") for e in n["represents"]["examples"]))
    cl = pic["cluster"]
    assert cl["of"] == len(cl["nodes"]) == 3
    assert {e[2] for e in cl["edges"]} >= {"same picture"}
    assert all("same picture" in n["via"] for n in cl["nodes"])
    gta = next(n for n in r["narratives"] if any(e["mint"].startswith("G") for e in n["represents"]["examples"]))
    assert any(e[2] == "same X post" for e in gta["cluster"]["edges"])
    for n in r["narratives"]:
        k = len(n["cluster"]["nodes"])
        assert all(0 <= a < k and 0 <= b < k and a != b for a, b, _ in n["cluster"]["edges"])


def test_api_sends_the_largest_narratives_and_clusters_separately(tmp_path, fake_model):
    from fastapi.testclient import TestClient

    from radar.api import create_app
    from radar.scheduler import State
    from tests.conftest import make_settings

    def nar(label, state, buyers, launches):
        return {"label": label, "state": state, "traction": {"buyers_h1": buyers}, "popularity": {"launches_6h": launches},
                "cluster": {"nodes": [{"mint": label}], "edges": []}}
    small_new = [nar(f"new{i}", "new", 0, 3) for i in range(100)]
    big_fading = nar("fading", "fading", 500, 40)
    State.narratives = {"as_of": T0, "narratives": small_new + [big_fading], "parents": [], "events": [],
                        "launches_considered": 0, "factory_launches_excluded": 0}
    s = make_settings(tmp_path)
    try:
        with TestClient(create_app(s)) as client:
            body = client.get("/api/narratives").json()
            assert body["total"] == 101 and len(body["narratives"]) == 80
            assert any(n["label"] == "fading" for n in body["narratives"])         # not crowded out by small new ones
            assert all("cluster" not in n for n in body["narratives"])
            assert client.get("/api/narratives/cluster", params={"label": "fading"}).json()["nodes"] == [{"mint": "fading"}]
            assert client.get("/api/narratives/cluster", params={"label": "nope"}).status_code == 404
    finally:
        State.narratives = None
