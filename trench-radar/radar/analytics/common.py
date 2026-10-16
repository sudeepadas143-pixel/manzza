"""Point-in-time helpers shared by the analytics modules.

Rule: every query takes `as_of` and may only read rows this app had observed at
that moment (observed_at / first_seen_at / collected_at / detected_at <= as_of).
`Lineage` records the newest timestamp actually read so tests and the backtest
can assert nothing from the future leaked in.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..db import rows

# Expected cadence per (source, job); used for freshness. Matches config defaults.
EXPECTED_EVERY_S = {
    ("geckoterminal", "new_pools"): 180, ("geckoterminal", "active_pools"): 300,
    ("geckoterminal", "refresh"): 300, ("solana_rpc", "bonding_curves"): 300,
    ("solana_rpc", "deployers"): 300, ("dexscreener", "boosts_profiles"): 600,
    ("defillama", "launchpad_volume"): 3600, ("x_api", "recent_search"): 900,
    ("reddit", "new_posts"): 900, ("bitquery", "net_flow"): 300,
    ("pumpfun", "latest_coins"): 300, ("outcomes", "label"): 1800,
}


@dataclass
class Lineage:
    max_ts: int = 0
    reads: dict = field(default_factory=dict)

    def saw(self, table: str, ts: int | None, n: int = 1) -> None:
        if ts:
            self.max_ts = max(self.max_ts, int(ts))
        self.reads[table] = self.reads.get(table, 0) + n


def logistic(x: float, mid: float, steep: float) -> float:
    return 1 / (1 + math.exp(-steep * (x - mid)))


def clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def source_freshness(con, as_of: int) -> dict[str, dict]:
    """Per source/job: last ok run, age, status of latest run, and a 0..1 freshness factor."""
    out = {}
    for r in rows(con, """
        SELECT source, job,
               MAX(CASE WHEN status='ok' THEN finished_at END) AS last_ok,
               MAX(finished_at) AS last_run
        FROM source_runs WHERE finished_at <= ? GROUP BY source, job
    """, (as_of,)):
        latest = rows(con, "SELECT status, error FROM source_runs WHERE source=? AND job=? AND finished_at=? "
                           "ORDER BY id DESC LIMIT 1", (r["source"], r["job"], r["last_run"]))[0]
        every = EXPECTED_EVERY_S.get((r["source"], r["job"]), 900)
        age = as_of - r["last_ok"] if r["last_ok"] else None
        if age is None:
            fresh, state = 0.0, latest["status"]
        elif age <= 2 * every:
            fresh, state = 1.0, "fresh"
        elif age <= 6 * every:
            fresh, state = 0.5, "stale"
        else:
            fresh, state = 0.0, "expired"
        if latest["status"] in ("unavailable", "error") and state == "fresh":
            state = "degraded"
        out[f"{r['source']}/{r['job']}"] = {
            "source": r["source"], "job": r["job"], "last_ok": r["last_ok"], "age_s": age,
            "state": state, "freshness": fresh, "last_status": latest["status"],
            "last_error": latest["error"], "expected_every_s": every,
        }
    return out


def launch_coverage(con, as_of: int, window_s: int) -> float:
    """Share of the window during which new launches were actually being observed.

    Each ok `new_pools` run sees back ~span seconds (9 pages ≈ 4 min). Coverage is
    the union of [run_time - span, run_time] intervals inside the window."""
    runs = rows(con, """SELECT finished_at FROM source_runs WHERE source='geckoterminal' AND job='new_pools'
                        AND status='ok' AND finished_at > ? AND finished_at <= ? ORDER BY finished_at""",
                (as_of - window_s, as_of))
    spans = rows(con, """SELECT value FROM market_obs WHERE metric='new_pools_span_s' AND observed_at <= ?
                         AND observed_at > ? ORDER BY value""", (as_of, as_of - window_s - 86400))
    span = spans[len(spans) // 2]["value"] if spans else 240
    covered, last_end = 0.0, as_of - window_s
    for r in runs:
        start = max(r["finished_at"] - span, last_end)
        if r["finished_at"] > start:
            covered += r["finished_at"] - start
            last_end = r["finished_at"]
    return clip01(covered / window_s)
