"""Collection jobs. Each one: call a source inside record_run, append observations."""
from __future__ import annotations

import logging
import random

from .config import Settings
from .db import insert, now, one, rows
from .sources import geckoterminal as gt
from .sources import misc, social, solana_rpc
from .sources.base import Http, blocked_backoff, record_run
from .text import fingerprint, is_spam

log = logging.getLogger("radar.collect")

OBS_FIELDS = ("price_usd", "mcap_usd", "fdv_usd", "liquidity_usd", "vol_m5", "vol_h1", "vol_h6", "vol_h24",
              "buys_h1", "sells_h1", "buyers_h1", "sellers_h1", "buys_h24", "sells_h24", "buyers_h24",
              "sellers_h24", "chg_h1", "chg_h24")


class Ctx:
    def __init__(self, con, settings: Settings, http: Http):
        self.con, self.s, self.http = con, settings, http


def _store_pools(ctx: Ctx, pools: list[dict], source: str) -> dict:
    """Upsert tokens, append token_obs, register PumpSwap graduations of pump tokens."""
    t = now()
    stats = {"new_tokens": 0, "obs": 0, "graduations": 0}
    for p in pools:
        if not p.get("quote_is_sol"):
            continue
        dex = p["dex"]
        if dex == "pump-fun":
            stats["new_tokens"] += insert(ctx.con, "tokens", {
                "mint": p["mint"], "name": p["name"], "symbol": p["symbol"], "pool": p["pool"],
                "launchpad": "pump-fun", "created_at": p["pool_created_at"], "first_seen_at": t,
                "source": source}, or_ignore=True)
        elif dex == "pumpswap" and p["mint"].endswith("pump"):
            # PumpSwap pool for a pump.fun mint: the token graduated at pool creation.
            # Launch time is unknown unless we saw the curve earlier.
            known = one(ctx.con, "SELECT mint FROM tokens WHERE mint=?", (p["mint"],))
            if not known:
                insert(ctx.con, "tokens", {
                    "mint": p["mint"], "name": p["name"], "symbol": p["symbol"], "pool": None,
                    "launchpad": "pump-fun", "created_at": None, "first_seen_at": t, "source": source},
                    or_ignore=True)
            stats["graduations"] += insert(ctx.con, "graduations", {
                "mint": p["mint"], "detected_at": t, "graduated_at": p["pool_created_at"],
                "source": "pumpswap_pool", "pool": p["pool"]}, or_ignore=True)
        else:
            continue
        insert(ctx.con, "token_obs", {"mint": p["mint"], "observed_at": t, "source": source,
                                      "dex": dex, "pool": p["pool"], **{k: p.get(k) for k in OBS_FIELDS}})
        stats["obs"] += 1
    ctx.con.commit()
    return stats


async def collect_launches(ctx: Ctx) -> None:
    async with record_run(ctx.con, ctx.s, "geckoterminal", "new_pools") as run:
        pools = await gt.new_pools(ctx.http, pages=9)
        st = _store_pools(ctx, pools, "gt_new_pools")
        run.items = st["obs"]
        sol = [p["sol_price"] for p in pools if p.get("sol_price")]
        if sol:
            insert(ctx.con, "market_obs", {"observed_at": now(), "metric": "sol_price_usd",
                                           "value": sol[0], "source": "geckoterminal", "detail": None})
        # How far back did 9 pages reach? Needed to judge launch-count coverage.
        created = [p["pool_created_at"] for p in pools if p.get("pool_created_at")]
        if created:
            insert(ctx.con, "market_obs", {"observed_at": now(), "metric": "new_pools_span_s",
                                           "value": max(created) - min(created), "source": "geckoterminal",
                                           "detail": None})
        ctx.con.commit()


