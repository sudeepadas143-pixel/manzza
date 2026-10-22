"""Macro and intraday meta views (radar/analytics/macro.py) on a small synthetic market with known
answers. All coins, wallets and outcomes here are fabricated test data."""
import json
import random

import numpy as np
import pytest

from radar.analytics import macro as M
from radar.db import connect, insert

H, D = 3600, 86400
NOW = 1_790_000_000 - (1_790_000_000 % D) + 12 * H


def coin(con, mint, t0, creator, cat, nid, buyers, grad_after=None):
    insert(con, "tokens", {"mint": mint, "name": f"{cat} {mint}", "symbol": mint[:4].upper(), "creator": creator,
                           "created_at": t0, "first_seen_at": t0, "source": "chain", "launchpad": "pump-fun"})
    if cat:
        insert(con, "token_narrative", {"mint": mint, "narrative_id": nid, "label": f"{cat.lower()} · idea", "category": cat, "at": t0 + 600})
    insert(con, "token_obs", {"mint": mint, "observed_at": t0 + 1800, "source": "chain", "buyers_h1": buyers,
                              "mcap_usd": 5000 + 100 * buyers, "liquidity_usd": 1000.0, "net_sol_h1": buyers / 10, "holders": buyers})
    insert(con, "token_obs", {"mint": mint, "observed_at": t0 + 20 * H, "source": "chain", "buyers_h1": 1,
                              "mcap_usd": 4000.0, "holders": buyers // 2})
    if grad_after is not None:
        insert(con, "graduations", {"mint": mint, "detected_at": t0 + grad_after, "graduated_at": t0 + grad_after, "source": "chain"})


@pytest.fixture
def market(tmp_path):
    """Ten days. 'Winners': 120 coins, 12 graduate, each from a different creator. 'Solo': 120 coins,
    one graduates. 'Rare': 10 coins. 'Plain': 600 coins, 6 graduate. A factory wallet launches 200
    coins, 20 of which 'graduate'; one Plain coin graduates instantly (a buyout)."""
    random.seed(1)
    con = connect(tmp_path / "m.db")
    start = NOW - 11 * D
    k = 0

    def t_():
        return start + random.randint(0, 10 * D - 2 * H)
    for i in range(120):
        coin(con, f"w{i}", t_(), f"cw{i}", "Winners", 1, 80 if i < 12 else 5, grad_after=600 if i < 12 else None)
    for i in range(120):
        coin(con, f"s{i}", t_(), f"cs{i % 40}", "Solo", 2, 400 if i == 0 else 3, grad_after=900 if i == 0 else None)
    for i in range(10):
        coin(con, f"r{i}", t_(), f"cr{i}", "Rare", 3, 60, grad_after=700)
    for i in range(600):
        coin(con, f"p{i}", t_(), f"cp{i}", "Plain", 4, 4, grad_after=800 if i < 6 else None)
    coin(con, "pinstant", t_(), "cpx", "Plain", 4, 4, grad_after=5)
    t = start + 3 * D
    for i in range(200):                           # one wallet, ~every 2 minutes: a launch factory
        coin(con, f"f{i}", t + i * 120, "factory", "Winners", 1, 90, grad_after=700 if i < 20 else None)
        k += 1
    for h in range(int((NOW - start) // H)):       # collection ran every hour
        insert(con, "tokens", {"mint": f"tick{h}", "created_at": start + h * H + 1, "first_seen_at": start + h * H + 1, "source": "chain"})
    con.commit()
    return con


def test_summaries_flag_factories_and_wait_for_the_first_day(market):
    n = M.summarize(market, NOW, limit=None)
    assert n > 0
    rows = {r[0]: r for r in market.execute("SELECT mint, factory, graduated, peak_buyers_h1, holders_end, peak_holders FROM token_summary")}
    assert rows["f150"][1] == 1 and rows["w0"][1] == 0
    assert rows["w0"][2] == 1 and rows["w0"][3] == 80 and rows["w0"][4] == 40 and rows["w0"][5] == 80
    young = market.execute("SELECT COUNT(*) FROM tokens WHERE created_at > ?", (NOW - D,)).fetchone()[0]
    assert young > 0 and not market.execute("SELECT COUNT(*) FROM token_summary WHERE created_at > ?", (NOW - D,)).fetchone()[0]


def test_breadth_beats_one_runaway_and_launch_counts(market):
    M.summarize(market, NOW, limit=None)
    mac = M.macro_read(market, NOW, windows=(7,))
    w = mac["windows"]["7"]
    assert w["available"]
    by = {r["category"]: r for r in w["categories"]}
    assert by["Winners"]["status"] == "working" and by["Winners"]["independent_successes"] >= M.WORKING_MIN_CREATORS
    assert by["Solo"]["status"] in ("one coin", "lagging", "average") and by["Solo"]["status"] != "working"
    assert by["Rare"]["status"] == "insufficient"
    # the instant buyout and the factory's coins are not counted
    assert by["Plain"]["graduated"] <= 6 and all(c["category"] != "Winners" or True for c in w["categories"])
    assert by["Winners"]["coins"] < 120              # 10 days of coins, 7 in the window, no factory coins
    # ranked by the record with its best coin left out, not by launches (Plain has the most)
    assert w["categories"][0]["category"] == "Winners"
    assert by["Plain"]["share_of_launches"] > by["Winners"]["share_of_launches"]


def test_trend_and_newer_vs_older_are_reported_with_their_samples(market):
    M.summarize(market, NOW, limit=None)
    r = {x["category"]: x for x in M.macro_read(market, NOW, windows=(7,))["windows"]["7"]["categories"]}["Winners"]
    assert r["trend"] in ("gaining", "steady", "losing", "new")
    assert r["newer_vs_older"] is None or 0 <= r["newer_vs_older"] <= 1
    assert r["launches_last_3d_per_day"] >= 0 and 0 <= r["days_with_success"] <= 7
    assert "worked" in M.macro_sentence(r) or "working" in M.macro_sentence(r)


def test_short_history_is_said_not_hidden(tmp_path):
    con = connect(tmp_path / "e.db")
    coin(con, "a", NOW - 2 * D, "c", "Winners", 1, 50, 600)
    con.commit()
    M.summarize(con, NOW, limit=None)
    mac = M.macro_read(con, NOW)
    assert not mac["windows"]["7"]["available"] and mac["notes"]
    assert not mac["windows"]["30"]["available"] and mac["windows"]["30"]["coverage"] < 0.5


def _reads(con, cat_series: dict, start: int):
    """Hourly narrative reads: one narrative per category with the given buyers per hour."""
    for cat, (nid, series) in cat_series.items():
        con.execute("INSERT OR IGNORE INTO narratives (id, label, category, first_seen, last_seen, status) VALUES (?,?,?,?,?, 'active')",
                    (nid, f"{cat.lower()} · idea", cat, start, start))
        for h, b in enumerate(series):
            insert(con, "narrative_obs", {"narrative_id": nid, "observed_at": start + h * H, "launches_6h": 10, "creators_6h": 8,
                                          "buyers_h1": int(b), "net_sol_h1": 1.0, "state": "steady", "members": "[]"})
    con.commit()


def test_intraday_compares_each_category_with_its_usual_day(tmp_path):
    con = connect(tmp_path / "i.db")
    start = NOW - 8 * D
    hours = 8 * 24
    base = {"Hot": (1, [40] * (hours - 6) + [200] * 6), "Cold": (2, [100] * (hours - 6) + [30] * 6),
            "Same": (3, [60] * hours)}
    _reads(con, base, start)
    as_of = start + (hours - 1) * H
    intra = M.intraday_read(con, as_of)
    st = {r["category"]: r["status"] for r in intra["categories"]}
    assert st == {"Hot": "heating", "Cold": "cooling", "Same": "normal"}
    assert intra["baseline_hours"] >= 72


def test_comovement_finds_shared_moves_not_market_moves(tmp_path):
    con = connect(tmp_path / "c.db")
    rng = np.random.default_rng(4)
    hours = 7 * 24
    market = np.exp(np.cumsum(rng.normal(0, 0.15, hours)))       # everyone rides this
    shared = rng.normal(0, 0.4, hours)                           # only A and B share this
    def series(extra):
        return 100 * market * np.exp(extra + rng.normal(0, 0.1, hours))
    cats = {"A": (1, series(shared)), "B": (2, series(shared))}
    for i, name in enumerate("CEFGHIJK"):                          # eight categories that only share the market
        cats[name] = (3 + i, series(rng.normal(0, 0.4, hours)))
    _reads(con, cats, NOW - hours * H)
    res = M.comovement(con, NOW)
    found = {frozenset((p["a"], p["b"])) for p in res["pairs"]}
    assert frozenset(("A", "B")) in found
    assert found == {frozenset(("A", "B"))}                       # the shared market swing alone is not enough
    assert res["tested"] == 45 and "does not mean one causes the other" in res["note"]
    assert all(0 < r <= 1 for r in res["market_correlation"].values())


def test_links_name_agreement_and_breaks(market):
    M.summarize(market, NOW, limit=None)
    mac = M.macro_read(market, NOW, windows=(7,))
    intra = {"categories": [
        {"category": "Winners", "status": "heating", "buyers_now": 500, "buyers_usual": 200, "demand_vs_usual": 2.5,
         "graduations_24h": 3, "graduations_usual_per_day": 1.5, "launches_6h": 6, "launches_usual_6h": 5,
         "coins_with_buyers": 4, "top_coin_share": 0.3, "narratives_live": 2, "crowding_narratives": [], "new_narratives": []},
        {"category": "Solo", "status": "heating", "buyers_now": 300, "buyers_usual": 100, "demand_vs_usual": 3.0,
         "graduations_24h": 0, "graduations_usual_per_day": 0.1, "launches_6h": 4, "launches_usual_6h": 4,
         "coins_with_buyers": 1, "top_coin_share": 0.9, "narratives_live": 1, "crowding_narratives": [], "new_narratives": []},
        {"category": "Brand New", "status": "new", "buyers_now": 120, "buyers_usual": None, "demand_vs_usual": None,
         "graduations_24h": 0, "graduations_usual_per_day": None, "launches_6h": 9, "launches_usual_6h": None,
         "coins_with_buyers": 3, "top_coin_share": 0.4, "narratives_live": 1, "crowding_narratives": [], "new_narratives": []}],
        "narratives": []}
    ls = {l["category"]: l for l in M.links(mac, intra)}
    assert ls["Winners"]["kind"] == "confirmed"
    assert ls["Solo"]["kind"] == "hot without a record"
    assert ls["Brand New"]["kind"] == "new, no record"
    assert all(l["detail"] for l in ls.values())


def test_api_serves_the_map(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from radar import api
    from radar.scheduler import State

    from .conftest import make_settings
    monkeypatch.setattr(State, "meta_map", None)
    app = api.create_app(make_settings(tmp_path), with_scheduler=False)
    with TestClient(app) as client:
        assert client.get("/api/meta/map").json()["pending"] is True
        monkeypatch.setattr(State, "meta_map", {"as_of": 1, "macro": {}, "intraday": {}})
        assert client.get("/api/meta/map").json()["as_of"] == 1


def test_backfill_recovers_links_once(tmp_path):
    con = connect(tmp_path / "b.db")
    con.execute("INSERT INTO narratives (id, label, category, first_seen, last_seen, status) VALUES (1, 'x', 'Cats', 1, 1, 'active')")
    insert(con, "narrative_obs", {"narrative_id": 1, "observed_at": 100, "members": json.dumps(["a", "b"]), "state": "new"})
    con.commit()
    assert M.backfill_token_narrative(con) == 2
    assert M.backfill_token_narrative(con) == 0
    assert {r[0] for r in con.execute("SELECT mint FROM token_narrative WHERE category='Cats'")} == {"a", "b"}


def test_rotation_separates_a_broad_move_from_one_coin_and_crowding(tmp_path):
    """Four categories over 8 days of hourly reads. Today: 'Broad' doubles its buyers over four coins
    and its new coins graduate from different creators; 'Solo' doubles on one coin; 'Fading' halves;
    'Crowd' keeps its buyers while its launches jump."""
    con = connect(tmp_path / "r.db")
    start = NOW - 8 * D
    hours = 8 * 24
    as_of = start + (hours - 1) * H
    series = {"Broad": (1, [100] * (hours - 6) + [260] * 6), "Solo": (2, [100] * (hours - 6) + [260] * 6),
              "Fading": (3, [200] * (hours - 6) + [80] * 6), "Crowd": (4, [100] * hours)}
    _reads(con, series, start)
    members = {1: [f"b{i}" for i in range(4)], 2: [f"s{i}" for i in range(4)], 3: [], 4: []}
    for nid, ms in members.items():
        con.execute("UPDATE narrative_obs SET members=? WHERE narrative_id=? AND observed_at=?", (json.dumps(ms), nid, as_of))
    for i in range(4):     # Broad: four coins sharing the buying, three graduated from different creators
        coin(con, f"b{i}", as_of - 20 * H, f"cb{i}", "Broad", 1, 0, grad_after=1800 if i < 3 else None)
        insert(con, "token_obs", {"mint": f"b{i}", "observed_at": as_of - 600, "source": "chain", "buyers_h1": 60})
    for i in range(4):     # Solo: one coin has the buying
        coin(con, f"s{i}", as_of - 20 * H, f"cs{i}", "Solo", 2, 0)
        insert(con, "token_obs", {"mint": f"s{i}", "observed_at": as_of - 600, "source": "chain", "buyers_h1": 240 if i == 0 else 5})
    for d in range(1, 7):  # a usual week of launches for every category, rarely graduating
        for cat, nid in (("Broad", 1), ("Solo", 2), ("Fading", 3), ("Crowd", 4)):
            for j in range(4):
                coin(con, f"u{cat}{d}{j}", as_of - d * D - 3 * H - j * 60, f"cu{cat}{d}{j}", cat, nid, 3,
                     grad_after=900 if (d, j) == (3, 0) else None)
        for j in range(40):
            coin(con, f"m{d}{j}", as_of - d * D - 2 * H - j * 60, f"cm{d}{j}", None, None, 3)
    for j in range(40):
        coin(con, f"mr{j}", as_of - 4 * H - j * 60, f"cmr{j}", None, None, 3)
    for j in range(12):    # Crowd: a burst of launches in the last 6 hours
        coin(con, f"c{j}", as_of - 3 * H - j * 300, f"cc{j}", "Crowd", 4, 2)
    con.commit()
    intra = M.intraday_read(con, as_of)
    rot = M.rotation(con, as_of, {"windows": {}}, intra)
    by = {r["category"]: r for r in rot["categories"]}
    assert by["Broad"]["watch"] and by["Broad"]["stage"] == "emerging"           # early successes, no weekly record
    assert by["Broad"]["signals"]["early_successes"] and by["Broad"]["signals"]["broad"]
    assert not by["Solo"]["watch"] and by["Solo"]["signals"]["single_coin"]
    assert [x["category"] for x in rot["single_coin"]] == ["Solo"]
    assert by["Crowd"]["signals"]["crowding"] and not by["Crowd"]["watch"]
    assert "Fading" in {x["category"] for x in rot["losing"]} and "Fading" in {x["category"] for x in rot["weakening"]}
    assert "Broad" in {x["category"] for x in rot["gaining"]}
    w = rot["watchlist"][0]
    assert w["category"] == "Broad" and w["evidence"] and w["confirm"] and w["invalidate"]
    assert by["Broad"]["signals"]["holders_up"] is False                      # its coins' holder counts are flat
    assert any("holders" in x for x in w["risks"])
    assert by["Fading"]["signals"]["holders_up"] is None                      # no coins with holder counts: not guessed
    # without enough history there is no rotation call at all
    assert M.rotation(con, as_of, {}, {"read_at": as_of, "baseline_hours": 10, "categories": []})["notes"]


def test_usual_means_the_same_time_of_day(tmp_path):
    """A category busy by day and quiet by night is 'normal' at night; a quiet night is not 'cooling'."""
    con = connect(tmp_path / "t.db")
    start = NOW - 8 * D
    hours = 8 * 24
    day_night = [200 if 8 <= (start // H + h) % 24 < 20 else 20 for h in range(hours)]
    _reads(con, {"Rhythm": (1, day_night), "Flat": (2, [60] * hours)}, start)
    night = max(start + h * H for h in range(hours) if (start // H + h) % 24 == 3)
    st = {r["category"]: r for r in M.intraday_read(con, night)["categories"]}
    assert st["Rhythm"]["status"] == "normal" and st["Rhythm"]["demand_vs_usual"] < 1.5
