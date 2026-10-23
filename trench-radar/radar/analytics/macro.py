"""Macro and intraday meta intelligence: which categories and narratives are producing successful
coins this week (and over 14 / 30 days), what is working today, and how the two connect.

Built on what the app already records:
  token_narrative  each coin's first narrative and category (written by narratives._persist)
  token_summary    each coin's first 24 hours (summarize(), below), kept after snapshots are pruned
  narrative_obs    every narrative read (14 days), for intraday baselines and co-movement
  graduations, token_outcomes, early_buyers, market_obs

Success is judged per coin and by breadth, never by launch counts: a category "works" when
several independent coins (different creators) graduate or draw real buying, and its record is
judged with its best coin left out so one runaway cannot carry it. A graduation within a minute
of launch is not counted as success: that is the creator's own wallets buying out the curve.
"""
from __future__ import annotations

from ..db import now as _now

H = 3600
D = 86400
FACTORY_N, FACTORY_S = 10, 7 * H


WRITE_CHUNK = 500        # rows per write transaction: keeps the database's write lock brief for the live stream


def summarize(con, now_t: int | None = None, *, limit: int | None = 5000, lookback: int = 30 * D) -> int:
    """Summarise every coin whose first 24 hours have passed and that has no summary yet."""
    now_t = now_t or _now()
    done = 0
    while True:
        batch = con.execute(
            """SELECT k.mint, k.created_at, k.creator FROM tokens k
               LEFT JOIN token_summary s ON s.mint = k.mint
               WHERE s.mint IS NULL AND k.created_at IS NOT NULL AND k.created_at <= ? AND k.created_at > ?
               ORDER BY k.created_at LIMIT ?""", (now_t - D, now_t - lookback, 20000 if limit is None else min(limit, 20000))
        ).fetchall()
        if not batch:
            return done
        # Read first, write after: under WAL a read never blocks the live stream's writes, while an
        # INSERT ... SELECT over a batch would hold the write lock for the whole aggregation and stall
        # the stream (its writes run on the event loop).
        con.execute("CREATE TEMP TABLE IF NOT EXISTS _sb (mint TEXT PRIMARY KEY, created_at INTEGER, creator TEXT)")
        con.execute("DELETE FROM _sb")
        con.executemany("INSERT INTO _sb VALUES (?,?,?)", batch)
        rows_ = con.execute(f"""
                SELECT b.mint, b.created_at, b.creator,
                    (SELECT COUNT(*) FROM tokens t2 WHERE b.creator IS NOT NULL AND t2.creator = b.creator
                        AND t2.created_at > b.created_at - {FACTORY_S} AND t2.created_at <= b.created_at) >= {FACTORY_N},
                    tn.narrative_id, tn.label, tn.category,
                    o.peak_buyers, o.peak_holders,
                    (SELECT holders FROM token_obs x WHERE x.mint = b.mint AND x.observed_at <= b.created_at + {D}
                        AND x.holders IS NOT NULL ORDER BY x.observed_at DESC LIMIT 1),
                    o.peak_mcap, o.peak_liq, o.peak_net, c.max_progress,
                    g.at IS NOT NULL AND g.at <= b.created_at + {D}, g.at, oc.ret_max, COALESCE(o.n, 0), ?
                FROM _sb b
                LEFT JOIN token_narrative tn ON tn.mint = b.mint
                LEFT JOIN (SELECT x.mint, MAX(x.buyers_h1) AS peak_buyers, MAX(x.holders) AS peak_holders,
                                  MAX(COALESCE(x.mcap_usd, x.fdv_usd, x.price_usd * 1e9)) AS peak_mcap,
                                  MAX(x.liquidity_usd) AS peak_liq, MAX(x.net_sol_h1) AS peak_net, COUNT(*) AS n
                           FROM token_obs x JOIN _sb y ON y.mint = x.mint
                           WHERE x.observed_at <= y.created_at + {D} GROUP BY x.mint) o ON o.mint = b.mint
                LEFT JOIN (SELECT x.mint, MAX(CASE WHEN x.complete THEN 1.0 ELSE x.progress END) AS max_progress
                           FROM curve_obs x JOIN _sb y ON y.mint = x.mint
                           WHERE x.observed_at <= y.created_at + {D} GROUP BY x.mint) c ON c.mint = b.mint
                LEFT JOIN (SELECT mint, COALESCE(graduated_at, detected_at) AS at FROM graduations) g ON g.mint = b.mint
                LEFT JOIN token_outcomes oc ON oc.mint = b.mint AND oc.horizon_h = 24""", (now_t,)).fetchall()
        for i in range(0, len(rows_), WRITE_CHUNK):
            con.execute("BEGIN")
            try:
                con.executemany("""INSERT OR REPLACE INTO token_summary (mint, created_at, creator, factory, narrative_id,
                                   label, category, peak_buyers_h1, peak_holders, holders_end, peak_mcap_usd, peak_liq_usd,
                                   peak_net_sol_h1, max_progress, graduated, graduated_at, ret_max, obs, summarized_at)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows_[i:i + WRITE_CHUNK])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        done += len(batch)
        if limit is not None and done >= limit:
            return done


# ---------------------------------------------------------------- shared statistics
SUCCESS_BUYERS = 50          # "drew real buying": 50+ unique buyers in some hour of its first day
MIN_COINS = 30               # fewer coins than this in a window: no conclusion about that category
WORKING_MIN_CREATORS = 3     # a category "works" only with successes from 3+ different creators
_rng = None


def _np():
    import numpy as np
    return np


def _draws(k: float, n: float, p0: float, m: float, size: int = 4000):
    """Posterior draws of a rate: k successes in n coins, shrunk toward the market rate p0 with
    prior strength m (a Beta(p0*m, (1-p0)*m) prior)."""
    global _rng
    np = _np()
    if _rng is None:
        _rng = np.random.default_rng(17)
    return _rng.beta(k + p0 * m + 1e-9, max(n - k, 0) + (1 - p0) * m + 1e-9, size)


def _ratio_summary(k: int, n: int, p0: float, m: float) -> dict:
    """Rate against the market as a ratio, with an 80% range; and the same with the single best
    coin left out (k-1 of n-1), the figure categories are ranked by."""
    np = _np()
    if n == 0 or p0 <= 0:
        return {"ratio": None, "low": None, "high": None, "ratio_ex_best": None, "low_ex_best": None}
    if n < MIN_COINS:     # too few to judge (shown as such): a plain estimate, no ranges
        return {"ratio": round(k / n / p0, 3), "low": None, "high": None,
                "ratio_ex_best": round(max(k - 1, 0) / max(n - 1, 1) / p0, 3), "low_ex_best": None}
    d = _draws(k, n, p0, m) / p0
    dx = _draws(max(k - 1, 0), max(n - 1, 0), p0, m) / p0
    return {"ratio": round(float(np.median(d)), 3), "low": round(float(np.percentile(d, 10)), 3),
            "high": round(float(np.percentile(d, 90)), 3), "ratio_ex_best": round(float(np.median(dx)), 3),
            "low_ex_best": round(float(np.percentile(dx, 10)), 3)}


def _prob_higher(k1, n1, p1, k0, n0, p0, m) -> float | None:
    """P(the first period's rate, relative to its market, beats the second period's)."""
    np = _np()
    if min(n1, n0) < 10 or p1 <= 0 or p0 <= 0:
        return None
    return float(np.mean(_draws(k1, n1, p1, m) / p1 > _draws(k0, n0, p0, m) / p0))


def coverage(con, start: int, end: int) -> float:
    """Share of hours in [start, end) in which the app saw any launch (collection was running)."""
    hrs = {r[0] for r in con.execute("SELECT DISTINCT created_at / 3600 FROM tokens WHERE created_at >= ? AND created_at < ?",
                                     (start, end))}
    total = max(1, (end - start) // H)
    return round(len(hrs) / total, 3)


# ---------------------------------------------------------------- macro: what has been working
def _coins(con, start: int, end: int) -> list[dict]:
    """Matured, non-factory coins launched in [start, end), with their 24-hour summary."""
    cur = con.execute("""SELECT s.mint, s.created_at, s.creator, s.narrative_id, s.label, s.category, s.peak_buyers_h1,
                                s.peak_holders, s.holders_end, s.peak_mcap_usd, s.peak_liq_usd, s.peak_net_sol_h1,
                                s.max_progress, s.graduated, s.graduated_at, s.ret_max, k.name, k.symbol
                         FROM token_summary s JOIN tokens k ON k.mint = s.mint
                         WHERE s.created_at >= ? AND s.created_at < ? AND NOT s.factory""", (start, end))
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


INSTANT_S = 60   # a graduation inside a minute of launch is a buyout by the creator's own wallets, not success


def _success(c: dict) -> bool:
    return bool(c["graduated"]) and (c["graduated_at"] or 0) - c["created_at"] >= INSTANT_S


def _traction(c: dict) -> bool:
    return (c["peak_buyers_h1"] or 0) >= SUCCESS_BUYERS


def _med(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def _group_stats(cs: list[dict], p0: float, p0t: float, m: float) -> dict:
    n = len(cs)
    wins = [c for c in cs if _success(c)]
    pulls = [c for c in cs if _traction(c)]
    win_creators = {c["creator"] for c in wins if c["creator"]}
    buyers = [c["peak_buyers_h1"] or 0 for c in cs]
    tot_b = sum(buyers)
    best = max(cs, key=lambda c: (_success(c), c["peak_buyers_h1"] or 0), default=None)
    retention = [c["holders_end"] / c["peak_holders"] for c in cs if c["peak_holders"] and c["holders_end"] is not None]
    return {
        "coins": n, "graduated": len(wins), "drew_buyers": len(pulls),
        "creators": len({c["creator"] for c in cs if c["creator"]}),
        "independent_successes": len(win_creators),
        "grad": _ratio_summary(len(wins), n, p0, m),
        "traction": _ratio_summary(len(pulls), n, p0t, m),
        "top_coin_buyer_share": round(max(buyers) / tot_b, 3) if tot_b else None,
        "median_peak_buyers_successes": _med([c["peak_buyers_h1"] for c in wins + pulls]),
        "median_peak_mcap_successes": _med([c["peak_mcap_usd"] for c in wins]),
        "median_peak_liq_successes": _med([c["peak_liq_usd"] for c in wins]),
        "median_holder_retention": round(_med(retention), 3) if retention else None,
        "holder_data_coins": len(retention),
        "best_coin": {"mint": best["mint"], "name": best["name"], "symbol": best["symbol"],
                      "graduated": _success(best), "peak_buyers_h1": best["peak_buyers_h1"],
                      "peak_mcap_usd": best["peak_mcap_usd"]} if best and (best["graduated"] or best["peak_buyers_h1"]) else None,
    }


def _status(st: dict) -> str:
    if st["coins"] < MIN_COINS:
        return "insufficient"
    g = st["grad"]
    if g["low_ex_best"] is not None and g["low_ex_best"] >= 1.0 and st["independent_successes"] >= WORKING_MIN_CREATORS:
        return "working"
    if st["graduated"] >= 1 and st["independent_successes"] <= 1 and (g["ratio_ex_best"] or 0) < 1.0:
        return "one coin"
    if g["high"] is not None and g["high"] < 1.0:
        return "lagging"
    return "average"


def macro_read(con, as_of: int | None = None, windows=(7, 14, 30)) -> dict:
    """Per category and per narrative: how its coins did over the past 7 / 14 / 30 days, against
    every coin launched in the same days, with breadth, trend, crowding and newer-vs-older launches."""
    np = _np()
    from .quant import fit_beta_strength
    as_of = as_of or _now()
    end = as_of - D                      # only coins whose first 24 hours have passed
    out = {"as_of": as_of, "matured_until": end, "windows": {}, "notes": []}
    span = max(max(windows), 14)                 # the trend needs the week before this one
    pool = sorted(_coins(con, end - span * D, end), key=lambda c: c["created_at"])   # fetched once, sliced below
    times = [c["created_at"] for c in pool]

    def coins(a, b):
        from bisect import bisect_left
        return pool[bisect_left(times, a):bisect_left(times, b)]
    for w in windows:
        start = end - w * D
        cov = coverage(con, start, end)
        cs = coins(start, end)
        if not cs or cov < 0.5:
            out["windows"][str(w)] = {"days": w, "coverage": cov, "coins": len(cs), "available": False}
            continue
        n0 = len(cs)
        p0 = max(sum(_success(c) for c in cs) / n0, 1e-4)
        p0t = max(sum(_traction(c) for c in cs) / n0, 1e-4)
        by_cat: dict[str, list] = {}
        for c in cs:
            by_cat.setdefault(c["category"] or "", []).append(c)
        cats = {k: v for k, v in by_cat.items() if k}
        # prior strength from how much categories really differ (method of moments), floored
        big = [(sum(_success(c) for c in v), len(v)) for v in cats.values() if len(v) >= MIN_COINS]
        m = fit_beta_strength(np.array([b[0] for b in big], float), np.array([b[1] for b in big], float),
                              np.full(len(big), p0)) if len(big) >= 5 else 200.0
        m = float(min(max(m, 50.0), 2000.0))
        rows_ = []
        for cat, v in cats.items():
            st = _group_stats(v, p0, p0t, m)
            st["category"] = cat
            st["status"] = _status(st)
            st["share_of_launches"] = round(len(v) / n0, 4)
            rows_.append(st)
        out["windows"][str(w)] = {"days": w, "coverage": cov, "available": True, "coins": n0,
                                  "categorised_share": round(sum(len(v) for v in cats.values()) / n0, 3),
                                  "market": {"graduation_rate": round(p0, 5), "drew_buyers_rate": round(p0t, 5)},
                                  "prior_strength": round(m, 1),
                                  "categories": sorted(rows_, key=lambda r: -(r["grad"]["low_ex_best"] or 0))}
    w7 = out["windows"].get("7")
    if w7 and w7.get("available"):
        _trends(coins, out, end)
        _narratives(coins, out, end)
    else:
        out["notes"].append("Less than a week of collection: the weekly view needs 7 days of matured coins.")
    return out


def _trends(coins, out: dict, end: int) -> None:
    """For each category in the 7-day view: this week vs the week before, newer launches vs older
    ones in this week, launches per day (crowding), and how steadily it produced successes."""
    w7 = out["windows"]["7"]
    m = w7["prior_strength"]
    this = coins(end - 7 * D, end)
    prev = coins(end - 14 * D, end - 7 * D)
    early = [c for c in this if c["created_at"] < end - 3 * D]
    late = [c for c in this if c["created_at"] >= end - 3 * D]

    def rate(cs):
        return max(sum(_success(c) for c in cs) / len(cs), 1e-4) if cs else None
    P = {"this": rate(this), "prev": rate(prev), "early": rate(early), "late": rate(late)}
    groups = {}
    for name, cs in (("this", this), ("prev", prev), ("early", early), ("late", late)):
        g: dict[str, list] = {}
        for c in cs:
            if c["category"]:
                g.setdefault(c["category"], []).append(c)
        groups[name] = g
    n_late = sum(len(v) for v in groups["late"].values())
    n_early = sum(len(v) for v in groups["early"].values())
    mgrow = (n_late / 3) / (n_early / 4) if n_early and n_late else 1.0
    for row in w7["categories"]:
        cat = row["category"]
        t, p, e, l = (groups[k].get(cat, []) for k in ("this", "prev", "early", "late"))
        k_ = lambda cs: sum(_success(c) for c in cs)  # noqa: E731
        row["vs_last_week"] = (_prob_higher(k_(t), len(t), P["this"], k_(p), len(p), P["prev"], m)
                               if P["prev"] and len(p) >= MIN_COINS and len(t) >= MIN_COINS else None)
        row["newer_vs_older"] = (_prob_higher(k_(l), len(l), P["late"], k_(e), len(e), P["early"], m)
                                 if P["late"] and P["early"] and len(l) >= 15 and len(e) >= 15 else None)
        row["launches_last_3d_per_day"] = round(len(l) / 3, 1)
        row["launches_prior_4d_per_day"] = round(len(e) / 4, 1)
        row["launches_prev_week"] = len(p)
        days = {(c["created_at"] - (end - 7 * D)) // D for c in t if _success(c)}
        row["days_with_success"] = len(days)
        vs = row["vs_last_week"]
        row["trend"] = ("new" if len(p) < MIN_COINS else "gaining" if vs is not None and vs >= 0.9
                        else "losing" if vs is not None and vs <= 0.1 else "steady")
        nv = row["newer_vs_older"]
        # its launch growth against the growth of all categorised launches, so a busier market (or
        # more coins finding a category) does not make every category look crowded
        grow = (row["launches_last_3d_per_day"] / max(row["launches_prior_4d_per_day"], 0.5)) / mgrow
        row["crowding"] = ("saturating" if grow >= 1.3 and nv is not None and nv <= 0.2 else
                           "filling up" if grow >= 1.3 else "thinning" if grow <= 0.7 else "stable")


def _narratives(coins, out: dict, end: int) -> None:
    """The narratives inside each category that produced its successes this week."""
    w7 = out["windows"]["7"]
    p0 = w7["market"]["graduation_rate"]
    cs = coins(end - 7 * D, end)
    by: dict[tuple, list] = {}
    for c in cs:
        if c["category"] and c["narrative_id"] is not None:
            by.setdefault((c["category"], c["narrative_id"]), []).append(c)
    per_cat: dict[str, list] = {}
    for (cat, nid), v in by.items():
        wins = [c for c in v if _success(c)]
        pulls = [c for c in v if _traction(c)]
        if not wins and not pulls:
            continue
        lab = next((c["label"] for c in v if c["label"]), str(nid))
        per_cat.setdefault(cat, []).append({
            "narrative_id": nid, "label": lab, "coins": len(v), "graduated": len(wins), "drew_buyers": len(pulls),
            "independent_successes": len({c["creator"] for c in wins if c["creator"]}),
            "graduation_ratio": round(len(wins) / len(v) / p0, 2) if p0 else None,
            "coins_succeeding": [{"mint": c["mint"], "name": c["name"], "symbol": c["symbol"], "graduated": _success(c),
                                  "peak_buyers_h1": c["peak_buyers_h1"], "peak_mcap_usd": c["peak_mcap_usd"]}
                                 for c in sorted(wins + [x for x in pulls if x not in wins],
                                                 key=lambda c: (-_success(c), -(c["peak_buyers_h1"] or 0)))[:6]]})
    for row in w7["categories"]:
        row["narratives"] = sorted(per_cat.get(row["category"], []),
                                   key=lambda r: (-r["independent_successes"], -r["graduated"], -r["drew_buyers"]))[:8]


# ---------------------------------------------------------------- intraday: what is working today
def _poisson_sf(k: int, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam): how surprising k events are against a usual rate."""
    import math
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    term, cdf = math.exp(-lam), 0.0
    for i in range(k):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - cdf)


