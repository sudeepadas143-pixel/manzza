"""How much do the macro and intraday meta views say about what comes next? Measured on history
replayed through the app's own pipeline (scripts/meta_replay.py), using only what each view
knew at the time.

1. Weekly record -> next day. At the end of each day d, the 7-day macro view (coins matured by
   then). Outcome: each category's coins launched on day d+1, graduated (not instantly) against
   all coins that day. Rank correlation across categories per day; and the next-day record of
   categories marked "working" against all other categorised coins.
2. Today's heat -> next 6 hours. Every 6 hours, the intraday view. Outcome: each category's coins
   launched in the next 6 hours, against all coins then. "Heating" categories against the rest.

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
    if w:
        holds = w["ci90"][0] > 0
        res["text_week"] = (f"On {w['days']} days of replayed history, a category's week ranked its next day "
                            f"{'better than chance' if holds else 'no better than chance'} "
                            f"(average rank correlation {w['mean_rank_correlation']:+.2f}, 90% range {w['ci90'][0]:+.2f} to {w['ci90'][1]:+.2f}).")
    wn = res.get("working_next_day")
    if wn:
        res["text_working"] = (f"Coins launched the next day in categories marked “working” graduated {wn['top']:.2f}× the market, "
                               f"against {wn['rest']:.2f}× for other categories (difference, 90% range {wn['difference_ci90'][0]:+.2f} "
                               f"to {wn['difference_ci90'][1]:+.2f}).")
    hn = res.get("heating_next_6h")
    if hn:
        res["text_heating"] = (f"Coins launched in the 6 hours after a category was “heating” graduated {hn['top']:.2f}× the market, "
                               f"against {hn['rest']:.2f}× elsewhere (difference, 90% range {hn['difference_ci90'][0]:+.2f} "
                               f"to {hn['difference_ci90'][1]:+.2f}).")
    print(json.dumps(res, indent=1))
    if a.write:
        OUT.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
