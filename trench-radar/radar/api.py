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
from .analytics.backtest import run_backtest
from .analytics.common import source_freshness
from .analytics.scoring import run_analysis
from .config import ROOT, Settings, load_settings
from .db import connect, now, rows
from .reports import make_report
from .scheduler import State, run_forever
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
        bt = rows(con, "SELECT created_at, results FROM backtests ORDER BY id DESC LIMIT 1")
        return {
            "as_of": r["as_of"], "model_version": r["model_version"], "market": r["market"],
            "metas": r["metas"], "context": r["context"], "social_measured": r["social_measured"],
            "freshness": r["freshness"], "config": settings.public_view(),
            "backtest": ({"created_at": bt[0]["created_at"], **{k: v for k, v in json.loads(bt[0]["results"]).items()
                                                                  if k != "sample"}} if bt else None),
            "db": {t: rows(con, f"SELECT COUNT(*) n FROM {t}")[0]["n"]
                   for t in ("tokens", "token_obs", "curve_obs", "social_posts", "graduations", "token_outcomes")},
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

    @app.get("/api/sources")
    async def sources():
        return {"freshness": source_freshness(con, now()),
                "recent_runs": rows(con, """SELECT source, job, started_at, status, items, latency_ms, error
                                            FROM source_runs ORDER BY id DESC LIMIT 60""")}

    @app.get("/api/reports/latest")
    async def latest_report():
        r = rows(con, "SELECT id, created_at, kind, analyst, body FROM reports ORDER BY id DESC LIMIT 1")
        return r[0] if r else None

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
            return FileResponse(Path(WEB) / "index.html")

    return app
