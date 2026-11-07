"""Which early signals went with a 2x? Univariate check on the Solana Memecoin Dataset.

Source: github.com/ian05012/solana-memecoin-dataset (MIT), data/tokens.parquet: 44,460
snapshots of pump.fun tokens after graduation or on GMGN's trending board, June 2026, with
forward max-return labels. One snapshot per token is kept (its first detection) so repeat
detections do not count twice. For each feature: the share of tokens reaching 2x within 24h
in the top vs bottom fifth of the feature, with a 90% bootstrap interval resampled by day.

Read the output as descriptive, not causal: one 20-day regime, survivors only (tokens that
lived long enough to be detected), and `reaches_2x` is a peak, not an exit you could take.

    python scripts/research_dataset.py <dataset>/data/tokens.parquet > docs/RESEARCH_DATA.md
"""
import random
import sys
from collections import defaultdict
from datetime import timezone

import pyarrow.parquet as pq

# dataset column -> what it corresponds to in TRENCH//RADAR
FEATURES = {
    "unique_buyers": "unique buyers (buyers_h1)",
    "net_flow_usd": "net buy flow (net_flow_usd_h1)",
    "trade_buy_sell_ratio": "buy/sell balance (buyer_share_h1)",
    "smart_buy_1h": "smart-money buys, 1h (proven / labelled buyers)",
    "smart_money_count": "smart-money holders",
    "kol_buy_1h": "KOL buys, 1h",
    "bundler_ratio": "bundler share of active wallets (launch-block buyers)",
    "sniper_count": "snipers (launch-block buyers)",
    "top10_holder_pct": "top-10 holder share (top10_pct)",
    "dev_remaining_pct": "creator still holds (dev_holds_pct)",
    "insider_pct_holders": "insider share of holders (insider buyers)",
    "crew_cohesion": "coordinated buyer crew",
    "fresh_wallet_pct": "fresh wallets among holders",
    "has_twitter": "has an X link (metadata)",
    "is_boosted": "paid DexScreener boost",
    "time_since_launch_sec": "token age at detection",
    "price_change_1h": "1h price change at detection",
}


def main(path: str) -> None:
    cols = ["token_address", "captured_at", "reaches_2x", "staged_exit_return"] + list(FEATURES)
    rows = pq.read_table(path, columns=cols).to_pylist()
    rows.sort(key=lambda r: r["captured_at"])
    first, seen = [], set()
    for r in rows:
        if r["token_address"] not in seen and r["reaches_2x"] is not None:
            seen.add(r["token_address"])
            first.append(r)
    base = sum(bool(r["reaches_2x"]) for r in first) / len(first)
    days = sorted({r["captured_at"].astimezone(timezone.utc).date() for r in first})
    print("# Dataset check: which early signals went with a 2x\n")
    print(f"Source: Solana Memecoin Dataset (MIT), {len(rows):,} snapshots -> {len(first):,} tokens "
          f"(first detection each), {days[0]} to {days[-1]} ({len(days)} days).")
    print(f"Base rate: {base:.1%} of tokens reached 2x within 24h of detection.\n")
    print("| Signal (dataset column) | TRENCH//RADAR equivalent | n bottom / top | 2x rate, bottom fifth | 2x rate, top fifth | top − bottom (90% CI, by day) | staged exit, mean: bottom / top |")
    print("|---|---|---|---|---|---|---|")
    rng = random.Random(7)
    for col, ours in FEATURES.items():
        vals = [(r[col], bool(r["reaches_2x"]), r["captured_at"].date()) for r in first
                if r[col] is not None and r[col] == r[col]]
        ex = [(r[col], r["staged_exit_return"]) for r in first
              if r[col] is not None and r[col] == r[col] and r["staged_exit_return"] is not None]
        if len(vals) < 500:
            print(f"| `{col}` | {ours} | {len(vals)} | — | — | too few values |")
            continue
        binary = len({v for v, _, _ in vals}) <= 2
        if binary:   # binary feature: compare the two groups
            lo = [y for v, y, _ in vals if not v]
            hi = [y for v, y, _ in vals if v]
            groups = {d: ([], []) for d in days}
            for v, y, d in vals:
                groups[d][1 if v else 0].append(y)
        else:
            vs = sorted(v for v, _, _ in vals)
            q1, q4 = vs[len(vs) // 5], vs[4 * len(vs) // 5]
            # many features are mostly zero: "top" is then everything above the bottom value
            is_lo = lambda v: v <= q1  # noqa: E731
            is_hi = lambda v: v >= q4 and v > q1  # noqa: E731
            lo = [y for v, y, _ in vals if is_lo(v)]
            hi = [y for v, y, _ in vals if is_hi(v)]
            groups = {d: ([], []) for d in days}
            for v, y, d in vals:
                if is_lo(v):
                    groups[d][0].append(y)
                elif is_hi(v):
                    groups[d][1].append(y)
        if not lo or not hi:
            print(f"| `{col}` | {ours} | {len(vals)} | — | — | no spread |")
            continue
        diffs = []
        for _ in range(1000):
            pick = [groups[rng.choice(days)] for _ in days]
            a = [y for g in pick for y in g[0]]
            b = [y for g in pick for y in g[1]]
            if a and b:
                diffs.append(sum(b) / len(b) - sum(a) / len(a))
        diffs.sort()
        d = sum(hi) / len(hi) - sum(lo) / len(lo)
        ci = f"{d:+.1%} ({diffs[50]:+.1%} to {diffs[949]:+.1%})"
        flag = " **" if diffs[50] > 0 or diffs[949] < 0 else ""
        if binary:
            e_lo = [e for v, e in ex if not v]
            e_hi = [e for v, e in ex if v]
        else:
            e_lo = [e for v, e in ex if is_lo(v)]
            e_hi = [e for v, e in ex if is_hi(v)]
        med = lambda xs: sorted(xs)[len(xs) // 2] if xs else float("nan")  # noqa: E731
        print(f"| `{col}` | {ours} | {len(lo):,} / {len(hi):,} | {sum(lo) / len(lo):.1%} | {sum(hi) / len(hi):.1%} | {ci}{flag} "
              f"| {sum(e_lo) / len(e_lo):.2f}x / {sum(e_hi) / len(e_hi):.2f}x |")
    allx = [r["staged_exit_return"] for r in first if r["staged_exit_return"] is not None]
    print(f"\n** = the 90% interval excludes zero. Staged exit = the dataset's simulated "
          f"sell-in-stages return (1.00x = break-even, before fees); all tokens: {sum(allx) / len(allx):.2f}x.")


if __name__ == "__main__":
    main(sys.argv[1])
