"""Plain-language meta explanations (radar/analytics/explain.py): the reasons must be the model's
own arithmetic, negative evidence must never be dropped, and no internal names may leak into
the text. All market data here is fabricated test data."""
import math
import re

import pytest

from radar.analytics import explain as X
from radar.analytics import meta_model as mm
from radar.analytics.scoring import EDGE_MODEL, run_analysis

from .conftest import T0

TEXT_KEYS = ("attention", "risks", "watch")


@pytest.fixture
def read(history_db):
    return run_analysis(history_db, T0, persist=False)


def test_contributions_add_up_to_the_lift_over_the_reads_average(read):
    model = EDGE_MODEL
    lifts = [model.lift(mm.transform(mm.raw(m, read["market"]))) for m in read["metas"]]
    mean = sum(lifts) / len(lifts)
    for items, lift in zip(X.contributions(read["metas"], read["market"], model), lifts):
        assert sum(i["contribution"] for i in items) == pytest.approx(lift - mean, abs=1e-9)
    # every model input is accounted for exactly once, missing-value indicators included
    assert {i["input"] for i in items} == set(model.names)


def test_every_meta_is_explained_in_all_sections(read):
    metas = X.attach(read, None)
    assert metas and all(m["explain"] for m in metas)
    for m in metas:
        x = m["explain"]
        assert x["concept"]["text"] and x["concept"]["connects"]
        assert x["happening"]["status"] in {"new", "growing", "steady", "fading", "crowded"} and x["happening"]["text"]
        assert x["attention"] and x["watch"] and x["evidence"]
        r = x["recommendation"]
        assert r["rank"] == m["edge"]["rank"] and r["tier"] == m["edge"]["tier"]
        # the per-theme effects are the per-input contributions, regrouped
        assert sum(d["effect"] for d in r["drivers"]) == pytest.approx(
            sum(e["effect"] for e in x["evidence"] if e["theme"] != "market"), abs=0.01)
        # risks are never hidden: the last line always says graduation is not profit
        assert x["risks"][-1].startswith("Graduation is not profit")
        assert x["confidence"]["level"] in {"low", "mixed", "moderate"} and x["confidence"]["notes"]


def test_reasons_follow_the_sign_of_their_theme(read):
    metas = X.attach(read, None)
    for m in metas:
        r = m["explain"]["recommendation"]
        effect = {d["theme"]: d["effect"] for d in r["drivers"]}
        pos = [t for t, v in effect.items() if t != "market" and v >= 0.05]
        neg = [t for t, v in effect.items() if t != "market" and v <= -0.05]
        assert len(r["for"]) == len(pos) and len(r["against"]) == len(neg)


def test_no_internal_names_reach_the_reader(read):
    plain_words = {"market", "tracked"}           # input names that are also ordinary English
    internal = (set(mm.FEATURES) - plain_words) | set(X.RAW_KEY.values()) | {"lift_logit", "meta_key"}
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, sorted(internal, key=len, reverse=True))) + r")\b")
    for m in X.attach(read, None):
        x = m["explain"]
        lines = x["concept"]["text"] + x["happening"]["text"] + [r["text"] for r in x["recommendation"]["for"] + x["recommendation"]["against"]]
        lines += [t for k in TEXT_KEYS for t in x[k]] + x["confidence"]["notes"] + [x["confidence"]["summary"]]
        for line in lines:
            assert not pattern.search(line), line
            assert "nan" not in line.lower().split() and "None" not in line, line


def test_confidence_reports_the_tested_periods_honestly(read):
    m = X.attach(read, None)[0]
    c = m["explain"]["confidence"]
    assert {p["period"].split(" (")[0] for p in c["periods"]} == {"June–July 2026", "September 16", "October 15"}
    # in the shipped validation the tiers did not separate on October 15: that must be said
    assert any("October 15" in t and "barely" in t for t in c["text"])
    assert c["level"] != "moderate"


