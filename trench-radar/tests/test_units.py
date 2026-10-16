import base64
import struct

from radar.analytics.outcomes import bucket, price_path
from radar.sources.geckoterminal import parse_pools
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


GT_PAYLOAD = {
    "data": [{
        "id": "solana_POOL1", "type": "pool",
        "attributes": {"address": "POOL1", "name": "FROG / SOL", "pool_created_at": "2026-10-16T01:31:51Z",
                       "base_token_price_usd": "0.0000046", "quote_token_price_usd": "105.1",
                       "market_cap_usd": None, "fdv_usd": "4664.2", "reserve_in_usd": "3800.5",
                       "price_change_percentage": {"h1": "12.5", "h24": "40"},
                       "transactions": {"h1": {"buys": 20, "sells": 7, "buyers": 19, "sellers": 6},
                                        "h24": {"buys": 20, "sells": 7, "buyers": 19, "sellers": 6}},
                       "volume_usd": {"m5": "10", "h1": "2564.5", "h6": "2564.5", "h24": "2564.5"}},
        "relationships": {"base_token": {"data": {"id": "solana_FrogMintpump", "type": "token"}},
                          "quote_token": {"data": {"id": "solana_So11111111111111111111111111111111111111112"}},
                          "dex": {"data": {"id": "pump-fun", "type": "dex"}}}}],
    "included": [{"id": "solana_FrogMintpump", "type": "token",
                  "attributes": {"address": "FrogMintpump", "name": "Frog Lord", "symbol": "FROG"}}],
}


def test_parse_geckoterminal_pool():
    (p,) = parse_pools(GT_PAYLOAD)
    assert p["mint"] == "FrogMintpump" and p["name"] == "Frog Lord" and p["dex"] == "pump-fun"
    assert p["buyers_h1"] == 19 and p["vol_h1"] == 2564.5 and p["quote_is_sol"] and p["sol_price"] == 105.1
    assert p["pool_created_at"] == 1792114311


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
