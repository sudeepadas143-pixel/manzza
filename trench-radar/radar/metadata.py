"""Token metadata from each launch's metadata URI (the JSON pump.fun stores for a coin).

Gives the description, image and social links. The `twitter` field very often links a
specific X post the coin is about; several launches citing the same post show which posts
are spawning coins, without reading X itself.

ipfs.io and dweb.link now refuse scripted requests (HTTP 429, "service worker gateway
only", checked 2026-10-21), so IPFS URIs are fetched through gateways that still serve
plain HTTP. Metadata is creator-supplied and untrusted: it is stored as text and escaped
by the dashboard; links are never fetched.
"""
from __future__ import annotations

import asyncio
import re

import httpx

IPFS_GATEWAYS = ("https://ipfs.filebase.io/ipfs/", "https://4everland.io/ipfs/")
_IPFS = re.compile(r"/ipfs/([A-Za-z0-9]{40,100}(?:/[^?#]*)?)")
_X_POST = re.compile(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d{5,25})", re.I)
_X_USER = re.compile(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/?(?:[?#]|$)", re.I)
_X_RESERVED = {"i", "home", "search", "intent", "share", "hashtag", "explore", "messages"}


def candidate_urls(uri: str) -> list[str]:
    m = _IPFS.search(uri or "")
    if m:
        return [g + m.group(1) for g in IPFS_GATEWAYS]
    if (uri or "").startswith("ipfs://"):
        return [g + uri[7:] for g in IPFS_GATEWAYS]
    return [uri] if (uri or "").startswith(("https://", "http://")) else []


def x_ref(*links: str | None) -> tuple[str | None, str | None]:
    """(post, account) for the first X link found: post as 'user/status/id', lowercase user."""
    for link in links:
        if not link:
            continue
        m = _X_POST.search(link)
        if m:
            return f"{m.group(1).lower()}/status/{m.group(2)}", m.group(1).lower()
    for link in links:
        m = _X_USER.search(link or "")
        if m and m.group(1).lower() not in _X_RESERVED:
            return None, m.group(1).lower()
    return None, None


def _s(v, n: int) -> str | None:
    return v.strip()[:n] or None if isinstance(v, str) else None


def parse(doc) -> dict:
    if not isinstance(doc, dict):
        raise ValueError("metadata is not a JSON object")
    ext = doc.get("extensions") if isinstance(doc.get("extensions"), dict) else {}
    tw = _s(doc.get("twitter") or ext.get("twitter"), 300)
    web = _s(doc.get("website") or ext.get("website"), 300)
    post, account = x_ref(tw, web)
    return {"description": _s(doc.get("description"), 500), "twitter": tw, "website": web,
            "telegram": _s(doc.get("telegram") or ext.get("telegram"), 300),
            "image": _s(doc.get("image"), 300), "x_post": post, "x_account": account}


async def fetch(client: httpx.AsyncClient, uri: str) -> dict | None:
    for url in candidate_urls(uri):
        try:
            r = await client.get(url, timeout=6.0)
            if r.status_code == 200 and len(r.content) < 200_000:
                return parse(r.json())
        except (httpx.HTTPError, ValueError):
            continue
    return None


async def fetch_many(client: httpx.AsyncClient, items: list[tuple[str, str]], concurrency: int = 6) -> dict[str, dict | None]:
    sem = asyncio.Semaphore(concurrency)

    async def one(mint: str, uri: str):
        async with sem:
            return mint, await fetch(client, uri)
    return dict(await asyncio.gather(*(one(m, u) for m, u in items)))
