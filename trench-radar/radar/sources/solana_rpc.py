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


async def deployer(http: Http, url: str, mint: str) -> str | None:
    """Fee payer of the mint's earliest transaction (the create), if within 1000 sigs."""
    sigs = await _rpc(http, url, "getSignaturesForAddress", [mint, {"limit": 1000}])
    if not sigs or len(sigs) >= 1000:
        return None  # history too long to reach the create cheaply
    tx = await _rpc(http, url, "getTransaction",
                    [sigs[-1]["signature"], {"maxSupportedTransactionVersion": 1, "encoding": "json"}])
    if not tx:
        return None
    logs = (tx.get("meta") or {}).get("logMessages") or []
    if not any("Instruction: Create" in line for line in logs):
        return None
    return tx["transaction"]["message"]["accountKeys"][0]


async def wallet_activity(http: Http, url: str, wallet: str) -> dict:
    bal = await _rpc(http, url, "getBalance", [wallet])
    sigs = await _rpc(http, url, "getSignaturesForAddress", [wallet, {"limit": 100}])
    return {"sol_balance": (bal or {}).get("value", 0) / 10 ** SOL_DECIMALS,
            "recent_tx": len(sigs or [])}
