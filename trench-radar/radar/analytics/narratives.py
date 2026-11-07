"""Narrative intelligence: what each emerging meta actually is, and whether it is working.

The keyword metas (metas.py) count words. This module reads meaning:

1. Every launch becomes a short document: name, ticker, its description (launchpad
   boilerplate stripped) and the text of the X post it links to, when fetched. Each is
   embedded with all-MiniLM-L6-v2 (embed.py).
2. Tokens are grouped by meaning (leader clustering on cosine similarity), plus hard links
   that need no interpretation: the same picture (images.py), the same linked X post, the
   same name from different creators. Tokens people are buying seed the groups; launches
   with no buyers yet join the closest group or form launch-only groups of their own.
   Launch factories (metas.SERIAL_MIN+ launches in the lookback) are left out, as in metas.
3. Groups with 3+ tokens from 2+ creators are sub-metas; sub-metas whose centres are close
   form a parent narrative. Labels come from class-based TF-IDF: the words that are frequent
   in the group and rare elsewhere in the window, never from a fixed list.
4. Categories are matched by meaning against short written descriptions (CATEGORY_SEEDS),
   not keywords. A narrative close to none of them is "novel"; once one has enough evidence
   it becomes a new category of its own (stored, so later narratives can join it).
5. Each narrative is tracked across runs (narratives / narrative_obs / narrative_events):
   persistence, growth, merges and splits.
6. Popularity (launches, creators), traction (buyers, SOL) and opportunity are reported
   separately. A state (new, accelerating, heating, bought, saturating, steady, fading) comes
   with the measurements behind it; drivers and risks are picked from observable evidence.

Point-in-time: only rows seen at or before `as_of` are read (launches by first_seen_at,
stats by observed_at, posts and images by fetched_at). Token metadata has no fetch time; it is
fetched within about a minute of launch and treated as known from launch.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict

from ..db import insert, now, rows
from ..text import terms
from . import metas
from .common import Lineage

H = 3600
WINDOW_S = 6 * H
T_SUB = 0.62          # same sub-meta (cosine of document embeddings; set from real launches)
T_PARENT = 0.47       # same parent narrative (cosine of sub-meta centres; median nearest pair was 0.46)
T_SAME = 0.80         # same narrative as in the previous run
T_CAT = 0.24          # close enough to a described category (top scores on real narratives: median 0.27)
T_CAT_MARGIN = 0.04   # ...or at least T_CAT - 0.04 and this far ahead of the runner-up
T_NEWCAT = 0.62       # a novel narrative joins an earlier emergent category
MIN_TOKENS, MIN_CREATORS = 3, 2
OBS_KEEP_S = 21 * 86400   # hourly narrative history kept: meta health compares 3 days with the 11 before, up to 4 days back
MAX_SEED, MAX_POINTS = 2000, 6000

# Categories are described, not keyword-matched: each line is a sentence the embedding of a
# narrative is compared with. They are starting points; novel narratives create their own.
CATEGORY_SEEDS: dict[str, list[str]] = {
    "Art & visual memes": ["a meme based on an image, artwork, drawing or visual style",
                           "an aesthetic, art movement or distinctive picture"],
    "Characters & creatures": ["a mascot, cartoon character or named creature",
                               "an animal meme: a dog, cat, frog, monkey or other pet",
                               "a cute or funny animal with a name"],
    "Internet culture & slang": ["a viral joke, catchphrase or internet slang",
                                 "a social media trend, reaction meme or copypasta",
                                 "main character energy, aura, vibes, rizz, brainrot"],
    "Technology & AI": ["artificial intelligence, AI agents, chatbots and large language models",
                        "robots, futuristic technology and software",
                        "a tech company announcement, coding, hacking or cybersecurity"],
    "Gaming, anime & entertainment": ["a video game, anime, cartoon, film or TV show reference",
                                      "a celebrity, streamer, musician or entertainment moment",
                                      "a game leak, a game character or something from a new game release"],
    "Current events & news": ["a news story or something that happened today",
                              "a viral real-world event, scandal or announcement",
                              "breaking news reported by a newspaper, a zoo or a company"],
    "Politics & geopolitics": ["a politician, president, election or government",
                               "countries, wars, laws and geopolitical events"],
    "Communities & fandoms": ["a community, fandom, subculture or group identity",
                              "a country, city or nationality community coin",
                              "a charity, movement or cause people rally behind"],
    "Absurdist & surreal": ["absurd, surreal or nonsensical humor",
                            "anti-humor, random words and deliberately stupid ideas"],
    "Crypto-native": ["crypto trading, memecoin culture, degens, pump and dump",
                      "blockchain, Solana, DeFi, tokens, wallets and exchanges",
                      "a crypto founder, influencer or project"],
    "Lifestyle & nostalgia": ["luxury, fashion, money, cars and lifestyle",
                              "nostalgia, retro things, childhood memories and old brands",
                              "food, drinks and everyday objects"],
}
SEED_CATS = list(CATEGORY_SEEDS)

_URL = re.compile(r"https?://\S+|\b[\w-]+\.(?:io|com|xyz|ai|fun|app|net|org|gg|so|sh|cc|me|tv|live)(?:/\S*)?", re.I)
_B58 = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
_HANDLE = re.compile(r"@(\w{1,15})")
# words that make up launchpad boilerplate ("Deployed using x", "Fees to @y via z"); a
# description left with fewer than two other words carries no narrative
_BOILER = {"deployed", "using", "launched", "launch", "launching", "on", "created", "create", "via", "fees", "fee",
           "to", "with", "by", "made", "deploy", "coin", "token", "the", "a", "an", "and", "of", "for", "is",
           "this", "in", "at", "discord", "gg", "ca", "contract", "address", "official", "pump", "fun",
           "pumpfun", "usepaid", "j7tracker", "rapidlaunch", "uxento", "launchblitz"}


def clean(text: str | None, limit: int = 300) -> str:
    if not text:
        return ""
    t = _B58.sub(" ", _URL.sub(" ", text))
    t = _HANDLE.sub(r"\1", t).replace("CA:", " ")
    return re.sub(r"\s+", " ", t).strip()[:limit]


def meaningful_description(desc: str | None) -> str:
    t = clean(desc, 200)
    # a tagged account is not narrative ("Fees to @dev via x"), so handles don't count here
    words = re.findall(r"[a-zA-Z]{2,}", _HANDLE.sub(" ", _URL.sub(" ", desc or "")).lower())
    return t if sum(w not in _BOILER for w in words) >= 2 else ""


def document(tok: dict) -> str:
    parts = [f"{tok.get('name') or ''} ({tok.get('symbol') or ''})"]
    d = meaningful_description(tok.get("description"))
    if d and d.lower() != (tok.get("name") or "").lower():
        parts.append(d)
    if tok.get("post_text"):
        parts.append(clean(tok["post_text"], 300))
    return ". ".join(p for p in parts if p.strip())


def _norm_name(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ---------------------------------------------------------------- loading (point in time)

def load(con, as_of: int, lineage: Lineage, window_s: int = WINDOW_S) -> tuple[list[dict], int]:
    toks = rows(con, """SELECT k.mint, k.name, k.symbol, k.creator, k.created_at, k.first_seen_at, k.description,
                               k.x_post, x.text AS post_text, x.author AS post_author, x.followers AS post_followers,
                               x.likes AS post_likes, i.hash AS image_hash
                        FROM tokens k
                        LEFT JOIN x_posts x ON x.post = k.x_post AND x.status = 'ok' AND x.fetched_at <= ?
                        LEFT JOIN token_images i ON i.mint = k.mint AND i.status = 'ok' AND i.fetched_at <= ?
                        WHERE k.launchpad = 'pump-fun' AND k.created_at > ? AND k.created_at <= ?
                          AND k.first_seen_at <= ?""", (as_of, as_of, as_of - window_s, as_of, as_of))
    for t in toks:
        lineage.saw("tokens", t["first_seen_at"])
    per = Counter(t["creator"] for t in toks if t["creator"])
    factory = {c for c, n in per.items() if n >= metas.SERIAL_MIN}
    kept = [t for t in toks if not t["creator"] or t["creator"] not in factory]
    factory_launches = len(toks) - len(kept)
    # latest trading stats per token (2h), and the same an hour earlier for growth
    stats = _obs(con, [t["mint"] for t in kept], as_of, lineage)
    prev = _obs(con, [t["mint"] for t in kept], as_of - H, lineage)
    for t in kept:
        s = stats.get(t["mint"]) or {}
        t["obs"] = s
        t["obs_prev"] = prev.get(t["mint"]) or {}
        t["buyers"] = s.get("organic_buyers_h1") if s.get("organic_buyers_h1") is not None else (s.get("buyers_h1") or 0)
        t["doc"] = document(t)
        if t["image_hash"] is not None:
            t["image_hash"] &= (1 << 64) - 1
    return kept, factory_launches


def _obs(con, mints: list[str], as_of: int, lineage: Lineage) -> dict:
    out = {}
    for i in range(0, len(mints), 500):
        chunk = mints[i:i + 500]
        qs = ",".join("?" * len(chunk))
        for r in rows(con, f"""SELECT * FROM token_obs WHERE id IN (SELECT MAX(id) FROM token_obs
                               WHERE observed_at <= ? AND observed_at > ? AND mint IN ({qs}) GROUP BY mint)""",
                      (as_of, as_of - 2 * H, *chunk)):
            out[r["mint"]] = r
            lineage.saw("token_obs", r["observed_at"])
    return out


# ---------------------------------------------------------------- grouping

class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[max(a, b)] = min(a, b)


def group(toks: list[dict], vecs, np) -> tuple[list[list[int]], dict[int, dict[str, int]]]:
    """Indices of tokens per group, and per group how its members were linked."""
    from ..images import distance
    order = sorted(range(len(toks)), key=lambda i: (-(toks[i]["buyers"] or 0), -(toks[i]["created_at"] or 0)))
    seeds = [i for i in order if (toks[i]["buyers"] or 0) >= 3][:MAX_SEED]
    rest = [i for i in order if (toks[i]["buyers"] or 0) < 3][:MAX_POINTS - len(seeds)]
    points = seeds + rest
    label = [-1] * len(toks)
    cent = np.zeros((len(points), vecs.shape[1]), dtype=np.float32)
    k = 0
    for i in points:                                   # leader clustering, buyers first
        v = vecs[i]
        if k:
            sims = cent[:k] @ v
            j = int(sims.argmax())
            if sims[j] >= T_SUB:
                label[i] = j
                c = cent[j] * 0.0 + cent[j] + v * 0.25        # drift slowly toward new members
                cent[j] = c / (np.linalg.norm(c) or 1)
                continue
        cent[k] = v
        label[i] = k
        k += 1
    for i in range(len(toks)):                         # anything beyond the cap: nearest group
        if label[i] == -1 and k:
            sims = cent[:k] @ vecs[i]
            j = int(sims.argmax())
            label[i] = j if sims[j] >= T_SUB else -1
    # hard links: same picture, same linked post, same name from another creator
    uf = _UF(max(k, 1))
    why: dict[tuple, str] = {}
    by_post, by_name = defaultdict(list), defaultdict(list)
    for i, t in enumerate(toks):
        if label[i] < 0:
            continue
        if t["x_post"]:
            by_post[t["x_post"]].append(i)
        nm = _norm_name(t["name"])
        if len(nm) >= 3:
            by_name[nm].append(i)
    for key, members in list(by_post.items()) + list(by_name.items()):
        for a in members[1:]:
            if label[a] != label[members[0]]:
                why[(min(label[a], label[members[0]]), max(label[a], label[members[0]]))] = \
                    "same X post" if key in by_post else "same name"
                uf.union(label[a], label[members[0]])
    imgs = [i for i, t in enumerate(toks) if t["image_hash"] is not None and label[i] >= 0]
    for x in range(len(imgs)):
        for y in range(x):
            a, b = imgs[x], imgs[y]
            if label[a] != label[b] and distance(toks[a]["image_hash"], toks[b]["image_hash"]) <= 6:
                why[(min(label[a], label[b]), max(label[a], label[b]))] = "same picture"
                uf.union(label[a], label[b])
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(toks)):
        if label[i] >= 0:
            groups[uf.find(label[i])].append(i)
    links: dict[int, dict[str, int]] = {}
    out = []
    for root, members in groups.items():
        g = len(out)
        out.append(members)
        c = Counter(r for (a, b), r in why.items() if uf.find(a) == root)
        links[g] = dict(c)
    return out, links


# function words that post text brings in; kept out of labels only (text.STOP also feeds keyword
# scoring, which stays as it is)
_LABEL_STOP = set("""which what when where who whom whose why how than then there their they them these those
was were been being have has had having will would could should can may might must shall does did doing
not but about into over under after before again also only very more most much many some such own same
other any each every both few all one two get got like just really cool imo lol currently along long
again here because while being""".split())


# What each state did on past data (scripts/narrative_backtest.py; Shrine archive, 2026-09-16
# and 2026-10-15, names and tickers only): new launches in the narrative, graduating within 6h,
# against launches outside any narrative in the same hours. Shown as context, never as a score.
PAST = {
    "accelerating": "On past data, launches in accelerating narratives graduated less often than others "
                    "(-1.3 pts in September, no difference in October): a launch rush is mostly copies. ",
    "bought": "On past data, launches in bought narratives graduated a little more often than others in "
              "both periods tested (+0.4 and +0.7 pts; the first could be chance). ",
    "heating": "On past data, heating narratives were mixed (-0.9 pts in September, +0.2 in October). ",
    "new": "On past data, launches in new narratives graduated no more often than others. ",
    "saturating": "On past data, saturating narratives were mixed (+0.9 pts in September, none in October). ",
}


def ctfidf(groups: list[list[int]], toks: list[dict], top: int = 5) -> list[list[str]]:
    """Words frequent in a group and rare across the window (class-based TF-IDF)."""
    doc_terms = [{w for w in terms(t["doc"], max_terms=30) if w not in _LABEL_STOP} for t in toks]
    df = Counter(w for ts in doc_terms for w in ts)
    n = len(toks) or 1
    out = []
    for members in groups:
        tf = Counter(w for i in members for w in doc_terms[i])
        need = max(2, math.ceil(0.25 * len(members)))
        scored = [(c / len(members) * math.log(1 + n / df[w]), w) for w, c in tf.items() if c >= need]
        out.append([w for _, w in sorted(scored, reverse=True)[:top]])
    return out


# ---------------------------------------------------------------- categories

def _seed_vectors(emb, np):
    names, vecs = [], []
    for cat, lines in CATEGORY_SEEDS.items():
        for v in emb.embed(lines):
            names.append(cat)
            vecs.append(v)
    return names, np.stack(vecs)


def categorize(centroid, seed_names, seed_vecs, emergent: list[dict], np) -> dict:
    sims = seed_vecs @ centroid
    best: dict[str, float] = {}
    for n, s in zip(seed_names, sims):
        best[n] = max(best.get(n, -1.0), float(s))
    ranked = sorted(best.items(), key=lambda x: -x[1])
    top_name, top_s = ranked[0]
    em = max(((e, float(np.frombuffer(e["centroid"], dtype=np.float16).astype(np.float32) @ centroid))
              for e in emergent), key=lambda x: x[1], default=(None, -1.0))
    runner = ranked[1][1] if len(ranked) > 1 else -1.0
    if top_s >= T_CAT or (top_s >= T_CAT - T_CAT_MARGIN and top_s - runner >= T_CAT_MARGIN):
        secondary = [n for n, s in ranked[1:3] if s >= T_CAT - 0.02 and s >= top_s - 0.04]
        return {"primary": top_name, "primary_score": round(top_s, 2), "secondary": secondary,
                "emergent": False, "scores": {n: round(s, 2) for n, s in ranked[:4]}}
    if em[0] is not None and em[1] >= T_NEWCAT:
        return {"primary": em[0]["label"], "primary_score": round(em[1], 2), "secondary": [],
                "emergent": True, "emergent_id": em[0]["id"], "scores": {n: round(s, 2) for n, s in ranked[:3]}}
    return {"primary": None, "primary_score": round(top_s, 2), "secondary": [], "emergent": False,
            "novel": True, "nearest_seed": top_name, "scores": {n: round(s, 2) for n, s in ranked[:3]}}


# ---------------------------------------------------------------- build

def build(con, as_of: int, lineage: Lineage | None = None, *, persist: bool = False) -> dict:
    from ..embed import Embedder
    lineage = lineage or Lineage()
    emb = Embedder.get()
    toks, factory = load(con, as_of, lineage)
    base = {"as_of": as_of, "narratives": [], "parents": [], "events": [], "factory_launches_excluded": factory,
            "launches_considered": len(toks), "semantic": emb is not None}
    if emb is None:
        base["note"] = ("The language model is not loaded (first start downloads 23 MB; SEMANTIC_METAS=0 turns "
                        "it off), so narratives cannot be read by meaning. The keyword metas still work.")
        return base
    if len(toks) < MIN_TOKENS:
        return base
    np = emb.np
    vecs = emb.embed_many([t["doc"] for t in toks])
    groups, links = group(toks, vecs, np)
    keep = []
    for g, members in enumerate(groups):
        creators = {toks[i]["creator"] for i in members if toks[i]["creator"]}
        if len(members) >= MIN_TOKENS and len(creators) >= MIN_CREATORS:
            keep.append((members, links.get(g, {})))
    if not keep:
        return base
    labels = ctfidf([m for m, _ in keep], toks)
    seed_names, seed_vecs = _seed_vectors(emb, np)
    emergent = rows(con, "SELECT id, label, centroid FROM narrative_categories WHERE seed = 0 AND created_at <= ?",
                    (as_of,)) if _has(con, "narrative_categories") else []
    history = _history(con, as_of) if _has(con, "narratives") else {"active": [], "seen": []}
    out = []
    for (members, link), words in zip(keep, labels):
        c = vecs[members].mean(0)
        c = c / (np.linalg.norm(c) or 1)
        out.append(_describe(toks, members, link, words, c, vecs, as_of, np, seed_names, seed_vecs, emergent))
    _relate(out, np)
    parents = _parents(out, np)
    for n in out:
        _novelty(n, history["seen"], np)
    events = _track(con, out, history["active"], as_of, np, persist) if _has(con, "narratives") else []
    for n in out:
        n.setdefault("id", None)
        n.setdefault("first_seen", as_of)
        n.setdefault("history_hours", 0)
    for n in out:
        _assess(n, con, as_of)
    out.sort(key=lambda n: (n["state_rank"], -(n["traction"]["buyers_h1"] or 0), -n["popularity"]["launches_6h"]))
    if persist:
        _persist(con, out, as_of, emb, np, events)
    base.update(narratives=out, parents=parents, events=events)
    for n in out:
        n.pop("_centroid", None)
        n["members"] = n.pop("_members", [])[:500]   # joins keyword metas to their narrative (explain.py)
    return base


def _has(con, table: str) -> bool:
    return bool(rows(con, "SELECT 1 AS x FROM sqlite_master WHERE type='table' AND name=?", (table,)))


def _describe(toks, members, link, words, c, vecs, as_of, np, seed_names, seed_vecs, emergent) -> dict:
    ms = [toks[i] for i in members]
    sims = vecs[members] @ c
    order = [members[j] for j in np.argsort(-sims)]
    medoid = toks[order[0]]
    by_buyers = sorted(ms, key=lambda t: -(t["buyers"] or 0))
    creators = {t["creator"] for t in ms if t["creator"]}
    posts = Counter(t["x_post"] for t in ms if t["x_post"] and t["post_text"])
    top_post = None
    if posts:
        p, n = posts.most_common(1)[0]
        src = next(t for t in ms if t["x_post"] == p)
        top_post = {"post": p, "url": "https://x.com/" + p, "author": src["post_author"], "text": clean(src["post_text"], 280),
                    "followers": src["post_followers"], "likes": src["post_likes"], "tokens": n}
    descs = Counter(meaningful_description(t["description"]) for t in ms if meaningful_description(t["description"]))
    names = Counter(_norm_name(t["name"]) for t in ms)
    clones = sum(n - 1 for n in names.values() if n > 1)
    by_meaning = len(ms) - sum(link.values())
    s1 = [t["obs"] for t in ms if t["obs"]]
    s0 = [t["obs_prev"] for t in ms if t["obs_prev"]]
    sm = lambda xs, k: sum((x.get(k) or 0) for x in xs)  # noqa: E731
    recent = [t for t in ms if t["created_at"] > as_of - H]
    base = [t for t in ms if t["created_at"] <= as_of - H]
    rate = len({t["creator"] for t in base if t["creator"]}) / ((WINDOW_S - H) / H)
    n1 = len({t["creator"] for t in recent if t["creator"]})
    return {
        "_centroid": c, "_members": [t["mint"] for t in ms],
        "title": medoid["name"] or medoid["symbol"] or medoid["mint"][:6],
        "label": " · ".join(words[:3]) if words else (medoid["name"] or "?"),
        "terms": words,
        "category": categorize(c, seed_names, seed_vecs, emergent, np),
        "represents": {"post": top_post, "description": descs.most_common(1)[0][0] if descs else None,
                       "examples": [{"name": t["name"], "symbol": t["symbol"], "mint": t["mint"], "buyers": t["buyers"]}
                                    for t in by_buyers[:6]]},
        "grouping": {"by_meaning": by_meaning, "links": link, "coherence": round(float(sims.mean()), 2),
                     "weakest_member_similarity": round(float(sims.min()), 2)},
        "cluster": _cluster(ms, vecs[members], c, np),
        "popularity": {"launches_6h": len(ms), "creators_6h": len(creators), "launches_1h": len(recent),
                       "creators_1h": n1, "creator_rate_h": round(rate, 2),
                       "velocity_z": round((n1 - rate) / math.sqrt(rate + 1), 2),
                       "clone_share": round(clones / len(ms), 2),
                       "posts_linked": sum(posts.values()), "first_launch_at": min(t["created_at"] for t in ms)},
        "traction": {"tokens_traded": len(s1), "buyers_h1": sm(s1, "buyers_h1"), "organic_buyers_h1": sm(s1, "organic_buyers_h1"),
                     "buyers_h1_hour_ago": sm(s0, "buyers_h1") if s0 else None, "net_sol_h1": round(sm(s1, "net_sol_h1"), 2),
                     "top_token_share": round((by_buyers[0]["buyers"] or 0) / max(1, sum(t["buyers"] or 0 for t in ms)), 2)
                     if s1 else None,
                     "smart_buyers_h1": sm(s1, "smart_buyers_h1") + sm(s1, "labelled_buyers_h1"),
                     "buyers_per_launch_1h": round(sm(s1, "buyers_h1") / max(1, len(recent) or len(ms)), 1)},
        "risks_raw": {"bundled_tokens": sum(1 for x in s1 if (x.get("launch_block_buyers") or 0) >= 3),
                      "insider_buyers": sm(s1, "insider_buyers_h1"),
                      "dev_sold_tokens": sum(1 for x in s1 if (x.get("dev_sold_sol") or 0) >= 0.5),
                      "bot_heavy_tokens": sum(1 for x in s1 if x.get("organic_buyers_h1") is not None and (x.get("buyers_h1") or 0) >= 5
                                              and x["organic_buyers_h1"] < 0.5 * x["buyers_h1"])},
    }


def _cluster(ms: list[dict], v, c, np, cap: int = 40) -> dict:
    """The member tokens as a graph for display: the most-bought `cap` of them, joined by the hard
    links that grouped them (same post, picture, name) and each to its nearest neighbour by meaning."""
    from ..images import distance
    keep = sorted(range(len(ms)), key=lambda i: -(ms[i]["buyers"] or 0))[:cap]
    sub = v[keep]
    sims = sub @ c
    nodes = [{"mint": ms[i]["mint"], "name": ms[i]["name"], "symbol": ms[i]["symbol"], "buyers": ms[i]["buyers"] or 0,
              "similarity": round(float(s), 2), "created_at": ms[i]["created_at"]} for i, s in zip(keep, sims)]
    edges, seen = [], set()

    def add(a, b, kind):
        k = (min(a, b), max(a, b))
        if a != b and k not in seen:
            seen.add(k)
            edges.append([a, b, kind])
    hubs: dict = {}
    for a, i in enumerate(keep):
        t = ms[i]
        for kind, key in (("same X post", t["x_post"]), ("same name", _norm_name(t["name"]) if len(_norm_name(t["name"])) >= 3 else None)):
            if key:
                b = hubs.setdefault((kind, key), a)
                add(a, b, kind)
    imgs = [(a, ms[i]["image_hash"]) for a, i in enumerate(keep) if ms[i]["image_hash"] is not None]
    for x in range(len(imgs)):
        for y in range(x):
            if distance(imgs[x][1], imgs[y][1]) <= 6:
                add(imgs[x][0], imgs[y][0], "same picture")
                break
    if len(keep) > 1:
        S = sub @ sub.T
        np.fill_diagonal(S, -1)
        for a in range(len(keep)):
            add(a, int(S[a].argmax()), "meaning")
    for a, n in enumerate(nodes):
        n["via"] = sorted({e[2] for e in edges if a in e[:2] and e[2] != "meaning"}) or ["meaning"]
    return {"nodes": nodes, "edges": edges, "shown": len(keep), "of": len(ms)}


def _relate(out: list[dict], np) -> None:
    """Closest other narrative, and what sets this one apart from it."""
    if len(out) < 2:
        return
    C = np.stack([n["_centroid"] for n in out])
    S = C @ C.T
    for i, n in enumerate(out):
        S[i, i] = -1
        j = int(S[i].argmax())
        other = out[j]
        own = [w for w in n["terms"] if w not in set(other["terms"])][:3]
        n["closest"] = {"label": other["label"], "title": other["title"], "similarity": round(float(S[i, j]), 2),
                        "distinct_terms": own}


def _parents(out: list[dict], np) -> list[dict]:
    if not out:
        return []
    order = sorted(range(len(out)), key=lambda i: -out[i]["popularity"]["launches_6h"])
    heads: list[int] = []
    assign = {}
    for i in order:
        best = max(heads, key=lambda h: float(out[h]["_centroid"] @ out[i]["_centroid"]), default=None)
        if best is not None and float(out[best]["_centroid"] @ out[i]["_centroid"]) >= T_PARENT:
            assign[i] = best
        else:
            heads.append(i)
            assign[i] = i
    parents = []
    for h in heads:
        kids = [i for i, p in assign.items() if p == h]
        words = Counter(w for i in kids for w in out[i]["terms"][:3])
        label = " · ".join(w for w, _ in words.most_common(3))
        parents.append({"label": label, "sub_metas": [out[i]["label"] for i in kids],
                        "launches_6h": sum(out[i]["popularity"]["launches_6h"] for i in kids)})
        for i in kids:
            out[i]["parent"] = {"label": label, "siblings": [out[k]["label"] for k in kids if k != i][:4]}
    return parents


# ---------------------------------------------------------------- history, tracking

def _history(con, as_of: int) -> dict:
    act = rows(con, """SELECT id, label, centroid, first_seen, last_seen FROM narratives
                       WHERE last_seen <= ? AND last_seen > ? AND status = 'active'""", (as_of, as_of - 12 * H))
    seen = rows(con, "SELECT id, label, centroid, first_seen FROM narratives WHERE first_seen <= ? AND first_seen > ?",
                (as_of - H, as_of - 7 * 86400))
    return {"active": act, "seen": seen}


def _vec(blob, np):
    return np.frombuffer(blob, dtype=np.float16).astype(np.float32)


def _novelty(n: dict, seen: list[dict], np) -> None:
    sims = [(float(_vec(s["centroid"], np) @ n["_centroid"]), s) for s in seen]
    best = max(sims, key=lambda x: x[0], default=(None, None))
    n["novelty"] = {"score": round(1 - best[0], 2) if best[0] is not None else None,
                    "most_similar_before": best[1]["label"] if best[1] and best[0] >= 0.5 else None,
                    "basis": f"compared with {len(seen)} narratives from the last 7 days" if seen else "no history yet"}


def _track(con, out: list[dict], active: list[dict], as_of: int, np, persist: bool) -> list[dict]:
    """Give each narrative the id it had before, and record merges and splits."""
    events = []
    if not active:
        for n in out:
            n["id"], n["first_seen"], n["history_hours"] = None, as_of, 0
        return events
    A = np.stack([_vec(a["centroid"], np) for a in active])
    claimed = defaultdict(list)
    for i, n in enumerate(out):
        s = A @ n["_centroid"]
        hits = [j for j in np.argsort(-s) if s[j] >= T_SAME]
        n["id"] = active[hits[0]]["id"] if hits else None
        n["first_seen"] = active[hits[0]]["first_seen"] if hits else as_of
        if hits:
            claimed[hits[0]].append(i)
        if len(hits) >= 2:
            events.append({"kind": "merge", "at": as_of, "into": n["label"],
                           "from": [active[j]["label"] for j in hits[:3]]})
            n["merged_from"] = [active[j]["label"] for j in hits[1:3]]
    for j, idx in claimed.items():
        if len(idx) >= 2:                                 # one old narrative, several new ones
            keep = max(idx, key=lambda i: out[i]["popularity"]["launches_6h"])
            for i in idx:
                if i != keep:
                    out[i]["id"], out[i]["first_seen"] = None, as_of
                    out[i]["split_from"] = active[j]["label"]
            events.append({"kind": "split", "at": as_of, "from": active[j]["label"],
                           "into": [out[i]["label"] for i in idx]})
    for n in out:
        n["history_hours"] = round((as_of - n["first_seen"]) / H, 1)
    return events


def _assess(n: dict, con, as_of: int) -> None:
    """State, drivers and risks, each tied to a measurement."""
    P, T, R = n["popularity"], n["traction"], n["risks_raw"]
    z, b1, b0 = P["velocity_z"], T["buyers_h1"], T["buyers_h1_hour_ago"]
    growth = (b1 / b0) if b0 else None
    hist = rows(con, """SELECT observed_at, launches_6h, buyers_h1, buyers_per_launch, state FROM narrative_obs
                        WHERE narrative_id = ? AND observed_at <= ? ORDER BY observed_at""",
                (n["id"], as_of)) if n.get("id") and _has(con, "narrative_obs") else []
    bpl_before = next((h["buyers_per_launch"] for h in hist if h["observed_at"] <= as_of - H), None)
    n["history"] = [[h["observed_at"], h["launches_6h"], h["buyers_h1"], h["state"]] for h in hist[-36:]]
    reasons = []
    if n["history_hours"] < 1 and P["first_launch_at"] > as_of - 2 * H:
        state = "new"
        reasons.append(f"first seen {round((as_of - P['first_launch_at']) / 60)} min ago")
    elif z >= 2 and growth is not None and growth >= 1.2:
        state = "accelerating"
        reasons.append(f"creators launching at {P['creators_1h']}/h vs {P['creator_rate_h']}/h before (z={z})")
        reasons.append(f"buyers up {round((growth - 1) * 100)}% on an hour ago")
    elif z >= 2:
        state = "heating"
        reasons.append(f"creators launching at {P['creators_1h']}/h vs {P['creator_rate_h']}/h before (z={z})")
        reasons.append("buying has not followed yet" if not b1 else "buyers flat on an hour ago")
    elif (growth or 0) >= 1.3 and b1 >= 20:
        state = "bought"
        reasons.append(f"buyers up {round((growth - 1) * 100)}% while launches are not accelerating")
    elif P["clone_share"] >= 0.5 or (bpl_before and T["buyers_per_launch_1h"] < 0.6 * bpl_before and z >= 0):
        state = "saturating"
        if P["clone_share"] >= 0.5:
            reasons.append(f"{round(P['clone_share'] * 100)}% of launches reuse a name already in the group")
        if bpl_before and T["buyers_per_launch_1h"] < 0.6 * bpl_before:
            reasons.append(f"buyers per launch fell from {bpl_before} to {T['buyers_per_launch_1h']}")
    elif z <= -1 and (growth is not None and growth < 0.8):
        state = "fading"
        reasons.append(f"creators down to {P['creators_1h']}/h from {P['creator_rate_h']}/h; buyers down "
                       f"{round((1 - growth) * 100)}%")
    else:
        state = "steady"
        reasons.append(f"launch rate near its 5-hour average (z={z})")
    n["state"] = state
    n["state_rank"] = ["accelerating", "bought", "heating", "new", "steady", "saturating", "fading"].index(state)
    n["state_reasons"] = reasons
    drivers = []
    post = n["represents"]["post"]
    if post and post["tokens"] >= 2:
        drivers.append((3 + post["tokens"] + math.log10((post["followers"] or 0) + 1),
                        f"{post['tokens']} launches cite @{post['author']}'s post"
                        + (f" ({_k(post['followers'])} followers)" if post["followers"] else "") + f": “{post['text'][:140]}”"))
    if T["top_token_share"] and T["top_token_share"] >= 0.5 and b1 >= 20:
        top = n["represents"]["examples"][0]
        drivers.append((4, f"buying is concentrated in ${top['symbol'] or top['name']} "
                           f"({round(T['top_token_share'] * 100)}% of the group's buyers)"))
    if n["grouping"]["links"].get("same picture"):
        drivers.append((3, "the same picture is being relaunched under different names"))
    if P["creators_6h"] >= 5 and not (post and post["tokens"] >= 2):
        drivers.append((2 + P["creators_6h"] / 10, f"{P['creators_6h']} independent creators launching variations"))
    if T["smart_buyers_h1"] >= 2:
        drivers.append((3, f"{T['smart_buyers_h1']} buys from proven or labelled wallets"))
    if z >= 3:
        drivers.append((2, f"launch rate {round(P['creators_1h'] / max(P['creator_rate_h'], 0.2), 1)}× its recent average"))
    n["drivers"] = [d for _, d in sorted(drivers, key=lambda x: -x[0])][:3]
    risks = []
    if R["bundled_tokens"]:
        risks.append(f"{R['bundled_tokens']} token(s) bundled at launch")
    if R["insider_buyers"]:
        risks.append(f"{R['insider_buyers']} labelled insider buyer(s)")
    if R["dev_sold_tokens"]:
        risks.append(f"creator sold in {R['dev_sold_tokens']} token(s)")
    if R["bot_heavy_tokens"]:
        risks.append(f"bot-heavy buying in {R['bot_heavy_tokens']} token(s)")
    if P["clone_share"] >= 0.3:
        risks.append(f"{round(P['clone_share'] * 100)}% copycat launches")
    n["risks"] = risks
    # evidence quality: how much the grouping and the assessment rest on
    q, why = 0.0, []
    q += min(1, P["creators_6h"] / 6) * 0.35
    if P["creators_6h"] < 3:
        why.append(f"only {P['creators_6h']} creators")
    q += (0.25 if post else 0.1 if n["represents"]["description"] else 0)
    if not post and not n["represents"]["description"]:
        why.append("names only: no description or linked post to read")
    q += min(1, T["tokens_traded"] / 3) * 0.25
    if not T["tokens_traded"]:
        why.append("no token has 5+ buyers yet")
    q += 0.15 if n["grouping"]["coherence"] >= 0.7 else 0.07 if n["grouping"]["coherence"] >= 0.6 else 0
    if n["grouping"]["coherence"] < 0.6:
        why.append(f"loosely related members (coherence {n['grouping']['coherence']})")
    n["evidence"] = {"quality": round(q, 2), "level": "high" if q >= 0.7 else "medium" if q >= 0.45 else "low",
                     "gaps": why}
    n["opportunity"] = "Not assessed: no tested link between a narrative state and profit. " + PAST.get(
        n["state"], "") + "Details in docs/RESEARCH_NARRATIVES.md."
    n["explanation"] = _explain(n)


def _k(v) -> str:
    if v is None:
        return "?"
    return f"{v / 1e6:.1f}M" if v >= 1e6 else f"{v / 1e3:.0f}k" if v >= 1e3 else str(v)


def _explain(n: dict) -> list[str]:
    """Plain sentences built only from the evidence above."""
    P, T, cat = n["popularity"], n["traction"], n["category"]
    ex = n["represents"]["examples"]
    names = ", ".join(e["name"] or e["symbol"] for e in ex[:4])
    s = [f"{P['launches_6h']} launches from {P['creators_6h']} creators in 6 hours, including {names}."]
    if n["represents"]["post"]:
        p = n["represents"]["post"]
        s.append(f"They point to a post by @{p['author']}: “{p['text'][:200]}”")
    elif n["represents"]["description"]:
        s.append(f"Creators describe it as: “{n['represents']['description'][:200]}”")
    else:
        s.append(f"Read from the names alone, the shared idea is: {', '.join(n['terms'][:4]) or n['title']}.")
    if cat.get("primary"):
        sec = f", also {', '.join(cat['secondary'])}" if cat["secondary"] else ""
        s.append(f"Category: {cat['primary']}{sec}" + (" (a category this app created from earlier narratives)"
                                                       if cat.get("emergent") else "") + ".")
    else:
        s.append(f"It fits none of the known categories (closest: {cat['nearest_seed']}, {cat['primary_score']}); "
                 "treated as a new kind of meta.")
    if n.get("closest") and n["closest"]["similarity"] >= 0.5 and n["closest"]["distinct_terms"]:
        s.append(f"Closest other narrative is {n['closest']['label']} ({n['closest']['similarity']}); this one is "
                 f"specifically about {', '.join(n['closest']['distinct_terms'])}.")
    g = n["grouping"]["links"]
    if g:
        s.append("Grouped by meaning, plus " + ", ".join(f"{v} link(s) by {k}" for k, v in g.items()) + ".")
    return s


def _persist(con, out: list[dict], as_of: int, emb, np, events: list[dict]) -> None:
    con.execute("BEGIN")
    try:
        for n in out:
            blob = n["_centroid"].astype(np.float16).tobytes()
            if n.get("id"):
                con.execute("UPDATE narratives SET label=?, centroid=?, last_seen=?, category=? WHERE id=?",
                            (n["label"], blob, as_of, n["category"].get("primary"), n["id"]))
            else:
                cur = con.execute("INSERT INTO narratives (label, centroid, first_seen, last_seen, category, status) "
                                  "VALUES (?,?,?,?,?, 'active')", (n["label"], blob, as_of, as_of, n["category"].get("primary")))
                n["id"] = cur.lastrowid
            insert(con, "narrative_obs", {"narrative_id": n["id"], "observed_at": as_of,
                                          "launches_6h": n["popularity"]["launches_6h"],
                                          "creators_6h": n["popularity"]["creators_6h"],
                                          "buyers_h1": n["traction"]["buyers_h1"],
                                          "buyers_per_launch": n["traction"]["buyers_per_launch_1h"],
                                          "net_sol_h1": n["traction"]["net_sol_h1"], "state": n["state"],
                                          "members": json.dumps(n["_members"][:200])})
            cat = n["category"]
            # a novel narrative with enough evidence becomes a category of its own
            if cat.get("novel") and n["popularity"]["launches_6h"] >= 5 and n["popularity"]["creators_6h"] >= 3:
                cur = con.execute("INSERT INTO narrative_categories (label, centroid, created_at, seed) VALUES (?,?,?,0)",
                                  (n["label"], blob, as_of))
                cat.update(primary=n["label"], emergent=True, emergent_id=cur.lastrowid, novel=False, created_now=True)
            # each coin's first narrative and category, kept for the macro view (analytics/macro.py)
            con.executemany("INSERT OR IGNORE INTO token_narrative (mint, narrative_id, label, category, at) VALUES (?,?,?,?,?)",
                            [(m, n["id"], n["label"], cat.get("primary"), as_of) for m in n["_members"]])
        for e in events:
            insert(con, "narrative_events", {"at": as_of, "kind": e["kind"], "detail": json.dumps(e)})
        con.execute("UPDATE narratives SET status='ended' WHERE status='active' AND last_seen < ?", (as_of - 12 * H,))
        if OBS_KEEP_S:
            con.execute("DELETE FROM narrative_obs WHERE observed_at < ?", (as_of - OBS_KEEP_S,))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
