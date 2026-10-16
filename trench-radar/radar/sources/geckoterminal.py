"""GeckoTerminal public API (no key, ~30 req/min).

Verified 2026-10-16: the `pump-fun` dex lists bonding-curve pools whose pool
address is the pump.fun BondingCurve PDA; `pumpswap` lists post-graduation AMM
pools. Per-pool `transactions` carry buys/sells AND unique buyers/sellers for
m5/m15/m30/h1/h6/h24 windows. `new_pools` serves 20 pools/page, 10 pages max
(page 10 is empty in practice), which covers roughly the last 4 minutes.
"""
from __future__ import annotations

from datetime import datetime

from .base import Http, SourceUnavailable

BASE = "https://api.geckoterminal.com/api/v2/networks/solana"
SOL_MINT = "So11111111111111111111111111111111111111112"


def _f(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _ts(s: str | None) -> int | None:
    if not s:
        return None
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def parse_pools(payload: dict) -> list[dict]:
    """Normalise a GeckoTerminal pools payload (with include=base_token)."""
    tokens = {}
    for inc in payload.get("included", []) or []:
        if inc.get("type") == "token":
            a = inc.get("attributes", {})
            tokens[inc["id"]] = {"name": a.get("name"), "symbol": a.get("symbol"), "mint": a.get("address")}
    out = []
    for p in payload.get("data", []) or []:
        a = p.get("attributes", {})
        rel = p.get("relationships", {})
        base_id = (rel.get("base_token", {}).get("data") or {}).get("id", "")
        quote_id = (rel.get("quote_token", {}).get("data") or {}).get("id", "")
        dex = (rel.get("dex", {}).get("data") or {}).get("id")
        mint = base_id.split("_", 1)[1] if "_" in base_id else None
        if not mint or mint == SOL_MINT:
            continue
        tok = tokens.get(base_id, {})
        name = tok.get("name")
        symbol = tok.get("symbol") or (a.get("name") or "").split(" / ")[0] or None
        tx = a.get("transactions") or {}
        vol = a.get("volume_usd") or {}
        chg = a.get("price_change_percentage") or {}
        h1, h24 = tx.get("h1") or {}, tx.get("h24") or {}
        out.append({
            "mint": mint, "pool": a.get("address"), "dex": dex,
            "quote_is_sol": quote_id.endswith(SOL_MINT),
            "sol_price": _f(a.get("quote_token_price_usd")) if quote_id.endswith(SOL_MINT) else None,
            "name": name, "symbol": symbol,
            "pool_created_at": _ts(a.get("pool_created_at")),
            "price_usd": _f(a.get("base_token_price_usd")),
            "mcap_usd": _f(a.get("market_cap_usd")),
            "fdv_usd": _f(a.get("fdv_usd")),
            "liquidity_usd": _f(a.get("reserve_in_usd")),
            "vol_m5": _f(vol.get("m5")), "vol_h1": _f(vol.get("h1")),
            "vol_h6": _f(vol.get("h6")), "vol_h24": _f(vol.get("h24")),
            "buys_h1": h1.get("buys"), "sells_h1": h1.get("sells"),
            "buyers_h1": h1.get("buyers"), "sellers_h1": h1.get("sellers"),
            "buys_h24": h24.get("buys"), "sells_h24": h24.get("sells"),
            "buyers_h24": h24.get("buyers"), "sellers_h24": h24.get("sellers"),
            "chg_h1": _f(chg.get("h1")), "chg_h24": _f(chg.get("h24")),
        })
    return out


async def new_pools(http: Http, pages: int = 9) -> list[dict]:
    out: list[dict] = []
    for page in range(1, pages + 1):
        try:
            payload = await http.get_json(f"{BASE}/new_pools?page={page}&include=base_token")
        except SourceUnavailable:
            if out:          # keep the pages we already have
                break
            raise
        batch = parse_pools(payload)
        if not batch:
            break
        out.extend(batch)
    return out


async def dex_pools(http: Http, dex: str, pages: int = 4, sort: str = "h24_tx_count_desc") -> list[dict]:
    out: list[dict] = []
    for page in range(1, pages + 1):
        try:
            payload = await http.get_json(f"{BASE}/dexes/{dex}/pools?page={page}&sort={sort}&include=base_token")
        except SourceUnavailable:
            if out:
                break
            raise
        batch = parse_pools(payload)
        if not batch:
            break
        out.extend(batch)
    return out


async def pools_multi(http: Http, pool_addresses: list[str]) -> list[dict]:
    out: list[dict] = []
    for i in range(0, len(pool_addresses), 30):
        chunk = ",".join(pool_addresses[i:i + 30])
        try:
            payload = await http.get_json(f"{BASE}/pools/multi/{chunk}?include=base_token")
        except SourceUnavailable:
            if out:          # rate-limited part-way: keep what we have, the rest waits for next run
                break
            raise
        out.extend(parse_pools(payload))
    return out


async def ohlcv(http: Http, pool: str, timeframe: str = "minute", aggregate: int = 5,
                limit: int = 300, before_ts: int | None = None) -> list[tuple]:
    """[(ts, open, high, low, close, volume_usd)] newest first."""
    url = f"{BASE}/pools/{pool}/ohlcv/{timeframe}?aggregate={aggregate}&limit={limit}&currency=usd"
    if before_ts:
        url += f"&before_timestamp={before_ts}"
    payload = await http.get_json(url)
    lst = ((payload.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    return [tuple(x) for x in lst]
