import base64
import struct

from radar.analytics.outcomes import bucket, price_path
from radar.sources.social import parse_reddit_listing, parse_x_search
from radar.sources.solana_rpc import BONDING_CURVE_DISC, INITIAL_REAL_TOKEN_RESERVES, b58encode, decode_bonding_curve
from radar.text import classify, fingerprint, is_spam, terms, token_terms


def curve_bytes(vtok, vsol, rtok, rsol, supply, complete, tail=b""):
    return base64.b64encode(BONDING_CURVE_DISC + struct.pack("<QQQQQ", vtok, vsol, rtok, rsol, supply)
                            + bytes([complete]) + tail).decode()


def test_curve_decode_progress_and_trailing_bytes():
    rtok = INITIAL_REAL_TOKEN_RESERVES // 2
    dec, err = decode_bonding_curve(curve_bytes(10**15, 40 * 10**9, rtok, 42 * 10**9, 10**15, 0, b"\x00" * 117))
    assert err is None
    assert abs(dec["progress"] - 0.5) < 1e-9
    assert dec["real_sol"] == 42 and dec["complete"] is False


def test_curve_decode_migrated_with_zero_reserves_is_kept():
    # solana-launch-study bug 2.2: migration zeroes virtual reserves; must not be dropped as an error
    dec, err = decode_bonding_curve(curve_bytes(0, 0, 0, 0, 10**15, 1))
    assert err is None and dec["complete"] is True and dec["progress"] == 1.0 and dec["price_sol"] is None


def test_curve_decode_rejects_wrong_discriminator():
    bad = base64.b64encode(b"\x01" * 8 + b"\x00" * 41).decode()
    assert decode_bonding_curve(bad) == (None, "discriminator_mismatch")


def test_b58():
    assert b58encode(b"\x00\x01") == "12"
    assert b58encode(bytes(32)) == "1" * 32


def test_terms_split_concatenated_names_and_drop_noise():
    assert {"cat", "wif", "hat"} <= set(token_terms("CatWifHat", "CWH"))
    t = terms("Official $FROG coin on Solana pump.fun https://x.com/abc")
    assert "frog" in t and "solana" not in t and "coin" not in t and "official" not in t
    assert terms("Cats") == ["cat"]


def test_sentiment_and_spam():
    assert classify("this will moon, huge gem, buying more")["polarity"] > 0
    assert classify("rugged by insiders, dev dumped")["label"] == "panic"
    assert is_spam({"text": "join telegram for airdrop and presale whitelist"}, 0)
    assert not is_spam({"text": "frog meta looks strong today", "author_followers": 500}, 0)
    assert fingerprint("b a c") == fingerprint("c b a")


def test_outcome_bucket_thresholds():
    assert bucket(0.1, False) == "dead" and bucket(1, False) == "weak"
    assert bucket(6, False) == "alive" and bucket(0, True) == "migrated" and bucket(None, False) == "unknown"


def test_price_path_unknown_end_when_no_trades_near_horizon():
    c0 = 1000
    candles = [(c0, 1.0, 2.0, 0.9, 1.5, 10), (c0 + 900, 1.5, 3.0, 1.4, 2.0, 5)]
    pp = price_path(candles, c0, 24)
    assert pp["ret_max"] == 2.0 and pp["end_price"] is None and pp["ret_end"] is None
    pp = price_path(candles, c0, 1)  # horizon 1h: last trade 15 min in -> within tolerance
    assert pp["ret_end"] == 1.0


def _pk(i: int) -> bytes:
    return bytes([i]) * 32


def trade_bytes(mint, user, creator, sol, buy, ts, real_sol, real_tok):
    from radar.sources.pump_events import TRADE
    return (TRADE + _pk(mint) + struct.pack("<QQ", int(sol * 1e9), 10**12) + bytes([buy]) + _pk(user)
            + struct.pack("<qQQQQ", ts, int((real_sol + 30) * 1e9), int((real_tok + 279.9e6) * 1e6),
                          int(real_sol * 1e9), int(real_tok * 1e6))
            + _pk(99) + struct.pack("<QQ", 95, 1000) + _pk(creator) + b"\x00" * 40)


