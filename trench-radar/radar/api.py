"""FastAPI app: JSON API + static dashboard. Optionally runs the scheduler in-process.

All endpoints are `async def` so they run on the event loop thread that owns the
SQLite connection (no cross-thread use).
"""
from __future__ import annotations

import asyncio
import hmac
import json
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import collectors as c
from . import early
from .analytics import explain
from .analytics.backtest import run_backtest
from .analytics.common import LAUNCH_SOURCES, OBS_SOURCES, RETIRED, in_list, source_freshness
from .analytics.scoring import run_analysis
from .config import ROOT, Settings, load_settings
from .db import connect, now, rows
from .reports import make_report
from .scheduler import State, run_forever
from .stream import LIVE
from .stream import image_groups as stream_image_groups
from .sources.base import Http

# inside a PyInstaller bundle, data files are unpacked under sys._MEIPASS
WEB = Path(getattr(sys, "_MEIPASS", ROOT)) / "web"


def create_app(settings: Settings | None = None, *, with_scheduler: bool = False) -> FastAPI:
    settings = settings or load_settings()
    con = connect(settings.db_path)
    cache: dict = {"t": 0, "result": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        http = Http(settings)
        app.state.ctx = c.Ctx(con, settings, http)
        task = asyncio.create_task(run_forever(app.state.ctx)) if with_scheduler else None
        yield
        if task:
            task.cancel()
        await http.close()

    app = FastAPI(title="TRENCH//RADAR", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.middleware("http")
    async def auth(request: Request, call_next):
        if settings.dashboard_token and request.url.path.startswith("/api/"):
            supplied = request.headers.get("x-radar-token") or request.query_params.get("token") or ""
            if not hmac.compare_digest(supplied, settings.dashboard_token):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    def current(max_age_s: int = 60) -> dict:
        # Prefer the scheduler's last persisted analysis; otherwise compute read-only.
        if State.last_result and now() - State.last_result["as_of"] < 900:
            return State.last_result
        if cache["result"] and time.time() - cache["t"] < max_age_s:
            return cache["result"]
        cache["result"], cache["t"] = run_analysis(con, persist=False), time.time()
        return cache["result"]

    @app.get("/api/overview")
    async def overview():
        r = current()
        bt = rows(con, "SELECT created_at, params, results FROM backtests ORDER BY id DESC LIMIT 1")
        metas = explain.attach(r, State.narratives, LIVE)
        return {
            "as_of": r["as_of"], "model_version": r["model_version"], "market": r["market"],
            "edge_model": r.get("edge_model"), "edge_monitor": explain.monitor(metas),
            "metas": metas, "context": r["context"], "social_measured": r["social_measured"],
            "freshness": r["freshness"], "config": settings.public_view(),
            "backtest": ({"created_at": bt[0]["created_at"], "dataset": json.loads(bt[0]["params"]).get("dataset"),
                          "range": [json.loads(bt[0]["params"]).get("start"), json.loads(bt[0]["params"]).get("end")],
                          **{k: v for k, v in json.loads(bt[0]["results"]).items() if k != "sample"}} if bt else None),
            "db": {t: rows(con, f"SELECT COUNT(*) n FROM {t}")[0]["n"]
                   for t in ("tokens", "token_obs", "curve_obs", "social_posts", "graduations", "token_outcomes",
                             "early_buyers")},
        }

    @app.get("/api/metas/{key}/history")
    async def meta_history(key: str, hours: int = 48):
        return rows(con, """SELECT computed_at, score, confidence, verdict FROM scores
                            WHERE meta_key=? AND computed_at > ? ORDER BY computed_at""",
                    (key, now() - hours * 3600))

    @app.get("/api/market/history")
    async def market_history(hours: int = 72):
        return rows(con, """SELECT observed_at, metric, value FROM market_obs WHERE observed_at > ?
                            AND metric IN ('market_score','sol_price_usd','active_median_chg_h24','active_top80_vol_h24')
                            ORDER BY observed_at""", (now() - hours * 3600,))

    @app.get("/api/charts")
    async def charts(hours: int = 24):
        """Time series for the dashboard. Bucket size follows the range so bars stay legible."""
        hours = hours if hours in (6, 24, 72) else 24
        t = now()
        step = {6: 300, 24: 900, 72: 3600}[hours]
        start = t - hours * 3600
        launches = rows(con, f"""SELECT (created_at / ?) * ? AS b, COUNT(*) AS n FROM tokens
                                WHERE source IN {in_list(LAUNCH_SOURCES)} AND created_at > ? AND created_at <= ?
                                GROUP BY b ORDER BY b""", (step, step, start, t))
        gstep = max(step, 3600)
        grads = rows(con, """SELECT (COALESCE(graduated_at, detected_at) / ?) * ? AS b, COUNT(*) AS n
                             FROM graduations WHERE COALESCE(graduated_at, detected_at) > ? GROUP BY b ORDER BY b""",
                     (gstep, gstep, start))
        # when were launches actually being observed? (bars are only meaningful where coverage exists)
        runs = rows(con, """SELECT (finished_at / ?) * ? AS b, COUNT(*) AS n FROM source_runs
                            WHERE ((source='chain' AND job='pump_stream') OR (source='geckoterminal' AND job='new_pools'))
                            AND status='ok' AND finished_at > ? GROUP BY b""", (step, step, start))
        uptime = {}
        for r in rows(con, """SELECT source || '/' || job AS k, (finished_at / 3600) * 3600 AS b,
                                     SUM(status='ok') AS ok, SUM(status IN ('error','unavailable')) AS bad,
                                     SUM(status='skipped') AS skipped
                              FROM source_runs WHERE finished_at > ? GROUP BY k, b""", (t - 24 * 3600,)):
            if tuple(r["k"].split("/", 1)) in RETIRED:
                continue
            uptime.setdefault(r["k"], []).append([r["b"], r["ok"], r["bad"], r["skipped"]])
        market = rows(con, """SELECT observed_at AS t, value FROM market_obs WHERE metric='market_score'
                              AND value IS NOT NULL AND observed_at > ? ORDER BY observed_at""", (start,))
        sol = rows(con, """SELECT observed_at AS t, value FROM market_obs WHERE metric='sol_price_usd'
                           AND observed_at > ? ORDER BY observed_at""", (start,))
        return {"now": t, "hours": hours, "step_s": step, "graduation_step_s": gstep,
                "launches": [[r["b"], r["n"]] for r in launches],
                "observed_buckets": [r["b"] for r in runs],
                "graduations": [[r["b"], r["n"]] for r in grads],
                "uptime_1h": uptime, "market_score": [[r["t"], r["value"]] for r in market],
                "sol_price": [[r["t"], r["value"]] for r in sol[:: max(1, len(sol) // 300)]]}

    @app.get("/api/tokens")
    async def tokens(limit: int = 60):
        """Most active tokens right now, from the latest observation per token (last 2h)."""
        t = now()
        out = rows(con, f"""SELECT o.mint, k.name, k.symbol, k.created_at, k.creator, o.observed_at,
                                  o.vol_h1, o.vol_h24, o.buyers_h1, o.sellers_h1, o.buys_h1, o.sells_h1,
                                  o.organic_buyers_h1, o.smart_buyers_h1, o.net_sol_h1, o.dev_sold_sol,
                                  o.labelled_buyers_h1, o.insider_buyers_h1, o.launch_block_buyers, o.top10_pct,
                                  o.dev_holds_pct, k.x_post,
                                  COALESCE(o.mcap_usd, o.fdv_usd) AS mcap_usd, o.liquidity_usd, o.chg_h1, o.dex,
                                  (SELECT progress FROM curve_obs c WHERE c.mint=o.mint ORDER BY id DESC LIMIT 1) AS progress,
                                  (SELECT 1 FROM graduations g WHERE g.mint=o.mint) AS graduated,
                                  CASE WHEN k.creator IS NOT NULL AND k.creator != 'unknown' THEN
                                    (SELECT COUNT(*) FROM tokens d WHERE d.creator=k.creator AND d.created_at > ?) END
                                    AS deployer_launches_24h
                           FROM token_obs o JOIN tokens k ON k.mint=o.mint
                           WHERE o.id IN (SELECT MAX(id) FROM token_obs WHERE observed_at > ?
                                          AND source IN {in_list(OBS_SOURCES)} GROUP BY mint)
                           ORDER BY COALESCE(o.vol_h1, 0) DESC LIMIT ?""", (t - 86400, t - 7200, min(limit, 200)))
        return {"now": t, "tokens": out}

    @app.get("/api/tokens/{mint}")
    async def token_detail(mint: str, hours: int = 24):
        t = now()
        tok = rows(con, "SELECT mint, name, symbol, creator, pool, created_at, first_seen_at, source, description, "
                        "twitter, website, telegram, x_post, x_account, meta_status FROM tokens WHERE mint=?", (mint,))
        if not tok:
            raise HTTPException(404, "unknown token")
        since = t - min(max(hours, 1), 72) * 3600
        obs = rows(con, f"""SELECT observed_at, price_usd, COALESCE(mcap_usd, fdv_usd) AS mcap_usd, liquidity_usd,
                                  vol_h1, vol_h24, buyers_h1, sellers_h1, buys_h1, sells_h1, chg_h1, dex, source,
                                  organic_buyers_h1, smart_buyers_h1, net_sol_h1, dev_sold_sol, labelled_buyers_h1,
                                  insider_buyers_h1, launch_block_buyers, launch_block_pct, top10_pct, dev_holds_pct,
                                  sol_paired
                           FROM token_obs WHERE mint=? AND observed_at > ? AND source IN {in_list(OBS_SOURCES)}
                           ORDER BY observed_at""", (mint, since))
        curve = rows(con, """SELECT observed_at, real_sol, progress, complete FROM curve_obs
                             WHERE mint=? AND observed_at > ? ORDER BY observed_at""", (mint, since))
        grad = rows(con, "SELECT detected_at, graduated_at, source, pool FROM graduations WHERE mint=?", (mint,))
        pool = rows(con, "SELECT observed_at, price_sol, quote_sol FROM pool_obs WHERE mint=? AND observed_at > ? "
                         "ORDER BY observed_at", (mint, since))
        same_post = (rows(con, "SELECT COUNT(*) AS n, COUNT(DISTINCT creator) AS c FROM tokens WHERE x_post=? "
                               "AND created_at > ?", (tok[0]["x_post"], t - 86400))[0] if tok[0]["x_post"] else None)
        creator = tok[0]["creator"]
        dep = None
        if creator and creator != "unknown":
            dep = {"wallet": creator,
                   "launches_seen_24h": rows(con, "SELECT COUNT(*) n FROM tokens WHERE creator=? AND created_at > ?",
                                             (creator, t - 86400))[0]["n"],
                   "label": "insider" if creator in LIVE.labels.insider else "smart" if creator in LIVE.labels.smart else None,
                   "activity": (rows(con, "SELECT sol_balance, recent_tx, observed_at FROM creator_obs WHERE creator=? "
                                          "ORDER BY id DESC LIMIT 1", (creator,)) or [None])[0]}
        outcome = rows(con, "SELECT horizon_h, graduated, bucket, ret_end, ret_max, evaluated_at FROM token_outcomes "
                            "WHERE mint=?", (mint,))
        boosts = rows(con, "SELECT kind, amount, observed_at FROM attention_obs WHERE mint=? ORDER BY id DESC LIMIT 5",
                      (mint,))
        return {"now": t, "token": tok[0], "observations": obs, "curve": curve,
                "graduation": grad[0] if grad else None, "pool": pool, "same_x_post_24h": same_post,
                "deployer": dep, "outcomes": outcome,
                "attention": boosts, "launch_window": early.latest(con, mint),
                "launch_model": early.model_card()}

    @app.get("/api/narratives")
    async def narratives_now():
        """Latest narrative read (computed by the scheduler every 5 minutes)."""
        n = State.narratives
        if n is None:
            return {"pending": True, "narratives": [], "parents": [], "events": [],
                    "note": "The first narrative read runs a few minutes after start."}
        # token clusters are large; the selected one is fetched on its own
        # the 80 largest by buyers and launches, in the read's order, so saturating and fading
        # narratives are not crowded out by the many small new ones
        big = set(map(id, sorted(n["narratives"], key=lambda x: -((x["traction"]["buyers_h1"] or 0)
                                                                   + 5 * x["popularity"]["launches_6h"]))[:80]))
        slim = [{k: v for k, v in x.items() if k not in ("cluster", "members")} for x in n["narratives"] if id(x) in big]
        return {**n, "narratives": slim, "total": len(n["narratives"])}

    @app.get("/api/narratives/cluster")
    async def narrative_cluster(label: str):
        n = State.narratives
        hit = next((x for x in (n or {}).get("narratives", []) if x["label"] == label), None)
        if hit is None:
            raise HTTPException(404, "narrative not in the latest read")
        return {"as_of": n["as_of"], "label": label, **hit.get("cluster", {"nodes": [], "edges": []})}

    @app.get("/api/narratives/{nid}/history")
    async def narrative_history(nid: int):
        return rows(con, """SELECT observed_at, launches_6h, creators_6h, buyers_h1, buyers_per_launch, net_sol_h1, state
                            FROM narrative_obs WHERE narrative_id=? ORDER BY observed_at""", (nid,))

    @app.get("/api/live")
    async def live():
        """What the chain stream is seeing right now (in memory, updated per event)."""
        v = LIVE.view()
        v["source_posts"] = LIVE.source_posts(con, v["now"])
        v["image_groups"] = stream_image_groups(con, v["now"])
        v["stream"]["enabled"] = bool(settings.intervals.get("stream", 1)) and with_scheduler
        return v

    @app.get("/api/sources")
    async def sources():
        return {"freshness": source_freshness(con, now()),
                "recent_runs": rows(con, """SELECT source, job, started_at, status, items, latency_ms, error
                                            FROM source_runs ORDER BY id DESC LIMIT 60""")}

    @app.get("/api/reports/latest")
    async def latest_report():
        r = rows(con, "SELECT id, created_at, kind, analyst, body FROM reports ORDER BY id DESC LIMIT 1")
        return r[0] if r else None

    @app.get("/api/reports")
    async def report_list(limit: int = 20):
        return rows(con, "SELECT id, created_at, kind, analyst FROM reports ORDER BY id DESC LIMIT ?", (min(limit, 100),))

    @app.get("/api/reports/{rid}")
    async def report_one(rid: int):
        r = rows(con, "SELECT id, created_at, kind, analyst, body FROM reports WHERE id=?", (rid,))
        if not r:
            raise HTTPException(404, "unknown report")
        return r[0]

    @app.post("/api/reports")
    async def new_report(request: Request):
        return await make_report(con, settings, request.app.state.ctx.http, "on_demand", send=False)

    @app.get("/api/alerts")
    async def alerts(limit: int = 30):
        return rows(con, "SELECT created_at, kind, meta_key, message, delivered, error FROM alerts "
                         "ORDER BY id DESC LIMIT ?", (limit,))

    @app.get("/api/backtests/latest")
    async def latest_backtest():
        r = rows(con, "SELECT created_at, params, results FROM backtests ORDER BY id DESC LIMIT 1")
        if not r:
            return None
        return {"created_at": r[0]["created_at"], "params": json.loads(r[0]["params"]),
                "results": json.loads(r[0]["results"])}

    @app.post("/api/backtests")
    async def new_backtest(days: float = 3.0, step_h: float = 1.0):
        if days > 14:
            raise HTTPException(400, "max 14 days per run")
        end = now()
        return run_backtest(con, int(end - days * 86400), end, step_s=int(step_h * 3600))

    if WEB.exists():
        app.mount("/static", StaticFiles(directory=WEB), name="static")

        @app.get("/")
        async def index():
            return FileResponse(Path(WEB) / "index.html", headers={"Cache-Control": "no-cache"})

        @app.get("/manifest.webmanifest")
        async def manifest():
            return FileResponse(Path(WEB) / "manifest.webmanifest", media_type="application/manifest+json")

        @app.get("/sw.js")
        async def service_worker():
            # served from the root so its scope covers the whole app
            return FileResponse(Path(WEB) / "sw.js", media_type="text/javascript",
                                headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

    return app
