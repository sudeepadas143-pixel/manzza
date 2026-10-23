"""Meta saturation: is the theme already crowded, copied or fading?

Each signal is 0 (fresh) .. 1 (saturated). The index is the mean of signals that
have data; `signals` keeps every input so the dashboard can show why.
"""
from __future__ import annotations

from .common import clip01


def saturation(launch: dict, social: dict, demand_now: dict, demand_prev: dict) -> dict:
    sig: dict[str, dict] = {}

    # Copycats: same ticker launched repeatedly in 6h.
    dup = launch.get("duplicate_symbol_share_6h")
    if dup is not None and launch["launches_6h"] >= 5:
        sig["copycat_tickers"] = {"value": dup, "s": clip01(dup / 0.5),
                                  "why": f"{dup:.0%} of the last 6h launches reuse a ticker already used in this meta"}

    # Supply vs demand: buyers per launch in the last hour.
    if launch["launches_1h"] >= 3 and demand_now.get("tokens_tracked"):
        bpl = demand_now["unique_buyers_h1_sum"] / launch["launches_1h"]
        sig["buyers_per_launch"] = {"value": round(bpl, 1), "s": clip01(1 - bpl / 40),
                                    "why": f"{bpl:.1f} buyers/h per new launch (40+ reads as uncrowded)"}

    # Launches accelerating while buyers do not.
    prev_b = demand_prev.get("unique_buyers_h1_sum") or 0
    now_b = demand_now.get("unique_buyers_h1_sum") or 0
    if launch["launch_base_rate_h"] > 0 and prev_b >= 20:
        launch_growth = launch["launches_1h"] / max(launch["launch_rate_h"], 0.5)
        buyer_growth = now_b / prev_b
        gap = launch_growth - buyer_growth
        sig["launches_outpacing_buyers"] = {
            "value": round(gap, 2), "s": clip01(gap / 2),
            "why": f"launch rate x{launch_growth:.2f} vs 6h avg, buyers x{buyer_growth:.2f} vs 1h ago"}

    # Winner already took the meta.
    top = demand_now.get("top_token_share_vol24")
    if top is not None and demand_now.get("vol_h24_usd", 0) > 5000:
        sig["winner_concentration"] = {"value": top, "s": clip01((top - 0.4) / 0.5),
                                       "why": f"top token holds {top:.0%} of the meta's 24h volume"}

    # Attention fading: social and volume.
    young = (launch.get("first_seen_in_window_h") or 0) < 6   # 6h averages mean nothing for a younger meta
    if social.get("mentions_6h", 0) >= 6 and not young:
        ratio = social["mentions_1h"] / max(social["mention_rate_h"], 0.1)
        sig["social_fading"] = {"value": round(ratio, 2), "s": clip01(1 - ratio),
                                "why": f"mentions last hour = {ratio:.2f}x the 6h hourly average"}
    v1, v6 = demand_now.get("vol_h1_usd") or 0, demand_now.get("vol_h6_usd") or 0
    if v6 > 3000 and not young:
        ratio = v1 / (v6 / 6)
        sig["volume_fading"] = {"value": round(ratio, 2), "s": clip01(1 - ratio),
                                "why": f"volume last hour = {ratio:.2f}x the 6h hourly average"}

    # Age: a theme visible for most of the lookback is not early.
    age = launch.get("first_seen_in_window_h")
    if age is not None and launch["launches_base"] >= 5:
        # 0 for a theme under 3h old, 1 once it spans the whole 7h lookback
        sig["meta_age"] = {"value": age, "s": clip01((age - 3) / 4),
                           "why": f"launches in this meta go back {age:.0f}h in the 7h lookback"}

    vals = [v["s"] for v in sig.values()]
    return {"index": round(sum(vals) / len(vals), 3) if vals else None, "signals": sig, "n_signals": len(vals)}
