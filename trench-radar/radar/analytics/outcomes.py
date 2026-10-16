"""Outcome labels for matured tokens (targets for the backtest — never features).

Two separate questions, kept separate on purpose (solana-launch-study's main lesson):
  graduated   — did the bonding curve complete?  (RPC curve state / PumpSwap pool)
  ret_end     — what happened to the price from its first observed candle to the horizon?
A token can graduate and still lose money for anyone who bought after the first minutes.
"""
from __future__ import annotations

import random

from ..db import insert, now, rows
from ..sources import geckoterminal as gt
from ..sources import solana_rpc
from ..sources.base import SourceUnavailable

H = 3600


def bucket(real_sol: float | None, complete: bool) -> str:
    """Same thresholds as solana-launch-study's outcome_tracker."""
    if complete:
        return "migrated"
    if real_sol is None:
        return "unknown"
    if real_sol >= 5:
        return "alive"
    if real_sol >= 0.5:
        return "weak"
    return "dead"


def price_path(candles: list[tuple], created_at: int, horizon_h: int) -> dict | None:
    """From OHLCV candles (any order): first open after launch, close at horizon, max high in between."""
    end_ts = created_at + horizon_h * H
    pts = sorted(c for c in candles if created_at - 300 <= c[0] <= end_ts)
    if len(pts) < 2:
        return None
    first = pts[0][1]
    end = pts[-1][4]
    hi = max(c[2] for c in pts)
    if not first or first <= 0:
        return None
    if end_ts - pts[-1][0] > 2 * H:
        end = None          # no trades near the horizon; the end price is unknown, not the last trade
    return {"first_price": first, "end_price": end, "max_price": hi,
            "ret_end": (end / first - 1) if end else None, "ret_max": hi / first - 1}


async def label_batch(ctx, horizons=(6, 24), max_price_lookups: int = 25, rng: random.Random | None = None) -> int:
    rng = rng or random.Random()
    t = now()
    labelled = 0
    for hz in horizons:
        due = rows(ctx.con, """SELECT k.mint, k.pool, k.created_at FROM tokens k
            LEFT JOIN token_outcomes o ON o.mint=k.mint AND o.horizon_h=?
            WHERE o.mint IS NULL AND k.pool IS NOT NULL AND k.created_at <= ? AND k.created_at > ?
            ORDER BY k.created_at LIMIT 2000""", (hz, t - hz * H, t - (hz + 48) * H))
        if not due:
            continue
        curves = await solana_rpc.bonding_curves(ctx.http, ctx.s.solana_rpc_url, {r["mint"]: r["pool"] for r in due})
        grads = {g["mint"]: g for g in rows(ctx.con, "SELECT mint, pool, COALESCE(graduated_at, detected_at) AS at FROM graduations")}
        # price paths for a random sample (bounded API budget); unbiased across the cohort
        sample = set(r["mint"] for r in rng.sample(due, min(max_price_lookups, len(due))))
        for r in due:
            c = curves.get(r["mint"]) or {}
            g = grads.get(r["mint"])
            graduated_by_h = bool(g and g["at"] and g["at"] <= r["created_at"] + hz * H)
            # curve state is read *now*; if now is far past the horizon it can include later graduations
            late_read = t - (r["created_at"] + hz * H) > 6 * H
            row = {"mint": r["mint"], "horizon_h": hz, "evaluated_at": t,
                   "graduated": int(graduated_by_h or (bool(c.get("complete")) and not late_read)),
                   "bucket": bucket(c.get("real_sol"), bool(c.get("complete"))) if not late_read else "unknown",
                   "source": "rpc+graduations"}
            if r["mint"] in sample:
                try:
                    before = r["created_at"] + hz * H + 900
                    candles = await gt.ohlcv(ctx.http, r["pool"], "minute", 15, 1000, before_ts=before)
                    if g and g.get("pool"):   # after graduation trading moves to the PumpSwap pool
                        candles += await gt.ohlcv(ctx.http, g["pool"], "minute", 15, 1000, before_ts=before)
                    pp = price_path(candles, r["created_at"], hz)
                    if pp:
                        row.update(pp)
                        row["source"] += "+ohlcv"
                except SourceUnavailable:
                    pass
            insert(ctx.con, "token_outcomes", row, or_replace=True)
            labelled += 1
        ctx.con.commit()
    return labelled