def test_narrative_join_prefers_the_narrative_named_after_the_meta():
    coins = [f"m{i}" for i in range(20)]
    broad = {"title": "DOGE PEPE", "terms": ["doge", "cat", "pepe"], "members": coins[:15]}
    named = {"title": "Weird Cat", "terms": ["weird", "cat"], "members": coins[10:14]}
    other = {"title": "Frog", "terms": ["frog"], "members": coins[:2]}
    assert X._narrative_for(coins, [broad, named, other], "cat") is named
    assert X._narrative_for(coins, [broad, other], "cat") is broad        # named only in its terms
    assert X._narrative_for(coins, [other], "cat") is None                # 2 of 20 coins: not enough
    frogs = {"title": "Frog", "terms": ["frog"], "members": coins[:3]}
    assert X._narrative_for(coins[:6], [frogs], "cat") is frogs           # 3 shared coins, half of them


def test_narrative_text_comes_from_the_narrative(read):
    m = read["metas"][0]
    nar = {"label": "frog · leap", "title": "Frog Leap", "state": "accelerating", "terms": [m["terms"][0]],
           "members": read["meta_mints"][m["meta_key"]][:5],
           "represents": {"post": {"tokens": 4, "author": "someone", "text": "frogs are back", "followers": 1200},
                          "description": None, "examples": [{"name": "Frog Leap"}, {"name": "Leap Frog"}]},
           "category": {"primary": "Animals", "secondary": []}}
    x = X.attach(read, {"narratives": [nar]})[0]["explain"]
    assert x["concept"]["narrative"]["title"] == "Frog Leap" and x["concept"]["source"] == "post"
    assert any("frogs are back" in t for t in x["concept"]["text"])
    assert any("@someone" in t for t in x["attention"])
    assert "Leap Frog" in x["concept"]["text"][0] and "others include Frog Leap" not in x["concept"]["text"][0]


def test_each_reason_says_whether_it_held_up_on_its_own(read):
    rel = X.reliability(EDGE_MODEL)
    assert set(rel) == set(X.THEMES) and all(r["tested"] == 2 for r in rel.values())
    # shipped check: buying signals held in both later periods; 'who is launching' in neither
    assert rel["money_in"]["held"] == 2 and "both" in rel["money_in"]["note"]
    assert rel["creators"]["held"] == 0 and "did not hold up" in rel["creators"]["note"]
    for m in X.attach(read, None):
        for r in m["explain"]["recommendation"]["for"] + m["explain"]["recommendation"]["against"]:
            assert r["reliability"] == rel[r["theme"]]


def test_live_history_is_point_in_time_and_marked_as_not_used():
    class Ctx:
        hist = {"frog": [(T0 - 9 * 86400, 1, 0), (T0 - 3600, 1, 0), (T0 - 7200, 0, 0)]}
        gsum = [100, 2, 10]

    class Live:
        early_ctx = Ctx()
    h = X.history({"terms": ["frog"]}, Live(), T0)
    assert h["launches"] == 2 and h["graduated"] == 1            # the 9-day-old launch is outside 7 days
    assert h["all_rate_24h"] == pytest.approx(0.02) and "Not used for the ranking" in h["note"]
    assert X.history({"terms": ["frog"]}, object(), T0) is None


def test_overview_carries_explanations_and_input_monitoring(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from radar import api
    from radar.db import connect

    from .conftest import build_history, make_settings
    con = connect(tmp_path / "x.db")
    build_history(con)
    con.close()
    monkeypatch.setattr(api, "now", lambda: T0)
    import radar.analytics.scoring as sc
    monkeypatch.setattr(sc, "now", lambda: T0)
    app = api.create_app(make_settings(tmp_path, db_path=tmp_path / "x.db"), with_scheduler=False)
    with TestClient(app) as client:
        ov = client.get("/api/overview").json()
    assert ov["edge_model"] and ov["metas"] and all(m["explain"] for m in ov["metas"])
    mon = ov["edge_monitor"]
    assert mon["inputs"] == len(ov["metas"]) * len(EDGE_MODEL.names) and 0 <= mon["unusual_share"] <= 1
    assert "meta_mints" not in ov and "members" not in json_dumps(ov)


def json_dumps(o):
    import json
    return json.dumps(o)


def test_missing_inputs_are_not_turned_into_reasons(read):
    metas = X.attach(read, None)
    for m in metas:
        rows = {e["input"]: e for e in m["explain"]["evidence"]}
        for e in rows.values():
            if e["value"] == "not measured yet":
                assert e["reads"].startswith("no data")
    assert math.isfinite(sum(e["effect"] for e in metas[0]["explain"]["evidence"]))
