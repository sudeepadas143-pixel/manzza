"""Live launch-window features (radar/early.py) must equal the corpus research definitions
(scripts/quant_dataset.py) on the same trades, or a model fitted on the corpus would be scoring
something else live. All trades here are fabricated test data."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from radar import early
from radar.db import connect, rows
from radar.stream import Live

pytest.importorskip("pyarrow")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import quant_dataset as QD  # noqa: E402

T0 = 1_790_000_000
SYSTEM = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
P = 30.0 / 1_073_000_191


def trade(mint, ts, user, buy, sol, tokens, price_mult=1.0, creator="C"):
    vt = 1_000_000_000.0
    return {"type": "trade", "mint": mint, "ts": ts, "user": user, "is_buy": buy, "sol": sol, "tokens": tokens,
            "v_sol": P * price_mult * vt, "v_tokens": vt, "real_sol": 1.0, "real_tokens": 5e8, "creator": creator,
            "sol_paired": True, "slot": 10}


TRADES = [  # (dt, wallet, buy, sol, tokens, price multiple)
    (0, "C", True, 1.0, 3e7, 1.0), (1, "A", True, 0.5, 1e7, 1.1), (2, "B", True, 0.2, 4e6, 1.15),
    (5, SYSTEM, True, 0.1, 2e6, 1.2), (20, "A", False, 0.6, 1e7, 1.1), (30, "D", True, 2.0, 3e7, 1.6),
    (45, "C", False, 0.3, 5e6, 1.5), (59, "E", True, 0.05, 1e6, 1.55), (90, "F", True, 1.0, 1e7, 1.9),
]


def feed(live, mint="M1", t0=T0):
    live.on_event({"type": "create", "mint": mint, "name": "Test Cat", "symbol": "TCAT", "uri": "", "bonding_curve": "BC",
                   "user": "C", "creator": "C", "ts": t0, "initial_real_tokens": 793_100_000, "sol_paired": True,
                   "slot": 10, "mayhem": False, "cashback": True}, t=t0)
    for dt, w, b, sol, tok, pm in TRADES:
        live.on_event(trade(mint, t0 + dt, w, b, sol, tok, pm), t=t0 + dt)


def test_live_window_matches_the_corpus_definition(tmp_path):
    live = Live()
    feed(live)
    ms = live.mints["M1"]
    got = early.window_features(ms, 60, live)
    # the same trades through the corpus code
    wallets = sorted({w for _, w, *_ in TRADES})
    wid = {w: i for i, w in enumerate(wallets)}
    tr = {"tok": np.zeros(len(TRADES), int), "ssl": np.array([t[0] for t in TRADES], float),
          "buy": np.array([t[2] for t in TRADES]), "sol": np.array([t[3] for t in TRADES]),
          "amt": np.array([t[4] for t in TRADES]), "wallet": np.array([wid[t[1]] for t in TRADES]),
          "mcap": np.array([27.959 * t[5] for t in TRADES])}
    ref = QD.per_token_window(tr, 1, 60, np.array([wid["C"]]), wid[SYSTEM])
    for k in ("n_trades", "n_buys", "n_sells", "buy_sol", "sell_sol", "uniq_buyers", "uniq_sellers",
              "top_buyer_share", "snipers", "dumped_share", "creator_sold"):
        assert got[k] == pytest.approx(float(ref[k][0])), k
    assert got["mcap_ratio"] == pytest.approx(1.55, rel=1e-6)        # price at the last trade <= 60 s
    assert got["uniq_buyers"] == 5                                     # C, A, B, D, E; the System Program is left out


def test_capture_writes_rows_at_each_age_and_credits_graduations(tmp_path):
    con = connect(tmp_path / "e.db")
    live = Live()
    feed(live)
    assert early.capture(con, live, T0 + 50, None) == 0                # window not closed yet
    assert early.capture(con, live, T0 + 75, None) == 1
    r = rows(con, "SELECT * FROM token_early WHERE mint='M1'")
    assert len(r) == 1 and r[0]["age_s"] == 60 and r[0]["p_grad"] is None
    f = json.loads(r[0]["features"])
    assert f["uniq_buyers"] == 5 and f["cashback"] is True and f["meta_term"] in {"test", "cat", "tcat"}
    # graduation credits the first-minute buyers only
    live.on_event({"type": "complete", "mint": "M1", "user": "x", "bonding_curve": "BC", "ts": T0 + 200}, t=T0 + 200)
    assert live.credit_count("A", T0 + 300) == 1 and live.credit_count("F", T0 + 300) == 0
    assert live.credit_count("A", T0 + 100) == 0                       # not before it happened
    live.flush(con)
    assert {r["wallet"] for r in rows(con, "SELECT wallet FROM wallet_credits")} == {"C", "A", "B", "D", "E"}
    # graduated before 300 s: no row at 300 s or 900 s, and the window buffer is released
    early.capture(con, live, T0 + 1000, None)
    assert {r["age_s"] for r in rows(con, "SELECT age_s FROM token_early WHERE mint='M1'")} == {60}
    assert live.mints["M1"].ew is None


def test_meta_and_track_record_are_point_in_time():
    ctx = early.Context()
    for i in range(6):
        ctx.on_launch(f"k{i}", T0 + i * 60, "Kimchi Dog", "KIM", f"c{i}")
    m = ctx.meta(T0 + 330, ["kimchi", "dog"], "Kimchi Dog")
    assert m["m_launch_1h"] == 6 and m["m_hist_n"] == 0                # nothing matured yet
    grads = {"k0": T0 + 100}
    ctx.mature(T0 + 2 * 3600, grads.get)
    m = ctx.meta(T0 + 2 * 3600, ["kimchi"], "Kimchi Dog")
    assert m["m_hist_n"] == 6 and m["m_hist_grad"] == 1 and m["m_launch_1h"] == 0
