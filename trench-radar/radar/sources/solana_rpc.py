"""Solana JSON-RPC: pump.fun bonding-curve state and deployer wallets.

Decoder adapted from Chrisymcsoup/solana-launch-study (MIT), outcome_tracker.py:
verify the Anchor discriminator, read `complete` BEFORE treating zero virtual
reserves as an error (migration zeroes them — rejecting first silently drops
every graduated token), ignore trailing bytes so appended fields don't break it.
"""
from __future__ import annotations

import base64
import hashlib
import struct

from .base import Http, SourceUnavailable

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BONDING_CURVE_DISC = hashlib.sha256(b"account:BondingCurve").digest()[:8]
TOKEN_DECIMALS = 6
SOL_DECIMALS = 9
# Real token reserves a fresh pump.fun curve starts with (793.1M tokens, 6 dp).
INITIAL_REAL_TOKEN_RESERVES = 793_100_000 * 10 ** TOKEN_DECIMALS

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = _B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def decode_bonding_curve(b64: str) -> tuple[dict | None, str | None]:
    buf = base64.b64decode(b64)
    if buf[:8] != BONDING_CURVE_DISC:
        return None, "discriminator_mismatch"
    if len(buf) < 8 + 40 + 1:
        return None, "too_short"
    vtok, vsol, rtok, rsol, supply = struct.unpack_from("<QQQQQ", buf, 8)
    complete = bool(buf[48])
    price_sol = ((vsol / 10 ** SOL_DECIMALS) / (vtok / 10 ** TOKEN_DECIMALS)) if vtok else None
    if complete:
        progress = 1.0
    else:
        progress = max(0.0, min(1.0, 1 - rtok / INITIAL_REAL_TOKEN_RESERVES))
    return {
        "real_sol": rsol / 10 ** SOL_DECIMALS,
        "real_token_reserves": rtok / 10 ** TOKEN_DECIMALS,
        "progress": progress,
        "complete": complete,
        "price_sol": price_sol,
    }, None


async def _rpc(http: Http, url: str, method: str, params: list):
    payload = await http.post_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in payload:
        raise SourceUnavailable(f"rpc {method}: {payload['error'].get('message', '')[:120]}")
    return payload.get("result")


async def bonding_curves(http: Http, url: str, curve_by_mint: dict[str, str]) -> dict[str, dict]:
    """mint -> decoded curve (or {'error': ...}). Batches of 100 via getMultipleAccounts."""
    mints = list(curve_by_mint)
    out: dict[str, dict] = {}
    for i in range(0, len(mints), 100):
        chunk = mints[i:i + 100]
        res = await _rpc(http, url, "getMultipleAccounts",
                         [[curve_by_mint[m] for m in chunk], {"encoding": "base64"}])
        for mint, acc in zip(chunk, (res or {}).get("value") or []):
            if not acc:
                out[mint] = {"error": "missing_account"}
                continue
            if acc.get("owner") != PUMP_PROGRAM:
                out[mint] = {"error": "not_pump_curve"}
                continue
            dec, err = decode_bonding_curve(acc["data"][0])
            out[mint] = dec if dec else {"error": err}
    return out


# ---------------------------------------------------------------- PumpSwap pools (after graduation)

PUMP_AMM_PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
POOL_DISC = hashlib.sha256(b"account:Pool").digest()[:8]
WSOL_MINT = "So11111111111111111111111111111111111111112"


def decode_pool(b64: str) -> dict | None:
    """Pool account per pump.fun's pump_amm IDL. `virtual_quote_reserves` is a signed i128
    that is negative while fees wait in the quote vault; pools created before the field
    existed decode with 0."""
    buf = base64.b64decode(b64)
    if buf[:8] != POOL_DISC or len(buf) < 211:
        return None
    k = lambda o: b58encode(buf[o:o + 32])  # noqa: E731
    vq = int.from_bytes(buf[245:261], "little", signed=True) if len(buf) >= 261 else 0
    return {"base_mint": k(43), "quote_mint": k(75), "base_vault": k(139), "quote_vault": k(171),
            "virtual_quote_reserves": vq}


async def pumpswap_prices(http: Http, url: str, pool_by_mint: dict[str, str]) -> dict[str, dict]:
    """mint -> {price_sol, quote_sol, base_tokens} for SOL-quoted PumpSwap pools.

    price = (quote vault + virtual_quote_reserves) / base vault, the "effective reserves"
    pump.fun documents (NEGATIVE_VIRTUAL_QUOTE_RESERVES.md); the raw vault balance includes
    fees waiting to be swept and would overstate liquidity."""
    mints = list(pool_by_mint)
    pools: dict[str, dict] = {}
    for i in range(0, len(mints), 100):
        chunk = mints[i:i + 100]
        res = await _rpc(http, url, "getMultipleAccounts", [[pool_by_mint[m] for m in chunk], {"encoding": "base64"}])
        for mint, acc in zip(chunk, (res or {}).get("value") or []):
            if acc and acc.get("owner") == PUMP_AMM_PROGRAM:
                p = decode_pool(acc["data"][0])
                if p and p["base_mint"] == mint and p["quote_mint"] == WSOL_MINT:
                    pools[mint] = p
    vaults = [v for p in pools.values() for v in (p["base_vault"], p["quote_vault"])]
    bal: dict[str, int] = {}
    for i in range(0, len(vaults), 100):
        chunk = vaults[i:i + 100]
        res = await _rpc(http, url, "getMultipleAccounts", [chunk, {"encoding": "jsonParsed"}])
        for addr, acc in zip(chunk, (res or {}).get("value") or []):
            amt = ((((acc or {}).get("data") or {}).get("parsed") or {}).get("info") or {}).get("tokenAmount") or {}
            if amt.get("amount") is not None:
                bal[addr] = int(amt["amount"])
    out = {}
    for mint, p in pools.items():
        base, quote = bal.get(p["base_vault"]), bal.get(p["quote_vault"])
        if not base or quote is None:
            continue
        q = max(0, quote + p["virtual_quote_reserves"]) / 10 ** SOL_DECIMALS
        b = base / 10 ** TOKEN_DECIMALS
        out[mint] = {"price_sol": q / b, "quote_sol": q, "base_tokens": b}
    return out
