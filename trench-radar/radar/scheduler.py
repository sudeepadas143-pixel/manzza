"""In-process asyncio scheduler. Each job runs on its own interval; a failing job
is logged and retried next tick — it never stops the others."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from . import collectors as c
from . import stream
from .alerts import detect_changes, dispatch
from .analytics.scoring import run_analysis
from .reports import make_report

log = logging.getLogger("radar.scheduler")


class State:
    last_result: dict | None = None


async def analyze_and_alert(ctx: c.Ctx) -> None:
    result = run_analysis(ctx.con, persist=True)
    State.last_result = result
    events = detect_changes(ctx.con, ctx.s, result)
    if events:
        await dispatch(ctx.con, ctx.s, ctx.http, events)


def jobs(ctx: c.Ctx) -> dict:
    return {
        "solprice": c.collect_sol_price, "attention": c.collect_attention, "macro": c.collect_macro,
        "social": c.collect_social, "analyze": analyze_and_alert, "outcomes": c.label_outcomes,
        "bitquery": c.collect_bitquery,
    }


async def _loop(name: str, fn, ctx: c.Ctx, every: int, delay: float) -> None:
    await asyncio.sleep(delay)
    while True:
        try:
            # a hung job must not stall its own schedule forever
            await asyncio.wait_for(fn(ctx), timeout=max(600, 3 * every))
        except asyncio.TimeoutError:
            log.error("job %s timed out; it will run again next interval", name)
        except Exception:
            log.exception("job %s crashed", name)
        await asyncio.sleep(every)


async def _reports(ctx: c.Ctx) -> None:
    sent_for = set()
    while True:
        now = datetime.now(timezone.utc)
        hm = now.strftime("%H:%M")
        key = now.strftime("%Y-%m-%d ") + hm
        if hm in ctx.s.report_times_utc and key not in sent_for:
            sent_for.add(key)
            try:
                await make_report(ctx.con, ctx.s, ctx.http, "scheduled", send=True)
            except Exception:
                log.exception("scheduled report failed")
        await asyncio.sleep(20)


async def run_forever(ctx: c.Ctx) -> None:
    intervals = dict(ctx.s.intervals)
    intervals.setdefault("bitquery", 300 if ctx.s.bitquery_token else 0)
    tasks = []
    if intervals.get("stream", 1):
        tasks.append(asyncio.create_task(stream.run_stream(ctx)))
        tasks.append(asyncio.create_task(stream.run_maintenance(ctx, snapshot_every_s=intervals.get("snapshot", 120))))
    # stagger start so jobs that feed analysis run first
    order = ["solprice", "macro", "attention", "social", "bitquery", "analyze", "outcomes"]
    fns = jobs(ctx)
    for i, name in enumerate(order):
        every = intervals.get(name, 0)
        if every <= 0:
            continue
        delay = {"analyze": 150, "outcomes": 300}.get(name, i * 5)
        tasks.append(asyncio.create_task(_loop(name, fns[name], ctx, every, delay)))
    tasks.append(asyncio.create_task(_reports(ctx)))
    log.info("scheduler started: %s", {k: v for k, v in intervals.items() if v})
    await asyncio.gather(*tasks)
