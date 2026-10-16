"""Meta detection: which themes are accelerating in launches and in social posts.

A *meta* is a cluster of terms (e.g. {cat, wif}) that appear together in token
names/symbols and posts. Detection is term-frequency based with co-occurrence
merging — inspectable, and wrong in inspectable ways.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from ..db import rows
from ..text import classify, terms, token_terms
from .common import Lineage

H = 3600
RECENT_S, WINDOW_S, BASE_S = 1 * H, 6 * H, 24 * H   # baseline = the 24h before the 6h window


def load_launches(con, as_of: int, lineage: Lineage) -> list[dict]:
    out = rows(con, """SELECT mint, name, symbol, creator, created_at, first_seen_at FROM tokens
                       WHERE launchpad='pump-fun' AND created_at > ? AND created_at <= ?
                       AND first_seen_at <= ?""", (as_of - WINDOW_S - BASE_S, as_of, as_of))
    for r in out:
        r["terms"] = token_terms(r["name"], r["symbol"])
        lineage.saw("tokens", r["first_seen_at"])
    return out


def load_posts(con, as_of: int, lineage: Lineage) -> list[dict]:
    out = rows(con, """SELECT id, source, author_id, author_handle, author_followers, text, created_at,
                              collected_at, likes, reposts, replies, views, url, fingerprint
                       FROM social_posts WHERE is_spam=0 AND created_at > ? AND created_at <= ?
                       AND collected_at <= ?""", (as_of - WINDOW_S - BASE_S, as_of, as_of))
    for r in out:
        r["terms"] = terms(r["text"], max_terms=20)
        lineage.saw("social_posts", r["collected_at"])
    return out


def _poisson_z(recent: float, base_rate_per_window: float) -> float:
    return (recent - base_rate_per_window) / math.sqrt(base_rate_per_window + 1)


def candidate_terms(launches: list[dict], posts: list[dict], as_of: int,
                    min_launches: int = 4, min_mentions: int = 5, top: int = 40) -> list[str]:
    lc, pc = Counter(), Counter()
    for r in launches:
        if r["created_at"] > as_of - WINDOW_S:
            lc.update(r["terms"])
    for p in posts:
        if p["created_at"] > as_of - WINDOW_S:
            pc.update(p["terms"])
    cands = {t for t, n in lc.items() if n >= min_launches} | {t for t, n in pc.items() if n >= min_mentions}
    return sorted(cands, key=lambda t: lc[t] + 0.5 * pc[t], reverse=True)[:top]


def cluster_terms(cands: list[str], launches: list[dict], posts: list[dict], as_of: int,
                  overlap: float = 0.7) -> list[list[str]]:
    """Merge terms whose documents overlap strongly (e.g. 'wif' inside 'cat wif hat')."""
    docs = defaultdict(set)
    for r in launches:
        if r["created_at"] > as_of - WINDOW_S:
            for t in r["terms"]:
                docs[t].add(r["mint"])
    for p in posts:
        if p["created_at"] > as_of - WINDOW_S:
            for t in p["terms"]:
                docs[t].add(p["id"])
    clusters: list[list[str]] = []
    for t in cands:                       # cands are ordered by activity, so heads are dominant terms
        for c in clusters:
            a, b = docs[c[0]], docs[t]
            if a and b and len(a & b) / min(len(a), len(b)) >= overlap:
                c.append(t)
                break
        else:
            clusters.append([t])
    return clusters


def meta_social(posts: list[dict], term_set: set[str], as_of: int) -> dict:
    mine = [p for p in posts if term_set & set(p["terms"])]
    recent = [p for p in mine if p["created_at"] > as_of - RECENT_S]
    window = [p for p in mine if p["created_at"] > as_of - WINDOW_S]
    base = [p for p in mine if p["created_at"] <= as_of - WINDOW_S]
    base_rate_h = len(base) / (BASE_S / H)
    window_rate_h = len(window) / (WINDOW_S / H)
    # independent accounts: distinct authors, ignoring copy-paste waves (fingerprint used >= 3 times)
    fp_counts = Counter(p["fingerprint"] for p in window)
    independent = {p["author_id"] for p in window if fp_counts[p["fingerprint"]] < 3 and p["author_id"]}
    def eng(p):
        return (p["likes"] or 0) + 2 * (p["reposts"] or 0) + (p["replies"] or 0)
    influential = sorted(window, key=lambda p: (eng(p), p["author_followers"] or 0), reverse=True)[:3]
    sent = [classify(p["text"]) for p in window]
    labels = Counter(s["label"] for s in sent)
    return {
        "mentions_1h": len(recent), "mentions_6h": len(window), "mentions_base_24h": len(base),
        "mention_rate_h": round(window_rate_h, 3), "mention_base_rate_h": round(base_rate_h, 3),
        "mention_accel_z": round(_poisson_z(len(recent), base_rate_h), 2) if mine else None,
        "authors_6h": len({p["author_id"] for p in window if p["author_id"]}),
        "independent_authors_6h": len(independent),
        "copy_paste_posts_6h": sum(n for n in fp_counts.values() if n >= 3),
        "sentiment_6h": round(sum(s["polarity"] for s in sent) / len(sent), 3) if sent else None,
        "sentiment_labels": dict(labels),
        "influential_posts": [{
            "url": p["url"], "author": p["author_handle"], "followers": p["author_followers"],
            "engagement": eng(p), "text": p["text"][:280], "created_at": p["created_at"],
        } for p in influential],
    }


def meta_launches(launches: list[dict], term_set: set[str], as_of: int, all_window: int) -> dict:
    mine = [r for r in launches if term_set & set(r["terms"])]
    recent = [r for r in mine if r["created_at"] > as_of - RECENT_S]
    window = [r for r in mine if r["created_at"] > as_of - WINDOW_S]
    base = [r for r in mine if r["created_at"] <= as_of - WINDOW_S]
    base_rate_h = len(base) / (BASE_S / H)
    sym = Counter((r["symbol"] or "").upper() for r in window)
    first = min((r["created_at"] for r in mine), default=None)
    return {
        "mints_6h": [r["mint"] for r in window],
        "mints_all": [r["mint"] for r in mine],
        "launches_1h": len(recent), "launches_6h": len(window), "launches_base_24h": len(base),
        "launch_rate_h": round(len(window) / 6, 3), "launch_base_rate_h": round(base_rate_h, 3),
        "launch_accel_z": round(_poisson_z(len(recent), base_rate_h), 2),
        "launch_share_6h": round(len(window) / all_window, 4) if all_window else None,
        "duplicate_symbol_share_6h": round(sum(n for n in sym.values() if n > 1) / len(window), 3) if window else None,
        "first_seen_in_window_h": round((as_of - first) / H, 1) if first else None,
        "creators_known_6h": sum(1 for r in window if r["creator"] and r["creator"] != "unknown"),
    }


def detect(con, as_of: int, lineage: Lineage | None = None) -> tuple[list[dict], dict]:
    lineage = lineage or Lineage()
    launches = load_launches(con, as_of, lineage)
    posts = load_posts(con, as_of, lineage)
    all_window = sum(1 for r in launches if r["created_at"] > as_of - WINDOW_S)
    clusters = cluster_terms(candidate_terms(launches, posts, as_of), launches, posts, as_of)
    metas = []
    for cl in clusters:
        ts = set(cl)
        metas.append({"key": cl[0], "terms": cl,
                      "launch": meta_launches(launches, ts, as_of, all_window),
                      "social": meta_social(posts, ts, as_of)})
    ctx = {"launches_6h_total": all_window, "posts_6h_total": sum(1 for p in posts if p["created_at"] > as_of - WINDOW_S),
           "launches_loaded": len(launches), "posts_loaded": len(posts)}
    return metas, ctx
