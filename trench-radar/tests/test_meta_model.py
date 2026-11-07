"""The launch-edge model (radar/analytics/meta_model.py): the live app must compute exactly the
inputs the research scripts validated, rank every meta, and fall back to the readiness order
when no model is installed. All market data here is fabricated test data."""
import math

import numpy as np
import pytest

from radar.analytics import meta_model as mm
from radar.analytics import scoring
from radar.analytics.backtest import _top_picks, run_backtest
from radar.analytics.scoring import run_analysis
from radar.db import insert, rows

from .conftest import H, T0


def test_shipped_model_matches_the_feature_definitions():
    model = mm.EdgeModel.load()
    assert model is not None, "radar/data/meta_model.json is missing"
    assert model.names == mm.FEATURES
    assert len(model.b) == 1 + len(model.names) + len(model.ind)
    assert model.spec["use"].startswith("ranking only")
    # every input missing: imputed at the training medians, still a finite lift
    assert math.isfinite(model.lift({k: float("nan") for k in mm.FEATURES}))


def test_live_scalar_inputs_equal_the_research_array_inputs(history_db):
    """scripts/meta_validate.py transforms arrays of raw values; the app transforms one meta."""
    res = run_analysis(history_db, T0, persist=False)
    raws = [mm.raw(m, res["market"]) for m in res["metas"]]
    keys = [k for k in raws[0] if k != "verdict"]
    arrays = {k: np.array([np.nan if r[k] is None else float(r[k]) for r in raws]) for k in keys}
    vec = mm.transform(arrays)
    for i, r in enumerate(raws):
        one = mm.transform(r)
        for k in mm.FEATURES:
            a, b = float(one[k]), float(vec[k][i])
            assert (math.isnan(a) and math.isnan(b)) or a == pytest.approx(b), k


def test_every_meta_gets_a_rank_and_the_list_follows_it(history_db):
    res = run_analysis(history_db, T0, persist=False)
    assert res["edge_model"] and res["edge_model"].startswith("meta-edge")
    ranks = [m["edge"]["rank"] for m in res["metas"]]
    assert ranks == list(range(1, len(ranks) + 1))
    assert {m["edge"]["of"] for m in res["metas"]} == {len(ranks)}
    lifts = [m["edge"]["lift_logit"] for m in res["metas"]]
    assert lifts == sorted(lifts, reverse=True)
    assert res["metas"][0]["edge"]["tier"] == "strongest"
    # the readiness score is still there, as the baseline
    assert all("score" in m and "verdict" in m for m in res["metas"])


def test_without_a_model_the_readiness_order_is_kept(history_db, monkeypatch):
    monkeypatch.setattr(scoring, "EDGE_MODEL", None)
    res = run_analysis(history_db, T0, persist=False)
    assert res["edge_model"] is None and all(m["edge"] is None for m in res["metas"])
    called = [m for m in res["metas"] if m["verdict"] != "insufficient data"]
    assert [m["score"] for m in called] == sorted((m["score"] for m in called), reverse=True)


def test_top_pick_comparison():
    sig = [  # two steps, two metas each
        {"t": 0, "score": 80, "edge_lift": -1.0, "k_future": 0, "n_future": 10, "grad_rate": 0.0, "base_grad_rate": 0.1},
        {"t": 0, "score": 20, "edge_lift": 1.0, "k_future": 3, "n_future": 10, "grad_rate": 0.3, "base_grad_rate": 0.1},
        {"t": 1, "score": 90, "edge_lift": 0.5, "k_future": 1, "n_future": 5, "grad_rate": 0.2, "base_grad_rate": 0.1},
        {"t": 1, "score": 10, "edge_lift": 0.1, "k_future": 0, "n_future": 5, "grad_rate": 0.0, "base_grad_rate": 0.1},
    ]
    tp = _top_picks(sig)
    assert tp["edge"] == {"steps": 2, "grad_rate": round(4 / 15, 4), "market_rate": 0.1, "ratio": round(4 / 1.5, 3)}
    assert tp["readiness"]["ratio"] == round(1 / 1.5, 3)
    assert _top_picks([{**s, "edge_lift": None} for s in sig])["edge"] is None


def test_backtest_records_both_top_picks(history_db, monkeypatch):
    for r in rows(history_db, "SELECT mint, name FROM tokens"):
        insert(history_db, "token_outcomes", {"mint": r["mint"], "horizon_h": 24, "evaluated_at": T0,
                                              "graduated": int(r["name"].startswith("Frog")), "bucket": "dead",
                                              "ret_end": -0.5, "source": "test"})
    history_db.commit()
    import radar.analytics.backtest as bt
    monkeypatch.setattr(bt, "now", lambda: T0 + 40 * H)
    res = run_backtest(history_db, T0 - 8 * H, T0, step_s=2 * H, follow_h=2, horizon_h=24, persist=False)
    assert set(res["top_pick"]) == {"readiness", "edge"}
    assert res["top_pick"]["edge"]["steps"] == res["top_pick"]["readiness"]["steps"] > 0
