"""Launch-readiness score per meta: transparent weighted components, confidence, reasons, risks.

MODEL_VERSION changes whenever weights or mappings change, so stored scores and
backtests can be compared like for like. The weights are priors, not fitted.
"""
from __future__ import annotations

import math

from ..db import dumps, insert, now, rows
from . import demand as dm
from . import market as mk
from . import metas as mt
from .common import Lineage, clip01, launch_coverage, logistic, source_freshness
from .saturation import saturation

MODEL_VERSION = "v1-priors-2026-10"
WEIGHTS = {"attention": 0.25, "demand": 0.35, "market": 0.15, "freshness": 0.25}
H = 3600


def _wavg(parts: dict[str, tuple[float | None, float]]) -> tuple[float | None, dict]:
    have = {k: (v, w) for k, (v, w) in parts.items() if v is not None}
    if not have:
        return None, {}
    tot = sum(w for _, w in have.values())
    return sum(v * w for v, w in have.values()) / tot, {k: round(v, 3) for k, (v, _) in have.items()}


def attention_component(launch: dict, social: dict, social_measured: bool) -> dict:
    share = clip01((launch["launch_share_6h"] or 0) / 0.03)
    z = launch["launch_accel_z"]
    launch_mom = share if z is None else 0.6 * logistic(z, 1.5, 0.8) + 0.4 * share
    parts = {"launch_momentum": (launch_mom, 0.3)}
    if social_measured:
        top_eng = max((p["engagement"] for p in social["influential_posts"]), default=0)
        sent = social["sentiment_6h"]
        social_score, sub = _wavg({
            "acceleration": (logistic(social["mention_accel_z"], 1.5, 1.0)
                             if social["mention_accel_z"] is not None else None, 0.35),
            "independent_accounts": (clip01(social["independent_authors_6h"] / 25), 0.35),
            "influence": (logistic(math.log10(top_eng + 1), 2.0, 2.0), 0.15),
            "sentiment": ((sent + 1) / 2 if sent is not None else None, 0.15),
        })
        parts["social"] = (social_score, 0.7)
    value, sub = _wavg(parts)
    return {"value": value, "parts": sub}


def demand_component(d: dict) -> dict:
    if not d["tokens_tracked"]:
        return {"value": None, "parts": {}}
    share = d["buyer_share_h1"] if d["buyer_share_h1"] is not None else d["buy_share_h1"]
    value, parts = _wavg({
        "unique_buyers": (logistic(math.log10(d["unique_buyers_h1_sum"] + 1), math.log10(60), 3.0), 0.3),
        "buy_pressure": (clip01((share - 0.4) / 0.3) if share is not None else None, 0.2),
        "curve_inflow": (logistic(d["curve_net_sol_1h"], 0.0, 0.15)
                         if d["curve_net_sol_1h"] is not None else None, 0.15),
        "curve_progress": (clip01(d["top_progress"][0]) if d["top_progress"] else None, 0.1),
        "graduations": (clip01(d["graduations_24h"] / 3), 0.1),
        "volume": (logistic(math.log10(d["vol_h1_usd"] + 1), math.log10(20000), 2.5), 0.15),
    })
    return {"value": value, "parts": parts}


def hype_check(att: dict, dem: dict, social_measured: bool) -> str:
    soc = att["parts"].get("social")
    d = dem["value"]
    if d is None:
        return "no demand data"
    if not social_measured or soc is None:
        return ("on-chain demand present; social not measured" if d >= 0.55
                else "weak on-chain demand; social not measured")
    if soc >= 0.55 and d >= 0.55:
        return "confirmed: buyers are following the social hype"
    if soc >= 0.55:
        return "hype without buyers: social attention is not converting"
    if d >= 0.55:
        return "on-chain demand ahead of social: early or organic"
    return "cold: neither social attention nor buying"


def _fmt_usd(x):
    return f"${x:,.0f}" if x is not None else "n/a"


