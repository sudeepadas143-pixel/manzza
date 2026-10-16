"""Synthetic fixtures. Everything here is fabricated test data and lives only in temp DBs."""
from __future__ import annotations

import random

import pytest

from radar.config import Settings
from radar.db import connect, insert

H = 3600
T0 = 1_790_000_000          # fixed "now" for deterministic tests


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(
        db_path=tmp_path / "t.db", solana_rpc_url="https://api.mainnet-beta.solana.com",
        x_bearer_token=None, x_queries=["q"], bitquery_token=None, anthropic_api_key=None,
        analyst_model="claude-opus-5-5", telegram_bot_token=None, telegram_chat_id=None,
        reddit_client_id=None, reddit_client_secret=None, reddit_subreddits=["solana"],
        dashboard_host="127.0.0.1", dashboard_port=0, dashboard_token=None,
        intervals={}, report_times_utc=[], x_daily_read_budget=1000, x_max_results=25,
    )
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


def build_history(con, now_ts: int = T0, hours: int = 40, seed: int = 1, surge: str = "frog") -> None:
    """40h of launches at a steady background rate, with `surge` launches ramping in the last 3h,
    collector runs every 180s, token stats and curve snapshots for recent tokens, and posts."""
    rng = random.Random(seed)
    filler = ["moon", "doge", "pepe", "king", "rocket", "chad", "panda", "wolf", "tiger", "owl"]
    start = now_ts - hours * H
    # collector runs (coverage)
    t = start
    while t <= now_ts:
        insert(con, "source_runs", {"source": "geckoterminal", "job": "new_pools", "started_at": t - 20,
                                    "finished_at": t, "status": "ok", "items": 100, "latency_ms": 900})
        insert(con, "market_obs", {"observed_at": t, "metric": "new_pools_span_s", "value": 240,
                                   "source": "geckoterminal", "detail": None})
        t += 180
    for job, src in (("refresh", "geckoterminal"), ("bonding_curves", "solana_rpc"),
                     ("launchpad_volume", "defillama"), ("new_posts", "reddit")):
        for k in range(0, hours * H, 300):
            ts = start + k
            insert(con, "source_runs", {"source": src, "job": job, "started_at": ts - 5, "finished_at": ts,
                                        "status": "ok", "items": 10, "latency_ms": 100})
    n = 0
    t = start
    while t < now_ts:
        t += rng.randint(30, 90)
        surge_phase = t > now_ts - 3 * H
        word = surge if (surge_phase and rng.random() < 0.35) else rng.choice(filler)
        mint = f"M{n:05d}pump"
        n += 1
        insert(con, "tokens", {"mint": mint, "name": f"{word.title()} {rng.choice(['Coin', 'Lord', 'Club'])}",
                               "symbol": word.upper()[:5] + str(rng.randint(0, 3)), "creator": f"C{rng.randint(0, 300)}",
                               "pool": f"P{mint}", "launchpad": "pump-fun", "created_at": t,
                               "first_seen_at": t + 60, "source": "gt_new_pools"})
        if t > now_ts - 4 * H:   # stats for recent tokens, observed after launch
            for obs_t in range(t + 120, now_ts + 1, 900):
                hot = word == surge
                insert(con, "token_obs", {
                    "mint": mint, "observed_at": obs_t, "source": "gt_refresh", "dex": "pump-fun",
                    "pool": f"P{mint}", "price_usd": 1e-5, "mcap_usd": 8000 if not hot else 30000,
                    "vol_h1": 3000 if hot else 200, "vol_h6": 9000 if hot else 900,
                    "vol_h24": 9000 if hot else 900, "buyers_h1": 40 if hot else 3, "sellers_h1": 15 if hot else 4,
                    "buys_h1": 60 if hot else 4, "sells_h1": 25 if hot else 6})
                insert(con, "curve_obs", {"mint": mint, "observed_at": obs_t,
                                          "real_sol": (obs_t - t) / 600 if hot else 0.3,
                                          "real_token_reserves": 7e8, "progress": 0.4 if hot else 0.02,
                                          "complete": 0, "price_sol": 3e-8})
    for d in range(30):
        insert(con, "market_obs", {"observed_at": now_ts - d * 3600, "metric": "pumpfun_launchpad_vol_7d_avg",
                                   "value": 1.6e8, "source": "defillama", "detail": None})
        insert(con, "market_obs", {"observed_at": now_ts - d * 3600, "metric": "pumpfun_launchpad_vol_30d_avg",
                                   "value": 1.5e8, "source": "defillama", "detail": None})
    for i in range(80):
        ct = now_ts - rng.randint(0, 30 * H) if i < 40 else now_ts - rng.randint(0, 2 * H)
        word = surge if i >= 40 else rng.choice(filler)
        insert(con, "social_posts", {
            "id": f"reddit:{i}", "source": "reddit", "author_id": f"a{i % 50}", "author_handle": f"user{i % 50}",
            "author_followers": None, "text": f"{word} season is here, bullish on {word} memes",
            "created_at": ct, "collected_at": ct + 300, "likes": rng.randint(0, 50), "reposts": 0,
            "replies": rng.randint(0, 10), "views": 0, "url": f"https://reddit.com/{i}", "query": "r/solana",
            "fingerprint": f"fp{i}", "is_spam": 0})
    con.commit()


@pytest.fixture
def history_db(tmp_path):
    con = connect(tmp_path / "h.db")
    build_history(con)
    return con
