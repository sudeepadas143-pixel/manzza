"""Smaller adapters: DexScreener, DefiLlama, pump.fun (optional), Bitquery (optional)."""
from __future__ import annotations

from .base import Http, SourceUnavailable


# ---------------------------------------------------------------- DexScreener (no key)

async def dexscreener_attention(http: Http) -> list[dict]:
    """Solana tokens that just bought a boost or a profile — attention being purchased."""
    out = []
    for kind, path in (("boost", "token-boosts/latest/v1"), ("profile", "token-profiles/latest/v1")):
        data = await http.get_json(f"https://api.dexscreener.com/{path}")
        for item in data if isinstance(data, list) else []:
            if item.get("chainId") != "solana" or not item.get("tokenAddress"):
                continue
            try:
                amount = float(item.get("totalAmount") or item.get("amount") or 0) or None
            except ValueError:
                amount = None
            out.append({
                "mint": item["tokenAddress"], "kind": kind, "amount": amount,
                "description": (item.get("description") or "")[:500],
                "links": len(item.get("links") or []),
            })
    return out


# ---------------------------------------------------------------- DefiLlama (no key)

LLAMA_PROTOCOLS = {"pumpfun_launchpad": "pump.fun", "pumpswap": "pumpswap"}


async def defillama_volume(http: Http) -> dict[str, list[tuple[int, float]]]:
    """Daily volume series per protocol: {key: [(day_ts, usd), ...]} (last 60 days)."""
    out = {}
    for key, slug in LLAMA_PROTOCOLS.items():
        data = await http.get_json(
            f"https://api.llama.fi/summary/dexs/{slug}?excludeTotalDataChart=false&dataType=dailyVolume")
        chart = data.get("totalDataChart") or []
        out[key] = [(int(t), float(v)) for t, v in chart[-60:]]
    return out


# ---------------------------------------------------------------- pump.fun (optional)

PUMP_API = "https://frontend-api-v3.pump.fun"


async def pumpfun_latest(http: Http, limit: int = 50) -> list[dict]:
    """Often Cloudflare-blocked from datacenter IPs; caller treats that as unavailable."""
    data = await http.get_json(
        f"{PUMP_API}/coins?offset=0&limit={limit}&sort=created_timestamp&order=DESC&includeNsfw=false",
        retries=0)
    out = []
    for c in data if isinstance(data, list) else []:
        out.append({
            "mint": c.get("mint"), "name": c.get("name"), "symbol": c.get("symbol"),
            "creator": c.get("creator"), "uri": c.get("metadata_uri") or c.get("uri"),
            "created_at": int((c.get("created_timestamp") or 0) / 1000) or None,
            "description": (c.get("description") or "")[:500],
            "reply_count": c.get("reply_count"),
        })
    return out


# ---------------------------------------------------------------- Bitquery (optional, key)

BITQUERY_URL = "https://streaming.bitquery.io/graphql"

# Written against the DEXTradeByTokens schema documented in bitquery/Pump-Fun-API.
# Not exercised live (no token in the build environment) — see docs/SETUP.md.
BITQUERY_FLOW = """
query ($mints: [String!], $since: DateTime) {
  Solana {
    DEXTradeByTokens(
      where: {Trade: {Currency: {MintAddress: {in: $mints}}},
              Block: {Time: {since: $since}},
              Transaction: {Result: {Success: true}}}
    ) {
      Trade { Currency { MintAddress } }
      buy_usd: sum(of: Trade_Side_AmountInUSD, if: {Trade: {Side: {Type: {is: buy}}}})
      sell_usd: sum(of: Trade_Side_AmountInUSD, if: {Trade: {Side: {Type: {is: sell}}}})
      buyers: count(distinct: Trade_Account_Owner, if: {Trade: {Side: {Type: {is: buy}}}})
      sellers: count(distinct: Trade_Account_Owner, if: {Trade: {Side: {Type: {is: sell}}}})
    }
  }
}
"""


async def bitquery_flow(http: Http, token: str | None, mints: list[str], since_iso: str) -> dict[str, dict]:
    if not token:
        raise SourceUnavailable("BITQUERY_TOKEN not set")
    data = await http.post_json(
        BITQUERY_URL, {"query": BITQUERY_FLOW, "variables": {"mints": mints, "since": since_iso}},
        headers={"Authorization": f"Bearer {token}"})
    if data.get("errors"):
        raise SourceUnavailable(f"bitquery: {str(data['errors'])[:200]}")
    out = {}
    for row in ((data.get("data") or {}).get("Solana") or {}).get("DEXTradeByTokens") or []:
        mint = row["Trade"]["Currency"]["MintAddress"]
        out[mint] = {k: float(row.get(k) or 0) for k in ("buy_usd", "sell_usd", "buyers", "sellers")}
    return out
