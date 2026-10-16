"""Shared HTTP plumbing: timeouts, bounded retries, per-host pacing, run bookkeeping."""
from __future__ import annotations

import asyncio
import os
import logging
import time
from contextlib import asynccontextmanager

import httpx

from ..config import Settings
from ..db import insert, now

log = logging.getLogger("radar.sources")

UA = "trench-radar/0.1 (+research; no trading)"


class SourceUnavailable(Exception):
    """Source is not configured, blocked, rate-limited or down. Never fatal."""


class Pacer:
    """Minimum spacing between calls to one host (free-tier rate limits)."""

    def __init__(self, min_interval_s: float):
        self.min_interval_s = min_interval_s
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delta = time.monotonic() - self._last
            if delta < self.min_interval_s:
                await asyncio.sleep(self.min_interval_s - delta)
            self._last = time.monotonic()


PACERS: dict[str, Pacer] = {
    # Documented free limit is 30/min, but it is shared per egress IP and 429s appear earlier
    # in practice; 4s spacing (15/min) held in testing. Override with GT_MIN_INTERVAL_S.
    "api.geckoterminal.com": Pacer(float(os.environ.get("GT_MIN_INTERVAL_S", "4.0"))),
    "api.dexscreener.com": Pacer(1.1),
    "api.llama.fi": Pacer(1.0),
    "api.x.com": Pacer(1.1),
    "oauth.reddit.com": Pacer(1.1),
    "www.reddit.com": Pacer(2.0),
}


class Http:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={"User-Agent": UA, "Accept": "application/json"},
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, url: str, *, retries: int = 2, **kw) -> httpx.Response:
        host = httpx.URL(url).host
        pacer = PACERS.get(host)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            if pacer:
                await pacer.wait()
            try:
                resp = await self.client.request(method, url, **kw)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("retry-after")
                default = 12.0 * (attempt + 1) if resp.status_code == 429 else 2.0 * (attempt + 1)
                wait = float(retry_after) if retry_after and retry_after.isdigit() else default
                last_exc = SourceUnavailable(f"{host} HTTP {resp.status_code}")
                if attempt < retries:
                    await asyncio.sleep(min(wait, 30))
                    continue
                raise last_exc
            if resp.status_code in (401, 403):
                hint = " (Cloudflare challenge)" if "Just a moment" in resp.text[:2000] else ""
                raise SourceUnavailable(f"{host} HTTP {resp.status_code}{hint}")
            if resp.status_code >= 400:
                raise SourceUnavailable(f"{host} HTTP {resp.status_code}: {self.settings.redact(resp.text[:200])}")
            return resp
        raise SourceUnavailable(self.settings.redact(f"{host} unreachable: {last_exc}"))

    async def get_json(self, url: str, **kw):
        resp = await self.request("GET", url, **kw)
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceUnavailable(f"{httpx.URL(url).host} returned non-JSON") from exc

    async def post_json(self, url: str, payload, **kw):
        resp = await self.request("POST", url, json=payload, **kw)
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceUnavailable(f"{httpx.URL(url).host} returned non-JSON") from exc


class RunRecorder:
    """Context for one source call; writes a source_runs row whatever happens."""

    def __init__(self, con, settings: Settings, source: str, job: str):
        self.con, self.settings, self.source, self.job = con, settings, source, job
        self.items = 0
        self.status = "ok"
        self.error: str | None = None

    def skip(self, reason: str) -> None:
        self.status, self.error = "skipped", reason


@asynccontextmanager
async def record_run(con, settings: Settings, source: str, job: str):
    rec = RunRecorder(con, settings, source, job)
    started = now()
    t0 = time.monotonic()
    try:
        yield rec
    except SourceUnavailable as exc:
        rec.status, rec.error = "unavailable", settings.redact(str(exc))
        log.warning("%s/%s unavailable: %s", source, job, rec.error)
    except Exception as exc:  # a bug or schema drift in one source must not stop the others
        rec.status, rec.error = "error", settings.redact(f"{type(exc).__name__}: {exc}")
        log.exception("%s/%s failed", source, job)
    finally:
        insert(con, "source_runs", {
            "source": source, "job": job, "started_at": started, "finished_at": now(),
            "status": rec.status, "items": rec.items,
            "latency_ms": int((time.monotonic() - t0) * 1000), "error": rec.error,
        })
        con.commit()
