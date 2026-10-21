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


def trade_tail(quote_pk: bytes, ix: str = "buy", shareholders: int = 0) -> bytes:
    s = struct.pack("<I", len(ix)) + ix.encode()
    return (bytes([1]) + struct.pack("<QQQq", 0, 0, 0, 0) + s + bytes([0]) + struct.pack("<QQQQ", 0, 0, 0, 0)
            + struct.pack("<I", shareholders) + b"\x07" * 34 * shareholders + quote_pk + struct.pack("<QQQ", 1, 2, 3))


def test_token_paired_trades_and_migration_events_decode():
    from radar.sources.pump_events import MIGRATION, decode_event
    base = trade_bytes(1, 3, 2, 0.0, 1, 1001, 0.0, 700e6)[:-24]          # keep creator fees, drop padding
    sol = decode_event(base + trade_tail(b"\x00" * 32, shareholders=2))
    other = decode_event(base + trade_tail(_pk(55)))
    old = decode_event(base)                                              # pre-quote-mint layout
    assert sol["sol_paired"] and not other["sol_paired"] and old["sol_paired"]
    mig = (MIGRATION + _pk(9) + _pk(1) + struct.pack("<QQQ", 206_900_000 * 10**6, 85 * 10**9, 15 * 10**8)
           + _pk(101) + struct.pack("<q", 1234) + _pk(77) + _pk(0))
    m = decode_event(mig)
    assert m["type"] == "migration" and m["mint"] == b58encode(_pk(1)) and m["pool"] == b58encode(_pk(77))
    assert abs(m["pool_sol"] - 85) < 1e-9 and m["ts"] == 1234


def test_launch_block_buyers_holdings_and_non_sol_coins(settings):
    from radar.db import connect, rows
    from radar.stream import Live
    con = connect(settings.db_path)
    live, t0 = Live(), 1_790_000_000
    live.on_event({"type": "create", "mint": "M", "name": "Frog", "symbol": "FROG", "uri": None, "bonding_curve": "C",
                   "user": "dev", "creator": "dev", "ts": t0, "slot": 100, "initial_real_tokens": 793.1e6,
                   "sol_paired": True}, t=t0)
    def trade(user, buy, tokens, slot, ts, sol=0.5, paired=True, mint="M"):
        live.on_event({"type": "trade", "mint": mint, "sol": sol, "tokens": tokens, "is_buy": buy, "user": user,
                       "ts": ts, "v_sol": 31, "v_tokens": 1.0e9, "real_sol": 1, "real_tokens": 700e6,
                       "creator": "dev", "slot": slot, "sol_paired": paired}, t=ts)
    trade("dev", True, 50e6, 100, t0)
    for i in range(4):
        trade(f"b{i}", True, 20e6, 100 + (i % 2), t0)         # launch block (and the next slot)
    trade("late", True, 5e6, 140, t0 + 30)
    trade("b0", False, 20e6, 150, t0 + 40)                    # sells everything
    ms = live.mints["M"]
    assert len(ms.block_buyers) == 4 and abs(ms.block_tokens - 80e6) < 1
    assert "b0" not in ms.holdings and abs(live.top10(ms) - (50e6 + 60e6 + 5e6) / 1e9) < 1e-9
    assert abs(live.dev_holds(ms) - 0.05) < 1e-9
    # a coin paired with another token: wallets count, SOL does not
    live.on_event({"type": "create", "mint": "Q", "name": "Q", "symbol": "Q", "uri": None, "bonding_curve": "C2",
                   "user": "d2", "creator": "d2", "ts": t0, "slot": 100, "initial_real_tokens": 793.1e6,
                   "sol_paired": False}, t=t0)
    for i in range(6):
        trade(f"q{i}", True, 1e6, 200, t0 + 50, sol=9.0, paired=False, mint="Q")
    live.flush(con)
    live.snapshot(con, sol_usd=100.0, t=t0 + 60)
    q = rows(con, "SELECT * FROM token_obs WHERE mint='Q'")[0]
    assert q["buyers_h1"] == 6 and q["net_sol_h1"] is None and q["vol_h1"] is None and q["sol_paired"] == 0
    # migration: graduation with its PumpSwap pool, once
    for _ in range(2):
        live.on_event({"type": "migration", "mint": "M", "user": "x", "bonding_curve": "C", "ts": t0 + 90,
                       "pool": "POOL", "pool_sol": 85, "pool_tokens": 2e8}, t=t0 + 90)
    live.flush(con)
    g = rows(con, "SELECT pool FROM graduations WHERE mint='M'")
    assert len(g) == 1 and g[0]["pool"] == "POOL" and len(live.grads) == 1


