"""Outcome labels for matured tokens (targets for the backtest — never features).

Two separate questions, kept separate on purpose (solana-launch-study's main lesson):
  graduated   — did the bonding curve complete?  (RPC curve state / PumpSwap pool)
  ret_end     — what happened to the price from its first observation to the horizon?
                (bonding-curve price from the live stream's snapshots; after graduation the
                price is unknown and left empty rather than guessed)
A token can graduate and still lose money for anyone who bought after the first minutes.
"""
from __future__ import annotations

from ..db import insert, now, rows
from ..sources import solana_rpc

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


async def label_batch(ctx, horizons=(6, 24)) -> int:
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
            snaps = rows(ctx.con, """SELECT observed_at, price_sol FROM curve_obs WHERE mint=? AND price_sol > 0
                                     AND observed_at <= ?""", (r["mint"], r["created_at"] + hz * H))
            pp = price_path([(s["observed_at"],) + (s["price_sol"],) * 4 for s in snaps], r["created_at"], hz)
            if pp:
                if graduated_by_h:
                    pp.update(end_price=None, ret_end=None)   # traded on PumpSwap after graduation: not observed
                row.update(pp)
                row["source"] += "+curve"
            insert(ctx.con, "token_outcomes", row, or_replace=True)
            labelled += 1
        ctx.con.commit()
    return labelled