def _latest_read(con, as_of: int) -> int | None:
    r = con.execute("SELECT MAX(observed_at) FROM narrative_obs WHERE observed_at <= ? AND observed_at > ?",
                    (as_of, as_of - 2 * H)).fetchone()
    return r[0] if r and r[0] else None


def _category_buyers(con, start: int, end: int, col: str = "buyers_h1") -> dict[str, list[tuple[int, float]]]:
    """Per category, per narrative read: the summed buyers (or `col`) in the last hour of its narratives."""
    assert col in ("buyers_h1", "net_sol_h1")
    out: dict[str, dict[int, float]] = {}
    for t, cat, b in con.execute(f"""SELECT o.observed_at, n.category, SUM(COALESCE(o.{col}, 0))
                                    FROM narrative_obs o JOIN narratives n ON n.id = o.narrative_id
                                    WHERE o.observed_at > ? AND o.observed_at <= ? AND n.category IS NOT NULL
                                    GROUP BY o.observed_at, n.category""", (start, end)):
        out.setdefault(cat, {})[t] = b
    return {k: sorted(v.items()) for k, v in out.items()}


def _same_hours(t: int, as_of: int, width: int = 2 * H) -> bool:
    """t falls within `width` of as_of's time of day: trading has a daily rhythm, so "usual" for a
    category at 2 a.m. is its other nights, not its daily average."""
    return abs((t - as_of + D // 2) % D - D // 2) <= width


def intraday_read(con, as_of: int | None = None, live_narratives: dict | None = None) -> dict:
    """Each category and narrative now, against its own last 7 days: buyers, new launches,
    graduations, how widely buying is spread, standout coins, and narratives too new for a record."""
    import json
    as_of = as_of or _now()
    t_read = _latest_read(con, as_of)
    out = {"as_of": as_of, "read_at": t_read, "categories": [], "narratives": [], "standouts": [], "notes": []}
    if t_read is None:
        out["notes"].append("No narrative read in the last two hours: intraday needs the narrative grouping running.")
        return out
    base_start, base_end = as_of - 7 * D, as_of - D
    reads = {r[0] for r in con.execute("SELECT DISTINCT observed_at FROM narrative_obs WHERE observed_at > ? AND observed_at <= ?",
                                        (base_start, base_end))}
    base_hours = len({t // H for t in reads})
    same = sorted(t for t in reads if _same_hours(t, as_of))
    cb = _category_buyers(con, base_start, as_of)
    # current narratives
    nar = con.execute("""SELECT o.narrative_id, n.label, n.category, n.first_seen, o.launches_6h, o.creators_6h, o.buyers_h1,
                                o.net_sol_h1, o.state, o.members
                         FROM narrative_obs o JOIN narratives n ON n.id = o.narrative_id
                         WHERE o.observed_at = ?""", (t_read,)).fetchall()
    titles = {}
    for x in (live_narratives or {}).get("narratives") or []:
        if x.get("id"):
            titles[x["id"]] = x
    members = {r[0]: json.loads(r[9] or "[]") for r in nar}
    allm = sorted({m for v in members.values() for m in v})
    latest: dict[str, dict] = {}
    for i in range(0, len(allm), 900):
        chunk = allm[i:i + 900]
        q = ",".join("?" * len(chunk))
        for mint, b, name, sym in con.execute(
                f"""SELECT o.mint, o.buyers_h1, k.name, k.symbol FROM token_obs o JOIN tokens k ON k.mint = o.mint
                    WHERE o.id IN (SELECT MAX(id) FROM token_obs WHERE mint IN ({q}) AND observed_at <= ? AND observed_at > ?
                                   GROUP BY mint)""", (*chunk, as_of, as_of - 2 * H)):
            latest[mint] = {"mint": mint, "buyers_h1": b or 0, "name": name, "symbol": sym}
    # graduations of categorised coins, today and in the baseline week
    grads: dict[str, list[int]] = {}
    for cat, at in con.execute(f"""SELECT tn.category, COALESCE(g.graduated_at, g.detected_at) FROM graduations g
                                  JOIN token_narrative tn ON tn.mint = g.mint JOIN tokens k ON k.mint = g.mint
                                  WHERE COALESCE(g.graduated_at, g.detected_at) > ? AND COALESCE(g.graduated_at, g.detected_at) <= ?
                                  AND tn.category IS NOT NULL
                                  AND COALESCE(g.graduated_at, g.detected_at) - k.created_at >= {INSTANT_S}""", (base_start, as_of)):
        grads.setdefault(cat, []).append(at)
    launches: dict[str, list[int]] = {}
    for cat, at in con.execute("""SELECT tn.category, k.created_at FROM token_narrative tn JOIN tokens k ON k.mint = tn.mint
                                  WHERE k.created_at > ? AND k.created_at <= ? AND tn.category IS NOT NULL""", (base_start, as_of)):
        launches.setdefault(cat, []).append(at)
    by_cat: dict[str, list] = {}
    for nid, label, cat, first_seen, l6, c6, b1, net, state, _ in nar:
        coins = sorted((latest[m] for m in members[nid] if m in latest), key=lambda c: -c["buyers_h1"])
        active = [c for c in coins if c["buyers_h1"] >= 20]
        med = _med([c["buyers_h1"] for c in coins if c["buyers_h1"] > 0]) or 0
        live = titles.get(nid) or {}
        row = {"narrative_id": nid, "label": label, "title": live.get("title") or label, "category": cat,
               "first_seen": first_seen, "age_h": round((as_of - first_seen) / H, 1), "launches_6h": l6, "creators_6h": c6,
               "buyers_h1": b1, "net_sol_h1": net, "state": state, "coins_with_buyers": len(active),
               "top_coin_share": round(coins[0]["buyers_h1"] / max(1, sum(c["buyers_h1"] for c in coins)), 2) if coins and coins[0]["buyers_h1"] else None,
               "coins": coins[:6]}
        for c in coins[:3]:
            if c["buyers_h1"] >= max(20, 3 * med) and len(coins) >= 3:
                out["standouts"].append({**c, "narrative_id": nid, "narrative": row["title"], "category": cat,
                                         "times_narrative_median": round(c["buyers_h1"] / max(med, 1), 1)})
        out["narratives"].append(row)
        if cat:
            by_cat.setdefault(cat, []).append(row)
    for cat, rows_ in by_cat.items():
        own = dict(cb.get(cat, []))
        hist = [own.get(t, 0) for t in same]       # a read where it had no narrative counts as zero buyers
        now_b = sum(r["buyers_h1"] or 0 for r in rows_)
        base_b = (sum(hist) / len(hist)) if hist else None
        g = grads.get(cat, [])
        g24 = sum(1 for t in g if t > as_of - D)
        g_base_daily = sum(1 for t in g if t <= base_end) / 6 if base_hours >= 72 else None
        l6 = sum(1 for t in launches.get(cat, []) if t > as_of - 6 * H)
        l_base_6h = (sum(1 for t in launches.get(cat, []) if t <= base_end and as_of - t < 7 * D
                         and (as_of - t) % D <= 6 * H) / 6) if base_hours >= 72 else None   # the same 6 hours of the day
        coins = sorted((c for r in rows_ for c in r["coins"]), key=lambda c: -c["buyers_h1"])
        tot = sum(c["buyers_h1"] for c in coins)
        demand = (now_b / base_b) if base_b else None
        status = ("new" if not base_b or base_hours < 72 else
                  "heating" if demand >= 1.5 else "cooling" if demand <= 0.6 else "normal")
        out["categories"].append({
            "category": cat, "status": status, "buyers_now": now_b, "buyers_usual": round(base_b, 1) if base_b else None,
            "demand_vs_usual": round(demand, 2) if demand else None,
            "graduations_24h": g24, "graduations_usual_per_day": round(g_base_daily, 2) if g_base_daily is not None else None,
            "graduation_surprise": round(_poisson_sf(g24, g_base_daily), 4) if g_base_daily is not None else None,
            "launches_6h": l6, "launches_usual_6h": round(l_base_6h, 1) if l_base_6h is not None else None,
            "narratives_live": len(rows_), "coins_with_buyers": sum(r["coins_with_buyers"] for r in rows_),
            "top_coin_share": round(coins[0]["buyers_h1"] / tot, 2) if tot else None,
            "new_narratives": [r["title"] for r in rows_ if r["age_h"] <= 24 and (r["buyers_h1"] or 0) >= 20][:5],
            "crowding_narratives": [r["title"] for r in rows_ if r["state"] in ("saturating", "fading")][:5],
        })
    out["categories"].sort(key=lambda r: -(r["buyers_now"] or 0))
    out["narratives"].sort(key=lambda r: -(r["buyers_h1"] or 0))
    out["standouts"].sort(key=lambda r: -r["buyers_h1"])
    out["standouts"] = out["standouts"][:12]
    out["narratives"] = out["narratives"][:60]
    out["baseline_hours"] = base_hours
    if base_hours < 72:
        out["notes"].append(f"Only {base_hours} hours of narrative history before today: comparisons with a usual day need 3+ days.")
    return out


# ---------------------------------------------------------------- rotation: what could work tomorrow
HEAT = 1.5            # buyers at 1.5x the category's usual level
BROAD_COINS = 3       # buying spread over 3+ coins with 20+ buyers in the last hour
ONE_COIN = 0.6        # one coin with 60%+ of a category's buying is a coin, not a meta
FACTORY_24H = 10      # a creator with 10+ launches in a day is a factory; its coins are left out


def _early_cohort(con, as_of: int) -> dict:
    """Per category: coins launched in the last 24 hours that already graduated (not instantly),
    against what its own last week and today's market say to expect. The last day's coins have had
    less time than a full day; comparing each category with the market on the same coins cancels that."""
    rows = con.execute(f"""SELECT tn.category, k.created_at, k.creator,
                                  CASE WHEN COALESCE(g.graduated_at, g.detected_at) <= ?
                                        AND COALESCE(g.graduated_at, g.detected_at) - k.created_at BETWEEN {INSTANT_S} AND {D}
                                       THEN 1 ELSE 0 END
                           FROM tokens k LEFT JOIN token_narrative tn ON tn.mint = k.mint
                           LEFT JOIN graduations g ON g.mint = k.mint
                           WHERE k.created_at > ? AND k.created_at <= ?""", (as_of, as_of - 7 * D, as_of)).fetchall()
    per_day: dict[tuple, int] = {}
    for _, t, cr, _ in rows:
        if cr:
            per_day[(cr, t // D)] = per_day.get((cr, t // D), 0) + 1
    rec, base = {"k": 0, "n": 0}, {"k": 0, "n": 0}
    cats: dict[str, dict] = {}
    for cat, t, cr, ok in rows:
        if cr and per_day[(cr, t // D)] >= FACTORY_24H:
            continue
        recent = t > as_of - D
        if not recent and t > as_of - 2 * D:     # the day before: not yet a full day old, in neither group
            continue
        g = rec if recent else base
        g["k"] += ok
        g["n"] += 1
        if cat:
            c = cats.setdefault(cat, {"k": 0, "n": 0, "bk": 0, "bn": 0, "creators": set()})
            if recent:
                c["k"] += ok
                c["n"] += 1
                if ok and cr:
                    c["creators"].add(cr)
            else:
                c["bk"] += ok
                c["bn"] += 1
    p_rec = rec["k"] / rec["n"] if rec["n"] else None
    p_base = base["k"] / base["n"] if base["n"] else None
    out = {}
    for cat, c in cats.items():
        # the category's usual rate against the market, shrunk toward 1 when it has few coins
        ratio = ((c["bk"] + 2 * (p_base or 0)) / (c["bn"] + 2) / p_base) if p_base else 1.0
        expected = c["n"] * (p_rec or 0) * ratio
        out[cat] = {"launched_24h": c["n"], "graduated_24h": c["k"], "creators": len(c["creators"]),
                    "expected": round(expected, 2), "usual_vs_market": round(ratio, 2),
                    "surprise": round(_poisson_sf(c["k"], expected), 4) if expected > 0 else None}
    return out


def _holder_growth(con, as_of: int) -> dict:
    """Per category, live installs only: holders gained in the last hour by coins with holder counts."""
    out: dict[str, dict] = {}
    for cat, mint, first, last in con.execute(
            """SELECT tn.category, o.mint,
                      (SELECT holders FROM token_obs a WHERE a.mint = o.mint AND a.observed_at >= ? AND a.holders IS NOT NULL
                       ORDER BY a.observed_at LIMIT 1),
                      (SELECT holders FROM token_obs b WHERE b.mint = o.mint AND b.observed_at <= ? AND b.holders IS NOT NULL
                       ORDER BY b.observed_at DESC LIMIT 1)
               FROM (SELECT DISTINCT mint FROM token_obs WHERE observed_at > ? AND observed_at <= ? AND holders IS NOT NULL) o
               JOIN token_narrative tn ON tn.mint = o.mint WHERE tn.category IS NOT NULL""",
            (as_of - H, as_of, as_of - H, as_of)):
        if first is None or last is None:
            continue
        g = out.setdefault(cat, {"coins": 0, "growing": 0, "holders_gained": 0})
        g["coins"] += 1
        g["growing"] += last > first
        g["holders_gained"] += last - first
    return out


def rotation(con, as_of: int, macro: dict, intraday: dict) -> dict:
    """Where buying is moving, and a watchlist of categories that might work next. Every signal is
    point-in-time; how each one did historically is measured in scripts/macro_check.py."""
    out = {"as_of": as_of, "categories": [], "gaining": [], "losing": [], "watchlist": [], "weakening": [],
           "crowding": [], "single_coin": [], "notes": []}
    I = {r["category"]: r for r in intraday.get("categories", [])}
    t_read = intraday.get("read_at")
    if t_read is None or intraday.get("baseline_hours", 0) < 72:
        out["notes"].append("Rotation needs a current narrative read and 3+ days of history before today.")
        return out
    w7 = (macro.get("windows") or {}).get("7") or {}
    M = {r["category"]: r for r in w7.get("categories", [])} if w7.get("available") else {}
    base_end = as_of - D
    cb = _category_buyers(con, as_of - 7 * D, as_of)
    cs = _category_buyers(con, as_of - 7 * D, as_of, "net_sol_h1")
    tot: dict[int, float] = {}
    for v in cb.values():
        for t, b in v:
            tot[t] = tot.get(t, 0) + b
    same = sorted(t for t in tot if t <= base_end and _same_hours(t, as_of))
    early = _early_cohort(con, as_of)
    holders = _holder_growth(con, as_of)
    for cat, i in I.items():
        own = dict(cb.get(cat, []))
        shares = [own.get(t, 0) / tot[t] for t in same if tot.get(t)]
        sh_usual = sum(shares) / len(shares) if shares else None
        sh_now = (i["buyers_now"] / tot[t_read]) if tot.get(t_read) else None
        own_sol = dict(cs.get(cat, []))
        sol_hist = [own_sol.get(t, 0) for t in same if tot.get(t)]
        sol_now = next((x for t, x in cs.get(cat, []) if t == t_read), None)
        sol_usual = sum(sol_hist) / len(sol_hist) if sol_hist else None
        e = early.get(cat) or {}
        m = M.get(cat)
        demand = i["demand_vs_usual"]
        sig = {
            "buyers_up": demand is not None and demand >= HEAT,
            "sol_up": sol_now is not None and sol_usual is not None and sol_now > 0 and sol_now >= HEAT * max(sol_usual, 0.5),
            "share_up": sh_now is not None and sh_usual is not None and sh_now >= 1.25 * sh_usual and sh_now - sh_usual >= 0.01,
            "share_down": sh_now is not None and sh_usual is not None and sh_now <= 0.75 * sh_usual and sh_usual - sh_now >= 0.01,
            "early_successes": e.get("graduated_24h", 0) >= 2 and e.get("creators", 0) >= 2 and (e.get("surprise") or 1) < 0.1,
            "broad": i["coins_with_buyers"] >= BROAD_COINS and (i["top_coin_share"] or 1) < ONE_COIN,
            "single_coin": (i["top_coin_share"] or 0) >= ONE_COIN and (i["buyers_now"] or 0) >= 50,
            "crowding": (i["launches_usual_6h"] or 0) >= 3 and demand is not None and i["launches_6h"] >= HEAT * i["launches_usual_6h"]
                        and demand * i["launches_usual_6h"] / max(i["launches_6h"], 1) < 1.0,
            "holders_up": None,
        }
        h = holders.get(cat)
        if h and h["coins"] >= 3:
            sig["holders_up"] = h["growing"] >= 0.6 * h["coins"]
        row = {"category": cat, "signals": sig, "buyers_now": i["buyers_now"], "buyers_usual": i["buyers_usual"],
               "demand_vs_usual": demand, "share_now": round(sh_now, 3) if sh_now is not None else None,
               "share_usual": round(sh_usual, 3) if sh_usual is not None else None,
               "sol_now": round(sol_now, 1) if sol_now is not None else None,
               "sol_usual": round(sol_usual, 1) if sol_usual is not None else None,
               "early": e or None, "holders": h, "coins_with_buyers": i["coins_with_buyers"],
               "top_coin_share": i["top_coin_share"], "launches_6h": i["launches_6h"], "launches_usual_6h": i["launches_usual_6h"],
               "week_status": m["status"] if m else "insufficient", "week_trend": m.get("trend") if m else None}
        row["watch"] = sig["buyers_up"] and sig["share_up"] and sig["broad"] and not sig["crowding"]
        if row["watch"]:
            row["stage"] = ("confirmed" if row["week_status"] == "working" else
                            "emerging" if row["week_trend"] == "gaining" or sig["early_successes"] else "speculative")
        out["categories"].append(row)
    rows = out["categories"]
    shifted = [r for r in rows if r["share_now"] is not None and r["share_usual"] is not None]
    shifted.sort(key=lambda r: r["share_now"] - r["share_usual"])
    out["gaining"] = [_share_item(r) for r in reversed(shifted) if r["signals"]["share_up"]][:6]
    out["losing"] = [_share_item(r) for r in shifted if r["signals"]["share_down"]][:6]
    order = {"confirmed": 0, "emerging": 1, "speculative": 2}
    for r in sorted((r for r in rows if r["watch"]), key=lambda r: (order[r["stage"]], -(r["demand_vs_usual"] or 0))):
        out["watchlist"].append(_watch_item(r))
    for r in rows:
        s = r["signals"]
        if s["single_coin"] and s["buyers_up"]:
            out["single_coin"].append({"category": r["category"], "top_coin_share": r["top_coin_share"],
                                       "text": f"{r['category']}: buyers are up, but one coin has {_pct(r['top_coin_share'])} of them. "
                                               "That is a coin working, not the category."})
        if s["crowding"]:
            out["crowding"].append({"category": r["category"],
                                    "text": f"{r['category']}: {r['launches_6h']} launches in 6 hours (usual {r['launches_usual_6h']:.0f}), "
                                            f"buyers at {_x(r['demand_vs_usual'])} usual. Launches are rising faster than buyers, so each new coin gets fewer."})
        if (s["share_down"] and (r["demand_vs_usual"] or 1) <= 0.8) or (r["week_trend"] == "losing" and (r["demand_vs_usual"] or 1) <= 0.8):
            out["weakening"].append({"category": r["category"],
                                     "text": f"{r['category']}: buyers at {_x(r['demand_vs_usual'])} usual"
                                             + (f", share of all buying {_pct(r['share_now'])} from {_pct(r['share_usual'])}" if s["share_down"] else "")
                                             + ("; its weekly rate is also falling." if r["week_trend"] == "losing" else ".")})
    return out


def _share_item(r: dict) -> dict:
    return {"category": r["category"], "share_now": r["share_now"], "share_usual": r["share_usual"],
            "text": f"{r['category']}: {_pct(r['share_now'])} of all category buying now, against {_pct(r['share_usual'])} on a usual day."}


def _watch_item(r: dict) -> dict:
    s, e, cat = r["signals"], r["early"] or {}, r["category"]
    ev = [f"Buyers {_x(r['demand_vs_usual'])} its usual level ({r['buyers_now']:,} in the last hour against about {r['buyers_usual']:,.0f}).",
          f"Its share of all category buying rose to {_pct(r['share_now'])} from {_pct(r['share_usual'])}.",
          f"Spread: {r['coins_with_buyers']} coins with 20+ buyers; the top one has {_pct(r['top_coin_share'])}."]
    if s["sol_up"]:
        ev.append(f"Net SOL into its coins in the last hour: {r['sol_now']:+.1f} against about {r['sol_usual']:+.1f} usual.")
    if e.get("graduated_24h"):
        ev.append(f"Of {e['launched_24h']} coins launched in the last day, {e['graduated_24h']} graduated "
                  f"(about {e['expected']:.1f} expected from its usual rate and today's market).")
    if r["stage"] == "confirmed":
        ev.append("Its week already shows it working across several creators.")
    elif r["week_trend"] == "gaining":
        ev.append("Its weekly rate is improving against last week.")
    risks = []
    if r["stage"] == "speculative":
        risks.append("No record behind it: its week " + ("is too thin to judge." if r["week_status"] == "insufficient"
                                                          else f"reads “{r['week_status']}”, not working."))
    if (r["top_coin_share"] or 0) >= 0.4:
        risks.append(f"Buying is still fairly concentrated: one coin has {_pct(r['top_coin_share'])}.")
    if r["launches_usual_6h"] and r["launches_6h"] >= 1.2 * r["launches_usual_6h"]:
        risks.append(f"Launches are rising too ({r['launches_6h']} in 6 hours, usual {r['launches_usual_6h']:.0f}): copycats arrive fast.")
    if not s["sol_up"]:
        risks.append("Money in has not risen with the buyers.")
    if e.get("launched_24h") and not e.get("graduated_24h"):
        risks.append("None of its coins launched in the last day has graduated yet.")
    if s["holders_up"] is False:
        risks.append("Most of its live coins are not adding holders.")
    usual_g = max(1, round(e.get("expected") or 0))
    confirm = [f"Buyers stay at {HEAT}× usual or more through the next reads, spread over {BROAD_COINS}+ coins.",
               f"{usual_g + 1}+ more graduations (not instant) from different creators among its new coins in the next 24 hours."]
    invalidate = ["Buyers fall back below its usual level.",
                  f"One coin takes {ONE_COIN:.0%}+ of its buying: then it is that coin, not the category.",
                  "Launches jump while buyers per launch fall (crowding)."]
    from .narratives import CATEGORY_SEEDS
    return {"category": cat, "stage": r["stage"], "emergent": cat not in CATEGORY_SEEDS, "evidence": ev, "risks": risks, "confirm": confirm, "invalidate": invalidate,
            "signals": {k: v for k, v in s.items() if v}, "demand_vs_usual": r["demand_vs_usual"],
            "share_now": r["share_now"], "share_usual": r["share_usual"], "week_status": r["week_status"]}


# ---------------------------------------------------------------- decay: is a meta losing its edge?
# Each check compares a category with its own baseline *and* with the market over the same hours
# (rates against all coins, shares of all buying), so a market-wide sell-off moves the baseline
# with it instead of reading as narrative-specific decay. Fast signals (demand, crowding,
# concentration) can warn early; outcome signals (results, breadth, follow-through) need coins
# whose first day is over, so they confirm a day or more later. A warning needs two independent
# families; "confirmed" needs an outcome family and two days in a row.
DECAY_BASE_D, DECAY_RECENT_D = 11, 3        # baseline = the 11 days before the last 3
DECAY_PRIOR = 20                            # prior strength for recent-vs-baseline rate comparisons
FAST = ("demand", "crowding", "concentration")
SLOW = ("results", "breadth", "follow_through")
DECAY_LABEL = {"healthy": "Healthy", "cooldown": "Cooling off", "early": "Early weakening", "confirmed": "Decay confirmed",
               "recovering": "Recovering", "no edge": "No edge to lose", "thin": "Too little data"}
FAMILY_LABEL = {"demand": "buyers and money in", "crowding": "crowding", "concentration": "concentration",
                "results": "results", "breadth": "breadth of winners", "follow_through": "follow-through"}


def _decay_data(con, as_of: int, back: int) -> dict:
    """Everything the decay checks need for evaluations at as_of - k days, k < back, fetched once."""
    lo = as_of - (back + DECAY_BASE_D + DECAY_RECENT_D + 1) * D
    coins = con.execute("""SELECT created_at, creator, category, graduated, graduated_at, peak_buyers_h1, max_progress,
                                  peak_holders, holders_end FROM token_summary
                           WHERE created_at > ? AND created_at <= ? AND NOT factory AND category IS NOT NULL""",
                        (lo, as_of - D)).fetchall()
    market = {}
    for day, n, tr, gr, pn, ph in con.execute(
            f"""SELECT created_at / {D}, COUNT(*), SUM(COALESCE(peak_buyers_h1, 0) >= {SUCCESS_BUYERS}),
                       SUM(graduated AND graduated_at - created_at >= {INSTANT_S}), COUNT(max_progress), SUM(max_progress >= 0.5)
                FROM token_summary WHERE created_at > ? AND created_at <= ? AND NOT factory GROUP BY 1""", (lo, as_of - D)):
        market[day] = (n, tr or 0, gr or 0, pn or 0, ph or 0)
    launches: dict[str, list[int]] = {}
    for cat, t in con.execute("""SELECT tn.category, k.created_at FROM token_narrative tn JOIN tokens k ON k.mint = tn.mint
                                 WHERE k.created_at > ? AND k.created_at <= ? AND tn.category IS NOT NULL""", (lo, as_of)):
        launches.setdefault(cat, []).append(t)
    for v in launches.values():
        v.sort()
    by_cat: dict[str, list] = {}
    for c in coins:
        by_cat.setdefault(c[2], []).append(c)
    out = {"coins": coins, "by_cat": by_cat, "market": market, "launches": launches,
           "cat_launch": sorted(t for v in launches.values() for t in v),
           "buyers": _category_buyers(con, lo, as_of), "sol": _category_buyers(con, lo, as_of, "net_sol_h1")}
    for key in ("buyers", "sol"):      # per read: the total over categories, and each category's own value
        tot: dict[int, float] = {}
        for v in out[key].values():
            for t, b in v:
                tot[t] = tot.get(t, 0) + max(b, 0)
        out[key + "_tot"] = sorted(tot.items())
        out[key + "_own"] = {k: dict(v) for k, v in out[key].items()}
    return out


def _mkt(data, start, end):
    n = tr = gr = pn = ph = 0
    for day, v in data["market"].items():
        if start < day * D + D // 2 <= end:     # days are whole; a day belongs to the window holding its middle
            n, tr, gr, pn, ph = n + v[0], tr + v[1], gr + v[2], pn + v[3], ph + v[4]
    return n, tr, gr, pn, ph


def _cat_coins(data, cat, start, end):
    return [c for c in data["by_cat"].get(cat, []) if start < c[0] <= end]


def _shares(data, key, cat, start, end):
    """Mean share of all category buying (or of positive net SOL) per read in (start, end]."""
    own = data[key + "_own"].get(cat, {})
    win = [(t, s) for t, s in data[key + "_tot"] if start < t <= end]
    xs = [max(own.get(t, 0), 0) / s for t, s in win if s > 0]
    neg = [own[t] < 0 for t, _ in win if t in own]
    return (sum(xs) / len(xs) if xs else None), len(xs), (sum(neg) / len(neg) if neg else None)


def _decay_eval(data, cat: str, t: int) -> dict:
    """The six families of decay evidence for one category at time t, from data available at t."""
    e = t - D                                       # outcomes: coins whose first day ended by t
    rs, bs = e - DECAY_RECENT_D * D, e - (DECAY_RECENT_D + DECAY_BASE_D) * D
    R, B = _cat_coins(data, cat, rs, e), _cat_coins(data, cat, bs, rs)
    mR, mB = _mkt(data, rs, e), _mkt(data, bs, rs)
    trac = lambda cs: [c for c in cs if (c[5] or 0) >= SUCCESS_BUYERS]  # noqa: E731
    grad = lambda cs: [c for c in cs if c[3] and (c[4] or 0) - c[0] >= INSTANT_S]  # noqa: E731
    tR, tB, gR, gB = trac(R), trac(B), grad(R), grad(B)
    pR, pB = (mR[1] / mR[0] if mR[0] else 0), (mB[1] / mB[0] if mB[0] else 0)
    base_ratio = (len(tB) / len(B) / pB) if B and pB else None
    base_grad = (len(gB) / len(B) / (mB[2] / mB[0])) if B and mB[2] else None
    win_creators_B = {c[1] for c in tB + gB if c[1]}
    ev = {"window": {"recent_days": DECAY_RECENT_D, "baseline_days": DECAY_BASE_D, "recent_coins": len(R), "baseline_coins": len(B)},
          "base_ratio": round(base_ratio, 2) if base_ratio else None, "base_grad_ratio": round(base_grad, 2) if base_grad else None,
          "families": {}, "metrics": {}, "against": []}
    ev["eligible"] = bool(len(B) >= 60 and len(win_creators_B) >= 3 and ((base_ratio or 0) >= 1.2 or (base_grad or 0) >= 1.2))
    ev["enough"] = len(R) >= 30 and len(B) >= 60
    fam, met = ev["families"], ev["metrics"]
    # results: drew-buyers and graduation rates against the market, recent vs baseline
    # a weak prior: a strong one pulls the short recent window toward the market harder than the long
    # baseline, which reads as a decline when nothing changed
    pt = _prob_higher(len(tR), len(R), pR, len(tB), len(B), pB, DECAY_PRIOR) if pR and pB else None
    pg = (_prob_higher(len(gR), len(R), mR[2] / mR[0], len(gB), len(B), mB[2] / mB[0], DECAY_PRIOR)
          if mR[2] and mB[2] and len(gB) >= 5 else None)
    met["traction_ratio"] = [round(len(tR) / len(R) / pR, 2) if R and pR else None, ev["base_ratio"]]
    met["graduation_ratio"] = [round(len(gR) / len(R) / (mR[2] / mR[0]), 2) if R and mR[2] else None, ev["base_grad_ratio"]]
    met["p_recent_better"] = round(pt, 3) if pt is not None else None
    # graduations are rare: their drop counts only when drawing buyers is not holding up either
    fam["results"] = bool(ev["enough"] and ((pt is not None and pt <= 0.15) or (pg is not None and pg <= 0.15 and pt is not None and pt <= 0.5)))
    # breadth: independent winners per day, against the market's; coins reaching half the curve
    wR, wB = len({c[1] for c in tR if c[1]}) / DECAY_RECENT_D, len({c[1] for c in tB if c[1]}) / DECAY_BASE_D
    mw = (mR[1] / DECAY_RECENT_D) / (mB[1] / DECAY_BASE_D) if mB[1] and mR[1] else None
    rel_w = (wR / wB) / mw if wB and mw else None
    hR, hB = [c for c in R if c[6] is not None], [c for c in B if c[6] is not None]
    rel_h = None
    if len(hR) >= 30 and len(hB) >= 60 and mR[3] and mB[3] and mR[4] and mB[4]:
        a = sum(c[6] >= 0.5 for c in hR) / len(hR) / (mR[4] / mR[3])
        b = sum(c[6] >= 0.5 for c in hB) / len(hB) / (mB[4] / mB[3])
        rel_h = a / b if b else None
    met["winners_per_day"] = [round(wR, 2), round(wB, 2)]
    met["winners_vs_market_change"] = round(rel_w, 2) if rel_w is not None else None
    met["half_curve_vs_baseline"] = round(rel_h, 2) if rel_h is not None else None
    fam["breadth"] = bool(ev["enough"] and wB >= 1 and ((rel_w is not None and rel_w <= 0.6) or (rel_h is not None and rel_h <= 0.7)))
    # follow-through: of coins that drew buyers, how many went on (half the curve or graduated); holders kept (live only)
    def follow(cs):
        return sum(1 for c in cs if (c[6] or 0) >= 0.5 or c[3]) / len(cs) if cs else None
    fR, fB = follow(tR), follow(tB)
    ret = lambda cs: _med([c[8] / c[7] for c in cs if c[7] and c[8] is not None])  # noqa: E731
    kR, kB = ret(R), ret(B)
    met["follow_through"] = [round(fR, 2) if fR is not None else None, round(fB, 2) if fB is not None else None]
    met["holder_retention"] = [round(kR, 2) if kR is not None else None, round(kB, 2) if kB is not None else None]
    fam["follow_through"] = bool((len(tR) >= 5 and len(tB) >= 10 and fB and fR is not None and fR <= 0.6 * fB)
                                 or (kR is not None and kB and kR <= 0.8 * kB))
    # demand: share of all category buying and of money in, last day and last 3 days vs the baseline
    s24, _, neg24 = _shares(data, "buyers", cat, t - D, t)
    s3, _, _ = _shares(data, "buyers", cat, t - DECAY_RECENT_D * D, t)
    sb, nb, _ = _shares(data, "buyers", cat, t - (DECAY_RECENT_D + DECAY_BASE_D) * D, t - DECAY_RECENT_D * D)
    q3, _, neg3 = _shares(data, "sol", cat, t - DECAY_RECENT_D * D, t)
    qb, _, negb = _shares(data, "sol", cat, t - (DECAY_RECENT_D + DECAY_BASE_D) * D, t - DECAY_RECENT_D * D)
    met["buyer_share"] = {"day": _r3(s24), "3d": _r3(s3), "baseline": _r3(sb)}
    met["sol_share"] = {"3d": _r3(q3), "baseline": _r3(qb)}
    met["sell_pressure"] = {"3d": _r3(neg3), "baseline": _r3(negb)}
    ok_d = sb is not None and sb >= 0.01 and nb >= 48
    buyers_down = ok_d and s3 is not None and s24 is not None and s3 <= 0.75 * sb and s24 <= 0.8 * sb
    money_down = (ok_d and q3 is not None and qb and q3 <= 0.7 * qb and neg3 is not None and negb is not None and neg3 - negb >= 0.15)
    fam["demand"] = bool(buyers_down or money_down)
    ev["cooldown"] = bool(ok_d and s24 is not None and s24 <= 0.75 * sb and not buyers_down)
    # crowding: its share of launches up while buyers per launch fall
    def lshare(a, b):
        from bisect import bisect_right
        cnt = lambda xs: bisect_right(xs, b) - bisect_right(xs, a)  # noqa: E731
        own, tot = cnt(data["launches"].get(cat, [])), cnt(data["cat_launch"])   # of categorised launches, not all
        return own / tot if tot else None
    l3, lb = lshare(t - DECAY_RECENT_D * D, t), lshare(t - (DECAY_RECENT_D + DECAY_BASE_D) * D, t - DECAY_RECENT_D * D)
    lg = l3 / lb if l3 is not None and lb else None
    bpl = (s3 / sb) / lg if lg and s3 is not None and sb else None
    met["launch_share_change"] = round(lg, 2) if lg is not None else None
    met["buyers_per_launch_change"] = round(bpl, 2) if bpl is not None else None
    fam["crowding"] = bool(ok_d and lg is not None and lg >= 1.3 and bpl is not None and bpl <= 0.7)
    # concentration: the recent drew-buyers coins rest on one or two, while the rest fall behind
    peaks = sorted((c[5] or 0 for c in tR), reverse=True)
    top2 = sum(peaks[:2]) / sum(peaks) if peaks and sum(peaks) else None
    rest = (max(len(tR) - 2, 0) / max(len(R) - 2, 1) / pR) / base_ratio if R and pR and base_ratio else None
    met["top_two_share"] = round(top2, 2) if top2 is not None else None
    met["rest_vs_baseline"] = round(rest, 2) if rest is not None else None
    fam["concentration"] = bool(ev["enough"] and len(tB) >= 3 and len(tR) >= 2 and top2 is not None and top2 >= 0.6
                                and rest is not None and rest <= 0.6)
    ev["n_on"] = sum(fam.values())
    ev["slow_on"] = any(fam[k] for k in SLOW)
    # what argues against decay
    if s24 is not None and sb and s24 >= sb:
        ev["against"].append(f"Its share of buying in the last day ({_pct(s24)}) is at or above its baseline ({_pct(sb)}).")
    if pt is not None and pt >= 0.5:
        ev["against"].append("Its recent coins drew buyers at least as often as before, against the market.")
    if neg3 is not None and negb is not None and neg3 <= negb - 0.1:
        ev["against"].append(f"Net selling is less frequent than before ({_pct(neg3)} of hours against {_pct(negb)}).")
    if lg is not None and lg <= 0.8:
        ev["against"].append("Fewer launches are crowding into it than before.")
    return ev


def _r3(x):
    return round(x, 3) if x is not None else None


def _decay_status(evs: list[dict]) -> str:
    """evs[0] is now, evs[k] k days ago."""
    now = evs[0]
    if not now["eligible"]:
        return "no edge"
    if not now["enough"]:
        return "thin"
    prev = evs[1] if len(evs) > 1 else None
    was = [_decay_status_simple(x) for x in evs[1:3] if x["eligible"] and x["enough"]]
    if now["n_on"] >= 2 and now["slow_on"] and prev and prev["n_on"] >= 2:
        return "confirmed"
    if now["n_on"] >= 2:
        return "early"
    if any(w in ("early", "confirmed") for w in was):
        return "recovering"
    if now["cooldown"] and not now["slow_on"]:
        return "cooldown"
    return "healthy"


def _decay_status_simple(ev):
    return "early" if ev["n_on"] >= 2 else "healthy"


def decay(con, as_of: int, back: int = 4) -> dict:
    """Meta health for every category that had an edge: status, how long, how broad, which way the
    evidence is moving, what argues against it, and what would confirm recovery or decay."""
    data = _decay_data(con, as_of, back)
    cats = {k for k, v in data["by_cat"].items() if len(v) >= 90 and k.strip()}    # fewer coins could never meet the baseline's 60 + 30
    out = {"as_of": as_of, "categories": [], "market": None, "notes": []}
    # market context: is everyone down?
    e = as_of - D
    mR, mB = _mkt(data, e - DECAY_RECENT_D * D, e), _mkt(data, e - (DECAY_RECENT_D + DECAY_BASE_D) * D, e - DECAY_RECENT_D * D)
    tot = lambda a, b: sum(x for v in data["buyers"].values() for t, x in v if a < t <= b)  # noqa: E731
    reads = lambda a, b: len({t for v in data["buyers"].values() for t, _ in v if a < t <= b}) or 1  # noqa: E731
    b3 = tot(as_of - DECAY_RECENT_D * D, as_of) / reads(as_of - DECAY_RECENT_D * D, as_of)
    bb = tot(as_of - (DECAY_RECENT_D + DECAY_BASE_D) * D, as_of - DECAY_RECENT_D * D) / reads(as_of - (DECAY_RECENT_D + DECAY_BASE_D) * D, as_of - DECAY_RECENT_D * D)
    if mR[0] and mB[0]:
        mk = {"drew_buyers_rate": [round(mR[1] / mR[0], 4), round(mB[1] / mB[0], 4)],
              "buyers_per_read": [round(b3), round(bb)] if bb else None,
              "launches_per_day": [round(mR[0] / DECAY_RECENT_D), round(mB[0] / DECAY_BASE_D)]}
        down = bb and b3 <= 0.7 * bb
        mk["text"] = ((f"The whole market is down: category buyers average {b3:,.0f} per read against {bb:,.0f} before. "
                       "Each category is judged against the market, so a broad sell-off alone does not read as its decay.")
                      if down else "The market as a whole is not in a broad downturn; categories are still judged against it.")
        out["market"] = mk
    for cat in sorted(cats):
        evs = [_decay_eval(data, cat, as_of - k * D) for k in range(back)]
        now = evs[0]
        if not now["eligible"]:
            continue
        st = _decay_status(evs)
        days = 0
        for x in evs:
            if x["n_on"] >= 2:
                days += 1
            else:
                break
        trend = (None if len(evs) < 2 else "strengthening" if now["n_on"] > evs[1]["n_on"]
                 else "easing" if now["n_on"] < evs[1]["n_on"] else "unchanged")
        prev_st = _decay_status(evs[1:]) if len(evs) > 1 else None
        out["categories"].append({"category": cat, "status": st, "label": DECAY_LABEL[st], "previous": prev_st,
                                  "days_flagged": days, "evidence_trend": trend,
                                  "families_on": [k for k, v in now["families"].items() if v],
                                  "history": [x["n_on"] for x in evs], **_decay_text(cat, st, prev_st, now, days, trend),
                                  "metrics": now["metrics"], "window": now["window"],
                                  "baseline": {"drew_buyers_vs_market": now["base_ratio"], "graduated_vs_market": now["base_grad_ratio"]}})
    order = {"confirmed": 0, "early": 1, "recovering": 2, "cooldown": 3, "healthy": 4, "thin": 5}
    out["categories"].sort(key=lambda r: (order[r["status"]], -len(r["families_on"])))
    if not out["categories"]:
        out["notes"].append(f"No category had an edge to lose: decay is tracked for categories whose coins did at least 1.2× the market "
                            f"over the {DECAY_BASE_D} days before the last {DECAY_RECENT_D}, from 3+ creators.")
    return out


def _decay_text(cat, st, prev_st, ev, days, trend) -> dict:
    m, f = ev["metrics"], ev["families"]
    lines = []
    bs = m["buyer_share"]
    if f["demand"]:
        lines.append(f"Buyers: {_pct(bs['3d'])} of all category buying over 3 days and {_pct(bs['day'])} in the last day, "
                     f"against {_pct(bs['baseline'])} before.")
        if m["sol_share"]["3d"] is not None and m["sol_share"]["baseline"]:
            lines.append(f"Money in: {_pct(m['sol_share']['3d'])} of the SOL flowing into categories, against {_pct(m['sol_share']['baseline'])}; "
                         f"net selling in {_pct(m['sell_pressure']['3d'])} of hours (before: {_pct(m['sell_pressure']['baseline'])}).")
    if f["results"]:
        tr, gr = m["traction_ratio"], m["graduation_ratio"]
        lines.append(f"Results: its recent coins drew 50+ buyers {_x(tr[0])} the market, against {_x(tr[1])} before"
                     + (f"; graduations {_x(gr[0])} against {_x(gr[1])}." if gr[1] else "."))
    if f["breadth"]:
        w = m["winners_per_day"]
        lines.append(f"Breadth: {w[0]:.1f} different creators a day had a coin draw buyers, against {w[1]:.1f} before"
                     + (f" ({_x(m['winners_vs_market_change'])} the market's change)." if m["winners_vs_market_change"] is not None else "."))
    if f["follow_through"]:
        ft, hr = m["follow_through"], m["holder_retention"]
        lines.append(f"Follow-through: of coins that drew buyers, {_pct(ft[0])} went on to half the curve or graduation, against {_pct(ft[1])}"
                     + (f"; holders kept after a day {_pct(hr[0])} against {_pct(hr[1])}." if hr[1] else "."))
    if f["crowding"]:
        lines.append(f"Crowding: its share of launches is {_x(m['launch_share_change'])} what it was, while buyers per launch are "
                     f"{_x(m['buyers_per_launch_change'])}.")
    if f["concentration"]:
        lines.append(f"Concentration: two coins hold {_pct(m['top_two_share'])} of its recent buying; the rest draw buyers at "
                     f"{_x(m['rest_vs_baseline'])} their earlier rate.")
    why = {"confirmed": f"{cat} is losing its edge: {_and([FAMILY_LABEL[k] for k, v in f.items() if v])} have weakened, including how its coins end up, "
                        f"for {days} day{'s' if days != 1 else ''} running.",
           "early": f"{cat} is showing early weakening in {_and([FAMILY_LABEL[k] for k, v in f.items() if v])}"
                    + ("; its coins' results have not turned yet." if not ev["slow_on"] else "; it needs another day to count as confirmed."),
           "recovering": f"{cat} was weakening in the last days, and the warning signs have eased.",
           "cooldown": f"{cat} is quieter in the last day than usual, but its 3-day demand and results hold up: a cooldown, not decay so far.",
           "healthy": f"{cat} is holding its edge: at most one sign of weakening, and none in how its coins end up.",
           "thin": f"{cat} had an edge, but too few recent coins to judge it now."}[st]
    if prev_st and prev_st != st and prev_st not in ("no edge", "thin"):
        why += f" It was “{DECAY_LABEL[prev_st].lower()}” a day ago."
    recover = ["Its share of buying returns to its baseline for a full day.",
               f"Its coins draw 50+ buyers at {_x(ev['base_ratio'])} the market again, from several creators."]
    worse = ["Results turn: its matured coins draw buyers clearly less often than before, against the market.",
             "Fewer different creators produce winners while launches keep coming.",
             "One or two coins take most of its buying while the rest fade."]
    return {"why": why, "evidence": lines, "against": ev["against"],
            "watch_recovery": recover, "watch_decay": [w for w, k in zip(worse, ("results", "breadth", "concentration")) if not f[k]] or worse[:1]}


def _decay_into_watchlist(rot: dict, dec: dict) -> None:
    """A watchlist category that is decaying says so: today's buying may be a last spike."""
    st = {r["category"]: r for r in dec.get("categories", [])}
    for w in rot.get("watchlist", []):
        d = st.get(w["category"])
        w["health"] = d["status"] if d else None
        if d and d["status"] in ("early", "confirmed"):
            w["risks"].insert(0, f"Its health reads “{d['label'].lower()}”: buying today may be a spike in a meta losing its edge.")


def _and(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


# ---------------------------------------------------------------- connecting the two
def _pct(x) -> str:
    return f"{x:.0%}" if x is not None else "—"


def _x(v) -> str:
    return f"{v:.1f}×" if v is not None else "—"


def macro_sentence(r: dict) -> str:
    """One plain sentence on a category's week."""
    g = r["grad"]
    cat = r["category"]
    if r["status"] == "insufficient":
        return f"{cat}: only {r['coins']} coins this week, too few to judge."
    base = (f"{r['graduated']} of its {r['coins']} coins graduated this week ({_x(g['ratio'])} the market rate)"
            if r["graduated"] else f"none of its {r['coins']} coins graduated this week")
    if r["status"] == "working":
        return (f"{cat} is working: {base}, from {r['independent_successes']} different creators, and it still runs "
                f"{_x(g['ratio_ex_best'])} the market without its best coin.")
    if r["status"] == "one coin":
        bc = r.get("best_coin") or {}
        return (f"{cat} rests on one coin: {base}, but that is {bc.get('name') or bc.get('symbol') or 'a single coin'}; "
                f"without it the rest do {_x(g['ratio_ex_best'])} the market.")
    if r["status"] == "lagging":
        return f"{cat} is lagging: {base}; even at the hopeful end of the range it trails the market."
    return f"{cat} is about average: {base}, a range that includes the market rate."


def links(macro: dict, intraday: dict) -> list[dict]:
    """How each category's week relates to its day, as findings with evidence and contradictions."""
    w7 = (macro.get("windows") or {}).get("7") or {}
    M = {r["category"]: r for r in w7.get("categories", [])} if w7.get("available") else {}
    I = {r["category"]: r for r in intraday.get("categories", [])}
    out = []
    for cat in sorted(set(M) | set(I)):
        m, i = M.get(cat), I.get(cat)
        ms = m["status"] if m else "insufficient"
        is_ = i["status"] if i else None
        ev = {"week": {k: m[k] for k in ("coins", "graduated", "independent_successes", "status", "trend", "crowding",
                                         "newer_vs_older", "launches_last_3d_per_day", "launches_prior_4d_per_day")} | {
                  "ratio": m["grad"]["ratio"], "ratio_ex_best": m["grad"]["ratio_ex_best"]} if m else None,
              "today": {k: i[k] for k in ("status", "buyers_now", "buyers_usual", "demand_vs_usual", "graduations_24h",
                                          "graduations_usual_per_day", "launches_6h", "launches_usual_6h", "coins_with_buyers",
                                          "top_coin_share")} if i else None}
        f = None
        against = []
        if ms == "working" and i and is_ in ("heating", "normal") and i["coins_with_buyers"] >= 2:
            f = ("confirmed", f"{cat} has worked all week and is still working today",
                 [macro_sentence(m), f"Today {i['coins_with_buyers']} of its coins have 20+ buyers in the last hour"
                  + (f", with demand {_x(i['demand_vs_usual'])} its usual level." if i["demand_vs_usual"] else ".")])
            if (i["top_coin_share"] or 0) >= 0.6:
                against.append(f"Today's buying is concentrated: one coin has {_pct(i['top_coin_share'])} of it.")
        elif ms == "working" and ((m.get("newer_vs_older") is not None and m["newer_vs_older"] <= 0.2) or
                                  (i and i["graduations_usual_per_day"] and i["graduations_24h"] < 0.5 * i["graduations_usual_per_day"]
                                   and i["launches_usual_6h"] and i["launches_6h"] >= i["launches_usual_6h"])):
            f = ("lagging new launches", f"{cat} has a strong week, but its newest launches are doing worse",
                 [macro_sentence(m)]
                 + ([f"Coins launched in the last 3 days did worse than the 4 days before (chance they did better: {_pct(m['newer_vs_older'])})."]
                    if m.get("newer_vs_older") is not None and m["newer_vs_older"] <= 0.2 else [])
                 + ([f"Today: {i['graduations_24h']} graduations against about {i['graduations_usual_per_day']:.1f} on a usual day, "
                     f"while {i['launches_6h']} coins launched in 6 hours (usual {i['launches_usual_6h']:.0f})."]
                    if i and i["graduations_usual_per_day"] else []))
        elif m and m.get("crowding") == "saturating" or (i and i["launches_usual_6h"] and i["launches_6h"] >= 1.5 * i["launches_usual_6h"]
                                                          and i["graduations_usual_per_day"] is not None
                                                          and i["graduations_24h"] <= i["graduations_usual_per_day"]
                                                          and (i["demand_vs_usual"] or 1) <= 1.0):
            f = ("saturating", f"{cat} is getting crowded: more launches, not more successes",
                 ([f"Launches went from {m['launches_prior_4d_per_day']:.0f} to {m['launches_last_3d_per_day']:.0f} a day while newer coins did worse."]
                  if m and m.get("crowding") == "saturating" else [])
                 + ([f"Today {i['launches_6h']} coins in 6 hours (usual {i['launches_usual_6h']:.0f}) but {i['graduations_24h']} graduations "
                     f"(usual {i['graduations_usual_per_day']:.1f}) and buyers at {_x(i['demand_vs_usual'])} usual."] if i and i["launches_usual_6h"] else []))
        elif m and m.get("trend") == "losing" and is_ == "cooling":
            f = ("fading", f"{cat} is losing momentum",
                 [macro_sentence(m), f"Its rate fell against last week (chance it improved: {_pct(m['vs_last_week'])}), "
                  f"and today's buyers are {_x(i['demand_vs_usual'])} its usual level."])
        elif ms == "working" and is_ == "cooling":
            f = ("quiet today", f"{cat} worked this week but is quiet today",
                 [macro_sentence(m), f"Today's buyers are {_x(i['demand_vs_usual'])} its usual level."])
        elif i and is_ == "heating" and ms in ("lagging", "average", "one coin"):
            f = ("hot without a record", f"{cat} is busy today, but its week does not back it up",
                 [f"Buyers today are {_x(i['demand_vs_usual'])} its usual level.", macro_sentence(m)])
        elif i and (is_ == "new" or ms == "insufficient") and (i["buyers_now"] or 0) >= 50 and i["coins_with_buyers"] >= 2:
            f = ("new, no record", f"{cat} is drawing buyers today with no track record yet",
                 [f"{i['buyers_now']:,} buyers in the last hour across {i['narratives_live']} narrative(s); "
                  + ("there is no week of history to compare with." if not m else f"only {m['coins']} coins last week, too few to judge.")])
        if f:
            if m and m["status"] == "working" and m.get("days_with_success", 7) <= 2:
                against.append(f"Its successes came on only {m['days_with_success']} of the 7 days.")
            if i and i.get("crowding_narratives"):
                against.append("Some of its narratives are already saturating or fading: " + ", ".join(i["crowding_narratives"][:3]) + ".")
            out.append({"kind": f[0], "category": cat, "title": f[1], "detail": f[2], "against": against, "evidence": ev})
    order = ["confirmed", "lagging new launches", "new, no record", "hot without a record", "saturating", "fading", "quiet today"]
    out.sort(key=lambda r: order.index(r["kind"]))
    for n in intraday.get("narratives", []):        # narratives too new for any track record
        if n["age_h"] <= 24 and (n["buyers_h1"] or 0) >= 50 and n["coins_with_buyers"] >= 2:
            out.append({"kind": "new, no record", "category": n["category"], "narrative": n["title"],
                        "title": f"New narrative “{n['title']}” is drawing buyers across several coins",
                        "detail": [f"First seen {n['age_h']:.0f} h ago; {n['buyers_h1']:,} buyers in the last hour across "
                                   f"{n['coins_with_buyers']} coins with 20+ buyers."],
                        "against": ["Under a day old: no record of how its coins end up."]
                                   + ([f"One coin has {_pct(n['top_coin_share'])} of its buying."] if (n["top_coin_share"] or 0) >= 0.6 else []),
                        "evidence": {"narrative": {k: n[k] for k in ("label", "age_h", "buyers_h1", "launches_6h", "coins_with_buyers", "top_coin_share", "state")}}})
    return out


def comovement(con, as_of: int, days: int = 7, min_hours: int = 72) -> dict:
    """Do categories move together beyond the market? Hourly buyers per category, the market-wide
    swing removed, hour-to-hour changes correlated; each pair tested against circular time shifts
    (which keep each series' own rhythm) and the set of pairs corrected for multiple testing."""
    np = _np()
    cb = _category_buyers(con, as_of - days * D, as_of)
    hours = sorted({t // H for v in cb.values() for t, _ in v})
    if len(hours) < min_hours:
        return {"pairs": [], "tested": 0, "hours": len(hours),
                "note": f"Needs {min_hours} hours of narrative history; {len(hours)} so far."}
    idx = {h: j for j, h in enumerate(hours)}
    mat = {}
    for cat, v in cb.items():
        arr = np.full(len(hours), np.nan)
        acc: dict[int, list] = {}
        for t, b in v:
            acc.setdefault(t // H, []).append(b)
        for h, bs in acc.items():
            arr[idx[h]] = np.mean(bs)
        if np.sum(~np.isnan(arr)) >= min_hours and np.nanmedian(arr) >= 10:
            mat[cat] = arr
    if len(mat) < 2:
        return {"pairs": [], "tested": 0, "hours": len(hours), "note": "Fewer than two categories with steady buying."}
    cats = sorted(mat)
    if len(cats) < 4:
        return {"pairs": [], "tested": 0, "hours": len(hours),
                "note": "Needs at least four categories with steady buying to tell a shared move from the market's."}
    dl = {c: np.diff(np.log1p(mat[c])) for c in cats}           # hour-to-hour change in log-buyers
    stack = np.vstack([dl[c] for c in cats])

    def market_without(skip):
        """The typical category's change each hour, leaving out `skip`: a median, so one shared
        theme among the others cannot pass for the market."""
        keep = [i for i, c in enumerate(cats) if c not in skip]
        return np.nanmedian(stack[keep], axis=0)

    def resid(d, mk):
        ok = ~np.isnan(d) & ~np.isnan(mk)
        b = float(np.polyfit(mk[ok], d[ok], 1)[0]) if ok.sum() > 10 else 0.0
        return d - b * mk, b
    def corr_with(d, mk):
        ok = ~np.isnan(d) & ~np.isnan(mk)
        return round(float(np.corrcoef(d[ok], mk[ok])[0, 1]), 2) if ok.sum() > 10 else None
    # how much of each category's hourly swing it shares with the rest of the market (a correlation:
    # a slope here would be shrunk by the noise in the market proxy)
    betas = {c: corr_with(dl[c], market_without({c})) for c in cats}
    rng = np.random.default_rng(23)
    tests = []
    for i_ in range(len(cats)):
        for j_ in range(i_ + 1, len(cats)):
            mk = market_without({cats[i_], cats[j_]})
            a, _ = resid(dl[cats[i_]], mk)
            b, _ = resid(dl[cats[j_]], mk)
            ok = ~np.isnan(a) & ~np.isnan(b)
            if ok.sum() < min_hours - 1:
                continue
            aa, bb = a[ok], b[ok]
            r = float(np.corrcoef(aa, bb)[0, 1])
            shifts = rng.integers(6, len(bb) - 6, 300)
            null = np.array([np.corrcoef(aa, np.roll(bb, s))[0, 1] for s in shifts])
            p = float((np.sum(null >= r) + 1) / (len(null) + 1))       # one-sided: moving together
            tests.append((cats[i_], cats[j_], r, p, int(ok.sum())))
    # Benjamini-Hochberg at 10%
    tests.sort(key=lambda t: t[3])
    m_ = len(tests)
    keep = 0
    for k, t in enumerate(tests, 1):
        if t[3] <= 0.1 * k / m_:
            keep = k
    sig = [t for t in tests[:keep] if t[2] >= 0.25]
    pairs = [{"a": a, "b": b, "r": round(r, 2), "p": round(p, 4), "hours": n} for a, b, r, p, n in sig]
    _shared_evidence(con, as_of, days, pairs)
    return {"pairs": pairs, "tested": m_, "hours": len(hours), "market_correlation": betas,
            "note": ("Hour-to-hour changes in buyers, after removing what the typical other category did; a pair is listed only when "
                     "it beats 300 random time shifts and survives a correction for testing many pairs. Moving together "
                     "does not mean one causes the other.")}


def _shared_evidence(con, as_of: int, days: int, pairs: list[dict]) -> None:
    """Concrete links behind a co-moving pair: the same early-buyer wallets, the same X posts."""
    if not pairs:
        return
    cats = {p["a"] for p in pairs} | {p["b"] for p in pairs}
    q = ",".join("?" * len(cats))
    wallets: dict[str, set] = {}
    for cat, w in con.execute(f"""SELECT tn.category, e.wallet FROM early_buyers e JOIN token_narrative tn ON tn.mint = e.mint
                                  WHERE tn.category IN ({q}) AND e.ts > ?""", (*cats, as_of - days * D)):
        wallets.setdefault(cat, set()).add(w)
    posts: dict[str, set] = {}
    for cat, xp in con.execute(f"""SELECT tn.category, k.x_post FROM tokens k JOIN token_narrative tn ON tn.mint = k.mint
                                   WHERE tn.category IN ({q}) AND k.created_at > ? AND k.x_post IS NOT NULL""",
                               (*cats, as_of - days * D)):
        posts.setdefault(cat, set()).add(xp)
    for p in pairs:
        wa, wb = wallets.get(p["a"], set()), wallets.get(p["b"], set())
        p["shared_early_buyers"] = len(wa & wb) if wa and wb else None
        p["early_buyer_overlap"] = round(len(wa & wb) / len(wa | wb), 3) if wa and wb else None
        p["shared_x_posts"] = len(posts.get(p["a"], set()) & posts.get(p["b"], set()))


def popularity_vs_success(macro: dict) -> dict | None:
    """Across categories this week: do the busiest categories produce the most successes per coin?"""
    np = _np()
    w7 = (macro.get("windows") or {}).get("7") or {}
    rows_ = [r for r in w7.get("categories", []) if r["coins"] >= MIN_COINS]
    if len(rows_) < 6:
        return None
    a = np.array([r["coins"] for r in rows_], float)
    b = np.array([r["grad"]["ratio"] for r in rows_], float)
    ra, rb = a.argsort().argsort(), b.argsort().argsort()
    rho = float(np.corrcoef(ra, rb)[0, 1])
    return {"spearman": round(rho, 2), "categories": len(rows_),
            "text": (f"Across {len(rows_)} categories this week, the busiest were "
                     + ("also the most successful per coin" if rho >= 0.4 else "not the most successful per coin" if rho <= 0.1
                        else "only loosely the most successful per coin")
                     + f" (rank correlation {rho:+.2f}): launch count is not a measure of what works.")}


def read(con, as_of: int | None = None, live_narratives: dict | None = None) -> dict:
    as_of = as_of or _now()
    mac = macro_read(con, as_of)
    intra = intraday_read(con, as_of, live_narratives)
    w7 = mac["windows"].get("7") or {}
    for r in w7.get("categories", []) if w7.get("available") else []:
        r["sentence"] = macro_sentence(r)
    rot, dec = rotation(con, as_of, mac, intra), decay(con, as_of)
    _decay_into_watchlist(rot, dec)
    return {"as_of": as_of, "macro": mac, "intraday": intra, "links": links(mac, intra),
            "rotation": rot, "decay": dec,
            "comovement": comovement(con, as_of), "popularity_vs_success": popularity_vs_success(mac),
            "check": _check()}


def _check() -> dict | None:
    """How much a week's record said about the next day, measured on history (scripts/macro_check.py)."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "data" / "macro_check.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def backfill_token_narrative(con) -> int:
    """Once: recover coin -> narrative links from the narrative history kept before this table existed
    (narrative_obs members, 14 days), so an existing install starts with what it already knows."""
    import json
    if con.execute("SELECT value FROM meta_info WHERE key='token_narrative_backfill'").fetchone():
        return 0
    rows_ = []
    for nid, at, members, label, cat in con.execute(
            """SELECT o.narrative_id, o.observed_at, o.members, n.label, n.category FROM narrative_obs o
               JOIN narratives n ON n.id = o.narrative_id ORDER BY o.observed_at""").fetchall():
        rows_ += [(m, nid, label, cat, at) for m in json.loads(members or "[]")]
    for i in range(0, len(rows_), WRITE_CHUNK):      # short transactions, in order: the first narrative wins
        con.execute("BEGIN")
        try:
            con.executemany("INSERT OR IGNORE INTO token_narrative (mint, narrative_id, label, category, at) VALUES (?,?,?,?,?)",
                            rows_[i:i + WRITE_CHUNK])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    con.execute("INSERT OR REPLACE INTO meta_info VALUES ('token_narrative_backfill', ?)", (str(_now()),))
    return len(rows_)