def create_bytes(mint, creator, name, ts):
    from radar.sources.pump_events import CREATE
    s = lambda x: struct.pack("<I", len(x)) + x.encode()  # noqa: E731
    return (CREATE + s(name) + s(name[:4].upper()) + s("https://x/meta.json") + _pk(mint) + _pk(mint + 100)
            + _pk(creator) + _pk(creator) + struct.pack("<qQQQQ", ts, 1, 2, 3, 4) + b"\x00" * 33)


def notification(payloads, err=None):
    import json
    logs = ["Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]"]
    logs += ["Program data: " + base64.b64encode(p).decode() for p in payloads]
    return json.dumps({"jsonrpc": "2.0", "method": "logsNotification", "params": {"result": {
        "context": {"slot": 1}, "value": {"signature": "sig", "err": err, "logs": logs}}}},
        separators=(",", ":"))


def test_pump_event_decoding_and_failed_tx_rejection():
    from radar.sources.pump_events import parse_notification
    raw = notification([create_bytes(1, 2, "Frog Lord", 1000),
                        trade_bytes(1, 3, 2, 0.5, 1, 1001, 0.5, 780e6)])
    c, t = parse_notification(raw)
    assert c["type"] == "create" and c["name"] == "Frog Lord" and c["symbol"] == "FROG" and c["creator"] == b58encode(_pk(2))
    assert t["type"] == "trade" and t["is_buy"] and abs(t["sol"] - 0.5) < 1e-9 and t["creator"] == b58encode(_pk(2))
    assert abs(t["v_sol"] - t["real_sol"] - 30) < 1e-6
    assert parse_notification(notification([trade_bytes(1, 3, 2, 0.5, 1, 1001, 0.5, 780e6)],
                                            err={"InstructionError": [0, "Custom"]})) is None
    # a log line the RPC truncated mid-base64 is skipped, not fatal
    bad = notification([trade_bytes(1, 3, 2, 0.5, 1, 1001, 0.5, 780e6)]).replace('","Program data', '","Program data: AAA=x","Program data', 1)
    assert len(parse_notification(bad)) == 1


def test_live_aggregates_wallet_signals_and_snapshots(settings):
    from radar.db import connect, rows
    from radar.sources.pump_events import parse_notification
    from radar.stream import Live
    con = connect(settings.db_path)
    live, t0 = Live(), 1_790_000_000
    feed = [create_bytes(1, 2, "Frog Lord", t0)]
    for i in range(8):        # 8 distinct buyers, one of them a "bot"
        feed.append(trade_bytes(1, 10 + i, 2, 1.0, 1, t0 + 10 + i, 1.0 + i, 790e6 - i * 1e6))
    feed.append(trade_bytes(1, 2, 2, 0.7, 0, t0 + 30, 7.3, 783e6))              # creator sells
    feed.append(trade_bytes(1, 11, 2, 0.2, 0, t0 + 40, 7.1, 784e6))             # a buyer sells
    for raw in (notification([p]) for p in feed):
        for ev in parse_notification(raw):
            live.on_event(ev, t=t0 + 50)
    bot = b58encode(_pk(10))
    for k in range(20):        # the bot trades 20 other tokens -> excluded from organic buyers
        live.on_event({"type": "trade", "mint": f"X{k}", "sol": 0.01, "tokens": 1, "is_buy": True, "user": bot,
                       "ts": t0 + 45, "v_sol": 30, "v_tokens": 1e9, "real_sol": 0, "real_tokens": 793e6,
                       "creator": None}, t=t0 + 50)
    live.smart = {b58encode(_pk(12)), b58encode(_pk(13))}
    assert live.flush(con) == 1 + 8 + 20  # a launch, 8 early buyers (creator excluded), the bot in 20 tokens
    assert live.snapshot(con, sol_usd=100.0, t=t0 + 60) == 1
    o = rows(con, "SELECT * FROM token_obs WHERE mint=?", (b58encode(_pk(1)),))[0]
    assert o["buyers_h1"] == 8 and o["sellers_h1"] == 2 and o["organic_buyers_h1"] == 7
    assert o["smart_buyers_h1"] == 2 and abs(o["dev_sold_sol"] - 0.7) < 1e-9
    assert abs(o["net_sol_h1"] - (8 - 0.9)) < 1e-6 and abs(o["buy_vol_h1"] - 800) < 1e-6
    v = live.view(t=t0 + 60)
    assert v["launches"][0]["name"] == "Frog Lord" and v["hot"][0]["buyers_5m"] == 8
    # completing the curve (real token reserves hit 0) registers a graduation once
    for _ in range(2):
        live.on_event(parse_notification(notification([trade_bytes(1, 30, 2, 5, 1, t0 + 70, 85, 0)]))[0], t=t0 + 70)
    live.flush(con)
    assert rows(con, "SELECT COUNT(*) n FROM graduations")[0]["n"] == 1 and len(live.grads) == 1


