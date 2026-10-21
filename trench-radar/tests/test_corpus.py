"""Corpus builder on a tiny synthetic corpus (fabricated rows, same schema as the real files)."""
from datetime import datetime, timedelta, timezone

import pytest

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from radar import corpus  # noqa: E402
from radar.db import connect, rows  # noqa: E402

T0 = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
PLUS1 = timezone(timedelta(hours=1))      # the real files mix UTC and +01:00 timestamps


def write_corpus(d):
    (d / "trades").mkdir(parents=True)
    (d / "REVISION").write_text("test-rev")
    pq.write_table(pa.table({
        "mint": ["A", "B", "C"], "detected_at": [T0, T0 + timedelta(minutes=5), T0 + timedelta(minutes=9)],
        "name": ["Frog King", "Cat Lord", "Dead Coin"], "symbol": ["FROG", "CAT", "DEAD"],
        "creator": ["c1", "c2", "c3"], "bonding_curve_key": ["pa", "pb", "pc"],
        "graduated_at": [T0 + timedelta(minutes=50), None, T0 - timedelta(hours=1)],   # C: impossible, dropped
    }), d / "tokens.parquet")
    trades = []
    for i in range(6):                                    # A: 5 distinct buyers + the non-trader address
        w = corpus.NON_TRADER if i == 5 else f"w{i}"
        trades.append(("A", (T0 + timedelta(minutes=10 + i)).astimezone(PLUS1), True, 1.0, 3.5e7, w, 2.857e-8, 31e9, 10.0))
    trades.append(("A", (T0 + timedelta(minutes=20)).astimezone(PLUS1), False, 0.5, 1.7e7, "w1", 2.94e-8, 30.5e9, 9.0))
    trades.append(("A", (T0 + timedelta(minutes=21)).astimezone(PLUS1), True, 9e6, 1.0e7, "w9", 3e-8, 30.6e9, 110.0))  # corrupt sol
    trades.append(("B", (T0 + timedelta(minutes=30)).astimezone(PLUS1), True, None, 1e6, "w1", None, None, None))
    cols = list(zip(*trades))
    pq.write_table(pa.table({
        "mint": cols[0], "event_time": pa.array(cols[1], pa.timestamp("us", "+01:00")), "is_buy": cols[2],
        "sol_amount": pa.array(cols[3], pa.float64()), "token_amount": cols[4], "user_wallet": cols[5],
        "price_sol": pa.array(cols[6], pa.float64()), "v_sol_bonding_curve": pa.array(cols[7], pa.float64()),
        "curve_pct_depleted": pa.array(cols[8], pa.float64())}), d / "trades" / "trades-00000.parquet")


def test_build_applies_known_issue_rules_and_stays_point_in_time(tmp_path):
    write_corpus(tmp_path / "c")
    hour = int(T0.timestamp()) // 3600 * 3600
    checks = corpus.build(tmp_path / "c", tmp_path / "r.db", prices={hour: 150.0})
    con = connect(tmp_path / "r.db")
    assert checks["tokens"] == 3 and checks["graduations"] == 1 and checks["graduation_before_launch_dropped"] == 1
    assert checks["trades_non_trader"] == 1
    o = rows(con, "SELECT * FROM token_obs WHERE mint='A'")[0]
    assert o["buyers_h1"] == 6 - 1 + 1 and o["sellers_h1"] == 1          # w0..w4 + w9; the non-trader excluded
    assert o["buys_h1"] == 7 and abs(o["net_sol_h1"] - (6 - 0.5)) < 1e-9  # the corrupt 9e6 SOL is not summed
    assert o["observed_at"] == hour + 3600                                 # end of the hour it describes
    c = rows(con, "SELECT progress FROM curve_obs WHERE mint='A'")[0]
    assert c["progress"] is None                                           # last curve value 110 -> unknown
    out = {(r["mint"], r["horizon_h"]): r for r in rows(con, "SELECT * FROM token_outcomes")}
    assert out[("A", 6)]["graduated"] == 1 and out[("B", 24)]["graduated"] == 0 and out[("C", 6)]["graduated"] == 0
    assert set(corpus.provenance_checks(con).values()) == {0}
    assert rows(con, "SELECT COUNT(*) n FROM market_obs WHERE metric='stream_connected_s'")[0]["n"] == 9   # minutes with trades


def test_backtest_skips_excluded_periods_and_reports_acceleration(history_db, monkeypatch):
    from radar.analytics import backtest
    from tests.conftest import T0 as HT0
    monkeypatch.setattr(backtest, "now", lambda: HT0 + 40 * 3600)
    res = backtest.run_backtest(history_db, HT0 - 6 * 3600, HT0, step_s=3600, persist=False,
                                exclude=[(HT0 - 3 * 3600, HT0 - 2 * 3600)])
    assert res["steps_excluded"] >= 1 and "accelerating (z >= 2)" in res["by_acceleration"]


def test_collection_gaps_are_found_from_empty_hours(tmp_path):
    from radar.db import insert
    con = connect(tmp_path / "g.db")
    for h in (0, 1, 5, 6):                          # hours 2-4 empty
        insert(con, "tokens", {"mint": f"m{h}", "launchpad": "pump-fun", "created_at": h * 3600 + 10,
                               "first_seen_at": h * 3600 + 10, "source": "corpus"})
    assert corpus.gaps(con) == [(2 * 3600, 5 * 3600)]
