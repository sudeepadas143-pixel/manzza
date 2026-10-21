"""Decode pump.fun program events from Solana `logsSubscribe` notifications.

The pump program emits Anchor events as `Program data: <base64>` log lines. Layouts were
checked against live mainnet traffic (2026-10): reserves are consistent (virtual SOL = real
SOL + 30, virtual tokens = real tokens + 279.9M) and timestamps are within ~1s of receipt.
Fields appended to an event in later program versions are ignored, so a program upgrade
that only appends does not break decoding.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import struct

from .solana_rpc import INITIAL_REAL_TOKEN_RESERVES, PUMP_PROGRAM, b58encode

__all__ = ["PUMP_PROGRAM", "parse_notification", "decode_event", "progress_from_real_tokens"]


def _disc(name: str) -> bytes:
    return hashlib.sha256(f"event:{name}".encode()).digest()[:8]


TRADE, CREATE, COMPLETE = _disc("TradeEvent"), _disc("CreateEvent"), _disc("CompleteEvent")
LAMPORTS, TOKEN_UNITS = 1e9, 1e6
_TRADE_MIN = 8 + 32 + 16 + 1 + 32 + 40          # up to and including real_token_reserves
_TRADE_CREATOR_AT = _TRADE_MIN + 32 + 16        # after fee_recipient, fee_basis_points, fee


def progress_from_real_tokens(real_token_units: float) -> float:
    return max(0.0, min(1.0, 1 - real_token_units * TOKEN_UNITS / INITIAL_REAL_TOKEN_RESERVES))


def _str(b: bytes, o: int) -> tuple[str, int]:
    n = struct.unpack_from("<I", b, o)[0]
    if n > 512:
        raise ValueError("string too long")
    return b[o + 4:o + 4 + n].decode("utf-8", "replace"), o + 4 + n


def decode_event(b: bytes) -> dict | None:
    """One event payload -> dict, or None when it is not an event this app uses."""
    d = b[:8]
    try:
        if d == TRADE and len(b) >= _TRADE_MIN:
            o = 8
            mint = b58encode(b[o:o + 32]); o += 32
            sol, tok = struct.unpack_from("<QQ", b, o); o += 16
            is_buy = b[o] == 1; o += 1
            user = b58encode(b[o:o + 32]); o += 32
            ts, vsol, vtok, rsol, rtok = struct.unpack_from("<qQQQQ", b, o)
            creator = b58encode(b[_TRADE_CREATOR_AT:_TRADE_CREATOR_AT + 32]) if len(b) >= _TRADE_CREATOR_AT + 32 else None
            return {"type": "trade", "mint": mint, "sol": sol / LAMPORTS, "tokens": tok / TOKEN_UNITS,
                    "is_buy": is_buy, "user": user, "ts": ts, "v_sol": vsol / LAMPORTS,
                    "v_tokens": vtok / TOKEN_UNITS, "real_sol": rsol / LAMPORTS,
                    "real_tokens": rtok / TOKEN_UNITS, "creator": creator}
        if d == CREATE:
            o = 8
            name, o = _str(b, o)
            symbol, o = _str(b, o)
            uri, o = _str(b, o)
            mint, curve, user, creator = (b58encode(b[o + 32 * i:o + 32 * (i + 1)]) for i in range(4))
            o += 128
            (ts,) = struct.unpack_from("<q", b, o)
            return {"type": "create", "mint": mint, "name": name, "symbol": symbol, "uri": uri,
                    "bonding_curve": curve, "user": user, "creator": creator, "ts": ts}
        if d == COMPLETE and len(b) >= 8 + 96 + 8:
            return {"type": "complete", "user": b58encode(b[8:40]), "mint": b58encode(b[40:72]),
                    "bonding_curve": b58encode(b[72:104]), "ts": struct.unpack_from("<q", b, 104)[0]}
    except (struct.error, ValueError):
        return None
    return None


def parse_notification(raw: str) -> list[dict] | None:
    """A raw websocket message -> decoded events of a successful transaction.

    Returns None for non-notifications and failed transactions. Most messages are failed
    bot transactions, so they are rejected before JSON parsing."""
    if '"err":null' not in raw:
        return None
    try:
        v = json.loads(raw)["params"]["result"]["value"]
    except (KeyError, TypeError, ValueError):
        return None
    if v.get("err") is not None:
        return None
    out = []
    for line in v.get("logs") or ():
        if not line.startswith("Program data: "):
            continue
        try:
            ev = decode_event(base64.b64decode(line[14:]))
        except binascii.Error:      # the RPC truncates very long logs mid-line
            continue
        if ev:
            ev["sig"] = v.get("signature")
            out.append(ev)
    return out
