"""Tune meta detection on one period of Shrine's archive, test it once on a later one.

The question: does handling launch factories (a few wallets launching hundreds of coins an
hour) make narrative acceleration more predictive of which launches graduate?

  1. Replay each period from Shrine's free hourly archive into its own research database,
     as a live run would have seen it (events stamped at their own time).
  2. Label every launch, failed ones included: graduated within 6 hours or not.
  3. Run the app's walk-forward backtest (hourly steps, 6h follow window) once per variant of
     metas.SPAM_MODE. Pick the variant on the tuning period only, then report all variants
     on the test period, which plays no part in the choice.

Usage:  python scripts/tune_metas.py --workdir research/ [--hours 18]
Downloads ~230 MB per archive hour (each period needs hours + 19 of archive).
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import corpus, shrine  # noqa: E402
from radar.analytics import backtest, metas  # noqa: E402
from radar.db import connect  # noqa: E402

H = 3600
PERIODS = {"tune": datetime(2026, 9, 16, tzinfo=timezone.utc), "test": datetime(2026, 10, 15, tzinfo=timezone.utc)}
VARIANTS = ["none", "creators", "exclude"]
FOLLOW_H, HORIZON_H = 6, 6


def build(path: Path, start: int, hours: int) -> None:
    con = connect(path)
    first, last = start - 7 * H, start + (hours + FOLLOW_H + HORIZON_H) * H - H
    prices = corpus.sol_prices(first, last + H)
    sol = sum(prices.values()) / len(prices) if prices else None
    con.execute("BEGIN")
    con.execute("DELETE FROM market_obs WHERE metric='sol_price_usd'")
    con.executemany("INSERT INTO market_obs (observed_at, metric, value, source, detail) "
                    "VALUES (?, 'sol_price_usd', ?, 'defillama', 'historical')", sorted(prices.items()))
    con.execute("COMMIT")
    stats = shrine.backfill(con, start_hour=first, end_hour=last, simulate_live=True, sol_usd=sol)
    logging.info("built %s: %s", path.name, stats)
    label(con)


def label(con) -> None:
    """Graduated within each horizon, from the replayed curve completions. No price labels."""
    con.execute("BEGIN")
    con.execute("DELETE FROM token_outcomes")
    con.execute("""INSERT INTO token_outcomes (mint, horizon_h, evaluated_at, graduated, bucket, source)
                   SELECT k.mint, ?, k.created_at + ? * 3600,
                          CASE WHEN g.graduated_at IS NOT NULL AND g.graduated_at <= k.created_at + ? * 3600
                               THEN 1 ELSE 0 END, 'unknown', 'shrine_replay'
                   FROM tokens k LEFT JOIN graduations g ON g.mint = k.mint
                   WHERE k.created_at IS NOT NULL""", (HORIZON_H, HORIZON_H, HORIZON_H))
    con.execute("COMMIT")


def run(path: Path, start: int, hours: int) -> dict:
    con = connect(path)
    out = {}
    for v in VARIANTS:
        metas.SPAM_MODE = v
        res = backtest.run_backtest(con, start, start + hours * H, step_s=H, follow_h=FOLLOW_H,
                                    horizon_h=HORIZON_H, persist=False, min_signals=30)
        acc = res["by_acceleration"]["accelerating (z >= 2)"]
        out[v] = {"steps": res["steps"], "signals": res["signals"], "accelerating": acc,
                  "favorable": res["by_verdict"]["favorable"], "spearman": res["spearman_score_vs_grad_lift"]}
    metas.SPAM_MODE = "none"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="research")
    ap.add_argument("--hours", type=int, default=18)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    wd = Path(a.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, day in PERIODS.items():
        path, start = wd / f"shrine_{name}.db", int(day.timestamp())
        build(path, start, a.hours)          # resumes: hours already replayed are skipped
        results[name] = run(path, start, a.hours)
    tune = results["tune"]
    # pick on the tuning period only: the variant whose accelerating metas beat the base rate most
    score = lambda v: (tune[v]["accelerating"]["grad_lift_lower90"] or -1, tune[v]["accelerating"]["mean_grad_lift"] or -1)  # noqa: E731
    chosen = max(VARIANTS, key=score)
    print(json.dumps({"chosen_on_tune": chosen, "results": results}, indent=1, default=str))


if __name__ == "__main__":
    main()
