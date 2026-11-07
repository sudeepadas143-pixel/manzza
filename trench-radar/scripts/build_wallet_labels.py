"""Build radar/data/wallet_labels.csv.gz from the Solana Memecoin Dataset.

Source: github.com/ian05012/solana-memecoin-dataset (MIT), data/wallets.parquet. Its labels
come from GMGN and the project's own rules ("smart_money" = hit rate >= 40% over 5+ trades
and realized PnL >= 1.0). Collected 2026-06-10..06-30; wallets change behaviour, so treat
these as a starting point, not ground truth.

Usage (needs pyarrow, which the app itself does not):
    python scripts/build_wallet_labels.py <path-to-dataset>/data/wallets.parquet
"""
import csv
import gzip
import sys
from pathlib import Path

import pyarrow.parquet as pq

KEEP = {"smart_money": "smart", "insider": "insider"}


def main(src: str) -> None:
    out = Path(__file__).resolve().parent.parent / "radar" / "data" / "wallet_labels.csv.gz"
    rows = [r for r in pq.read_table(src, columns=["address", "wallet_type", "win_rate"]).to_pylist()
            if r["wallet_type"] in KEEP and r["address"]]
    with gzip.open(out, "wt", newline="", compresslevel=9) as f:
        w = csv.writer(f)
        w.writerow(["address", "label", "win_rate"])
        for r in sorted(rows, key=lambda r: r["address"]):
            w.writerow([r["address"], KEEP[r["wallet_type"]],
                        "" if r["win_rate"] is None else round(r["win_rate"], 3)])
    print(f"wrote {len(rows)} labels to {out}")


if __name__ == "__main__":
    main(sys.argv[1])
