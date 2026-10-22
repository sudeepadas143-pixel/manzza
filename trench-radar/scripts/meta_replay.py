"""Replay the app's narrative read hour by hour over a research database, as a live install would
have run it, so the macro and intraday meta views (radar/analytics/macro.py) can be built and
tested on weeks of real history instead of the few days a fresh install has.

Each hour T: narratives.build(con, T, persist=True) reads only launches up to T and records
narrative identities, their hourly state (narrative_obs) and each coin's first narrative and
category (token_narrative). Hours whose 6-hour window touches a collection gap are skipped.
Afterwards every coin is summarised (macro.summarize) exactly as the live job does.

Usage: python scripts/meta_replay.py research_copy.db MODEL_DIR [--start T] [--end T]
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import corpus, embed  # noqa: E402
from radar.__main__ import CORPUS_GAPS  # noqa: E402
from radar.analytics import macro, narratives  # noqa: E402
from radar.db import connect  # noqa: E402

H = 3600
JUN19 = 1781827200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db", type=Path)
    ap.add_argument("models", type=Path)
    ap.add_argument("--start", type=int, default=JUN19 + 7 * H)
    ap.add_argument("--end", type=int)
    ap.add_argument("--fresh", action="store_true", help="clear earlier replay rows first")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if not embed.load(a.models):
        sys.exit("the language model could not be loaded")
    con = connect(a.db)
    if a.fresh:
        for t in ("narratives", "narrative_obs", "narrative_categories", "narrative_events", "token_narrative", "token_summary"):
            con.execute(f"DELETE FROM {t}")
        con.commit()
    end = a.end or con.execute("SELECT MAX(created_at) FROM tokens").fetchone()[0]
    gaps = CORPUS_GAPS + corpus.gaps(con)
    n, t0 = 0, time.time()
    for T in range(a.start, end, H):
        if any(x < T and T - 6 * H < y for x, y in gaps):
            continue
        narratives.build(con, T, persist=True)
        n += 1
        if n % 24 == 0:
            print(time.strftime("%H:%M:%S"), "reads", n, time.strftime("%m-%d %H:%M", time.gmtime(T)),
                  f"{(time.time() - t0) / n:.1f}s/read", flush=True)
    print("narrative reads:", n, flush=True)
    done = macro.summarize(con, end + 2 * 86400, limit=None)
    print("coins summarised:", done, flush=True)


if __name__ == "__main__":
    main()
