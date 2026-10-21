"""Walk-forward backtest of the readiness score against what happened next.

At each step T the full scoring pipeline is re-run with as_of=T, which can only
read rows observed at or before T (scoring.run_analysis raises if lineage shows
otherwise). The label for a (meta, T) signal is the fate of tokens in that meta
launched in (T, T+follow_h], compared with every launch in the same window:

  graduation lift   = meta graduation rate − all-launch graduation rate
  net-positive rate = share with ret_end > round-trip cost (early-buyer view)

These answer "did launching into this meta then beat launching anything then?".
Graduation and profitability are reported separately; neither implies the other.
Signals at adjacent steps share follow windows, so they are not independent;
the bootstrap resamples whole days to keep that from overstating certainty.
"""
from __future__ import annotations

import random
import statistics

from ..db import dumps, insert, now, rows
from ..text import token_terms
from .scoring import MODEL_VERSION, run_analysis

H = 3600


def _future_cohort(con, t0: int, t1: int, horizon_h: int) -> list[dict]:
    out = rows(con, """SELECT k.mint, k.name, k.symbol, o.graduated, o.ret_end
                       FROM tokens k JOIN token_outcomes o ON o.mint=k.mint AND o.horizon_h=?
                       WHERE k.launchpad='pump-fun' AND k.created_at > ? AND k.created_at <= ?""",
               (horizon_h, t0, t1))
    for r in out:
        r["terms"] = set(token_terms(r["name"], r["symbol"]))
    return out


def _rates(toks: list[dict], cost: float) -> dict:
    rets = [t["ret_end"] for t in toks if t["ret_end"] is not None]
    return {"n": len(toks), "grad_rate": sum(t["graduated"] or 0 for t in toks) / len(toks) if toks else None,
            "n_priced": len(rets), "net_positive_rate": sum(r > cost for r in rets) / len(rets) if rets else None,
            "median_ret": statistics.median(rets) if rets else None}


