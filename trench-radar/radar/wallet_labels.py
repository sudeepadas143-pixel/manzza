"""Wallet labels shipped with the app: smart money and insiders from the Solana Memecoin
Dataset (github.com/ian05012/solana-memecoin-dataset, MIT; labels originally from GMGN,
June 2026). Built by scripts/build_wallet_labels.py.

These complement the app's own learned "proven wallets" (stream.py), which come only from
graduations this app has seen. Labels can go stale: a wallet that was smart in June may not
be now, and insiders rotate wallets quickly.
"""
from __future__ import annotations

import csv
import gzip
import sys
from dataclasses import dataclass, field
from pathlib import Path

PATH = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "radar" / "data" / "wallet_labels.csv.gz"


@dataclass
class WalletLabels:
    smart: set[str] = field(default_factory=set)
    insider: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, path: Path = PATH) -> "WalletLabels":
        out = cls()
        if not path.exists():
            return out
        with gzip.open(path, "rt", newline="") as f:
            for r in csv.DictReader(f):
                (out.smart if r["label"] == "smart" else out.insider).add(r["address"])
        return out

    def __len__(self) -> int:
        return len(self.smart) + len(self.insider)
