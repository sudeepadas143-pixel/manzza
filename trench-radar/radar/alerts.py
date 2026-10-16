"""Material-change detection and Telegram delivery."""
from __future__ import annotations

import logging

from .config import Settings
from .db import insert, now, rows
from .sources.base import Http, SourceUnavailable

log = logging.getLogger("radar.alerts")

CRITICAL_SOURCES = ("geckoterminal/new_pools", "geckoterminal/refresh", "solana_rpc/bonding_curves")


def _previous_scores(con, before: int) -> dict[str, dict]:
    out = {}
    for r in rows(con, """SELECT s.meta_key, s.score, s.verdict, s.confidence FROM scores s
                          JOIN (SELECT meta_key, MAX(computed_at) m FROM scores WHERE computed_at < ?
                                AND computed_at > ? GROUP BY meta_key) x
                          ON s.meta_key=x.meta_key AND s.computed_at=x.m""", (before, before - 6 * 3600)):
        out[r["meta_key"]] = r
    return out


def detect_changes(con, settings: Settings, result: dict) -> list[dict]:
    t = result["as_of"]
    prev = _previous_scores(con, t)
    events = []
    for rank, m in enumerate(result["metas"]):
        p = prev.get(m["meta_key"])
        if m["verdict"] == "insufficient data":
            continue
        head = f"{m['meta_key']} — score {m['score']} ({m['verdict']}, conf {m['confidence']})"
        why = (m["reasons"][:2] or ["no strong positive signal"]) + m["risks"][:1]
        if p is None and rank < 5 and m["verdict"] in ("favorable", "mixed") and m["confidence"] >= 0.5:
            events.append({"kind": "new_meta", "meta_key": m["meta_key"],
                           "text": f"New meta in top 5: {head}\n" + "\n".join("• " + w for w in why)})
        elif p and p["verdict"] != m["verdict"] and "favorable" in (p["verdict"], m["verdict"]):
            events.append({"kind": "verdict_change", "meta_key": m["meta_key"],
                           "text": f"Verdict {p['verdict']} → {m['verdict']}: {head}\n"
                                   + "\n".join("• " + w for w in why)})
        elif p and p["score"] is not None and m["score"] is not None \
                and abs(m["score"] - p["score"]) >= settings.alert_score_delta:
            events.append({"kind": "score_move", "meta_key": m["meta_key"],
                           "text": f"Score {p['score']:.0f} → {m['score']:.0f}: {head}\n"
                                   + "\n".join("• " + w for w in why)})
    regime = result["market"].get("regime")
    last = rows(con, """SELECT detail FROM market_obs WHERE metric='market_score' AND observed_at < ?
                        ORDER BY observed_at DESC LIMIT 1""", (t,))
    if regime and last and last[0]["detail"] and last[0]["detail"] != regime:
        events.append({"kind": "market_regime", "meta_key": None,
                       "text": f"Market regime {last[0]['detail']} → {regime} (score {result['market']['score']})"})
    down = [k for k in CRITICAL_SOURCES if result["freshness"].get(k, {}).get("state") in ("expired", None)]
    if down:
        events.append({"kind": "source_down", "meta_key": None,
                       "text": "Data sources not updating: " + ", ".join(down) + ". Scores are degraded."})
    # cooldown
    out = []
    for e in events:
        recent = rows(con, """SELECT 1 FROM alerts WHERE kind=? AND COALESCE(meta_key,'')=COALESCE(?, '')
                              AND created_at > ? LIMIT 1""",
                      (e["kind"], e["meta_key"], t - settings.alert_cooldown_min * 60))
        if not recent:
            out.append(e)
    return out


async def send_telegram(settings: Settings, http: Http, text: str) -> None:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        raise SourceUnavailable("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    for i in range(0, len(text), 3900):                     # Telegram limit is 4096 chars
        await http.post_json(url, {"chat_id": settings.telegram_chat_id, "text": text[i:i + 3900],
                                   "disable_web_page_preview": True}, retries=1)


async def dispatch(con, settings: Settings, http: Http, events: list[dict]) -> int:
    sent = 0
    for e in events:
        text = "TRENCH//RADAR alert\n" + e["text"] + "\n\nResearch signal, not advice. Scores unvalidated unless stated."
        delivered, err = 0, None
        try:
            await send_telegram(settings, http, text)
            delivered = 1
            sent += 1
        except SourceUnavailable as exc:
            err = settings.redact(str(exc))
        insert(con, "alerts", {"created_at": now(), "kind": e["kind"], "meta_key": e["meta_key"],
                               "message": text, "delivered": delivered, "error": err})
    con.commit()
    return sent