def _bootstrap_lower(signals: list[dict], key: str, iters: int = 1000, q: float = 0.05,
                     block_s: int = 86400) -> float | None:
    days: dict[int, list[float]] = {}
    for s in signals:
        if s.get(key) is not None:
            days.setdefault(s["t"] // block_s, []).append(s[key])
    if len(days) < 3:
        return None
    rng = random.Random(7)
    groups = list(days.values())
    means = []
    for _ in range(iters):
        pick = [x for _ in groups for x in rng.choice(groups)]
        means.append(sum(pick) / len(pick))
    means.sort()
    return means[int(q * iters)]


def run_backtest(con, start: int, end: int, *, step_s: int = 3600, follow_h: int = 6, horizon_h: int = 24,
                 cost: float = 0.03, min_signals: int = 30, min_future: int = 3, persist: bool = True,
                 exclude: list[tuple[int, int]] | None = None, block_s: int = 86400) -> dict:
    """`end` is capped so every follow window plus horizon has already happened. `exclude`
    lists (start, end) periods whose steps are skipped (collection outages, regime breaks):
    a step is skipped when its lookback or follow window overlaps one."""
    end = min(end, now() - (follow_h + horizon_h) * H)
    exclude = exclude or []
    signals, leaks, skipped = [], 0, 0
    for t in range(start, end, step_s):
        if any(a < t + follow_h * H and t - 7 * H < b for a, b in exclude):
            skipped += 1
            continue
        res = run_analysis(con, t, persist=False)
        if res["lineage"]["max_ts"] > t:
            leaks += 1
            continue
        cohort = _future_cohort(con, t, t + follow_h * H, horizon_h)
        base = _rates(cohort, cost)
        for m in res["metas"]:
            mine = [c for c in cohort if c["terms"] & set(m["terms"])]
            if len(mine) < min_future:
                continue
            r = _rates(mine, cost)
            signals.append({
                "t": t, "meta": m["meta_key"], "score": m["score"], "verdict": m["verdict"],
                "confidence": m["confidence"], "n_future": r["n"],
                "accel_z": m["evidence"]["launch"].get("launch_accel_z"),
                "grad_rate": r["grad_rate"], "base_grad_rate": base["grad_rate"],
                "grad_lift": (r["grad_rate"] - base["grad_rate"]) if base["grad_rate"] is not None else None,
                "net_positive_rate": r["net_positive_rate"], "base_net_positive_rate": base["net_positive_rate"],
                "ret_lift": (r["net_positive_rate"] - base["net_positive_rate"])
                if r["net_positive_rate"] is not None and base["net_positive_rate"] is not None else None,
            })
    by = {}
    for v in ("favorable", "mixed", "unfavorable", "insufficient data"):
        ss = [s for s in signals if s["verdict"] == v]
        lifts = [s["grad_lift"] for s in ss if s["grad_lift"] is not None]
        rlifts = [s["ret_lift"] for s in ss if s["ret_lift"] is not None]
        by[v] = {
            "signals": len(ss),
            "mean_grad_lift": round(sum(lifts) / len(lifts), 4) if lifts else None,
            "grad_lift_lower90": _bootstrap_lower(ss, "grad_lift", block_s=block_s),
            "beat_base_graduation": round(sum(x > 0 for x in lifts) / len(lifts), 3) if lifts else None,
            "mean_net_positive_lift": round(sum(rlifts) / len(rlifts), 4) if rlifts else None,
            # false positive: called favorable, but the meta's later launches did no better than the market
            "false_positive_rate": round(sum(x <= 0 for x in lifts) / len(lifts), 3)
            if lifts and v == "favorable" else None,
        }
    # The launch-acceleration signal on its own (usable even where demand data is missing)
    by_accel = {}
    for name, lo, hi in (("accelerating (z >= 2)", 2, float("inf")), ("flat (0 <= z < 2)", 0, 2),
                         ("cooling (z < 0)", float("-inf"), 0)):
        ss = [s for s in signals if s["accel_z"] is not None and lo <= s["accel_z"] < hi and s["grad_lift"] is not None]
        lifts = [s["grad_lift"] for s in ss]
        by_accel[name] = {"signals": len(ss),
                          "mean_grad_rate": round(sum(s["grad_rate"] for s in ss) / len(ss), 4) if ss else None,
                          "mean_base_grad_rate": round(sum(s["base_grad_rate"] for s in ss) / len(ss), 4) if ss else None,
                          "mean_grad_lift": round(sum(lifts) / len(lifts), 4) if lifts else None,
                          "grad_lift_lower90": _bootstrap_lower(ss, "grad_lift", block_s=block_s),
                          "grad_lift_upper90": _bootstrap_lower(ss, "grad_lift", q=0.95, block_s=block_s)}
    scored = [s for s in signals if s["score"] is not None and s["grad_lift"] is not None]
    corr = None
    if len(scored) >= 10:
        try:
            corr = round(statistics.correlation([s["score"] for s in scored], [s["grad_lift"] for s in scored],
                                                method="ranked"), 3)
        except statistics.StatisticsError:
            corr = None
    fav = by["favorable"]
    validated = bool(fav["signals"] >= min_signals and fav["grad_lift_lower90"] is not None
                     and fav["grad_lift_lower90"] > 0)
    results = {
        "model_version": MODEL_VERSION, "validated": validated, "leaked_steps_skipped": leaks,
        "steps": len(range(start, end, step_s)) if end > start else 0, "steps_excluded": skipped,
        "signals": len(signals), "by_verdict": by, "by_acceleration": by_accel,
        "spearman_score_vs_grad_lift": corr,
        "verdict": ("validated: favorable calls beat the all-launch baseline on graduation (90% bootstrap)"
                    if validated else
                    f"not validated: need >= {min_signals} favorable signals with a positive lower bound "
                    f"(have {fav['signals']})"),
        "sample": signals[-50:],
    }
    if persist:
        insert(con, "backtests", {"created_at": now(), "params": dumps({
            "start": start, "end": end, "step_s": step_s, "follow_h": follow_h, "horizon_h": horizon_h,
            "cost": cost, "min_signals": min_signals, "min_future": min_future, "exclude": exclude}),
            "results": dumps(results)})
        con.commit()
    return results