def explain(meta: dict, comps: dict, sat: dict, mkt: dict, social_measured: bool) -> tuple[list, list]:
    L, S, D = meta["launch"], meta["social"], meta["demand"]
    reasons, risks = [], []
    if L["launch_accel_z"] is not None and L["launch_accel_z"] >= 2:
        reasons.append(f"Launches accelerating: {L['launches_1h']} in the last hour vs "
                       f"{L['launch_base_rate_h']:.1f}/h baseline (z={L['launch_accel_z']}).")
    if social_measured and S["mention_accel_z"] is not None and S["mention_accel_z"] >= 2:
        reasons.append(f"Mentions accelerating: {S['mentions_1h']} in the last hour vs "
                       f"{S['mention_base_rate_h']:.1f}/h baseline, {S['independent_authors_6h']} independent accounts in 6h.")
    if D["unique_buyers_h1_sum"] >= 60:
        reasons.append(f"{D['unique_buyers_h1_sum']} unique buyers in the last hour across "
                       f"{D['tokens_tracked']} tracked tokens (per-token sums).")
    if D["buyer_share_h1"] is not None and D["buyer_share_h1"] >= 0.55:
        reasons.append(f"Buyers outnumber sellers: {D['buyer_share_h1']:.0%} of wallets trading in the last hour were buying.")
    if D["curve_net_sol_1h"] is not None and D["curve_net_sol_1h"] > 5:
        reasons.append(f"+{D['curve_net_sol_1h']:.1f} SOL net into bonding curves over the last hour.")
    if D.get("smart_buyers_h1_sum"):
        reasons.append(f"{D['smart_buyers_h1_sum']} buy(s) in the last hour from wallets with a proven early-entry "
                       f"record, across {D['tokens_with_smart_buyers']} token(s). Evidence only; not weighted in the score.")
    if D.get("net_flow_source") == "chain" and D["net_flow_usd_h1"] and D["net_flow_usd_h1"] > 2000:
        reasons.append(f"${D['net_flow_usd_h1']:,.0f} more bought than sold in the last hour (on-chain).")
    if D["graduations_24h"]:
        reasons.append(f"{D['graduations_24h']} token(s) in this meta graduated in the last 24h.")
    if mkt.get("regime") == "hot":
        reasons.append("Overall pump.fun market is running hot.")

    if social_measured and S["copy_paste_posts_6h"] >= 5:
        risks.append(f"{S['copy_paste_posts_6h']} copy-paste posts in 6h: coordinated shilling inflates mentions.")
    if D["buyer_share_h1"] is not None and D["buyer_share_h1"] < 0.45:
        risks.append(f"Sellers dominate: only {D['buyer_share_h1']:.0%} of active wallets were buying in the last hour.")
    if D["curve_net_sol_1h"] is not None and D["curve_net_sol_1h"] < -2:
        risks.append(f"{D['curve_net_sol_1h']:.1f} SOL net out of bonding curves over the last hour.")
    if D.get("unique_buyers_h1_sum") and D.get("organic_buyers_h1_sum") is not None \
            and D["organic_buyers_h1_sum"] < 0.5 * D["unique_buyers_h1_sum"]:
        risks.append(f"Bot-heavy: only {D['organic_buyers_h1_sum']} of {D['unique_buyers_h1_sum']} buyers in the last hour "
                     "are not high-frequency bot wallets.")
    if D.get("tokens_dev_sold"):
        risks.append(f"Creator sold 0.5+ SOL back into {D['tokens_dev_sold']} of this meta's active token(s).")
    for sig in sat["signals"].values():
        if sig["s"] >= 0.6:
            risks.append("Saturation: " + sig["why"] + ".")
    if meta.get("creators", {}).get("serial_share") and meta["creators"]["serial_share"] >= 0.5:
        risks.append(f"{meta['creators']['serial_share']:.0%} of known deployers in this meta launched 3+ tokens "
                     "in the prior 24h (serial deployers graduate far less often).")
    if mkt.get("regime") == "cold":
        risks.append("Overall pump.fun market is cold.")
    if not social_measured:
        risks.append("Social sources not connected: attention is inferred from launch names only.")
    if L["launch_accel_z"] is None:
        risks.append("Baseline not established yet (needs ~7h of continuous collection): "
                     "launch acceleration is not scored.")
    if D["tokens_tracked"] < 3:
        risks.append(f"Only {D['tokens_tracked']} token(s) with fresh trading data: demand estimate is thin.")
    risks.append("Base rate: in a published 8,587-launch sample, ~90% of pump.fun tokens were dead within "
                 "30 minutes and none of 48 tested trading rules was profitable (solana-launch-study).")
    return reasons, risks


