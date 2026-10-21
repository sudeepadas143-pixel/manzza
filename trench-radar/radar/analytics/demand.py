"""Real buying demand for a meta's tokens, as of a moment.

Only observations taken within the last 2h of `as_of` count as current. Unique
buyer totals are sums of per-token unique buyers — a wallet buying three tokens
in the meta counts three times; the dashboard labels it so.
"""
from __future__ import annotations

from ..db import rows
from .common import OBS_SOURCES, Lineage, in_list

H = 3600
CURRENT_S = 2 * H


def _latest_obs(con, mints: list[str], as_of: int, lineage: Lineage, sources: tuple = OBS_SOURCES) -> dict:
    if not mints:
        return {}
    out = {}
    for i in range(0, len(mints), 500):
        chunk = mints[i:i + 500]
        qs = ",".join("?" * len(chunk))
        for r in rows(con, f"""SELECT * FROM token_obs WHERE id IN (
                SELECT MAX(id) FROM token_obs WHERE observed_at <= ? AND observed_at > ?
                AND source IN {in_list(sources)} AND mint IN ({qs}) GROUP BY mint)""",
                (as_of, as_of - CURRENT_S, *chunk)):
            out[r["mint"]] = r
            lineage.saw("token_obs", r["observed_at"])
    return out


def _curve_at(con, mints: list[str], ts: int, lookback_s: int, lineage: Lineage) -> dict:
    if not mints:
        return {}
    out = {}
    for i in range(0, len(mints), 500):
        chunk = mints[i:i + 500]
        qs = ",".join("?" * len(chunk))
        for r in rows(con, f"""SELECT * FROM curve_obs WHERE id IN (
                SELECT MAX(id) FROM curve_obs WHERE observed_at <= ? AND observed_at > ?
                AND mint IN ({qs}) GROUP BY mint)""", (ts, ts - lookback_s, *chunk)):
            out[r["mint"]] = r
            lineage.saw("curve_obs", r["observed_at"])
    return out


