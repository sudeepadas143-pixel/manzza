"""Social sources: X API v2 (official, paid) and Reddit (OAuth app-only or public JSON).

Browser scraping of X with a personal session (as openclaw-x-signal does) is
deliberately not used: it breaks on layout changes and risks the account.
"""
from __future__ import annotations

from datetime import datetime

from .base import Http, SourceUnavailable


def _ts(s: str | None) -> int | None:
    if not s:
        return None
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def parse_x_search(payload: dict, query: str) -> list[dict]:
    users = {u["id"]: u for u in (payload.get("includes") or {}).get("users", [])}
    out = []
    for t in payload.get("data") or []:
        u = users.get(t.get("author_id"), {})
        pm = t.get("public_metrics") or {}
        upm = u.get("public_metrics") or {}
        out.append({
            "id": f"x:{t['id']}", "source": "x",
            "author_id": t.get("author_id"), "author_handle": u.get("username"),
            "author_followers": upm.get("followers_count"),
            "author_created_at": _ts(u.get("created_at")),
            "text": t.get("text", ""), "created_at": _ts(t.get("created_at")),
            "likes": pm.get("like_count", 0), "reposts": pm.get("retweet_count", 0) + pm.get("quote_count", 0),
            "replies": pm.get("reply_count", 0), "views": pm.get("impression_count", 0),
            "url": f"https://x.com/{u.get('username', 'i')}/status/{t['id']}", "query": query,
        })
    return out


async def x_recent_search(http: Http, bearer: str | None, query: str, since_id: str | None = None,
                          max_results: int = 100) -> list[dict]:
    if not bearer:
        raise SourceUnavailable("X_BEARER_TOKEN not set")
    params = {
        "query": query, "max_results": str(max_results),
        "tweet.fields": "created_at,public_metrics,author_id,lang",
        "expansions": "author_id", "user.fields": "public_metrics,created_at,username",
    }
    if since_id:
        params["since_id"] = since_id
    payload = await http.get_json("https://api.x.com/2/tweets/search/recent", params=params,
                                  headers={"Authorization": f"Bearer {bearer}"}, retries=1)
    return parse_x_search(payload, query)


def parse_reddit_listing(payload: dict, sub: str) -> list[dict]:
    out = []
    for child in (payload.get("data") or {}).get("children", []):
        d = child.get("data") or {}
        text = (d.get("title") or "") + ("\n" + d["selftext"] if d.get("selftext") else "")
        out.append({
            "id": f"reddit:{d.get('id')}", "source": "reddit",
            "author_id": d.get("author_fullname") or d.get("author"), "author_handle": d.get("author"),
            "author_followers": None, "author_created_at": None,
            "text": text[:4000], "created_at": int(d.get("created_utc") or 0),
            "likes": d.get("score", 0), "reposts": d.get("num_crossposts", 0),
            "replies": d.get("num_comments", 0), "views": 0,
            "url": f"https://www.reddit.com{d.get('permalink', '')}", "query": f"r/{sub}",
        })
    return out


async def reddit_new(http: Http, client_id: str | None, secret: str | None, subs: list[str]) -> list[dict]:
    headers = {}
    base = "https://www.reddit.com"
    if client_id and secret:
        tok = await http.request(
            "POST", "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"}, auth=(client_id, secret), retries=0)
        headers = {"Authorization": f"Bearer {tok.json().get('access_token')}"}
        base = "https://oauth.reddit.com"
    out = []
    for sub in subs:
        suffix = "" if headers else ".json"
        payload = await http.get_json(f"{base}/r/{sub}/new{suffix}?limit=100", headers=headers, retries=0)
        out.extend(parse_reddit_listing(payload, sub))
    return out