def history_factor(hist: dict) -> float:
    """How much collection history backs this analysis (0.15 .. 1)."""
    depth = 0.5 * hist["launch_coverage_6h"] + 0.5 * hist["launch_coverage_baseline"]
    return 0.15 + 0.85 * clip01(depth / 0.8)


def score_meta(meta: dict, mkt: dict, fresh: dict, social_measured: bool, validated: bool,
               hist: dict | None = None) -> dict:
    att = attention_component(meta["launch"], meta["social"], social_measured)
    dem = demand_component(meta["demand"])
    sat = meta["saturation"]
    comps = {
        "attention": att["value"], "demand": dem["value"], "market": mkt.get("score"),
        "freshness": (1 - sat["index"]) if sat["index"] is not None else None,
    }
    have = {k: w for k, w in WEIGHTS.items() if comps[k] is not None}
    score = 100 * sum(comps[k] * w for k, w in have.items()) / sum(have.values()) if have else None
    coverage = sum(have.values()) / sum(WEIGHTS.values())
    D, L, S = meta["demand"], meta["launch"], meta["social"]
    sample = 0.6 * clip01(D["tokens_tracked"] / 8) + 0.4 * clip01((L["launches_6h"] + S["mentions_6h"]) / 20)
    used = ["chain/pump_stream", "chain/snapshot", "defillama/launchpad_volume"]
    if social_measured:
        used += [k for k in fresh if k.startswith(("x_api/", "reddit/")) and fresh[k]["freshness"] > 0]
    fvals = [fresh[k]["freshness"] for k in used if k in fresh]
    fresh_factor = sum(fvals) / len(fvals) if fvals else 0.0
    confidence = coverage * (0.4 + 0.6 * sample) * (0.3 + 0.7 * fresh_factor)
    if not social_measured:
        confidence *= 0.8
    hist = hist or {"launch_coverage_6h": 1.0, "launch_coverage_baseline": 1.0}
    confidence *= history_factor(hist)
    reasons, risks = explain(meta, comps, sat, mkt, social_measured)
    if confidence < 0.35 or score is None or hist["launch_coverage_baseline"] < 0.5:
        verdict = "insufficient data"
    elif score >= 65:
        verdict = "favorable"
    elif score >= 45:
        verdict = "mixed"
    else:
        verdict = "unfavorable"
    return {
        "meta_key": meta["key"], "terms": meta["terms"],
        "score": round(score, 1) if score is not None else None,
        "confidence": round(confidence, 2), "verdict": verdict, "validated": validated,
        "hype_check": hype_check(att, dem, social_measured),
        "components": {k: (round(v, 3) if v is not None else None) for k, v in comps.items()},
        "weights": WEIGHTS, "component_parts": {"attention": att["parts"], "demand": dem["parts"]},
        "confidence_factors": {"weight_coverage": round(coverage, 2), "sample": round(sample, 2),
                               "history": round(history_factor(hist), 2),
                               "freshness": round(fresh_factor, 2), "social_measured": social_measured},
        "reasons": reasons, "risks": risks,
        "evidence": {"launch": {k: v for k, v in L.items() if k not in ("mints_6h", "mints_all")},
                     "social": S, "demand": D, "saturation": sat,
                     "attention_purchased": meta.get("attention"), "creators": meta.get("creators")},
    }