async def collect_active(ctx: Ctx) -> None:
    async with record_run(ctx.con, ctx.s, "geckoterminal", "active_pools") as run:
        pools = await gt.dex_pools(ctx.http, "pump-fun", pages=3)
        pools += await gt.dex_pools(ctx.http, "pumpswap", pages=1, sort="h24_volume_usd_desc")
        st = _store_pools(ctx, pools, "gt_active")
        run.items = st["obs"]
        # snapshot of the top-traded bonding-curve tokens = "new tokens with traction"
        pf = [p for p in pools if p["dex"] == "pump-fun"]
        if pf:
            t = now()
            ages = [(t - p["pool_created_at"]) / 3600 for p in pf if p.get("pool_created_at")]
            chg = sorted(p["chg_h24"] for p in pf if p.get("chg_h24") is not None)
            insert(ctx.con, "market_obs", {"observed_at": t, "metric": "active_share_under_24h",
                                           "value": sum(a < 24 for a in ages) / max(1, len(ages)),
                                           "source": "geckoterminal", "detail": f"n={len(ages)}"})
            if chg:
                insert(ctx.con, "market_obs", {"observed_at": t, "metric": "active_median_chg_h24",
                                               "value": chg[len(chg) // 2], "source": "geckoterminal",
                                               "detail": f"n={len(chg)}"})
            insert(ctx.con, "market_obs", {"observed_at": t, "metric": "active_top80_vol_h24",
                                           "value": sum(p.get("vol_h24") or 0 for p in pf),
                                           "source": "geckoterminal", "detail": f"n={len(pf)}"})
            ctx.con.commit()


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


async def refresh_tracked(ctx: Ctx) -> None:
    async with record_run(ctx.con, ctx.s, "geckoterminal", "refresh") as run:
        tracked = tracked_tokens(ctx.con, min(ctx.s.max_tracked_tokens, 300))
        pools = await gt.pools_multi(ctx.http, [r["pool"] for r in tracked])
        run.items = _store_pools(ctx, pools, "gt_refresh")["obs"]


async def collect_curves(ctx: Ctx) -> None:
    async with record_run(ctx.con, ctx.s, "solana_rpc", "bonding_curves") as run:
        tracked = tracked_tokens(ctx.con, ctx.s.max_tracked_tokens)
        curves = await solana_rpc.bonding_curves(ctx.http, ctx.s.solana_rpc_url,
                                                 {r["mint"]: r["pool"] for r in tracked})
        t = now()
        for mint, c in curves.items():
            if "error" in c:
                continue
            insert(ctx.con, "curve_obs", {"mint": mint, "observed_at": t, "real_sol": c["real_sol"],
                                          "real_token_reserves": c["real_token_reserves"],
                                          "progress": c["progress"], "complete": int(c["complete"]),
                                          "price_sol": c["price_sol"]})
            if c["complete"]:
                insert(ctx.con, "graduations", {"mint": mint, "detected_at": t, "graduated_at": None,
                                                "source": "curve_complete", "pool": None}, or_ignore=True)
            run.items += 1
        ctx.con.commit()


async def collect_deployers(ctx: Ctx, max_lookups: int = 12) -> None:
    """Deployer = fee payer of the create tx. 2 RPC calls per token, so only top tokens."""
    async with record_run(ctx.con, ctx.s, "solana_rpc", "deployers") as run:
        todo = rows(ctx.con, """
            SELECT k.mint FROM tokens k JOIN token_obs o ON o.mint=k.mint
            WHERE k.creator IS NULL AND k.created_at >= ? AND o.observed_at >= ?
            GROUP BY k.mint ORDER BY MAX(COALESCE(o.buyers_h1,0)) DESC LIMIT ?
        """, (now() - 24 * 3600, now() - 3600, max_lookups))
        for r in todo:
            dep = await solana_rpc.deployer(ctx.http, ctx.s.solana_rpc_url, r["mint"])
            ctx.con.execute("UPDATE tokens SET creator=? WHERE mint=?", (dep or "unknown", r["mint"]))
            if dep:
                act = await solana_rpc.wallet_activity(ctx.http, ctx.s.solana_rpc_url, dep)
                insert(ctx.con, "creator_obs", {"creator": dep, "observed_at": now(), **act})
                run.items += 1
        ctx.con.commit()


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


async def collect_pumpfun(ctx: Ctx) -> None:
    """Optional enrichment (creator + description). Expect 'unavailable' from datacenters."""
    async with record_run(ctx.con, ctx.s, "pumpfun", "latest_coins") as run:
        if why := blocked_backoff(ctx.con, "pumpfun", "latest_coins"):
            run.skip(why)
            return
        coins = await misc.pumpfun_latest(ctx.http)
        for c in coins:
            if not c.get("mint"):
                continue
            insert(ctx.con, "tokens", {"mint": c["mint"], "name": c["name"], "symbol": c["symbol"],
                                       "creator": c["creator"], "uri": c["uri"], "pool": None,
                                       "launchpad": "pump-fun", "created_at": c["created_at"],
                                       "first_seen_at": now(), "source": "pumpfun"}, or_ignore=True)
            ctx.con.execute("UPDATE tokens SET creator=COALESCE(creator, ?) WHERE mint=?",
                            (c["creator"], c["mint"]))
            run.items += 1
        ctx.con.commit()


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


async def label_outcomes(ctx: Ctx, horizons=(6, 24), max_price_lookups: int = 25) -> None:
    """Outcome labels for matured tokens. Graduation/curve bucket for all (cheap, RPC batch);
    price path for a sample via OHLCV (1 GeckoTerminal call each). Labels are only ever used
    as backtest targets, never as features."""
    from .analytics.outcomes import label_batch
    async with record_run(ctx.con, ctx.s, "outcomes", "label") as run:
        run.items = await label_batch(ctx, horizons, max_price_lookups, rng=random.Random())
