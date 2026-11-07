"""Collection jobs. Each one: call a source inside record_run, append observations."""
from __future__ import annotations

import logging

from .config import Settings
from .db import insert, now, one, rows
from .sources import misc, social
from .sources.base import Http, blocked_backoff, record_run
from .text import fingerprint, is_spam

log = logging.getLogger("radar.collect")

class Ctx:
    def __init__(self, con, settings: Settings, http: Http):
        self.con, self.s, self.http = con, settings, http


def tracked_tokens(con, limit: int) -> list[dict]:
    """Which tokens get refreshed: recent ones with traction first, then the newest."""
    t = now()
    cand = rows(con, """
        SELECT k.mint, k.pool, k.created_at,
               (SELECT MAX(COALESCE(o.buyers_h1,0)) FROM token_obs o WHERE o.mint=k.mint) AS buyers
        FROM tokens k
        WHERE k.pool IS NOT NULL AND k.created_at >= ? AND k.mint NOT IN (SELECT mint FROM graduations)
    """, (t - 36 * 3600,))
    cand.sort(key=lambda r: ((r["buyers"] or 0) >= 3, r["buyers"] or 0, r["created_at"] or 0), reverse=True)
    return cand[:limit]


async def collect_sol_price(ctx: Ctx) -> None:
    async with record_run(ctx.con, ctx.s, "defillama", "sol_price") as run:
        price = await misc.sol_price(ctx.http)
        insert(ctx.con, "market_obs", {"observed_at": now(), "metric": "sol_price_usd", "value": price,
                                       "source": "defillama", "detail": None})
        run.items = 1


async def collect_attention(ctx: Ctx) -> None:
    async with record_run(ctx.con, ctx.s, "dexscreener", "boosts_profiles") as run:
        items = await misc.dexscreener_attention(ctx.http)
        t = now()
        for it in items:
            insert(ctx.con, "attention_obs", {"observed_at": t, **it})
        run.items = len(items)
        ctx.con.commit()


async def collect_macro(ctx: Ctx) -> None:
    async with record_run(ctx.con, ctx.s, "defillama", "launchpad_volume") as run:
        series = await misc.defillama_volume(ctx.http)
        t = now()
        for key, pts in series.items():
            if len(pts) < 8:
                continue
            last7 = sum(v for _, v in pts[-8:-1]) / 7      # skip the partial current day
            last30 = sum(v for _, v in pts[-31:-1]) / max(1, len(pts[-31:-1]))
            insert(ctx.con, "market_obs", {"observed_at": t, "metric": f"{key}_vol_7d_avg", "value": last7,
                                           "source": "defillama", "detail": None})
            insert(ctx.con, "market_obs", {"observed_at": t, "metric": f"{key}_vol_30d_avg", "value": last30,
                                           "source": "defillama", "detail": None})
            insert(ctx.con, "market_obs", {"observed_at": t, "metric": f"{key}_vol_daily",
                                           "value": pts[-2][1], "source": "defillama",
                                           "detail": str([[d, round(v)] for d, v in pts[-31:]])})
            run.items += 1
        ctx.con.commit()


def _store_posts(ctx: Ctx, posts: list[dict]) -> int:
    t = now()
    n = 0
    for p in posts:
        if not p.get("created_at"):
            continue
        p = {**p, "collected_at": t, "fingerprint": fingerprint(p["text"]), "is_spam": int(is_spam(p, t))}
        n += insert(ctx.con, "social_posts", p, or_ignore=True)
    ctx.con.commit()
    return n


async def collect_social(ctx: Ctx) -> None:
    for q in ctx.s.x_queries:
        async with record_run(ctx.con, ctx.s, "x_api", "recent_search") as run:
            if not ctx.s.x_bearer_token:
                run.skip("X_BEARER_TOKEN not set")
                continue
            # X bills per post returned (pay-per-use), so reads are capped per UTC day.
            day_start = now() - now() % 86400
            used = one(ctx.con, "SELECT COUNT(*) AS n FROM social_posts WHERE source='x' AND collected_at >= ?",
                       (day_start,))["n"]
            remaining = ctx.s.x_daily_read_budget - used
            if remaining < 10:
                run.skip(f"daily X read budget reached ({used}/{ctx.s.x_daily_read_budget})")
                continue
            last = one(ctx.con, "SELECT MAX(CAST(substr(id,3) AS INTEGER)) AS m FROM social_posts "
                                "WHERE source='x' AND query=?", (q,))
            since = str(last["m"]) if last and last["m"] else None
            per_call = max(10, min(ctx.s.x_max_results, remaining))
            run.items = _store_posts(ctx, await social.x_recent_search(
                ctx.http, ctx.s.x_bearer_token, q, since, max_results=per_call))
    async with record_run(ctx.con, ctx.s, "reddit", "new_posts") as run:
        if not ctx.s.reddit_client_id and (why := blocked_backoff(ctx.con, "reddit", "new_posts")):
            run.skip(why + " (set REDDIT_CLIENT_ID/SECRET for OAuth access)")
            return
        run.items = _store_posts(ctx, await social.reddit_new(
            ctx.http, ctx.s.reddit_client_id, ctx.s.reddit_client_secret, ctx.s.reddit_subreddits))


async def collect_bitquery(ctx: Ctx) -> None:
    async with record_run(ctx.con, ctx.s, "bitquery", "net_flow") as run:
        if not ctx.s.bitquery_token:
            run.skip("BITQUERY_TOKEN not set")
            return
        from datetime import datetime, timezone
        tracked = tracked_tokens(ctx.con, 100)
        since = datetime.fromtimestamp(now() - 3600, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        flow = await misc.bitquery_flow(ctx.http, ctx.s.bitquery_token, [r["mint"] for r in tracked], since)
        t = now()
        for mint, f in flow.items():
            insert(ctx.con, "token_obs", {"mint": mint, "observed_at": t, "source": "bitquery",
                                          "buy_vol_h1": f["buy_usd"], "sell_vol_h1": f["sell_usd"],
                                          "buyers_h1": int(f["buyers"]), "sellers_h1": int(f["sellers"])})
            run.items += 1
        ctx.con.commit()


async def label_outcomes(ctx: Ctx, horizons=(6, 24)) -> None:
    """Outcome labels for matured tokens: graduation and curve bucket for all (RPC batch),
    price path from the live stream's curve snapshots. Labels are only ever used as
    backtest targets, never as features."""
    from .analytics.outcomes import label_batch
    async with record_run(ctx.con, ctx.s, "outcomes", "label") as run:
        run.items = await label_batch(ctx, horizons)