def test_coverage_counts_only_connected_seconds(settings):
    from radar.analytics.common import launch_coverage
    from radar.db import connect, insert
    con = connect(settings.db_path)
    t0 = 1_790_000_000
    for k in range(60):        # one hour of heartbeats, connected 30s of each minute
        insert(con, "market_obs", {"observed_at": t0 - k * 60, "metric": "stream_connected_s", "value": 30,
                                   "source": "chain", "detail": None})
    assert abs(launch_coverage(con, t0, 3600) - 0.5) < 0.02


def test_parse_x_and_reddit():
    x = {"data": [{"id": "9", "text": "frog szn", "author_id": "u1", "created_at": "2026-10-16T00:00:00Z",
                   "public_metrics": {"like_count": 5, "retweet_count": 1, "quote_count": 1, "reply_count": 2,
                                      "impression_count": 100}}],
         "includes": {"users": [{"id": "u1", "username": "alice", "created_at": "2020-01-01T00:00:00Z",
                                 "public_metrics": {"followers_count": 1200}}]}}
    (p,) = parse_x_search(x, "q")
    assert p["id"] == "x:9" and p["author_followers"] == 1200 and p["reposts"] == 2
    r = {"data": {"children": [{"data": {"id": "a1", "title": "Frog", "selftext": "meta", "author": "bob",
                                         "created_utc": 1792000000, "score": 3, "num_comments": 1,
                                         "permalink": "/r/solana/a1"}}]}}
    (q,) = parse_reddit_listing(r, "solana")
    assert q["id"] == "reddit:a1" and "meta" in q["text"]


def test_pacer_backs_off_on_429_and_eases_back():
    from radar.sources.base import Pacer
    p = Pacer(4.0, max_interval_s=30.0)
    for _ in range(5):
        p.penalize()
    assert p.min_interval_s == 30.0
    for _ in range(200):
        p.relax()
    assert p.min_interval_s == 4.0


def test_blocked_backoff_only_after_repeated_refusals(settings):
    from radar.db import connect, insert, now
    from radar.sources.base import blocked_backoff
    con = connect(settings.db_path)
    def run(status, error, ago):
        t = now() - ago
        insert(con, "source_runs", {"source": "pumpfun", "job": "latest_coins", "started_at": t,
                                    "finished_at": t, "status": status, "items": 0, "error": error})
    run("unavailable", "frontend-api-v3.pump.fun HTTP 403 (Cloudflare challenge)", 900)
    run("unavailable", "frontend-api-v3.pump.fun HTTP 403 (Cloudflare challenge)", 600)
    assert blocked_backoff(con, "pumpfun", "latest_coins") is None
    run("unavailable", "frontend-api-v3.pump.fun HTTP 403 (Cloudflare challenge)", 300)
    assert blocked_backoff(con, "pumpfun", "latest_coins")
    run("skipped", "refused", 60)  # skips don't reset or extend the backoff
    assert blocked_backoff(con, "pumpfun", "latest_coins")
    run("unavailable", "HTTP 429", 30)  # rate limits are not refusals
    assert blocked_backoff(con, "pumpfun", "latest_coins") is None
