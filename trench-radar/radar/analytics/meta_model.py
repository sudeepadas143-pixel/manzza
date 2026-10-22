"""Launch-edge model: ranks metas by how their next launches are expected to graduate against
every launch in the same hours. Fitted and validated walk-forward in docs/RESEARCH_META.md.

Inputs are the evidence the readiness score already computes (scoring.score_meta), so the live
app and the research scripts (scripts/meta_dataset.py, scripts/meta_validate.py) share one
definition. The output is a *ranking*: in later months the ordering held up but the size of the
predicted lift did not, so the lift is not shown as a probability.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "meta_model.json"

MOMENTUM = ["launches_1h", "launches_6h", "accel_z", "share_6h", "growth_3h", "hours_above_base", "age_h", "creators_1h"]
DEMAND = ["buyers_1h", "buyer_share", "net_sol_1h", "top_progress", "grads_24h", "vol_1h", "tracked", "smart_1h"]
SATURATION = ["sat_index", "dup_share", "winner_share", "buyers_per_launch", "outpacing", "serial_share"]
MARKET = ["market"]
FEATURES = MOMENTUM + DEMAND + SATURATION + MARKET
SAT_SIGNALS = ("copycat_tickers", "buyers_per_launch", "launches_outpacing_buyers", "winner_concentration",
               "volume_fading", "meta_age")


def raw(scored: dict, market: dict) -> dict:
    """The evidence of one scored meta (scoring.score_meta output) as flat numbers, None if absent."""
    ev = scored["evidence"]
    L, D, S = ev["launch"], ev["demand"], ev["saturation"]
    hourly = L.get("launch_hourly_12h") or []
    last3, prev3 = sum(hourly[-3:]), sum(hourly[-6:-3])
    tp = D.get("top_progress") or []
    f = {
        "score": scored["score"], "confidence": scored["confidence"], "verdict": scored["verdict"],
        **{f"comp_{k}": v for k, v in scored["components"].items()},
        "launches_1h": L["launches_1h"], "launches_6h": L["launches_6h"], "launches_base": L["launches_base"],
        "accel_z": L["launch_accel_z"], "share_6h": L["launch_share_6h"], "dup_share": L["duplicate_symbol_share_6h"],
        "age_h": L["first_seen_in_window_h"], "creators_1h": L["creators_1h"],
        # sustained growth: launches in the last 3 hours vs the 3 before, and how many of the last
        # 3 hours each beat the 6 h baseline rate
        "growth_3h": math.log((last3 + 1) / (prev3 + 1)),
        "hours_above_base": sum(1 for x in hourly[-3:] if x > L["launch_base_rate_h"]),
        "buyers_1h": D.get("unique_buyers_h1_sum"), "buyer_share": D.get("buyer_share_h1"),
        "net_sol_1h": D.get("curve_net_sol_1h"), "top_progress": tp[0] if tp else None,
        "grads_24h": D.get("graduations_24h"), "vol_1h": D.get("vol_h1_usd"), "tracked": D.get("tokens_tracked"),
        "smart_1h": D.get("smart_buyers_h1_sum"), "organic_1h": D.get("organic_buyers_h1_sum"),
        "bundled": D.get("tokens_bundled"), "dev_sold": D.get("tokens_dev_sold"),
        "winner_share": D.get("top_token_share_vol24"), "over_50pct": D.get("tokens_over_50pct"),
        "sat_index": S["index"], "serial_share": (ev.get("creators") or {}).get("serial_share"),
        "market": market.get("score"),
    }
    for k in SAT_SIGNALS:
        f[f"sat_{k}"] = S["signals"][k]["value"] if k in S["signals"] else None
    return f


def _num(x):
    return np.asarray(np.nan if x is None else x, dtype=float)


def transform(R: dict) -> dict:
    """Model inputs from raw values. Works on scalars (live) and on arrays (research)."""
    g = lambda k: _num(R[k]) if not isinstance(R[k], np.ndarray) else R[k].astype(float)  # noqa: E731
    lg = lambda x: np.log1p(np.maximum(x, 0))  # noqa: E731
    net = g("net_sol_1h")
    return {
        "launches_1h": lg(g("launches_1h")), "launches_6h": lg(g("launches_6h")),
        "accel_z": np.clip(g("accel_z"), -5, 20), "share_6h": lg(1000 * g("share_6h")),
        "growth_3h": g("growth_3h"), "hours_above_base": g("hours_above_base"), "age_h": g("age_h"),
        "creators_1h": lg(g("creators_1h")),
        "buyers_1h": lg(g("buyers_1h")), "buyer_share": g("buyer_share"), "net_sol_1h": np.sign(net) * np.log1p(np.abs(net)),
        "top_progress": g("top_progress"), "grads_24h": lg(g("grads_24h")), "vol_1h": lg(g("vol_1h")),
        "tracked": lg(g("tracked")), "smart_1h": lg(g("smart_1h")),
        "sat_index": g("sat_index"), "dup_share": g("dup_share"), "winner_share": g("winner_share"),
        "buyers_per_launch": lg(g("sat_buyers_per_launch")), "outpacing": g("sat_launches_outpacing_buyers"),
        "serial_share": g("serial_share"), "market": g("market"),
    }


class EdgeModel:
    def __init__(self, spec: dict):
        self.spec = spec
        self.version = spec["version"]
        self.names = spec["features"]
        self.ind = spec["missing_indicators"]
        self.med, self.mu, self.sd, self.b = spec["median"], spec["mean"], spec["sd"], spec["coef"]

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "EdgeModel | None":
        try:
            return cls(json.loads(path.read_text()))
        except (OSError, ValueError, KeyError):
            return None

    def lift(self, x: dict) -> float:
        """Predicted log-odds of the meta's next launches graduating, against all launches then."""
        vals = [float(x[k]) for k in self.names]
        miss = [math.isnan(v) for v in vals]
        filled = [self.med[j] if miss[j] else v for j, v in enumerate(vals)] + [1.0 if miss[j] else 0.0 for j in self.ind]
        return self.b[0] + sum(b * (v - m) / s for b, v, m, s in zip(self.b[1:], filled, self.mu, self.sd))


def rank(scored: list[dict], market: dict, model: EdgeModel | None) -> None:
    """Attach `edge` to every scored meta, in place: the model's lift, its rank in this read and
    a tier by position (top fifth .. bottom fifth). No model: every edge is None."""
    if model is None or not scored:
        for s in scored:
            s["edge"] = None
        return
    lifts = [model.lift(transform(raw(s, market))) for s in scored]
    order = sorted(range(len(scored)), key=lambda i: -lifts[i])
    n = len(scored)
    for pos, i in enumerate(order):
        q = pos / max(n - 1, 1)
        tier = "strongest" if q < 0.2 else "above average" if q < 0.5 else "below average" if q < 0.8 else "weakest"
        scored[i]["edge"] = {"lift_logit": round(lifts[i], 3), "rank": pos + 1, "of": n, "tier": tier,
                             "model": model.version}