def test_pumpswap_price_uses_effective_quote_reserves(settings, monkeypatch):
    import asyncio
    from radar.sources import solana_rpc as rpc
    vq = -3 * 10**9                                                       # 3 SOL of fees waiting in the vault
    pool = (rpc.POOL_DISC + bytes([1]) + struct.pack("<H", 0) + _pk(5) + bytes(_b58d("MINT")) + bytes(_b58d(rpc.WSOL_MINT))
            + _pk(6) + _pk(7) + _pk(8) + struct.pack("<Q", 1) + _pk(9) + bytes([0, 0]) + vq.to_bytes(16, "little", signed=True))
    assert rpc.decode_pool(base64.b64encode(pool).decode())["virtual_quote_reserves"] == vq

    async def fake_rpc(http, url, method, params):
        if params[1]["encoding"] == "base64":
            return {"value": [{"owner": rpc.PUMP_AMM_PROGRAM, "data": [base64.b64encode(pool).decode()]}]}
        amounts = {b58encode(_pk(7)): 200_000_000 * 10**6, b58encode(_pk(8)): 103 * 10**9}
        return {"value": [{"data": {"parsed": {"info": {"tokenAmount": {"amount": str(amounts[a])}}}}} for a in params[0]]}
    monkeypatch.setattr(rpc, "_rpc", fake_rpc)
    mint = b58encode(bytes(_b58d("MINT")))
    out = asyncio.run(rpc.pumpswap_prices(None, "u", {mint: "POOL"}))
    assert abs(out[mint]["quote_sol"] - 100) < 1e-9 and abs(out[mint]["price_sol"] - 100 / 2e8) < 1e-15


def _b58d(s: str) -> bytes:
    """32-byte key for a readable test name (or a real base58 address)."""
    from radar.sources.solana_rpc import _B58
    if s == "MINT":
        return b"\x11" * 32
    n = 0
    for ch in s:
        n = n * 58 + _B58.index(ch)
    return n.to_bytes(32, "big")


def test_metadata_parsing_and_x_post_links():
    from radar.metadata import candidate_urls, parse, x_ref
    assert candidate_urls("https://ipfs.io/ipfs/QmWGC5oiV82nYXdyG7ov9wttkhmEkiEjCxKARFqmkvtie9")[0].startswith("https://ipfs.filebase.io/ipfs/Qm")
    assert candidate_urls("javascript:alert(1)") == []
    m = parse({"description": " frog king ", "twitter": "https://x.com/SomeOne/status/2112910854458839338?s=20",
               "website": "https://frog.example", "image": "https://img/x.png"})
    assert m["x_post"] == "someone/status/2112910854458839338" and m["x_account"] == "someone"
    assert m["description"] == "frog king"
    assert x_ref("https://twitter.com/home") == (None, None)
    assert x_ref(None, "https://x.com/frogdao") == (None, "frogdao")


def test_semantic_merge_is_recorded_and_keeps_activity_order(monkeypatch):
    import numpy as np
    from radar import embed
    vecs = {"cat": [1, 0, 0], "dog": [0, 1, 0], "kitty": [0.95, 0.31, 0], "frog": [0, 0, 1]}

    class Fake:
        def embed(self, texts):
            v = np.array([vecs[t] for t in texts], dtype=float)
            return v / np.linalg.norm(v, axis=1, keepdims=True)
    monkeypatch.setattr(embed.Embedder, "_inst", Fake())
    out, merges = embed.merge_clusters([["cat", "wif"], ["dog"], ["kitty"], ["frog"]])
    assert out == [["cat", "wif", "kitty"], ["dog"], ["frog"]] and merges[0][:2] == ["cat", "kitty"]
    monkeypatch.setattr(embed.Embedder, "_inst", None)
    assert embed.merge_clusters([["cat"], ["kitty"]]) == ([["cat"], ["kitty"]], [])


def test_shipped_wallet_labels_load():
    from radar.wallet_labels import WalletLabels
    lab = WalletLabels.load()
    assert len(lab.smart) > 1000 and len(lab.insider) > 1000 and not (lab.smart & lab.insider)


def test_posts_spawning_coins_are_grouped(settings):
    from radar.db import connect, insert
    from radar.stream import Live
    con = connect(settings.db_path)
    t0 = 1_790_000_000
    for i, (post, creator) in enumerate([("a/status/1", "c1"), ("a/status/1", "c2"), ("a/status/1", "c2"), ("b/status/2", "c3")]):
        insert(con, "tokens", {"mint": f"T{i}", "name": "x", "symbol": "X", "creator": creator, "launchpad": "pump-fun",
                               "created_at": t0 - 100, "first_seen_at": t0 - 99, "source": "chain", "x_post": post})
    posts = Live().source_posts(con, t0)
    assert len(posts) == 1 and posts[0]["launches"] == 3 and posts[0]["creators"] == 2
    assert posts[0]["url"] == "https://x.com/a/status/1"
