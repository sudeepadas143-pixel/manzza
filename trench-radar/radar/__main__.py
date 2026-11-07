"""CLI: python -m radar <command>

  init                      create the database
  collect [job ...]         run polling jobs once (default: all free sources)
  stream [--seconds N]      run the live chain stream for N seconds (default 180), then snapshot
  backfill [--hours N]      replay the last N hours from Shrine's free archive (~230 MB/hour)
  check-coverage [--hours N]  compare the live stream's launches with Shrine's archive, per hour
  corpus-download DIR       fetch the Pump.fun Memecoin Corpus (~5.9 GB; needs pyarrow later)
  corpus-build DIR --db F   build a research database from it (needs pyarrow)
  corpus-backtest --db F    walk-forward backtest over the research database
  analyze [--json]          score metas now and print the ranking
  report [--send]           write a pre-launch report (Telegram with --send)
  backtest [--days N]       walk-forward backtest over stored history
  status                    source freshness and table sizes
  run                       scheduler only (no web)
  serve [--no-scheduler]    dashboard + API (+ scheduler)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from . import collectors as c
from .analytics.backtest import run_backtest
from .analytics.common import source_freshness
from .analytics.scoring import run_analysis
from .config import load_settings
from .db import connect, now, rows
from .reports import make_report
from .scheduler import jobs, run_forever
from .sources.base import Http

FREE_JOBS = ["solprice", "macro", "attention", "social"]
# Pump.fun Memecoin Corpus periods to keep out of backtests (KNOWN_ISSUES.md §5): the Jul 3
# collection outage with its partial neighbouring days. Stored as UTC unix seconds.
CORPUS_GAPS = [(1782950400, 1783209600)]   # 2026-07-02 00:00 .. 2026-07-05 00:00


def _ts(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%m-%d %H:%M") if t else "never"


async def _with_ctx(fn):
    s = load_settings()
    con = connect(s.db_path)
    http = Http(s)
    try:
        return await fn(c.Ctx(con, s, http))
    finally:
        await http.close()


def print_analysis(res: dict) -> None:
    mk = res["market"]
    print(f"\nTRENCH//RADAR  as of {_ts(res['as_of'])} UTC  model {res['model_version']}")
    print(f"market: regime={mk.get('regime')} score={mk.get('score')} coverage={mk.get('coverage')}")
    for k, v in mk["metrics"].items():
        if not k.endswith("_series"):
            print(f"   {k}: {v}")
    print(f"social measured: {res['social_measured']}   context: {res['context']}\n")
    print(f"{'meta':<14}{'score':>6}{'conf':>6}  {'verdict':<18}{'L1h':>4}{'L6h':>5}{'buy/h':>7}{'sat':>6}  hype check")
    for m in res["metas"]:
        e = m["evidence"]
        sat = e["saturation"]["index"]
        print(f"{m['meta_key'][:13]:<14}{(m['score'] or 0):>6.1f}{m['confidence']:>6.2f}  {m['verdict']:<18}"
              f"{e['launch']['launches_1h']:>4}{e['launch']['launches_6h']:>5}{e['demand']['unique_buyers_h1_sum']:>7}"
              f"{(sat if sat is not None else float('nan')):>6.2f}  {m['hype_check']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="radar", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--days", type=float, default=3.0)
    ap.add_argument("--seconds", type=int, default=180)
    ap.add_argument("--hours", type=int, default=7)
    ap.add_argument("--db")
    ap.add_argument("--step-hours", type=float, default=3.0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--step-h", type=float, default=1.0)
    ap.add_argument("--no-scheduler", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    s = load_settings()

    if a.cmd == "init":
        connect(s.db_path)
        print(f"database ready: {s.db_path}")
    elif a.cmd == "collect":
        names = a.args or FREE_JOBS

        async def go(ctx):
            table = jobs(ctx)
            for n in names:
                if n not in table:
                    sys.exit(f"unknown job {n}; choose from {sorted(table)}")
                print(f"-> {n}", flush=True)
                await table[n](ctx)
            for r in rows(ctx.con, "SELECT source, job, status, items, latency_ms, error FROM source_runs "
                                   "ORDER BY id DESC LIMIT ?", (len(names) + len(ctx.s.x_queries),)):
                print(f"   {r['source']}/{r['job']}: {r['status']} items={r['items']} {r['latency_ms']}ms "
                      f"{r['error'] or ''}")
        asyncio.run(_with_ctx(go))
    elif a.cmd == "stream":
        from . import stream

        async def listen(ctx):
            await c.collect_sol_price(ctx)
            task = asyncio.create_task(stream.run_stream(ctx))
            await asyncio.sleep(a.seconds)
            task.cancel()
            live = stream.LIVE
            live.flush(ctx.con)
            live.refresh_smart(ctx.con)
            sol = rows(ctx.con, "SELECT value FROM market_obs WHERE metric='sol_price_usd' ORDER BY id DESC LIMIT 1")
            n = live.snapshot(ctx.con, sol[0]["value"] if sol else None)
            v = live.view()
            print(f"events {live.total_events}, launches {len(live.launches)}, graduations {len(live.grads)}, "
                  f"tokens snapshotted {n}, lag {v['stream']['lag_s']}s")
            for h in v["hot"][:10]:
                print(f"  {h['symbol'] or h['mint'][:6]:<12} buyers5m {h['buyers_5m']:>3} net {h['net_sol_5m']:>8} SOL "
                      f"smart {h['smart_5m']} progress {h['progress'] or 0:.0%}")
        asyncio.run(_with_ctx(listen))
    elif a.cmd == "backfill":
        from . import shrine
        con = connect(s.db_path)
        sol = rows(con, "SELECT value FROM market_obs WHERE metric='sol_price_usd' ORDER BY id DESC LIMIT 1")
        print(json.dumps(shrine.backfill(con, a.hours, sol_usd=sol[0]["value"] if sol else None)))
    elif a.cmd == "check-coverage":
        from . import shrine
        con = connect(s.db_path)
        t = now() // 3600 * 3600 - 3600
        for h in range(a.hours, 0, -1):
            try:
                print(json.dumps(shrine.coverage_check(con, t - (h - 1) * 3600)))
            except Exception as exc:  # hour not archived yet, network
                print(json.dumps({"hour": shrine.hour_key(t - (h - 1) * 3600), "error": str(exc)[:200]}))
    elif a.cmd == "corpus-download":
        from pathlib import Path

        from . import corpus
        print("revision", corpus.download(Path(a.args[0])))
    elif a.cmd == "corpus-build":
        from pathlib import Path

        from . import corpus
        print(json.dumps(corpus.build(Path(a.args[0]), Path(a.db), force=a.force)))
        print(json.dumps(corpus.provenance_checks(connect(a.db))))
    elif a.cmd == "corpus-backtest":
        from . import corpus
        con = connect(a.db)
        info = json.loads(rows(con, "SELECT value FROM meta_info WHERE key='corpus'")[0]["value"])
        lo, hi = info["launch_range"]
        found = corpus.gaps(con)
        res = run_backtest(con, lo + 8 * 3600, hi, step_s=int(a.step_hours * 3600), exclude=CORPUS_GAPS + found)
        res.pop("sample", None)
        res["provenance"] = {**corpus.provenance_checks(con), "corpus_revision": info["revision"],
                             "collection_gaps_excluded": [[datetime.fromtimestamp(x, timezone.utc).isoformat()
                                                           for x in g] for g in CORPUS_GAPS + found]}
        # also file it in the live database so the dashboard's backtest panel shows it
        live = connect(s.db_path)
        live.execute("INSERT INTO backtests (created_at, params, results) VALUES (?,?,?)", (now(), json.dumps({
            "dataset": "Pump.fun Memecoin Corpus", "revision": info["revision"], "start": lo, "end": hi,
            "step_s": int(a.step_hours * 3600), "follow_h": 6, "horizon_h": 24}), json.dumps(res, default=str)))
        print(json.dumps(res, indent=1, default=str))
    elif a.cmd == "analyze":
        res = run_analysis(connect(s.db_path), persist=True)
        print(json.dumps(res, indent=1, default=str) if a.json else "", end="")
        if not a.json:
            print_analysis(res)
    elif a.cmd == "report":
        out = asyncio.run(_with_ctx(lambda ctx: make_report(ctx.con, ctx.s, ctx.http, "on_demand", send=a.send)))
        print(out["body"])
        if a.send:
            print(f"\ntelegram: {out['telegram']}")
    elif a.cmd == "backtest":
        con = connect(s.db_path)
        end = now()
        res = run_backtest(con, int(end - a.days * 86400), end, step_s=int(a.step_h * 3600))
        res.pop("sample", None)
        print(json.dumps(res, indent=1, default=str))
    elif a.cmd == "status":
        con = connect(s.db_path)
        for k, v in source_freshness(con, now()).items():
            print(f"{k:<34} {v['state']:<10} last ok {_ts(v['last_ok'])}  {v['last_error'] or ''}"[:160])
        for t in ("tokens", "token_obs", "curve_obs", "graduations", "early_buyers", "social_posts", "scores",
                  "token_outcomes"):
            print(f"{t:<16}{rows(con, f'SELECT COUNT(*) n FROM {t}')[0]['n']:>10}")
        print("configured:", json.dumps(s.public_view()))
    elif a.cmd == "run":
        asyncio.run(_with_ctx(run_forever))
    elif a.cmd == "serve":
        import uvicorn

        from .api import create_app
        uvicorn.run(create_app(s, with_scheduler=not a.no_scheduler), host=s.dashboard_host,
                    port=s.dashboard_port, log_level="info")
    else:
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
