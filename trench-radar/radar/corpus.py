"""Historical backtest data from the Pump.fun Memecoin Corpus.

Source: huggingface.co/datasets/jocry/Pumpfun_Memecoin_Corpus ("PumpFun Launch-to-Graduation
Corpus"). The Hugging Face card says MIT and the README says CC BY 4.0; it is treated as
CC BY 4.0 (attribution required) and credited in THIRD_PARTY.md. Every pump.fun launch from
2026-06-05 to 2026-07-14 (798,430 tokens, 33.6M trades), collected live, with graduations.

`build()` turns it into a separate research database with the same tables the app uses, so
the app's own walk-forward backtest (analytics/backtest.py) runs on it unchanged:

  tokens        every launch, failed ones included (source 'corpus')
  graduations   from `graduated_at` (cross-checked: equals migrations.migrated_at to the second)
  token_obs     per token per hour, from the trades: buys, sells, distinct buyers/sellers,
                buy/sell SOL, observed at the end of the hour it describes
  curve_obs     curve state at the last trade of that hour
  token_outcomes  graduated within 6h/24h, and the curve price path for every token
  market_obs    SOL/USD by the hour (DefiLlama), and collection coverage per minute

Data-quality rules from the corpus's KNOWN_ISSUES.md, applied here:
  * BwWK17... (§3.3) is excluded from every wallet count;
  * trades whose sol_amount disagrees with token_amount x price by more than 100x (§3.1) or
    has no price (§3.2) are kept for counts but left out of SOL sums;
  * curve_pct_depleted above 100 (§3.4) is treated as unknown;
  * coverage is derived from minutes that contain trades, so the Jul 3 outage is a gap,
    not silently counted as a quiet market (§5.5);
  * entry_price_* columns, a near-perfect graduation proxy (§7), are never read.

Point-in-time: launches are stamped first_seen at their detection time (the corpus was
collected live), hourly stats at the end of their hour; outcome labels are only read by the
backtest as targets. Requires pyarrow (a research dependency, not part of the desktop app).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .analytics.outcomes import bucket, price_path
from .db import connect, now

log = logging.getLogger("radar.corpus")

REPO = "jocry/Pumpfun_Memecoin_Corpus"
HF = "https://huggingface.co"
NON_TRADER = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
MIN_BUYERS = 3            # hourly token rows below this are not stored (the app's live floor is 5)
H = 3600


def files(revision: str) -> list[str]:
    import httpx
    r = httpx.get(f"{HF}/api/datasets/{REPO}/tree/{revision}?recursive=true", timeout=30)
    r.raise_for_status()
    return [f["path"] for f in r.json() if f.get("type") == "file"
            and (f["path"] in ("tokens.parquet", "migrations.parquet", "KNOWN_ISSUES.md")
                 or f["path"].startswith("trades/"))]


def download(dest: Path, revision: str | None = None) -> str:
    """Fetch the files the backtest needs (~5.9 GB, mostly trades) at a pinned revision."""
    import httpx
    dest.mkdir(parents=True, exist_ok=True)
    if not revision:
        revision = httpx.get(f"{HF}/api/datasets/{REPO}", timeout=30).json()["sha"]
    sizes = {f["path"]: f.get("size") for f in httpx.get(
        f"{HF}/api/datasets/{REPO}/tree/{revision}?recursive=true", timeout=30).json()}
    for path in files(revision):
        out = dest / path
        if out.exists() and out.stat().st_size == sizes.get(path):
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading %s", path)
        with httpx.stream("GET", f"{HF}/datasets/{REPO}/resolve/{revision}/{path}", follow_redirects=True,
                          timeout=900) as r:
            r.raise_for_status()
            with open(out.with_suffix(".part"), "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
        out.with_suffix(".part").replace(out)
        if sizes.get(path) and out.stat().st_size != sizes[path]:
            raise IOError(f"{path}: size mismatch")
    (dest / "REVISION").write_text(revision)
    return revision


def _sec(col):
    import pyarrow as pa
    import pyarrow.compute as pc
    return pc.divide(pc.cast(pc.cast(col, pa.timestamp("us", "UTC")), pa.int64()), 1_000_000)


def sol_prices(start: int, end: int) -> dict[int, float]:
    """Hourly SOL/USD from DefiLlama's free coins API (hour start -> price)."""
    import httpx
    out: dict[int, float] = {}
    t = start - start % H
    while t < end:
        r = httpx.get(f"https://coins.llama.fi/chart/coingecko:solana?start={t}&span=500&period=1h", timeout=30)
        r.raise_for_status()
        pts = r.json()["coins"]["coingecko:solana"]["prices"]
        if not pts:
            break
        for p in pts:
            out[p["timestamp"] - p["timestamp"] % H] = p["price"]
        t = pts[-1]["timestamp"] - pts[-1]["timestamp"] % H + H
        time.sleep(1)
    return out


