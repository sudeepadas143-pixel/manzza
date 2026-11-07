"""Analyst: turns a scored analysis into a written briefing.

With ANTHROPIC_API_KEY set, Claude writes it from an evidence pack and is told to
use only numbers in that pack. Without a key (or on any API failure) a
deterministic rules analyst writes it. Either way the evidence pack is stored next
to the text so every claim can be checked.
"""
from __future__ import annotations

import json
import logging
import os

from .config import Settings

log = logging.getLogger("radar.analyst")


def evidence_pack(result: dict, backtest: dict | None, top: int = 8) -> dict:
    fresh = {k: {"state": v["state"], "age_min": round(v["age_s"] / 60) if v["age_s"] is not None else None}
             for k, v in result["freshness"].items()}
    metas = []
    for m in result["metas"][:top]:
        ev = m["evidence"]
        metas.append({
            "meta": m["meta_key"], "terms": m["terms"], "score": m["score"], "confidence": m["confidence"],
            "verdict": m["verdict"], "hype_check": m["hype_check"], "components": m["components"],
            "launches": {k: ev["launch"][k] for k in ("launches_1h", "launches_6h", "launch_base_rate_h",
                                                       "launch_accel_z", "duplicate_symbol_share_6h")},
            "social": {k: ev["social"][k] for k in ("mentions_1h", "mentions_6h", "mention_accel_z",
                                                     "independent_authors_6h", "sentiment_6h",
                                                     "copy_paste_posts_6h")} if result["social_measured"] else "not measured",
            "demand": {k: ev["demand"][k] for k in ("tokens_tracked", "unique_buyers_h1_sum", "buyer_share_h1",
                                                     "vol_h1_usd", "vol_h24_usd", "curve_net_sol_1h",
                                                     "graduations_24h", "top_token_share_vol24")},
            "top_tokens": [{k: t[k] for k in ("symbol", "age_h", "buyers_h1", "vol_h1", "progress", "graduated")}
                           for t in ev["demand"]["top_tokens"][:3]],
            "saturation_index": ev["saturation"]["index"],
            "reasons": m["reasons"], "risks": m["risks"][:-1],   # last risk is the standing base-rate note
        })
    return {
        "as_of_utc": result["as_of"], "model_version": result["model_version"],
        "market": {"regime": result["market"].get("regime"), "score": result["market"].get("score"),
                   "metrics": {k: v for k, v in result["market"]["metrics"].items() if not k.endswith("_series")},
                   "notes": result["market"]["notes"]},
        "social_measured": result["social_measured"], "source_freshness": fresh,
        "backtest": {"validated": bool(backtest and backtest.get("validated")),
                     "verdict": backtest.get("verdict") if backtest else "no backtest run yet"},
        "metas": metas,
    }


SYSTEM = """You are the analyst for TRENCH//RADAR, a research tool that helps someone decide whether market conditions favour launching a new pump.fun memecoin now or waiting.

Write only from the JSON evidence pack in the user message. Every number you state must appear in it. If something is not in the pack, say it was not measured. Do not invent tokens, accounts, prices, or trends.

The scores are hand-weighted priors. Unless backtest.validated is true, say plainly that the score has not been validated against outcomes and do not describe it as predictive. Graduation and profit are different outcomes; do not use one as evidence for the other.

You give research, not instructions: no buy/sell calls, no price targets, nothing about how to trade. The reader decides.

Structure, in markdown, under 450 words:
1. **Bottom line** — two sentences: overall conditions and the single most important fact.
2. **Metas gaining traction** — the strongest few, each with why it matters and its strongest evidence.
3. **Is buying confirming the hype?** — per meta, using hype_check and the demand numbers.
4. **Launch now vs wait** — evidence on each side; name what would change the call.
5. **Data gaps** — stale or missing sources and how they limit the conclusions."""


async def claude_brief(settings: Settings, pack: dict) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=180.0, max_retries=2)
    resp = await client.beta.messages.create(
        model=settings.analyst_model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": os.environ.get("ANALYST_EFFORT", "medium")},
        system=SYSTEM,
        messages=[{"role": "user", "content": "Evidence pack:\n```json\n" + json.dumps(pack, default=str) + "\n```"}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("analyst model declined the request")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    if not text:
        raise RuntimeError(f"empty analyst response (stop_reason={resp.stop_reason})")
    return text


def rules_brief(pack: dict) -> str:
    mk = pack["market"]
    metas = pack["metas"]
    lines = []
    usable = [m for m in metas if m["verdict"] != "insufficient data"]
    regime = mk["regime"] or "unknown (not enough market data)"
    lines.append("**Bottom line** — market regime: **%s**%s. %s" % (
        regime, f" (score {mk['score']:.2f})" if mk["score"] is not None else "",
        f"Strongest meta: **{usable[0]['meta']}** at {usable[0]['score']} ({usable[0]['verdict']}, "
        f"confidence {usable[0]['confidence']})." if usable else "No meta has enough data for a call yet."))
    if not pack["backtest"]["validated"]:
        lines.append("_Scores are unvalidated priors: %s._" % pack["backtest"]["verdict"])
    shown = usable[:4]
    provisional = not usable and bool(metas)
    if provisional:
        shown = metas[:3]
        lines.append("_No meta clears the confidence bar. Provisional readings below are not calls._")
    lines.append("\n**Metas gaining traction**")
    for m in shown:
        lines.append(f"- **{m['meta']}** ({', '.join(m['terms'][:4])}) — score {m['score']}, {m['verdict']}. "
                     + (m["reasons"][0] if m["reasons"] else "No strong positive signal."))
    if not shown:
        lines.append("- none detected")
    lines.append("\n**Is buying confirming the hype?**")
    for m in shown:
        d = m["demand"]
        lines.append(f"- **{m['meta']}**: {m['hype_check']} — {d['unique_buyers_h1_sum']} buyers/h (summed), "
                     f"buyer share {d['buyer_share_h1']}, curve flow {d['curve_net_sol_1h']} SOL/h.")
    lines.append("\n**Launch now vs wait**")
    fav = [m for m in usable if m["verdict"] == "favorable"]
    if fav:
        lines.append("- For now: " + "; ".join(f"{m['meta']} ({m['score']})" for m in fav[:3])
                     + " show attention and buying together.")
    risks = [r for m in usable[:3] for r in m["risks"][:2]]
    if risks:
        lines.append("- For waiting: " + " ".join(risks[:4]))
    lines.append("- A call changes when demand (unique buyers, curve inflow) moves with attention, "
                 "or when saturation signals (copycats, fading volume) appear.")
    lines.append("\n**Data gaps**")
    bad = [k for k, v in pack["source_freshness"].items() if v["state"] not in ("fresh",)]
    lines.append("- Not fresh: " + (", ".join(bad) if bad else "none") + ".")
    if not pack["social_measured"]:
        lines.append("- Social sources are not connected; attention is inferred from launch names only.")
    for n in mk["notes"]:
        lines.append(f"- {n}.")
    return "\n".join(lines)


async def brief(settings: Settings, pack: dict) -> tuple[str, str]:
    """(text, analyst_name)."""
    if settings.anthropic_api_key:
        try:
            return await claude_brief(settings, pack), f"claude:{settings.analyst_model}"
        except Exception as exc:  # any API problem -> rules analyst, never a missing report
            log.warning("Claude analyst failed, using rules: %s", settings.redact(str(exc))[:200])
            return rules_brief(pack) + f"\n\n_(Claude analyst unavailable: {type(exc).__name__})_", "rules"
    return rules_brief(pack), "rules"
