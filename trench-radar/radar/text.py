"""Term extraction, sentiment and spam heuristics for token names and posts.

Ideas re-implemented from DoradoDevs/solana-narrative-scanner (MIT: near-duplicate
fingerprints, bot heuristics) and TINZY0612/openclaw-x-signal (MIT: hype/panic/
shill categories). Lexicon-based on purpose: transparent, cheap, and its errors
are inspectable — it is not a trained model and is not claimed to be one.
"""
from __future__ import annotations

import hashlib
import re

STOP = set("""
a an the of and or to in on for with at by from is are be it its this that my your our we you i me
coin coins token tokens sol solana pump pumpfun pumpdotfun fun meme memes memecoin memecoins official
community cto dev devs ca mint launch launched new just now live chart dex dexscreener raydium jupiter
buy sell hold holders moon x100 x1000 gem gems lfg wagmi ngmi gm gn ser fren frens ape apes airdrop
inu the1 it's dont don't can will get got going go all not no yes one two first last day today time
http https www com io t co amp rt via what who how why when where than then so up out more most
v2 v3 2 3 10 100 1000 usd usdc sol's solanas based
""".split())

# Common meme roots, used to split concatenated names ("catwifhat" -> cat, wif, hat).
ROOTS = sorted(set("""
cat dog frog pepe doge shib trump elon musk ai agent baby moon bonk wif hat inu monkey ape bear bull
pig duck goat fish penguin hamster rat chill guy girl boy king queen god jesus grok gpt robot cyber
pnut squirrel peanut panda tiger lion wolf fox owl bird sloth otter capy capybara milady wojak chad
gigachad based retard degen mog pump rocket mars nasa space alien skibidi sigma rizz
""".split()), key=len, reverse=True)

_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")
_SPLIT = re.compile(r"[^a-z0-9$#]+")
_URL = re.compile(r"https?://\S+")
_TICKER = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,11})\b")


def _stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is", "os")):
        return w[:-1]
    return w


def _roots_in(word: str) -> list[str]:
    """Meme roots inside a concatenated word, greedy, only if they cover most of it."""
    found, i = [], 0
    covered = 0
    while i < len(word):
        for r in ROOTS:
            if word.startswith(r, i):
                found.append(r)
                covered += len(r)
                i += len(r)
                break
        else:
            i += 1
    return found if found and covered >= 0.6 * len(word) else []


def terms(text: str, *, max_terms: int = 12) -> list[str]:
    """Normalised, de-duplicated content terms from a name, symbol or post."""
    if not text:
        return []
    text = _URL.sub(" ", text)
    text = _CAMEL.sub(" ", text).lower()
    out: list[str] = []
    for raw in _SPLIT.split(text):
        w = raw.strip("$#")
        if not w or w.isdigit() or len(w) < 3 or w in STOP:
            continue
        w = _stem(w)
        if w in STOP:
            continue
        out.append(w)
        if len(w) >= 6:
            out.extend(r for r in _roots_in(w) if r != w and r not in STOP)
    seen, uniq = set(), []
    for w in out:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    return uniq[:max_terms]


def token_terms(name: str | None, symbol: str | None) -> list[str]:
    return terms(f"{name or ''} {symbol or ''}")


def tickers(text: str) -> list[str]:
    return sorted({t.upper() for t in _TICKER.findall(text or "")})


# ---------------------------------------------------------------- sentiment

LEX = {
    "hype": "moon mooning send sending pump pumping parabolic explode exploding 100x 1000x gem gems lfg ripping "
            "runner running bullish rocket next early alpha huge massive insane",
    "bullish": "buy buying bought accumulate accumulating long strong support breakout higher green up uptrend "
               "conviction undervalued love great good",
    "bearish": "sell selling sold dump dumping down bearish weak lower red overvalued dead over top topped exit",
    "panic": "rug rugged rugpull scam scammed honeypot drained exploit hack hacked rekt crash crashing "
             "liquidated jeet jeets bundle bundled insider insiders",
    "shill": "join telegram dm giveaway airdrop presale whitelist ref referral promo shill guaranteed",
}
LEX_SETS = {k: set(v.split()) for k, v in LEX.items()}


def classify(text: str) -> dict:
    """Category counts and a polarity in [-1, 1]. Shill is tracked, not counted as positive."""
    words = set(_SPLIT.split((text or "").lower()))
    counts = {k: len(words & s) for k, s in LEX_SETS.items()}
    pos = counts["hype"] + counts["bullish"]
    neg = counts["bearish"] + 1.5 * counts["panic"]
    polarity = 0.0 if pos + neg == 0 else (pos - neg) / (pos + neg)
    label = max(counts, key=counts.get) if any(counts.values()) else "neutral"
    return {"label": label, "polarity": round(polarity, 3), "counts": counts}


# ---------------------------------------------------------------- spam / duplicates

def fingerprint(text: str) -> str:
    """Order-insensitive hash of content words: catches copy-paste shill waves."""
    words = sorted(set(w for w in _SPLIT.split(_URL.sub(" ", (text or "").lower())) if len(w) > 2))
    return hashlib.sha1(" ".join(words[:40]).encode()).hexdigest()[:16]


def is_spam(post: dict, now_ts: int) -> bool:
    text = post.get("text") or ""
    c = classify(text)
    if c["counts"]["shill"] >= 2:
        return True
    if len(tickers(text)) >= 6:              # ticker-stuffed
        return True
    if len(_URL.findall(text)) >= 3:
        return True
    followers = post.get("author_followers")
    created = post.get("author_created_at")
    if followers is not None and followers < 10 and created and now_ts - created < 14 * 86400:
        return True                           # fresh, followerless account
    return False
