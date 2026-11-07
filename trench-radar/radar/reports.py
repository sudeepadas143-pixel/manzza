"""Pre-launch reports: analysis + analyst briefing, stored and optionally sent to Telegram."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .alerts import send_telegram
from .analyst import brief, evidence_pack
from .analytics.scoring import run_analysis
from .config import Settings
from .db import dumps, insert, now, rows
from .sources.base import Http, SourceUnavailable


def latest_backtest(con) -> dict | None:
    r = rows(con, "SELECT results FROM backtests ORDER BY id DESC LIMIT 1")
    return json.loads(r[0]["results"]) if r else None


async def make_report(con, settings: Settings, http: Http, kind: str = "pre_launch",
                      send: bool = True, result: dict | None = None) -> dict:
    result = result or run_analysis(con, persist=True)
    pack = evidence_pack(result, latest_backtest(con))
    text, analyst = await brief(settings, pack)
    stamp = datetime.fromtimestamp(result["as_of"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = f"# TRENCH//RADAR {kind.replace('_', '-')} report — {stamp}\n\n{text}\n\n" \
           f"_Analyst: {analyst}. Model {result['model_version']}. Research only; no trades or launches are automated._"
    insert(con, "reports", {"created_at": now(), "kind": kind, "analyst": analyst, "body": body,
                            "evidence": dumps(pack)})
    con.commit()
    rid = rows(con, "SELECT MAX(id) AS id FROM reports")[0]["id"]
    delivered = None
    if send and settings.telegram_bot_token and settings.telegram_chat_id:
        try:
            await send_telegram(settings, http, body.replace("**", "").replace("_", ""))
            delivered = True
        except SourceUnavailable as exc:
            delivered = settings.redact(str(exc))
    return {"id": rid, "body": body, "analyst": analyst, "telegram": delivered}
