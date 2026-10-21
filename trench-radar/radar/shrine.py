"""Optional: Shrine's free hourly replay archive of pump.fun events (shrine.trade).

What it is (checked 2026-10-21): every launch, trade and curve completion across pump.fun
(and other Solana DEXes) as hourly zstd JSON-lines files at
https://replay.shrine.trade/pump/YYYY/MM/DD/HH.jsonl.zst, listed in /pump/index.json.
Free and keyless, archived since 2026-09-14; a file appears a few minutes after its hour
ends. Each hour is ~230 MB compressed (~1 GB of JSON) because it covers every DEX, so this
is opt-in.

Two uses:
  backfill   replay recent hours into the database so baselines exist on the first start
             instead of after ~7h of listening (`SHRINE_BACKFILL_HOURS`, or the CLI).
  coverage   compare an hour the live stream recorded with the archive. On 2026-10-21 the
             free public RPC stream caught 214 of 278 launches (77%) in an 8-minute window;
             every launch it saw was also in the archive.

Provenance: rows get source 'shrine_replay'. Point-in-time honesty: a replayed hour is
stamped as first seen when its archive file became available (hour end + 5 min), never
earlier, so a backtest cannot use it before it existed.
"""
from __future__ import annotations

import io
import json
import logging
import time
from datetime import datetime, timezone

import httpx

from .db import insert, now, rows

log = logging.getLogger("radar.shrine")

BASE = "https://replay.shrine.trade/pump"
WSOL = "So11111111111111111111111111111111111111112"
PUBLISH_DELAY_S = 300
PROTOCOLS = ("PUMPFUN", "PUMPFUN_MAYHEM")


def hour_key(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y/%m/%d/%H")


def to_events(d: dict) -> list[dict]:
    """One archive line -> the stream's event dicts (pump.fun only)."""
    if d.get("protocol") not in PROTOCOLS:
        return []
    act, ts, slot = d.get("action"), d.get("timestamp"), d.get("block")
    paired = d.get("quoteMint") in (None, WSOL)
    if act == "create":
        return [{"type": "create", "mint": d["mint"], "name": d.get("name"), "symbol": d.get("symbol"),
                 "uri": d.get("uri"), "bonding_curve": d.get("pool"), "user": d.get("txSigner"),
                 "creator": d.get("creator") or d.get("txSigner"), "ts": ts, "slot": slot,
                 "initial_real_tokens": None, "sol_paired": paired}]
    if act in ("buy", "sell"):
        out = []
        for b in d.get("breakdown") or [d]:
            if b.get("action") not in ("buy", "sell") or not b.get("trader"):
                continue
            price = b.get("price") or d.get("price")
            out.append({"type": "trade", "mint": d["mint"], "sol": float(b.get("quoteAmount") or 0) if paired else 0.0,
                        "tokens": float(b.get("tokenAmount") or 0), "is_buy": b["action"] == "buy",
                        "user": b["trader"], "ts": ts, "slot": slot, "sol_paired": paired,
                        "v_sol": float(price or 0), "v_tokens": 1.0 if price else 0.0,
                        "real_sol": d.get("quoteInPool") if paired else None, "real_tokens": None,
                        "creator": None})
        return out
    if act == "curveComplete":
        return [{"type": "complete", "mint": d["mint"], "user": d.get("txSigner"), "bonding_curve": d.get("pool"),
                 "ts": ts, "slot": slot}]
    return []


def iter_hour(stream) -> "iter[dict]":
    """Events from an open binary zstd stream, pump.fun only, in archive order."""
    import zstandard
    for line in io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(stream), encoding="utf-8"):
        if '"PUMPFUN' not in line:          # cheap pre-filter: most lines are other DEXes
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        yield from to_events(d)


def available_hours(client: httpx.Client) -> list[str]:
    r = client.get(f"{BASE}/index.json", timeout=30)
    r.raise_for_status()
    return r.json().get("hours") or []