def social_is_measured(fresh: dict, posts_6h_total: int) -> bool:
    live = any(v["freshness"] > 0 and v["last_status"] == "ok"
               for k, v in fresh.items() if k.startswith(("x_api/", "reddit/")))
    return live and posts_6h_total > 0


def social_history_h(con, as_of: int) -> float:
    r = rows(con, """SELECT MIN(finished_at) AS t FROM source_runs WHERE source IN ('x_api','reddit')
                     AND status='ok' AND finished_at <= ?""", (as_of,))
    return round((as_of - r[0]["t"]) / H, 1) if r and r[0]["t"] else 0.0


def latest_validation(con) -> bool:
    r = rows(con, "SELECT results FROM backtests ORDER BY id DESC LIMIT 1")
    if not r:
        return False
    import json
    return bool(json.loads(r[0]["results"]).get("validated"))


def run_analysis(con, as_of: int | None = None, *, persist: bool = True, max_metas: int = 25) -> dict:
    as_of = as_of or now()
    lineage = Lineage()
    fresh = source_freshness(con, as_of)
    metas, ctx = mt.detect(con, as_of, lineage)
    mkt = mk.conditions(con, as_of, lineage)
    social_measured = social_is_measured(fresh, ctx["posts_6h_total"])
    hist = {"launch_coverage_6h": round(launch_coverage(con, as_of, 6 * H), 2),
            "launch_coverage_baseline": round(launch_coverage(con, as_of - mt.RECENT_S, mt.BASE_S), 2),
            "collected_h": round(launch_coverage(con, as_of, mt.RECENT_S + mt.BASE_S) * (mt.RECENT_S + mt.BASE_S) / H, 1),
            "needed_h": (mt.RECENT_S + mt.BASE_S) // H,
            "social_history_h": social_history_h(con, as_of)}
    ctx["history"] = hist
    validated = latest_validation(con) if persist else False
    scored = []
    for meta in metas:
        if hist["launch_coverage_baseline"] < 0.5:
            meta["launch"]["launch_accel_z"] = None
        if hist["social_history_h"] < (mt.RECENT_S + mt.BASE_S) / H:
            meta["social"]["mention_accel_z"] = None
        mints = meta["launch"]["mints_all"]
        meta["demand"] = dm.meta_demand(con, mints, as_of, lineage)
        prev = dm.meta_demand(con, mints, as_of - H, lineage)
        meta["attention"] = dm.attention(con, mints, as_of, lineage)
        meta["creators"] = dm.creator_history(con, meta["launch"]["mints_6h"], as_of, lineage)
        meta["saturation"] = saturation(meta["launch"], meta["social"], meta["demand"], prev)
        scored.append(score_meta(meta, mkt, fresh, social_measured, validated, hist))
    scored.sort(key=lambda s: (s["verdict"] != "insufficient data", s["score"] or 0), reverse=True)
    scored = scored[:max_metas]
    if lineage.max_ts > as_of:
        raise AssertionError(f"look-ahead: read data from {lineage.max_ts} > as_of {as_of}")
    result = {"as_of": as_of, "model_version": MODEL_VERSION, "market": mkt, "metas": scored,
              "context": ctx, "social_measured": social_measured, "freshness": fresh,
              "lineage": {"max_ts": lineage.max_ts, "reads": lineage.reads}}
    if persist:
        for s in scored:
            insert(con, "meta_obs", {"meta_key": s["meta_key"], "observed_at": as_of,
                                     "features": dumps({"components": s["components"], "evidence": s["evidence"]})})
            insert(con, "scores", {"meta_key": s["meta_key"], "computed_at": as_of, "score": s["score"],
                                   "confidence": s["confidence"], "verdict": s["verdict"],
                                   "model_version": MODEL_VERSION, "detail": dumps(s)})
        insert(con, "market_obs", {"observed_at": as_of, "metric": "market_score", "value": mkt.get("score"),
                                   "source": "analysis", "detail": mkt.get("regime")})
        con.commit()
    return result
