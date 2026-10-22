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
        con.execute("BEGIN")
        try:
            con.execute("CREATE TEMP TABLE IF NOT EXISTS _sb (mint TEXT PRIMARY KEY, created_at INTEGER, creator TEXT)")
            con.execute("DELETE FROM _sb")
            con.executemany("INSERT INTO _sb VALUES (?,?,?)", batch)
            con.execute(f"""
                INSERT OR REPLACE INTO token_summary (mint, created_at, creator, factory, narrative_id, label, category,
                    peak_buyers_h1, peak_holders, holders_end, peak_mcap_usd, peak_liq_usd, peak_net_sol_h1, max_progress,
                    graduated, graduated_at, ret_max, obs, summarized_at)
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
                LEFT JOIN token_outcomes oc ON oc.mint = b.mint AND oc.horizon_h = 24""", (now_t,))
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
    for w in windows:
        start = end - w * D
        cov = coverage(con, start, end)
        cs = _coins(con, start, end)
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
        _trends(con, out, end)
        _narratives(con, out, end)
    else:
        out["notes"].append("Less than a week of collection: the weekly view needs 7 days of matured coins.")
    return out


def _trends(con, out: dict, end: int) -> None:
    """For each category in the 7-day view: this week vs the week before, newer launches vs older
    ones in this week, launches per day (crowding), and how steadily it produced successes."""
    w7 = out["windows"]["7"]
    m = w7["prior_strength"]
    this = _coins(con, end - 7 * D, end)
    prev = _coins(con, end - 14 * D, end - 7 * D)
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
        grow = row["launches_last_3d_per_day"] / max(row["launches_prior_4d_per_day"], 0.5)
        row["crowding"] = ("saturating" if grow >= 1.3 and nv is not None and nv <= 0.2 else
                           "filling up" if grow >= 1.3 else "thinning" if grow <= 0.7 else "stable")


def _narratives(con, out: dict, end: int) -> None:
    """The narratives inside each category that produced its successes this week."""
    w7 = out["windows"]["7"]
    p0 = w7["market"]["graduation_rate"]
    cs = _coins(con, end - 7 * D, end)
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


def _category_buyers(con, start: int, end: int) -> dict[str, list[tuple[int, float]]]:
    """Per category, per narrative read: the summed buyers in the last hour of its narratives."""
    out: dict[str, dict[int, float]] = {}
    for t, cat, b in con.execute("""SELECT o.observed_at, n.category, SUM(COALESCE(o.buyers_h1, 0))
                                    FROM narrative_obs o JOIN narratives n ON n.id = o.narrative_id
                                    WHERE o.observed_at > ? AND o.observed_at <= ? AND n.category IS NOT NULL
                                    GROUP BY o.observed_at, n.category""", (start, end)):
        out.setdefault(cat, {})[t] = b
    return {k: sorted(v.items()) for k, v in out.items()}


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
        hist = [b for t, b in cb.get(cat, []) if t <= base_end]
        now_b = sum(r["buyers_h1"] or 0 for r in rows_)
        base_b = (sum(hist) / len(hist)) if hist else None
        g = grads.get(cat, [])
        g24 = sum(1 for t in g if t > as_of - D)
        g_base_daily = sum(1 for t in g if t <= base_end) / 6 if base_hours >= 72 else None
        l6 = sum(1 for t in launches.get(cat, []) if t > as_of - 6 * H)
        l_base_6h = sum(1 for t in launches.get(cat, []) if t <= base_end) / 24 if base_hours >= 72 else None
        coins = sorted((c for r in rows_ for c in r["coins"]), key=lambda c: -c["buyers_h1"])
        tot = sum(c["buyers_h1"] for c in coins)
        demand = (now_b / base_b) if base_b else None
        status = ("new" if base_b is None or base_hours < 72 else
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
        elif i and (is_ == "new" or ms == "insufficient") and (i["buyers_now"] or 0) >= 50:
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
    return {"as_of": as_of, "macro": mac, "intraday": intra, "links": links(mac, intra),
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
    n = 0
    con.execute("BEGIN")
    try:
        for nid, at, members, label, cat in con.execute(
                """SELECT o.narrative_id, o.observed_at, o.members, n.label, n.category FROM narrative_obs o
                   JOIN narratives n ON n.id = o.narrative_id ORDER BY o.observed_at""").fetchall():
            ms = json.loads(members or "[]")
            con.executemany("INSERT OR IGNORE INTO token_narrative (mint, narrative_id, label, category, at) VALUES (?,?,?,?,?)",
                            [(m, nid, label, cat, at) for m in ms])
            n += len(ms)
        con.execute("INSERT OR REPLACE INTO meta_info VALUES ('token_narrative_backfill', ?)", (str(_now()),))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return n
