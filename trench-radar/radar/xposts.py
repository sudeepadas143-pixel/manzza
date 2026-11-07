"""Text and engagement of the X posts that launches link to.

No API key and no X account. Two public, read-only endpoints, checked 2026-10-21:
  cdn.syndication.twimg.com/tweet-result   X's own embed service (what embedded tweets on
                                           websites use): text, likes, replies, author handle
  api.fxtwitter.com                        FxTwitter, an open-source embed proxy; used for the
                                           author's follower count and as a fallback
(publish.twitter.com/oembed redirects; api.vxtwitter.com is behind a Cloudflare challenge.)
Neither is a supported API: either can change or rate-limit without notice, so failures are
recorded and skipped. Only posts linked by 2+ launches, or by a token with 5+ buyers in an hour,
are fetched: a few dozen an hour.

Post text also goes into social_posts (source 'x_linked'), so narrative detection sees the
words of the posts coins are being launched about. That is a narrow sample of X (only posts
someone launched a coin for), and the dashboard says so.
"""
from __future__ import annotations

import re
from datetime import datetime

import httpx

SYND = "https://cdn.syndication.twimg.com/tweet-result?id={id}&token=a"
FX = "https://api.fxtwitter.com/{user}/status/{id}"
_POST = re.compile(r"^([A-Za-z0-9_]{1,15})/status/(\d{5,25})$")


def _ts(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except ValueError:
        try:
            return int(datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").timestamp())
        except ValueError:
            return None


def parse_syndication(d: dict) -> dict | None:
    if not isinstance(d, dict) or d.get("__typename") not in ("Tweet", None) or not d.get("id_str"):
        return None
    u = d.get("user") or {}
    q = d.get("quoted_tweet") or {}
    return {"text": (d.get("text") or "")[:1000], "likes": d.get("favorite_count"),
            "replies": d.get("conversation_count"), "created_at": _ts(d.get("created_at")),
            "author": (u.get("screen_name") or "").lower() or None, "followers": u.get("followers_count"),
            "verified": bool(u.get("is_blue_verified") or u.get("verified")),
            "quoted_text": (q.get("text") or "")[:500] or None, "has_photo": bool(d.get("photos") or d.get("mediaDetails"))}


def parse_fx(d: dict) -> dict | None:
    t = (d or {}).get("tweet") if isinstance(d, dict) else None
    if not t:
        return None
    a = t.get("author") or {}
    q = t.get("quote") or {}
    return {"text": (t.get("text") or "")[:1000], "likes": t.get("likes"), "replies": t.get("replies"),
            "reposts": t.get("retweets"), "views": t.get("views"), "created_at": t.get("created_timestamp"),
            "author": (a.get("screen_name") or "").lower() or None, "followers": a.get("followers"),
            "verified": bool((a.get("verification") or {}).get("verified")),
            "quoted_text": (q.get("text") or "")[:500] or None, "has_photo": bool((t.get("media") or {}).get("photos"))}


async def fetch_post(client: httpx.AsyncClient, post: str) -> dict | None:
    """post = 'user/status/id' -> merged fields, or None when both endpoints fail."""
    m = _POST.match(post or "")
    if not m:
        return None
    user, pid = m.groups()
    out: dict = {}
    try:
        r = await client.get(SYND.format(id=pid), timeout=10)
        if r.status_code == 200:
            out = parse_syndication(r.json()) or {}
    except (httpx.HTTPError, ValueError):
        pass
    try:
        r = await client.get(FX.format(user=user, id=pid), timeout=10)
        if r.status_code == 200:
            fx = parse_fx(r.json()) or {}
            out = {**fx, **{k: v for k, v in out.items() if v not in (None, "")}} if out else fx
    except (httpx.HTTPError, ValueError):
        pass
    return out or None