def build(data_dir: Path, db_path: Path, *, prices: dict[int, float] | None = None, force: bool = False) -> dict:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    data_dir, db_path = Path(data_dir), Path(db_path)
    if db_path.exists() and not force:
        raise FileExistsError(f"{db_path} exists (use force=True to rebuild)")
    for p in (db_path, db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")):
        p.unlink(missing_ok=True)
    con = connect(db_path)
    revision = (data_dir / "REVISION").read_text().strip() if (data_dir / "REVISION").exists() else "unknown"
    checks: dict[str, int] = {}

    # ---------------------------------------------------------------- launches + graduations
    tok = pq.read_table(data_dir / "tokens.parquet",
                        columns=["mint", "detected_at", "name", "symbol", "creator", "bonding_curve_key", "graduated_at"])
    det = _sec(tok["detected_at"]).to_pylist()
    grad = _sec(tok["graduated_at"]).to_pylist()
    mints = tok["mint"].to_pylist()
    created = dict(zip(mints, det))
    con.execute("BEGIN")
    con.executemany("INSERT OR IGNORE INTO tokens (mint, name, symbol, creator, pool, launchpad, created_at, "
                    "first_seen_at, source) VALUES (?,?,?,?,?,'pump-fun',?,?,'corpus')",
                    zip(mints, tok["name"].to_pylist(), tok["symbol"].to_pylist(), tok["creator"].to_pylist(),
                        tok["bonding_curve_key"].to_pylist(), det, det))
    graduated: dict[str, int] = {}
    checks["graduation_before_launch_dropped"] = 0
    for m, d, g in zip(mints, det, grad):
        if g is None:
            continue
        if g < d:
            checks["graduation_before_launch_dropped"] += 1
            continue
        graduated[m] = g
    con.executemany("INSERT OR IGNORE INTO graduations (mint, detected_at, graduated_at, source, pool) "
                    "VALUES (?,?,?,'corpus',NULL)", ((m, g, g) for m, g in graduated.items()))
    con.execute("COMMIT")
    checks["tokens"], checks["graduations"] = len(mints), len(graduated)
    lo, hi = min(det), max(det)
    prices = prices if prices is not None else sol_prices(lo - H, hi + 2 * H)
    con.execute("BEGIN")
    con.executemany("INSERT INTO market_obs (observed_at, metric, value, source, detail) "
                    "VALUES (?, 'sol_price_usd', ?, 'defillama', 'historical')", sorted(prices.items()))
    con.execute("COMMIT")
    del tok, det, grad

    # ---------------------------------------------------------------- trades -> hourly stats, outcomes
    covered_minutes: set[int] = set()
    paths: dict[str, list] = {}             # mint -> hourly (first ts, open, high, low, close) candles
    checks.update(trades=0, trades_non_trader=0, trades_without_usable_sol=0, obs_rows=0)
    for f in sorted((data_dir / "trades").glob("trades-*.parquet")):
        t0 = time.time()
        tb = pq.read_table(f, columns=["mint", "event_time", "is_buy", "sol_amount", "token_amount",
                                       "user_wallet", "price_sol", "v_sol_bonding_curve", "curve_pct_depleted"])
        ts = pc.cast(_sec(tb["event_time"]), pa.int64())
        hour_end = pc.multiply(pc.add(pc.divide(ts, H), 1), H)
        human = pc.not_equal(tb["user_wallet"], NON_TRADER)
        ratio = pc.divide(tb["sol_amount"], pc.multiply(tb["token_amount"], tb["price_sol"]))
        sol_ok = pc.fill_null(pc.and_(pc.greater_equal(ratio, 0.01), pc.less_equal(ratio, 100)), False)
        sol = pc.if_else(sol_ok, tb["sol_amount"], 0.0)
        is_buy = pc.fill_null(tb["is_buy"], False)
        t = pa.table({"mint": tb["mint"], "ts": ts, "hour": hour_end, "buy": is_buy,
                      "buy_i": pc.cast(is_buy, pa.int64()), "sell_i": pc.cast(pc.invert(is_buy), pa.int64()),
                      "buy_sol": pc.if_else(is_buy, sol, 0.0), "sell_sol": pc.if_else(is_buy, 0.0, sol),
                      "wallet": tb["user_wallet"], "human": human, "price": tb["price_sol"],
                      "vsol": tb["v_sol_bonding_curve"], "curve": tb["curve_pct_depleted"]})
        checks["trades"] += t.num_rows
        checks["trades_non_trader"] += t.num_rows - pc.sum(pc.cast(human, pa.int64())).as_py()
        checks["trades_without_usable_sol"] += t.num_rows - pc.sum(pc.cast(sol_ok, pa.int64())).as_py()
        covered_minutes.update(pc.unique(pc.divide(ts, 60)).to_pylist())
        t = t.take(pc.sort_indices(t, [("mint", "ascending"), ("ts", "ascending")]))
        agg = t.group_by(["mint", "hour"], use_threads=False).aggregate([
            ("buy_i", "sum"), ("sell_i", "sum"), ("buy_sol", "sum"), ("sell_sol", "sum"),
            ("price", "first"), ("price", "max"), ("price", "last"), ("vsol", "last"), ("curve", "last"),
            ("ts", "min"), ("ts", "max")])
        hm = t.filter(t["human"])
        buyers = hm.filter(hm["buy"]).group_by(["mint", "hour"]).aggregate([("wallet", "count_distinct")])
        sellers = hm.filter(pc.invert(hm["buy"])).group_by(["mint", "hour"]).aggregate([("wallet", "count_distinct")])
        bmap = {(m, h): n for m, h, n in zip(buyers["mint"].to_pylist(), buyers["hour"].to_pylist(),
                                             buyers["wallet_count_distinct"].to_pylist())}
        smap = {(m, h): n for m, h, n in zip(sellers["mint"].to_pylist(), sellers["hour"].to_pylist(),
                                             sellers["wallet_count_distinct"].to_pylist())}
        obs, curves = [], []
        for r in agg.to_pylist():
            key = (r["mint"], r["hour"])
            nb, ns = bmap.get(key, 0), smap.get(key, 0)
            if r["price_last"]:
                paths.setdefault(r["mint"], []).append((r["ts_min"], r["price_first"] or r["price_last"],
                                                        r["price_max"] or r["price_last"], None, r["price_last"]))
            if nb < MIN_BUYERS:
                continue
            usd = prices.get(r["hour"] - H) or prices.get(r["hour"] - 2 * H)
            u = (lambda x: x * usd) if usd else (lambda x: None)
            obs.append((r["mint"], r["hour"], "corpus", "pump-fun", r["price_last"] * usd if usd and r["price_last"] else None,
                        u(r["buy_sol_sum"] + r["sell_sol_sum"]), r["buy_i_sum"], r["sell_i_sum"], nb, ns,
                        u(r["buy_sol_sum"]), u(r["sell_sol_sum"]), round(r["buy_sol_sum"] - r["sell_sol_sum"], 4)))
            curve = r["curve_last"] if r["curve_last"] is not None and 0 <= r["curve_last"] <= 100 else None
            real = (r["vsol_last"] / 1e9 - 30) if r["vsol_last"] else None
            curves.append((r["mint"], r["hour"], real, curve / 100 if curve is not None else None,
                           int(r["mint"] in graduated and graduated[r["mint"]] <= r["hour"]), r["price_last"]))
        con.execute("BEGIN")
        con.executemany("INSERT INTO token_obs (mint, observed_at, source, dex, price_usd, vol_h1, buys_h1, sells_h1, "
                        "buyers_h1, sellers_h1, buy_vol_h1, sell_vol_h1, net_sol_h1) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", obs)
        con.executemany("INSERT INTO curve_obs (mint, observed_at, real_sol, progress, complete, price_sol) "
                        "VALUES (?,?,?,?,?,?)", curves)
        con.execute("COMMIT")
        checks["obs_rows"] += len(obs)
        log.info("%s: %d trades, %d hourly rows (%.0fs)", f.name, t.num_rows, len(obs), time.time() - t0)

    # ---------------------------------------------------------------- coverage + outcome labels
    con.execute("BEGIN")
    con.executemany("INSERT INTO market_obs (observed_at, metric, value, source, detail) "
                    "VALUES (?, 'stream_connected_s', 60.0, 'corpus', 'minute with trades')",
                    ((m * 60 + 60,) for m in sorted(covered_minutes)))
    labelled = 0
    for m, c in created.items():
        pts = sorted(paths.get(m, []))
        for hz in (6, 24):
            g = graduated.get(m)
            by_h = bool(g and g <= c + hz * H)
            row = {"graduated": int(by_h), "bucket": "migrated" if by_h else "unknown"}
            pp = price_path([p for p in pts if p[0] <= c + hz * H], c, hz) if pts else None
            if pp and by_h:
                pp.update(end_price=None, ret_end=None)        # post-graduation price not in these rows
            con.execute("""INSERT OR REPLACE INTO token_outcomes (mint, horizon_h, evaluated_at, graduated, bucket,
                           first_price, end_price, max_price, ret_end, ret_max, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (m, hz, c + hz * H, row["graduated"], row["bucket"],
                         *((pp["first_price"], pp["end_price"], pp["max_price"], pp["ret_end"], pp["ret_max"])
                           if pp else (None,) * 5), "corpus"))
            labelled += 1
    checks["outcome_labels"] = labelled
    checks["collection_runs"] = add_collection_runs(con, covered_minutes)
    checks["covered_minutes"] = len(covered_minutes)
    con.execute("INSERT OR REPLACE INTO meta_info VALUES ('corpus', ?)", (json.dumps({
        "repo": REPO, "revision": revision, "built_at": now(), "launch_range": [lo, hi], "checks": checks,
        "licence": "CC BY 4.0 per README (card says MIT)", "min_buyers_per_hour_row": MIN_BUYERS}),))
    con.execute("COMMIT")
    return checks


def add_collection_runs(con, covered_minutes: set[int] | None = None) -> int:
    """One source_runs row ('corpus', 'collection') per hour that has trades, so the scoring's
    source-freshness factor sees the corpus the way it sees the live stream. Gap hours get no
    row, so a step right after an outage reads as stale, as it should."""
    if covered_minutes is None:
        covered_minutes = {int(r[0]) // 60 - 1 for r in con.execute(
            "SELECT observed_at FROM market_obs WHERE metric='stream_connected_s' AND source='corpus'")}
    hours = sorted({m * 60 // H for m in covered_minutes})
    con.execute("DELETE FROM source_runs WHERE source='corpus'")
    con.executemany("INSERT INTO source_runs (source, job, started_at, finished_at, status, items, latency_ms) "
                    "VALUES ('corpus', 'collection', ?, ?, 'ok', 0, 0)", ((h * H, (h + 1) * H) for h in hours))
    return len(hours)


def gaps(con, min_hours: int = 1) -> list[tuple[int, int]]:
    """Collection gaps: runs of whole hours with no launch at all. pump.fun never goes an
    hour without one, so these are outages, not quiet markets. (The corpus README calls the
    collection uninterrupted; in revision bd8aed6 192 of 943 hours are empty, in ten runs.)"""
    hours = {r[0] for r in con.execute("SELECT created_at / 3600 FROM tokens WHERE source='corpus'")}
    if not hours:
        return []
    out, cur = [], None
    for h in range(min(hours), max(hours) + 1):
        if h not in hours:
            cur = [h, h] if cur is None else [cur[0], h]
        elif cur:
            if cur[1] - cur[0] + 1 >= min_hours:
                out.append((cur[0] * 3600, (cur[1] + 1) * 3600))
            cur = None
    return out


def provenance_checks(con) -> dict:
    """Point-in-time sanity for a research DB: nothing may be seen before it happened."""
    one = lambda q: con.execute(q).fetchone()[0]  # noqa: E731
    return {
        "tokens_seen_before_launch": one("SELECT COUNT(*) FROM tokens WHERE first_seen_at < created_at"),
        "graduations_before_launch": one("""SELECT COUNT(*) FROM graduations g JOIN tokens k ON k.mint=g.mint
                                            WHERE g.graduated_at < k.created_at"""),
        "obs_before_launch": one("""SELECT COUNT(*) FROM token_obs o JOIN tokens k ON k.mint=o.mint
                                    WHERE o.observed_at < k.created_at"""),
        "outcomes_evaluated_early": one("""SELECT COUNT(*) FROM token_outcomes o JOIN tokens k ON k.mint=o.mint
                                           WHERE o.evaluated_at < k.created_at + o.horizon_h * 3600"""),
    }