def meta_demand(con, mints: list[str], as_of: int, lineage: Lineage) -> dict:
    qs = ",".join("?" * len(mints)) or "NULL"
    grads = rows(con, f"""SELECT mint, COALESCE(graduated_at, detected_at) AS at, detected_at, source
                          FROM graduations WHERE detected_at <= ? AND mint IN ({qs})""", (as_of, *mints))
    for g in grads:
        lineage.saw("graduations", g["detected_at"])
    names = {r["mint"]: r for r in rows(
        con, f"SELECT mint, name, symbol, created_at FROM tokens WHERE mint IN ({qs})", tuple(mints))}

    obs = _latest_obs(con, mints, as_of, lineage)
    bq = _latest_obs(con, mints, as_of, lineage, sources=("bitquery",))
    now_c = _curve_at(con, mints, as_of, CURRENT_S, lineage)
    prev_c = _curve_at(con, mints, as_of - H, 45 * 60, lineage)
    def s(field):
        return sum((o.get(field) or 0) for o in obs.values())

    buys, sells = s("buys_h1"), s("sells_h1")
    buyers, sellers = s("buyers_h1"), s("sellers_h1")
    vol24 = s("vol_h24")
    inflow = []
    for m, c in now_c.items():
        if c["real_sol"] is None:
            continue
        if m in prev_c and prev_c[m]["real_sol"] is not None:
            inflow.append(c["real_sol"] - prev_c[m]["real_sol"])
        elif (names.get(m, {}).get("created_at") or 0) > as_of - H:
            inflow.append(c["real_sol"])        # a fresh curve starts at 0 real SOL
    progress = sorted((c["progress"] for c in now_c.values() if c["progress"] is not None), reverse=True)
    top = sorted(obs.values(), key=lambda o: o.get("vol_h24") or 0, reverse=True)[:6]
    # real buy/sell USD: the chain stream reports it per token; Bitquery overrides when configured
    flow = bq or {m: o for m, o in obs.items() if o.get("buy_vol_h1") is not None}
    f_buy = sum(o.get("buy_vol_h1") or 0 for o in flow.values())
    f_sell = sum(o.get("sell_vol_h1") or 0 for o in flow.values())
    chain = [o for o in obs.values() if o.get("smart_buyers_h1") is not None]
    return {
        "tokens_tracked": len(obs),
        "unique_buyers_h1_sum": int(buyers), "unique_sellers_h1_sum": int(sellers),
        "unique_buyers_h24_sum": int(s("buyers_h24")),
        "buys_h1": int(buys), "sells_h1": int(sells),
        "buy_share_h1": round(buys / (buys + sells), 3) if buys + sells else None,
        "buyer_share_h1": round(buyers / (buyers + sellers), 3) if buyers + sellers else None,
        "vol_h1_usd": round(s("vol_h1"), 2), "vol_h24_usd": round(vol24, 2),
        "vol_h6_usd": round(s("vol_h6"), 2),
        "net_flow_usd_h1": round(f_buy - f_sell, 2) if flow else None,
        "net_flow_source": ("bitquery" if bq else "chain") if flow else None,
        "net_sol_h1": round(sum(o.get("net_sol_h1") or 0 for o in chain), 3) if chain else None,
        # wallet-level signals from the chain stream (None when no chain data in the window)
        "organic_buyers_h1_sum": sum(o.get("organic_buyers_h1") or 0 for o in chain) if chain else None,
        "smart_buyers_h1_sum": sum(o.get("smart_buyers_h1") or 0 for o in chain) if chain else None,
        "tokens_with_smart_buyers": sum((o.get("smart_buyers_h1") or 0) > 0 for o in chain) if chain else None,
        "tokens_dev_sold": sum((o.get("dev_sold_sol") or 0) >= 0.5 for o in chain) if chain else None,
        "curve_net_sol_1h": round(sum(inflow), 3) if inflow else None,
        "curve_tokens_compared": len(inflow),
        "curves_observed": len(now_c),
        "top_progress": [round(p, 3) for p in progress[:5]],
        "tokens_over_50pct": sum(p >= 0.5 for p in progress),
        "graduations_24h": sum(1 for g in grads if g["at"] and g["at"] > as_of - 24 * H),
        "graduations_total": len(grads),
        "top_token_share_vol24": round((top[0].get("vol_h24") or 0) / vol24, 3) if top and vol24 else None,
        "top_tokens": [{
            "mint": o["mint"], "symbol": names.get(o["mint"], {}).get("symbol"),
            "name": names.get(o["mint"], {}).get("name"),
            "age_h": round((as_of - names[o["mint"]]["created_at"]) / H, 1)
            if names.get(o["mint"], {}).get("created_at") else None,
            "vol_h1": o.get("vol_h1"), "vol_h24": o.get("vol_h24"), "buyers_h1": o.get("buyers_h1"),
            "sellers_h1": o.get("sellers_h1"), "mcap_usd": o.get("mcap_usd") or o.get("fdv_usd"),
            "chg_h1": o.get("chg_h1"), "progress": (now_c.get(o["mint"]) or {}).get("progress"),
            "smart_buyers_h1": o.get("smart_buyers_h1"), "organic_buyers_h1": o.get("organic_buyers_h1"),
            "net_sol_h1": o.get("net_sol_h1"), "dev_sold_sol": o.get("dev_sold_sol"),
            "graduated": any(g["mint"] == o["mint"] for g in grads), "observed_at": o["observed_at"],
        } for o in top],
    }


def attention(con, mints: list[str], as_of: int, lineage: Lineage) -> dict:
    if not mints:
        return {"boosts_24h": 0, "profiles_24h": 0}
    qs = ",".join("?" * len(mints))
    r = rows(con, f"""SELECT kind, COUNT(DISTINCT mint) AS n, MAX(observed_at) AS m FROM attention_obs
                      WHERE observed_at <= ? AND observed_at > ? AND mint IN ({qs}) GROUP BY kind""",
             (as_of, as_of - 24 * H, *mints))
    for x in r:
        lineage.saw("attention_obs", x["m"])
    d = {x["kind"]: x["n"] for x in r}
    return {"boosts_24h": d.get("boost", 0), "profiles_24h": d.get("profile", 0)}


def creator_history(con, mints: list[str], as_of: int, lineage: Lineage, window_s: int = 24 * H) -> dict:
    """Causal serial-deployer check (method from solana-launch-study): for each token with a
    known deployer, count that deployer's launches strictly before this one in the prior window."""
    if not mints:
        return {"known": 0, "serial_share": None}
    qs = ",".join("?" * len(mints))
    toks = rows(con, f"""SELECT mint, creator, created_at FROM tokens WHERE mint IN ({qs})
                         AND creator IS NOT NULL AND creator != 'unknown' AND first_seen_at <= ?""",
                (*mints, as_of))
    serial = 0
    for t in toks:
        prior = rows(con, """SELECT COUNT(*) AS n FROM tokens WHERE creator=? AND created_at < ?
                             AND created_at >= ? AND first_seen_at <= ?""",
                     (t["creator"], t["created_at"], t["created_at"] - window_s, as_of))[0]["n"]
        serial += prior >= 3
    lineage.saw("tokens", None, len(toks))
    return {"known": len(toks), "serial_share": round(serial / len(toks), 3) if toks else None}
