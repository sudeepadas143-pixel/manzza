"""How much do the macro and intraday meta views say about what comes next? Measured on history
replayed through the app's own pipeline (scripts/meta_replay.py), using only what each view
knew at the time.

1. Weekly record -> next day. At the end of each day d, the 7-day macro view (coins matured by
   then). Outcome: each category's coins launched on day d+1, graduated (not instantly) against
   all coins that day. Rank correlation across categories per day; and the next-day record of
   categories marked "working" against all other categorised coins.
2. Today's heat -> next 6 hours. Every 6 hours, the intraday view. Outcome: each category's coins
   launched in the next 6 hours, against all coins then. "Heating" categories against the rest.
3. Rotation signals -> next 24 hours ("what could work tomorrow"). Every 6 hours, the rotation
   view (macro.rotation). For each signal, the categories it flagged against the categories it
   did not: their coins launched in the next 24 hours, graduated (not instantly) and drew 50+
   buyers, each against all coins then. Also broad momentum against single-coin momentum.
   Consecutive reads share outcome hours, so the bootstrap resamples whole days.

Day-block bootstrap for 90% ranges. Writes radar/data/macro_check.json for the app to show.

Usage: python scripts/macro_check.py replay.db [--write]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar.analytics import macro as M  # noqa: E402
from radar.db import connect  # noqa: E402

H, D = 3600, 86400
OUT = Path(__file__).resolve().parent.parent / "radar" / "data" / "macro_check.json"


def outcomes(con, start, end):
    """Per category: (successes, coins) of coins launched in [start, end); and the market rate."""
    cs = M._coins(con, start, end)
    if not cs:
        return {}, None
    p = sum(M._success(c) for c in cs) / len(cs)
    by = {}
    for c in cs:
        if c["category"]:
            k, n = by.get(c["category"], (0, 0))
            by[c["category"]] = (k + M._success(c), n + 1)
    return by, p


def ranks(a):
    return np.argsort(np.argsort(a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db", type=Path)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    con = connect(a.db)
    lo, hi = con.execute("SELECT MIN(created_at), MAX(created_at) FROM token_summary WHERE category IS NOT NULL").fetchone()
    first_day, last_day = lo // D + 8, hi // D - 1
    rhos, work = [], []        # per day: rank correlation; (day, working k, E, other k, E)
    for d in range(first_day, last_day):
        as_of = (d + 1) * D + D          # coins of the 7 days to the end of day d have matured
        mac = M.macro_read(con, as_of, windows=(7,))
        w7 = mac["windows"]["7"]
        if not w7.get("available"):
            continue
        nxt, p = outcomes(con, (d + 1) * D, (d + 2) * D)
        if not p:
            continue
        rows = [(r, nxt.get(r["category"])) for r in w7["categories"] if r["coins"] >= M.MIN_COINS]
        rows = [(r, o) for r, o in rows if o and o[1] >= 15]
        if len(rows) >= 5:
            x = np.array([r["grad"]["ratio_ex_best"] for r, _ in rows])
            y = np.array([(o[0] + 0.5) / (o[1] + 1) / p for _, o in rows])
            rhos.append((d, float(np.corrcoef(ranks(x), ranks(y))[0, 1])))
        wk = [(o[0], o[1] * p) for r, o in rows if r["status"] == "working"]
        ot = [(o[0], o[1] * p) for r, o in rows if r["status"] != "working"]
        work.append((d, sum(k for k, _ in wk), sum(e for _, e in wk), sum(k for k, _ in ot), sum(e for _, e in ot)))
    heat = []                                 # (day, heating k, E, other k, E)
    reads = [r[0] for r in con.execute("SELECT DISTINCT observed_at FROM narrative_obs ORDER BY observed_at")]
    last = 0
    for t in reads:
        if t - last < 6 * H or t < lo + 4 * D or t > hi - D:
            continue
        last = t
        intra = M.intraday_read(con, t)
        if intra.get("baseline_hours", 0) < 72:
            continue
        nxt, p = outcomes(con, t, t + 6 * H)
        if not p:
            continue
        hk = [nxt[c["category"]] for c in intra["categories"] if c["status"] == "heating" and c["category"] in nxt]
        ok = [nxt[c["category"]] for c in intra["categories"] if c["status"] != "heating" and c["category"] in nxt]
        heat.append((t // D, sum(k for k, _ in hk), sum(n for _, n in hk) * p, sum(k for k, _ in ok), sum(n for _, n in ok) * p))
    SIGNALS = ["buyers_up", "sol_up", "share_up", "share_down", "early_successes", "broad", "single_coin", "crowding", "watch",
               "watch_confirmed", "watch_emerging", "watch_speculative"]
    rot = {k: {"grad": [], "traction": []} for k in SIGNALS + ["broad_vs_single"]}
    last = 0
    for t in reads:
        if t - last < 6 * H or t < lo + 4 * D or t > hi - 2 * D:
            continue
        last = t
        intra = M.intraday_read(con, t)
        if intra.get("baseline_hours", 0) < 72:
            continue
        r = M.rotation(con, t, M.macro_read(con, t, windows=(7,)), intra)
        cs = M._coins(con, t, t + D)
        if not cs:
            continue
        p_g = sum(M._success(c) for c in cs) / len(cs)
        p_t = sum(M._traction(c) for c in cs) / len(cs)
        by: dict = {}
        for c in cs:
            if c["category"]:
                b = by.setdefault(c["category"], [0, 0, 0])
                b[0] += M._success(c)
                b[1] += M._traction(c)
                b[2] += 1
        flags = {}
        for row in r["categories"]:
            f = dict(row["signals"])
            f["single_coin"] = f["single_coin"] and f["buyers_up"]
            f["watch"] = row["watch"]
            for st in ("confirmed", "emerging", "speculative"):
                f[f"watch_{st}"] = row["watch"] and row.get("stage") == st
            flags[row["category"]] = f
        for k in SIGNALS:
            on = [by[c] for c, f in flags.items() if f.get(k) and c in by]
            off = [by[c] for c, f in flags.items() if not f.get(k) and c in by]
            if not on or not off:
                continue
            for j, (name, p) in enumerate((("grad", p_g), ("traction", p_t))):
                rot[k][name].append((t // D, sum(x[j] for x in on), sum(x[2] for x in on) * p,
                                     sum(x[j] for x in off), sum(x[2] for x in off) * p))
        br = [by[c] for c, f in flags.items() if f["buyers_up"] and f["broad"] and c in by]
        sg = [by[c] for c, f in flags.items() if f["single_coin"] and c in by]
        if br and sg:
            for j, (name, p) in enumerate((("grad", p_g), ("traction", p_t))):
                rot["broad_vs_single"][name].append((t // D, sum(x[j] for x in br), sum(x[2] for x in br) * p,
                                                     sum(x[j] for x in sg), sum(x[2] for x in sg) * p))
    rng = np.random.default_rng(31)

    def boot_mean(vals):
        days = sorted({d for d, _ in vals})
        by = {d: [v for dd, v in vals if dd == d] for d in days}
        m = []
        for _ in range(2000):
            pick = [v for d in rng.choice(days, len(days)) for v in by[d]]
            m.append(np.mean(pick))
        return [round(float(np.percentile(m, 5)), 3), round(float(np.percentile(m, 95)), 3)]

    def boot_ratio(rows):
        days = sorted({r[0] for r in rows})
        by = {d: [r for r in rows if r[0] == d] for d in days}
        out = []
        for _ in range(2000):
            pick = [r for d in rng.choice(days, len(days)) for r in by[d]]
            a_, b_ = sum(r[1] for r in pick) / max(sum(r[2] for r in pick), 1e-9), sum(r[3] for r in pick) / max(sum(r[4] for r in pick), 1e-9)
            out.append((a_, b_, a_ - b_))
        o = np.array(out)
        return {"top": round(float(np.median(o[:, 0])), 3), "rest": round(float(np.median(o[:, 1])), 3),
                "difference_ci90": [round(float(np.percentile(o[:, 2], 5)), 3), round(float(np.percentile(o[:, 2], 95)), 3)]}

    res = {"source": "Pump.fun Memecoin Corpus (June 19 - July 14 2026) replayed through the app's narrative pipeline",
           "days": len({d for d, _ in rhos})}
    if rhos:
        res["week_to_next_day"] = {"mean_rank_correlation": round(float(np.mean([r for _, r in rhos])), 3),
                                   "ci90": boot_mean(rhos), "days": len(rhos)}
    if work:
        res["working_next_day"] = boot_ratio(work) | {"days": len({w[0] for w in work})}
    if heat:
        res["heating_next_6h"] = boot_ratio(heat) | {"reads": len(heat)}
    w = res.get("week_to_next_day")
    if w and w["days"] >= 5:
        holds = w["ci90"][0] > 0
        res["text_week"] = (f"On {w['days']} days of replayed history, a category's week ranked its next day "
                            f"{'better than chance' if holds else 'no better than chance'} "
                            f"(average rank correlation {w['mean_rank_correlation']:+.2f}, 90% range {w['ci90'][0]:+.2f} to {w['ci90'][1]:+.2f}).")
    wn = res.get("working_next_day")
    if wn and wn["days"] >= 5:
        res["text_working"] = (f"Coins launched the next day in categories marked “working” graduated {wn['top']:.2f}× the market, "
                               f"against {wn['rest']:.2f}× for other categories (difference, 90% range {wn['difference_ci90'][0]:+.2f} "
                               f"to {wn['difference_ci90'][1]:+.2f}).")
    hn = res.get("heating_next_6h")
    if hn and len({h[0] for h in heat}) >= 5:
        res["text_heating"] = (f"Coins launched in the 6 hours after a category was “heating” graduated {hn['top']:.2f}× the market, "
                               f"against {hn['rest']:.2f}× elsewhere (difference, 90% range {hn['difference_ci90'][0]:+.2f} "
                               f"to {hn['difference_ci90'][1]:+.2f}).")
    LABEL = {"buyers_up": "buyers at 1.5× usual", "sol_up": "money in above usual", "share_up": "share of buying rising",
             "share_down": "share of buying falling", "early_successes": "new coins already graduating", "broad": "buying spread over 3+ coins",
             "single_coin": "buyers up on one coin", "crowding": "launches outpacing buyers", "watch": "on the watchlist",
             "watch_confirmed": "watchlist, confirmed", "watch_emerging": "watchlist, emerging", "watch_speculative": "watchlist, speculative",
             "broad_vs_single": "broad momentum (against single-coin momentum)"}
    res["rotation"] = {}
    for k, v in rot.items():
        if len({x[0] for x in v["grad"]}) < 5:
            res["rotation"][k] = {"label": LABEL[k], "reads": len(v["grad"]), "text": f"{LABEL[k].capitalize()}: too few occasions to test."}
            continue
        g, tr = boot_ratio(v["grad"]), boot_ratio(v["traction"])
        events = sum(x[1] for x in v["grad"])
        lo_g, hi_g = g["difference_ci90"]
        verdict = ("came before better outcomes" if lo_g > 0 else "came before worse outcomes" if hi_g < 0
                   else "made no clear difference")
        rest = "single-coin categories" if k == "broad_vs_single" else "other categories"
        days = sorted({x[0] for x in v["grad"]})
        mid = days[len(days) // 2]
        halves = []
        for part in ([x for x in v["grad"] if x[0] < mid], [x for x in v["grad"] if x[0] >= mid]):
            a_ = sum(x[1] for x in part) / max(sum(x[2] for x in part), 1e-9)
            b_ = sum(x[3] for x in part) / max(sum(x[4] for x in part), 1e-9)
            halves.append([round(a_, 2), round(b_, 2)])
        same_sign = (halves[0][0] - halves[0][1]) * (halves[1][0] - halves[1][1]) > 0
        res["rotation"][k] = {"label": LABEL[k], "reads": len(v["grad"]), "days": len(days),
                              "flagged_graduations": events, "grad": g, "traction": tr, "verdict": verdict,
                              "halves": halves, "both_halves_agree": same_sign,
                              "text": (f"{LABEL[k].capitalize()} {verdict}: the next day's coins graduated {g['top']:.2f}× the market "
                                       f"against {g['rest']:.2f}× for {rest} (difference, 90% range {lo_g:+.2f} to {hi_g:+.2f}; "
                                       f"{events} graduations behind it). Drew 50+ buyers: {tr['top']:.2f}× against {tr['rest']:.2f}×. "
                                       f"{'The same direction' if same_sign else 'Not the same direction'} in both halves of the period.")}
    print(json.dumps(res, indent=1))
    if a.write:
        OUT.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
