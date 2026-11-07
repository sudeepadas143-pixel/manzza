"""What did the narrative states predict? A walk-forward replay on research databases.

At every hour the narrative read (analytics/narratives.py) runs exactly as live, on data the
app could have seen by then, and keeps its own history (states need the previous runs). The
question for each state: do launches from the last hour that sit in a narrative in that state
graduate within the next 6 hours more often than the other launches of the same hour?
Failed launches count. Factory wallets are left out of both sides, as the live read does.

The research databases (scripts/tune_metas.py) come from Shrine's archive: names, tickers and
trading only, no descriptions, X posts or pictures, so this tests the weakest form of the read.

Usage:  python scripts/narrative_backtest.py DB [DB ...] --models DIR [--out results.json]
Each DB is copied first; the copies receive the narrative history.
"""
import argparse
import json
import random
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import embed  # noqa: E402
from radar.analytics import narratives as N  # noqa: E402
from radar.analytics.common import Lineage  # noqa: E402
from radar.db import connect, rows  # noqa: E402

H = 3600
FOLLOW_H = 6


def replay(path: Path) -> list[dict]:
    """One record per (hour, launch from the last hour): its narrative state and outcome."""
    con = connect(path)
    lo, hi = rows(con, "SELECT MIN(created_at) AS a, MAX(created_at) AS b FROM tokens")[0].values()
    grads = {r["mint"]: r["graduated_at"] for r in rows(con, "SELECT mint, MIN(graduated_at) AS graduated_at "
                                                                  "FROM graduations GROUP BY mint")}
    captured: dict = {}
    orig = N._persist

    def keep(con_, out, as_of, *a, **k):
        captured.update({m: n["state"] for n in out for m in n["_members"]})
        return orig(con_, out, as_of, *a, **k)

    N._persist = keep
    recs = []
    try:
        as_of = (lo // H + 7) * H                  # the live read needs ~6h of launches first
        while as_of + FOLLOW_H * H <= hi:
            t0 = time.time()
            captured.clear()
            res = N.build(con, as_of, Lineage(), persist=True)
            con.commit()
            launches, _ = N.load(con, as_of, Lineage())     # same factory rule as the read
            n = 0
            for t in launches:
                if t["created_at"] <= as_of - H:
                    continue
                g = grads.get(t["mint"])
                if g is not None and g <= as_of:
                    continue                        # already graduated: nothing left to predict
                recs.append({"hour": as_of, "mint": t["mint"], "state": captured.get(t["mint"], "none"),
                             "graduated": int(g is not None and g <= as_of + FOLLOW_H * H)})
                n += 1
            print(f"{path.name} {time.strftime('%m-%d %H:%M', time.gmtime(as_of))}: "
                  f"{len(res['narratives'])} narratives, {n} launches, {time.time() - t0:.0f}s", flush=True)
            as_of += H
    finally:
        N._persist = orig
        con.close()
    return recs


def summarise(recs: list[dict], boot: int = 2000, seed: int = 7) -> dict:
    """Graduation rate per state and its lift over launches outside any narrative in the same
    hours, with a 90% interval from resampling whole hours."""
    by_hour = defaultdict(list)
    for r in recs:
        by_hour[r["hour"]].append(r)
    hours = sorted(by_hour)

    def rate(rs, pred):
        sel = [r["graduated"] for r in rs if pred(r)]
        return (sum(sel) / len(sel), len(sel)) if sel else (None, 0)

    def lift(hs, state):
        a = [r for h in hs for r in by_hour[h] if r["state"] == state]
        b = [r for h in hs for r in by_hour[h] if r["state"] == "none"]
        if not a or not b:
            return None
        return 100 * (sum(r["graduated"] for r in a) / len(a) - sum(r["graduated"] for r in b) / len(b))

    rnd = random.Random(seed)
    states = sorted({r["state"] for r in recs})
    out = {"hours": len(hours), "launches": len(recs), "states": {}}
    for s in states:
        p, n = rate(recs, lambda r, s=s: r["state"] == s)
        row = {"launches": n, "graduation_pct": round(100 * p, 2) if p is not None else None}
        if s != "none":
            est = lift(hours, s)
            draws = sorted(x for x in (lift([rnd.choice(hours) for _ in hours], s) for _ in range(boot))
                           if x is not None)
            row["lift_pts"] = round(est, 2) if est is not None else None
            if len(draws) >= 100:
                row["lift_90"] = [round(draws[int(.05 * len(draws))], 2), round(draws[int(.95 * len(draws))], 2)]
            row["hours_with_state"] = len({r["hour"] for r in recs if r["state"] == s})
        out["states"][s] = row
    inn = [r for r in recs if r["state"] != "none"]
    if inn:
        out["any_narrative_lift_pts"] = round(100 * (sum(r["graduated"] for r in inn) / len(inn)
                                                     - out["states"]["none"]["graduation_pct"] / 100), 2)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dbs", nargs="+", type=Path)
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if not embed.load(a.models):
        sys.exit("language model not available")
    result = {}
    for db in a.dbs:
        work = db.with_name(db.stem + "_narratives.db")
        shutil.copyfile(db, work)
        result[db.stem] = summarise(replay(work))
        print(json.dumps(result[db.stem], indent=1), flush=True)
    if a.out:
        a.out.write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
