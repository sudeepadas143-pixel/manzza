"""Shared HTTP plumbing: timeouts, bounded retries, per-host pacing, run bookkeeping."""
from __future__ import annotations

import asyncio
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
    """Spacing between calls to one host (free-tier rate limits).

    Adaptive: a 429 doubles the spacing (up to max_interval_s), and each success eases it back
    toward the base by 5%. Free limits are shared per IP, so the safe rate differs by network.
    """

    def __init__(self, min_interval_s: float, max_interval_s: float = 60.0):
        self.base_interval_s = min_interval_s
        self.min_interval_s = min_interval_s
        self.max_interval_s = max_interval_s
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delta = time.monotonic() - self._last
            if delta < self.min_interval_s:
                await asyncio.sleep(self.min_interval_s - delta)
            self._last = time.monotonic()

    def penalize(self) -> None:
        before = self.min_interval_s
        self.min_interval_s = min(self.max_interval_s, self.min_interval_s * 2)
        if self.min_interval_s != before:
            log.info("rate limited: spacing requests %.0fs apart for a while", self.min_interval_s)

    def relax(self) -> None:
        self.min_interval_s = max(self.base_interval_s, self.min_interval_s * 0.95)


PACERS: dict[str, Pacer] = {
    "api.dexscreener.com": Pacer(1.1),
    "api.llama.fi": Pacer(1.0),
    "coins.llama.fi": Pacer(1.0),
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
            if resp.status_code == 429 and pacer:
                pacer.penalize()
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("retry-after")
                default = 15.0 * (attempt + 1) if resp.status_code == 429 else 2.0 * (attempt + 1)
                wait = float(retry_after) if retry_after and retry_after.isdigit() else default
                last_exc = SourceUnavailable(f"{host} HTTP {resp.status_code}")
                if attempt < retries:
                    await asyncio.sleep(min(wait, 60))
                    continue
                raise last_exc
            if resp.status_code in (401, 403):
                hint = " (Cloudflare challenge)" if "Just a moment" in resp.text[:2000] else ""
                raise SourceUnavailable(f"{host} HTTP {resp.status_code}{hint}")
            if resp.status_code >= 400:
                raise SourceUnavailable(f"{host} HTTP {resp.status_code}: {self.settings.redact(resp.text[:200])}")
            if pacer:
                pacer.relax()
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


def blocked_backoff(con, source: str, job: str, *, after: int = 3, hours: float = 6.0) -> str | None:
    """For optional sources that refuse this network (HTTP 401/403): once the last `after` runs
    were all refused, stop asking for `hours`, then try once more. Returns a skip reason or None."""
    rows = con.execute(
        "SELECT status, error, started_at FROM source_runs WHERE source=? AND job=? AND status!='skipped' "
        "ORDER BY started_at DESC LIMIT ?", (source, job, after)).fetchall()
    if len(rows) < after or not all(r["status"] == "unavailable" and r["error"] and
                                     ("HTTP 403" in r["error"] or "HTTP 401" in r["error"]) for r in rows):
        return None
    if now() - rows[0]["started_at"] >= hours * 3600:
        return None
    return f"refused {after} times in a row from this network; retrying {hours:g}h after the last attempt"


# Last outcome per source/job, so the console reports changes instead of repeating itself.
_LAST: dict[tuple[str, str], str] = {}


@asynccontextmanager
async def record_run(con, settings: Settings, source: str, job: str):
    rec = RunRecorder(con, settings, source, job)
    started = now()
    t0 = time.monotonic()
    key = (source, job)
    try:
        yield rec
    except SourceUnavailable as exc:
        rec.status, rec.error = "unavailable", settings.redact(str(exc))
        if _LAST.get(key) != f"unavailable:{rec.error}":
            log.warning("%s/%s unavailable: %s", source, job, rec.error)
    except Exception as exc:  # a bug or schema drift in one source must not stop the others
        rec.status, rec.error = "error", settings.redact(f"{type(exc).__name__}: {exc}")
        log.exception("%s/%s failed", source, job)
    finally:
        prev = _LAST.get(key)
        if rec.status == "ok":
            if prev and not prev.startswith("ok"):
                log.info("%s/%s recovered: %d items", source, job, rec.items)
            else:
                log.info("%s/%s ok: %d items", source, job, rec.items)
        elif rec.status == "skipped" and prev != f"skipped:{rec.error}":
            log.info("%s/%s skipped: %s", source, job, rec.error)
        _LAST[key] = rec.status if rec.status in ("ok", "error") else f"{rec.status}:{rec.error}"
        insert(con, "source_runs", {
            "source": source, "job": job, "started_at": started, "finished_at": now(),
            "status": rec.status, "items": rec.items,
            "latency_ms": int((time.monotonic() - t0) * 1000), "error": rec.error,
        })
        con.commit()