def backfill(con, hours: int = 0, live=None, client: httpx.Client | None = None, sol_usd: float | None = None,
             *, start_hour: int | None = None, end_hour: int | None = None, simulate_live: bool = False) -> dict:
    """Replay complete archive hours into the database via the stream's own aggregation, then
    snapshot each hour at its end. Skips hours already replayed.

    Default: the last `hours` hours, stamped first-seen when each archive hour became public.
    Research (`start_hour`..`end_hour`, `simulate_live=True`): an arbitrary past range, stamped
    as a live run would have seen it (each event at its own time), for backtests."""
    from .stream import Live
    live = live or Live()
    live.source = "shrine_replay"
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": "trench-radar/0.2 (+research)"}, follow_redirects=True)
    stats = {"hours": 0, "events": 0, "launches": 0, "skipped": 0, "bytes": 0}
    try:
        have = set(available_hours(client))
        done = {r["detail"] for r in rows(con, "SELECT detail FROM market_obs WHERE metric='shrine_hour_replayed'")}
        t_now = now()
        last_full = (t_now - PUBLISH_DELAY_S) // 3600 * 3600 - 3600
        first = start_hour if start_hour is not None else last_full - (hours - 1) * 3600
        last = end_hour if end_hour is not None else last_full
        for start in range(first, last + 1, 3600):
            key = hour_key(start)
            if key not in have or key in done:
                stats["skipped"] += 1
                continue
            t0 = time.time()
            raw = None
            for attempt in range(4):                 # large files: retry dropped transfers
                try:
                    with client.stream("GET", f"{BASE}/{key}.jsonl.zst", timeout=300) as r:
                        r.raise_for_status()
                        raw = io.BytesIO(r.read())
                    break
                except httpx.TransportError as exc:
                    log.warning("shrine %s: %s; retrying", key, exc)
                    time.sleep(5 * (attempt + 1))
            if raw is None:
                stats["skipped"] += 1
                continue
            stats["bytes"] += raw.getbuffer().nbytes
            seen = start + 3600 + PUBLISH_DELAY_S     # when this hour became public
            n = launches = 0
            seen_trades: set = set()
            for ev in iter_hour(raw):
                if ev["type"] == "trade":
                    key_ = (ev.get("slot"), ev["mint"], ev["user"], ev["tokens"], ev["is_buy"])
                    if key_ in seen_trades:
                        continue
                    seen_trades.add(key_)
                elif ev["type"] == "create" and ev["mint"] in live.mints and live.mints[ev["mint"]].created_at:
                    continue
                live.on_event(ev, t=ev["ts"])
                n += 1
                launches += ev["type"] == "create"
            for r_ in live.pending["tokens"]:
                r_["source"] = "shrine_replay"
                if not simulate_live:
                    r_["first_seen_at"] = seen
            live.flush(con)
            live.snapshot(con, sol_usd, t=start + 3600, source="shrine_replay")
            con.execute("BEGIN")
            for m in range(start + 60, start + 3601, 60):     # the archive covers the whole hour
                insert(con, "market_obs", {"observed_at": m, "metric": "stream_connected_s", "value": 60.0,
                                           "source": "shrine_replay", "detail": key})
            insert(con, "market_obs", {"observed_at": seen, "metric": "shrine_hour_replayed", "value": n,
                                       "source": "shrine_replay", "detail": key})
            insert(con, "source_runs", {"source": "shrine_replay", "job": "replay", "started_at": start,
                                        "finished_at": start + 3600 if simulate_live else seen, "status": "ok",
                                        "items": n, "latency_ms": 0})
            con.execute("COMMIT")
            stats["hours"] += 1
            stats["events"] += n
            stats["launches"] += launches
            log.info("shrine replay %s: %d events, %d launches (%.0fs)", key, n, launches, time.time() - t0)
    finally:
        if own:
            client.close()
    return stats


def coverage_check(con, hour_start: int, client: httpx.Client | None = None) -> dict:
    """Launches the live stream recorded in an hour vs the archive's list for that hour."""
    own = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        with client.stream("GET", f"{BASE}/{hour_key(hour_start)}.jsonl.zst", timeout=300) as r:
            r.raise_for_status()
            raw = io.BytesIO(r.read())
    finally:
        if own:
            client.close()
    archive = {ev["mint"] for ev in iter_hour(raw) if ev["type"] == "create"}
    ours = {r["mint"] for r in rows(con, "SELECT mint FROM tokens WHERE source='chain' AND created_at >= ? "
                                         "AND created_at < ?", (hour_start, hour_start + 3600))}
    return {"hour": hour_key(hour_start), "archive_launches": len(archive), "stream_launches": len(ours),
            "in_both": len(archive & ours), "only_stream": len(ours - archive),
            "completeness": round(len(archive & ours) / len(archive), 3) if archive else None}
