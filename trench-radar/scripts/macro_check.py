"""How much do the macro, intraday, rotation and decay views say about what comes next? Measured on
history replayed through the app's own pipeline (scripts/meta_replay.py), using only what each view
knew at the time. Signal rules are the app's; nothing here tunes them.

Comparisons (each flagged category against the categories not flagged at the same read, on coins
launched after the read, each against all coins launched then):
1. Weekly record -> next day. At the end of each day, the 7-day macro view. Outcome: graduations of
   each category's coins launched the next day. Rank correlation across categories per day; and
   categories marked "working" against the rest.
2. Today's heat -> next 6 hours. Every 6 hours, the intraday view; "heating" against the rest.
3. Rotation signals -> next 24 hours. Every 6 hours, macro.rotation: each signal, and the "busy
   today" rule (formerly the watchlist), against the rest; also broad against single-coin momentum.
4. Decay warnings -> next 3 days. Every 6 hours, macro.decay for categories that had an edge.
   "Declined" = drew 50+ buyers at 0.6x its own pre-read baseline or less (both against the market).
   Hit rate per status, false alarms, missed declines, the early-warning subset (results not yet
   turned), lead time, and single-signal rules.

Uncertainty: moving-block bootstrap over days (blocks of 2 days for outcomes up to 24 hours, 4 days
for 3-day outcomes), because reads 6 hours apart share outcome coins. Every comparison also reports
how many distinct categories it rests on, the largest category's share, and the result with that
category left out: one big category can carry a whole comparison. Many comparisons are run, so a
range just clear of zero is weak evidence on its own.

Usage: python scripts/macro_check.py replay.db [--cache rows.json] [--write]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar.analytics import macro as M  # noqa: E402
from radar.db import connect  # noqa: E402

H, D = 3600, 86400
OUT = Path(__file__).resolve().parent.parent / "radar" / "data" / "macro_check.json"
ROT_SIGNALS = ["buyers_up", "sol_up", "share_up", "share_down", "early_successes", "broad", "single_coin", "crowding", "watch",
               "watch_confirmed", "watch_emerging", "watch_speculative"]
LABEL = {"working": "marked “working” this week", "heating": "“heating” today", "buyers_up": "buyers at 1.5× usual",
         "sol_up": "money in above usual", "share_up": "share of buying rising", "share_down": "share of buying falling",
         "early_successes": "new coins already graduating", "broad": "buying spread over 3+ coins",
         "single_coin": "buyers up on one coin", "crowding": "launches outpacing buyers",
         "watch": "busy today (the former watchlist rule)", "watch_confirmed": "busy today, week working",
         "watch_emerging": "busy today, record improving", "watch_speculative": "busy today, no record",
         "broad_vs_single": "broad momentum (against single-coin momentum)"}


# ------------------------------------------------------------------ collection
def by_category(cs):
    """Per category: [graduated, drew 50+ buyers, coins]."""
    by: dict = {}
    for c in cs:
        if c["category"]:
            b = by.setdefault(c["category"], [0, 0, 0])
            b[0] += M._success(c)
            b[1] += M._traction(c)
            b[2] += 1
    return by


def market_rates(cs):
    return (sum(M._success(c) for c in cs) / len(cs), sum(M._traction(c) for c in cs) / len(cs)) if cs else (None, None)


def collect(con) -> dict:
    lo, hi = con.execute("SELECT MIN(created_at), MAX(created_at) FROM token_summary WHERE category IS NOT NULL").fetchone()
    reads = [r[0] for r in con.execute("SELECT DISTINCT observed_at FROM narrative_obs ORDER BY observed_at")]
    out = {"lo": lo, "hi": hi, "weekly": [], "heat": [], "rotation": [], "decay": []}
    # 1. weekly -> next day
    for d in range(lo // D + 8, hi // D - 1):
        as_of = (d + 1) * D + D          # coins of the 7 days to the end of day d have matured
        w7 = M.macro_read(con, as_of, windows=(7,))["windows"]["7"]
        if not w7.get("available"):
            continue
        cs = M._coins(con, (d + 1) * D, (d + 2) * D)
        pg, _ = market_rates(cs)
        if not pg:
            continue
        by = by_category(cs)
        for r in w7["categories"]:
            o = by.get(r["category"])
            if r["coins"] >= M.MIN_COINS and o and o[2] >= 15:
                out["weekly"].append({"day": d, "cat": r["category"], "x": r["grad"]["ratio_ex_best"],
                                      "working": r["status"] == "working", "k": o[0], "n": o[2], "p": pg})
    # 2.-3. intraday heat -> 6 h, rotation -> 24 h, every 6 hours
    last = 0
    for t in reads:
        if t - last < 6 * H or t < lo + 4 * D or t > hi - 2 * D:
            continue
        last = t
        intra = M.intraday_read(con, t)
        if intra.get("baseline_hours", 0) < 72:
            continue
        c6 = M._coins(con, t, t + 6 * H)
        pg6, _ = market_rates(c6)
        by6 = by_category(c6)
        if pg6:
            for c in intra["categories"]:
                o = by6.get(c["category"])
                if o:
                    out["heat"].append({"day": t // D, "cat": c["category"], "on": c["status"] == "heating",
                                        "k": o[0], "n": o[2], "p": pg6})
        rot = M.rotation(con, t, M.macro_read(con, t, windows=(7,)), intra)
        c24 = M._coins(con, t, t + D)
        pg, pt = market_rates(c24)
        if not pg:
            continue
        by = by_category(c24)
        for row in rot["categories"]:
            o = by.get(row["category"])
            if not o:
                continue
            f = dict(row["signals"])
            f["single_coin"] = bool(f["single_coin"] and f["buyers_up"])
            f["watch"] = row["watch"]
            for st in ("confirmed", "emerging", "speculative"):
                f[f"watch_{st}"] = bool(row["watch"] and row.get("stage") == st)
            out["rotation"].append({"day": t // D, "t": t, "cat": row["category"],
                                    "flags": {k: bool(f.get(k)) for k in ROT_SIGNALS},
                                    "kg": o[0], "kt": o[1], "n": o[2], "pg": pg, "pt": pt})
    # 4. decay -> 3 days
    last = 0
    for t in reads:
        if t - last < 6 * H or t > hi - 4 * D:
            continue
        last = t
        dec = M.decay(con, t)
        if not dec["categories"]:
            continue
        cs = M._coins(con, t, t + 3 * D)
        _, pt = market_rates(cs)
        if not pt:
            continue
        by = by_category(cs)
        for r in dec["categories"]:
            f = by.get(r["category"])
            if r["status"] == "thin" or not r["baseline"]["drew_buyers_vs_market"] or not f or f[2] < 30:
                continue
            out["decay"].append({"day": t // D, "t": t, "category": r["category"], "status": r["status"],
                                 "families": r["families_on"], "recent": r["metrics"]["traction_ratio"][0],
                                 "base": r["baseline"]["drew_buyers_vs_market"], "forward": f[1] / f[2] / pt})
    return out


# ------------------------------------------------------------------ statistics
def blocks(days, block, rng):
    """A moving-block resample of the observed days, in order (gaps in the record are not filled)."""
    n = len(days)
    if n <= block:
        return list(rng.choice(days, n))
    starts = rng.integers(0, n - block + 1, size=-(-n // block))
    return [days[s + i] for s in starts for i in range(block)][:n]


def _ratio(xs):
    return sum(o[3] for o in xs) / max(sum(o[4] for o in xs), 1e-9)


def compare(obs, block, rng, boots=2000):
    """obs: (day, category, flagged, successes, expected). Flagged against the rest: each group's
    successes over those expected (market rate, or 1 per reading for decay); the difference with a 90%
    range; and what it rests on."""
    on = [o for o in obs if o[2]]
    off = [o for o in obs if not o[2]]
    if not on or not off:
        return None
    days = sorted({o[0] for o in obs})
    by = {d: [o for o in obs if o[0] == d] for d in days}
    diffs = []
    for _ in range(boots):
        pick = [o for d in blocks(days, block, rng) for o in by[d]]
        a, b = [o for o in pick if o[2]], [o for o in pick if not o[2]]
        if a and b:
            diffs.append(_ratio(a) - _ratio(b))
    share: dict = {}
    for o in on:
        share[o[1]] = share.get(o[1], 0) + o[4]
    big = max(share, key=share.get)
    rest = [o for o in obs if o[1] != big]
    loo = (_ratio([o for o in rest if o[2]]) - _ratio([o for o in rest if not o[2]])) if any(o[2] for o in rest) else None
    mid = days[len(days) // 2]
    halves = []
    for part in ([o for o in obs if o[0] < mid], [o for o in obs if o[0] >= mid]):
        a, b = [o for o in part if o[2]], [o for o in part if not o[2]]
        halves.append(round(_ratio(a) - _ratio(b), 3) if a and b else None)
    ci = ([round(float(np.percentile(diffs, 5)), 3), round(float(np.percentile(diffs, 95)), 3)] if len(diffs) > 100 else None)
    return {"flagged": round(_ratio(on), 3), "rest": round(_ratio(off), 3), "difference": round(_ratio(on) - _ratio(off), 3),
            "ci90": ci, "days": len(days), "flagged_days": len({o[0] for o in on}), "flagged_obs": len(on),
            "flagged_successes": int(sum(o[3] for o in on)), "flagged_categories": len(share), "largest_category": big,
            "largest_share": round(share[big] / sum(share.values()), 2),
            "without_largest": round(loo, 3) if loo is not None else None, "halves": halves}


def verdict(c) -> str:
    if not c or not c["ci90"] or c["flagged_days"] < 5:
        return "untested"
    return "better" if c["ci90"][0] > 0 else "worse" if c["ci90"][1] < 0 else "no clear difference"


def describe(name, c, what="graduated") -> str:
    v = verdict(c)
    if v == "untested":
        return f"{LABEL[name].capitalize()}: too few occasions to test."
    head = {"better": "came before better outcomes", "worse": "came before worse outcomes",
            "no clear difference": "made no clear difference"}[v]
    s = (f"{LABEL[name].capitalize()} {head}: the coins that followed {what} {c['flagged']:.2f}× the market against "
         f"{c['rest']:.2f}× (difference {c['difference']:+.2f}, 90% range {c['ci90'][0]:+.2f} to {c['ci90'][1]:+.2f}; "
         f"flagged on {c['flagged_days']} of {c['days']} days, {c['flagged_obs']} readings, {c['flagged_successes']} graduations).")
    if c["flagged_categories"] == 1 or c["largest_share"] >= 0.7:
        s += (f" It rests mostly on one category ({c['largest_category']}, {c['largest_share']:.0%} of the flagged coins)"
              + (f"; without it the difference is {c['without_largest']:+.2f}." if c["without_largest"] is not None
                 else "; nothing else was flagged, so the category and the signal cannot be told apart."))
    h = c["halves"]
    if None not in h and h[0] * h[1] < 0:
        s += " The two halves of the period point in opposite directions."
    return s


def decay_summary(rows, rng, block=4) -> dict:
    if len({r["day"] for r in rows}) < 5:
        return {"rows": len(rows), "text": "Too few days with categories to track to test decay warnings."}
    for r in rows:
        r["declined"] = r["forward"] <= 0.6 * r["base"]
        r["visible"] = r["recent"] is not None and r["recent"] <= 0.6 * r["base"]
        r["warned"] = r["status"] in ("early", "confirmed")
    rules = {"warning": lambda r: r["warned"], "confirmed": lambda r: r["status"] == "confirmed",
             "early": lambda r: r["status"] == "early", "cooldown": lambda r: r["status"] == "cooldown",
             "recovering": lambda r: r["status"] == "recovering", "healthy": lambda r: r["status"] == "healthy",
             "demand_only": lambda r: "demand" in r["families"], "results_only": lambda r: "results" in r["families"],
             "crowding_only": lambda r: "crowding" in r["families"]}
    episodes = 0       # consecutive declined readings of one category count once
    for cat in {r["category"] for r in rows}:
        rs = sorted((r for r in rows if r["category"] == cat), key=lambda r: r["t"])
        episodes += sum(1 for i, r in enumerate(rs) if r["declined"] and (i == 0 or not rs[i - 1]["declined"]))

    def stats(sub, rule):
        c = compare([(r["day"], r["category"], rule(r), int(r["declined"]), 1.0) for r in sub], block, rng)
        on = [r for r in sub if rule(r)]
        dec = [r for r in sub if r["declined"]]
        if c:
            c["false_alarms"] = round(1 - float(np.mean([r["declined"] for r in on])), 3)
            c["declines_caught"] = round(float(np.mean([rule(r) for r in dec])), 3) if dec else None
        return c
    out = {"rows": len(rows), "days": len({r["day"] for r in rows}), "categories": len({r["category"] for r in rows}),
           "decline_readings": int(sum(r["declined"] for r in rows)), "decline_episodes": episodes,
           "base_rate": round(float(np.mean([r["declined"] for r in rows])), 3),
           "all": {k: stats(rows, f) for k, f in rules.items()}}
    early = [r for r in rows if not r["visible"]]
    out["not_yet_visible"] = {"rows": len(early), "decline_readings": int(sum(r["declined"] for r in early)),
                              "base_rate": round(float(np.mean([r["declined"] for r in early])), 3) if early else None,
                              "warning": stats(early, rules["warning"]) if len({r["day"] for r in early}) >= 5 else None}
    leads, unwarned = [], 0
    for cat in {r["category"] for r in rows}:
        rs = sorted((r for r in rows if r["category"] == cat), key=lambda r: r["t"])
        for i, r in enumerate(rs):
            if i > 0 and r["visible"] and not rs[i - 1]["visible"]:
                prior = [x for x in rs[:i] if x["warned"] and r["t"] - x["t"] <= 7 * D]
                if prior:
                    leads.append((r["t"] - prior[0]["t"]) / D)
                else:
                    unwarned += 1
    out["lead"] = {"collapses": len(leads) + unwarned, "warned_before": len(leads),
                   "median_days_ahead": round(float(np.median(leads)), 1) if leads else None}
    w, nv, lt = out["all"]["warning"], out["not_yet_visible"]["warning"], out["lead"]
    out["text"] = (f"Over {out['days']} days and {out['categories']} categories that had an edge ({out['rows']} readings, "
                   f"{episodes} separate declines), {w['flagged']:.0%} of warned readings were followed by a decline within 3 days, "
                   f"against {w['rest']:.0%} of the others (difference {w['difference']:+.2f}, 90% range {w['ci90'][0]:+.2f} to "
                   f"{w['ci90'][1]:+.2f}): {'better than chance' if w['ci90'][0] > 0 else 'not clear of chance'}. "
                   f"{w['false_alarms']:.0%} of warnings were false alarms; {w['declines_caught']:.0%} of declining readings had one.")
    out["text_early"] = ((f"Before a decline showed in results, warned readings declined {nv['flagged']:.0%} of the time against "
                          f"{nv['rest']:.0%} without a warning (90% range {nv['ci90'][0]:+.2f} to {nv['ci90'][1]:+.2f}; "
                          f"{out['not_yet_visible']['decline_readings']} declining readings): "
                          f"{'some' if nv['ci90'][0] > 0 else 'no'} reliable early warning. ")
                         if nv else "Too few readings before declines showed to test early warning. ") + (
        f"Of {lt['collapses']} collapses, {lt['warned_before']} had a warning first"
        + (f", a median {lt['median_days_ahead']:.1f} days ahead." if lt["median_days_ahead"] is not None else "."))
    rs = out["all"]["results_only"]
    out["text_results"] = (f"When results had already fallen, {rs['flagged']:.0%} declined further against {rs['rest']:.0%} "
                           f"(90% range {rs['ci90'][0]:+.2f} to {rs['ci90'][1]:+.2f}): deterioration already under way tends to "
                           "continue. That is a description, not an early warning.")
    return out


def summarize(rows: dict, rng) -> dict:
    lo, hi = rows["lo"], rows["hi"]
    res = {"status": "preliminary",
           "source": "Pump.fun Memecoin Corpus, replayed through the app's narrative pipeline",
           "period": [time.strftime("%Y-%m-%d", time.gmtime(lo)), time.strftime("%Y-%m-%d", time.gmtime(hi))],
           "method": ("Flagged categories against the rest at the same reads, on coins launched afterwards, each against "
                      "all coins launched then. 90% ranges from a moving-block bootstrap over days (2-day blocks; 4-day for "
                      "3-day outcomes). Signal rules were fixed before this test and not tuned on it."),
           "caveat": ("Preliminary: about two weeks of one market period from one corpus, with no out-of-period test. "
                      "Readings six hours apart share outcomes; categories differ greatly in size, so one category can carry "
                      "a comparison. Many comparisons were run, so a single range just clear of zero is weak evidence.")}
    wk = rows["weekly"]
    rhos = []
    for d in sorted({r["day"] for r in wk}):
        rs = [r for r in wk if r["day"] == d]
        if len(rs) >= 5:
            x = np.array([r["x"] for r in rs])
            y = np.array([(r["k"] + 0.5) / (r["n"] + 1) / r["p"] for r in rs])
            rhos.append((d, float(np.corrcoef(x.argsort().argsort(), y.argsort().argsort())[0, 1])))
    if rhos:
        days, val = [d for d, _ in rhos], dict(rhos)
        means = [np.mean([val[d] for d in blocks(days, 2, rng)]) for _ in range(2000)]
        res["week_to_next_day"] = {"mean_rank_correlation": round(float(np.mean(list(val.values()))), 3),
                                   "ci90": [round(float(np.percentile(means, 5)), 3), round(float(np.percentile(means, 95)), 3)],
                                   "days": len(rhos)}
    comps = {"working": compare([(r["day"], r["cat"], r["working"], r["k"], r["n"] * r["p"]) for r in wk], 2, rng),
             "heating": compare([(r["day"], r["cat"], r["on"], r["k"], r["n"] * r["p"]) for r in rows["heat"]], 2, rng)}
    rot = rows["rotation"]
    for k in ROT_SIGNALS:
        comps[k] = compare([(r["day"], r["cat"], r["flags"][k], r["kg"], r["n"] * r["pg"]) for r in rot], 2, rng)
        if comps[k]:
            t = compare([(r["day"], r["cat"], r["flags"][k], r["kt"], r["n"] * r["pt"]) for r in rot], 2, rng)
            comps[k]["drew_buyers"] = {"flagged": t["flagged"], "rest": t["rest"], "ci90": t["ci90"]} if t else None
    bs = [r for r in rot if r["flags"]["buyers_up"] and (r["flags"]["broad"] or r["flags"]["single_coin"])]
    comps["broad_vs_single"] = compare([(r["day"], r["cat"], r["flags"]["broad"], r["kg"], r["n"] * r["pg"]) for r in bs], 2, rng)
    res["signals"] = {k: {"label": LABEL[k], "verdict": verdict(c), **(c or {}), "text": describe(k, c)} for k, c in comps.items()}
    res["decay"] = decay_summary(rows["decay"], rng)
    tested = sum(1 for s in res["signals"].values() if s["verdict"] != "untested")
    res["comparisons_run"] = tested + 1 + (9 if res["decay"].get("all") else 0)
    w = res.get("week_to_next_day")
    if w:
        res["text_week"] = (f"Ranking categories by their week did {'better than' if w['ci90'][0] > 0 else 'no better than'} chance "
                            f"at ordering the next day (average rank correlation {w['mean_rank_correlation']:+.2f}, 90% range "
                            f"{w['ci90'][0]:+.2f} to {w['ci90'][1]:+.2f}; {w['days']} days).")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db", type=Path)
    ap.add_argument("--cache", type=Path, help="reuse (or save) the collected readings")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.cache and a.cache.exists():
        rows = json.loads(a.cache.read_text())
    else:
        rows = collect(connect(a.db))
        if a.cache:
            a.cache.write_text(json.dumps(rows))
    res = summarize(rows, np.random.default_rng(31))
    print(json.dumps(res, indent=1))
    if a.write:
        OUT.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
