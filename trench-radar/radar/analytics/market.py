"""Market readiness: is the pump.fun market as a whole receptive right now?

Sub-scores are heuristic mappings (documented midpoints), not fitted values.
"""
from __future__ import annotations

from ..db import rows
from .common import Lineage, clip01, launch_coverage, logistic

H = 3600


def _latest(con, metric: str, as_of: int, max_age_s: int, lineage: Lineage) -> dict | None:
    r = rows(con, """SELECT value, observed_at, detail, source FROM market_obs WHERE metric=? AND observed_at <= ?
                     AND observed_at > ? ORDER BY observed_at DESC LIMIT 1""", (metric, as_of, as_of - max_age_s))
    if r:
        lineage.saw("market_obs", r[0]["observed_at"])
        return r[0]
    return None


def _value_near(con, metric: str, ts: int, tol_s: int, lineage: Lineage) -> float | None:
    r = rows(con, """SELECT value, observed_at FROM market_obs WHERE metric=? AND observed_at <= ? AND observed_at > ?
                     ORDER BY observed_at DESC LIMIT 1""", (metric, ts, ts - tol_s))
    if r:
        lineage.saw("market_obs", r[0]["observed_at"])
        return r[0]["value"]
    return None


def conditions(con, as_of: int, lineage: Lineage | None = None) -> dict:
    lineage = lineage or Lineage()
    m: dict = {"metrics": {}, "components": {}, "notes": []}

    # 1. Launch flow we observed (coverage-adjusted)
    cov_1h = launch_coverage(con, as_of, H)
    cov_24h = launch_coverage(con, as_of, 24 * H)
    n_1h = rows(con, """SELECT COUNT(*) n FROM tokens WHERE launchpad='pump-fun' AND source IN ('chain','shrine_replay','corpus','gt_new_pools')
                        AND created_at > ? AND created_at <= ? AND first_seen_at <= ?""",
                (as_of - H, as_of, as_of))[0]["n"]
    n_24h = rows(con, """SELECT COUNT(*) n FROM tokens WHERE launchpad='pump-fun' AND source IN ('chain','shrine_replay','corpus','gt_new_pools')
                         AND created_at > ? AND created_at <= ? AND first_seen_at <= ?""",
                 (as_of - 24 * H, as_of, as_of))[0]["n"]
    lineage.saw("tokens", None, 2)
    m["metrics"].update({
        "launches_observed_1h": n_1h, "launch_coverage_1h": round(cov_1h, 2),
        "launches_est_per_h": round(n_1h / cov_1h) if cov_1h >= 0.3 else None,
        "launches_est_per_h_24h_avg": round(n_24h / cov_24h / 24) if cov_24h >= 0.3 else None,
        "launch_coverage_24h": round(cov_24h, 2),
    })

    # 2. Graduation rate: tokens we saw launch 24-48h ago, graduated by now
    if launch_coverage(con, as_of - 24 * H, 24 * H) >= 0.3:
        cohort = rows(con, """SELECT COUNT(*) n,
                SUM(CASE WHEN g.mint IS NOT NULL THEN 1 ELSE 0 END) AS grads
                FROM tokens k LEFT JOIN graduations g ON g.mint=k.mint AND g.detected_at <= ?
                WHERE k.source IN ('chain','shrine_replay','corpus','gt_new_pools') AND k.created_at > ? AND k.created_at <= ?""",
                      (as_of, as_of - 48 * H, as_of - 24 * H))[0]
        if cohort["n"] >= 200:
            rate = (cohort["grads"] or 0) / cohort["n"]
            m["metrics"]["graduation_rate_24_48h_cohort"] = round(rate, 4)
            m["metrics"]["graduation_cohort_n"] = cohort["n"]
            # ~1% is typical for pump.fun; 2%+ is a hot market. Detection undercounts when
            # collection had gaps, so this is a lower bound.
            m["components"]["graduation_rate"] = round(logistic(rate * 100, 1.0, 1.5), 3)
    if "graduation_rate" not in m["components"]:
        m["notes"].append("graduation rate needs >=24h of continuous launch collection")

    # 3. Launchpad volume trend (DefiLlama)
    for key in ("pumpfun_launchpad", "pumpswap"):
        v7 = _latest(con, f"{key}_vol_7d_avg", as_of, 3 * 86400, lineage)
        v30 = _latest(con, f"{key}_vol_30d_avg", as_of, 3 * 86400, lineage)
        if v7 and v30 and v30["value"]:
            ratio = v7["value"] / v30["value"]
            m["metrics"][f"{key}_vol_7d_vs_30d"] = round(ratio, 3)
            m["metrics"][f"{key}_vol_7d_avg_usd"] = round(v7["value"])
            if key == "pumpfun_launchpad":
                m["components"]["launchpad_volume_trend"] = round(logistic(ratio, 1.0, 5.0), 3)
        daily = _latest(con, f"{key}_vol_daily", as_of, 3 * 86400, lineage)
        if daily and daily["detail"]:
            m["metrics"][f"{key}_daily_series"] = daily["detail"]

    # 4. How are new tokens with traction doing?
    med = _latest(con, "active_median_chg_h24", as_of, 2 * H, lineage)
    if med:
        m["metrics"]["active_median_chg_h24_pct"] = round(med["value"], 1)
        m["components"]["new_token_performance"] = round(logistic(med["value"], 0.0, 0.03), 3)
    share = _latest(con, "active_share_under_24h", as_of, 2 * H, lineage)
    if share:
        m["metrics"]["active_share_under_24h"] = round(share["value"], 3)
        # Fresh tokens reaching the most-traded list = rotation into new launches.
        m["components"]["fresh_rotation"] = round(clip01(share["value"] / 0.6), 3)
    vol_now = _latest(con, "active_top80_vol_h24", as_of, 2 * H, lineage)
    vol_prev = _value_near(con, "active_top80_vol_h24", as_of - 24 * H, 2 * H, lineage)
    if vol_now and vol_prev:
        m["metrics"]["active_vol_24h_change"] = round(vol_now["value"] / vol_prev - 1, 3)

    # 5. SOL price (context only)
    sol = _latest(con, "sol_price_usd", as_of, H, lineage)
    sol_prev = _value_near(con, "sol_price_usd", as_of - 24 * H, 2 * H, lineage)
    if sol:
        m["metrics"]["sol_price_usd"] = round(sol["value"], 2)
        if sol_prev:
            chg = sol["value"] / sol_prev - 1
            m["metrics"]["sol_chg_24h"] = round(chg, 4)
            m["components"]["sol_trend"] = round(logistic(chg * 100, 0.0, 0.4), 3)

    comps = m["components"]
    weights = {"launchpad_volume_trend": 0.3, "new_token_performance": 0.25, "graduation_rate": 0.25,
               "fresh_rotation": 0.1, "sol_trend": 0.1}
    have = {k: w for k, w in weights.items() if k in comps}
    m["score"] = round(sum(comps[k] * w for k, w in have.items()) / sum(have.values()), 3) if have else None
    m["coverage"] = round(sum(have.values()) / sum(weights.values()), 2)
    m["regime"] = (None if m["score"] is None else "hot" if m["score"] >= 0.62
                   else "neutral" if m["score"] >= 0.42 else "cold")
    return m
