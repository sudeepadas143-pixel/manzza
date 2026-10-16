"""Shared SQLite store. All times are UTC unix seconds.

`observed_at` = when this app saw the fact; `created_at` = when the chain or the
post says it happened. Observation tables are append-only so any metric can be
recomputed as of a past moment (see analytics/backtest.py).
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta_info (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL, job TEXT NOT NULL,
  started_at INTEGER NOT NULL, finished_at INTEGER,
  status TEXT NOT NULL,            -- ok | error | unavailable | skipped
  items INTEGER DEFAULT 0, latency_ms INTEGER, error TEXT
);
CREATE INDEX IF NOT EXISTS ix_runs_source ON source_runs(source, started_at);

CREATE TABLE IF NOT EXISTS tokens (
  mint TEXT PRIMARY KEY,
  name TEXT, symbol TEXT, creator TEXT, uri TEXT,
  pool TEXT,                       -- pump-fun pool address = BondingCurve PDA
  launchpad TEXT,                  -- pump-fun | other
  created_at INTEGER,              -- pool creation time per source
  first_seen_at INTEGER NOT NULL,
  source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tokens_created ON tokens(created_at);
CREATE INDEX IF NOT EXISTS ix_tokens_creator ON tokens(creator, created_at);

CREATE TABLE IF NOT EXISTS token_obs (
  id INTEGER PRIMARY KEY,
  mint TEXT NOT NULL, observed_at INTEGER NOT NULL, source TEXT NOT NULL,
  dex TEXT, pool TEXT,
  price_usd REAL, mcap_usd REAL, fdv_usd REAL, liquidity_usd REAL,
  vol_m5 REAL, vol_h1 REAL, vol_h6 REAL, vol_h24 REAL,
  buys_h1 INTEGER, sells_h1 INTEGER, buyers_h1 INTEGER, sellers_h1 INTEGER,
  buys_h24 INTEGER, sells_h24 INTEGER, buyers_h24 INTEGER, sellers_h24 INTEGER,
  chg_h1 REAL, chg_h24 REAL,
  buy_vol_h1 REAL, sell_vol_h1 REAL          -- only when a source reports them (Bitquery)
);
CREATE INDEX IF NOT EXISTS ix_tobs_mint ON token_obs(mint, observed_at);
CREATE INDEX IF NOT EXISTS ix_tobs_time ON token_obs(observed_at);

CREATE TABLE IF NOT EXISTS curve_obs (
  id INTEGER PRIMARY KEY,
  mint TEXT NOT NULL, observed_at INTEGER NOT NULL,
  real_sol REAL, real_token_reserves REAL, progress REAL, complete INTEGER,
  price_sol REAL
);
CREATE INDEX IF NOT EXISTS ix_curve_mint ON curve_obs(mint, observed_at);

CREATE TABLE IF NOT EXISTS graduations (
  mint TEXT PRIMARY KEY, detected_at INTEGER NOT NULL, graduated_at INTEGER,
  source TEXT NOT NULL, pool TEXT
);

CREATE TABLE IF NOT EXISTS creator_obs (
  id INTEGER PRIMARY KEY,
  creator TEXT NOT NULL, observed_at INTEGER NOT NULL,
  sol_balance REAL, recent_tx INTEGER
);

CREATE TABLE IF NOT EXISTS attention_obs (       -- paid boosts / profiles (DexScreener)
  id INTEGER PRIMARY KEY,
  mint TEXT NOT NULL, observed_at INTEGER NOT NULL, kind TEXT NOT NULL,
  amount REAL, description TEXT, links INTEGER
);
CREATE INDEX IF NOT EXISTS ix_att ON attention_obs(observed_at);

CREATE TABLE IF NOT EXISTS social_posts (
  id TEXT PRIMARY KEY,             -- source:native_id
  source TEXT NOT NULL, author_id TEXT, author_handle TEXT,
  author_followers INTEGER, author_created_at INTEGER,
  text TEXT NOT NULL, created_at INTEGER NOT NULL, collected_at INTEGER NOT NULL,
  likes INTEGER DEFAULT 0, reposts INTEGER DEFAULT 0, replies INTEGER DEFAULT 0,
  views INTEGER DEFAULT 0, url TEXT, query TEXT,
  fingerprint TEXT, is_spam INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_posts_created ON social_posts(created_at);

CREATE TABLE IF NOT EXISTS market_obs (
  id INTEGER PRIMARY KEY,
  observed_at INTEGER NOT NULL, metric TEXT NOT NULL, value REAL,
  source TEXT NOT NULL, detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_market ON market_obs(metric, observed_at);

CREATE TABLE IF NOT EXISTS meta_obs (
  id INTEGER PRIMARY KEY,
  meta_key TEXT NOT NULL, observed_at INTEGER NOT NULL,
  features TEXT NOT NULL           -- JSON feature vector as of observed_at
);
CREATE INDEX IF NOT EXISTS ix_metaobs ON meta_obs(meta_key, observed_at);

CREATE TABLE IF NOT EXISTS scores (
  id INTEGER PRIMARY KEY,
  meta_key TEXT NOT NULL, computed_at INTEGER NOT NULL,
  score REAL, confidence REAL, verdict TEXT, model_version TEXT,
  detail TEXT NOT NULL             -- JSON: components, reasons, risks, evidence, freshness
);
CREATE INDEX IF NOT EXISTS ix_scores ON scores(computed_at, meta_key);

CREATE TABLE IF NOT EXISTS token_outcomes (
  mint TEXT NOT NULL, horizon_h INTEGER NOT NULL,
  evaluated_at INTEGER NOT NULL,
  graduated INTEGER, bucket TEXT,                -- dead|weak|alive|migrated|unknown
  first_price REAL, end_price REAL, max_price REAL,
  ret_end REAL, ret_max REAL,                    -- vs first observed price, before costs
  source TEXT,
  PRIMARY KEY (mint, horizon_h)
);

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL, kind TEXT NOT NULL,
  meta_key TEXT, message TEXT NOT NULL, delivered INTEGER DEFAULT 0, error TEXT
);

CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL, kind TEXT NOT NULL,
  analyst TEXT NOT NULL, body TEXT NOT NULL, evidence TEXT
);

CREATE TABLE IF NOT EXISTS backtests (
  id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL,
  params TEXT NOT NULL, results TEXT NOT NULL
);
"""


def now() -> int:
    return int(time.time())


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit: observations are append-only, and an implicit transaction left open
    # across an awaited network call would lock out every other reader/writer.
    con = sqlite3.connect(str(path), timeout=30, check_same_thread=False, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    have = con.execute("SELECT value FROM meta_info WHERE key='schema_version'").fetchone()
    if not have or have[0] != str(SCHEMA_VERSION):
        con.execute("INSERT OR REPLACE INTO meta_info VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    return con


def insert(con: sqlite3.Connection, table: str, row: dict, *, or_ignore: bool = False,
           or_replace: bool = False) -> int:
    cols = ",".join(row)
    qs = ",".join("?" for _ in row)
    verb = "INSERT OR IGNORE" if or_ignore else "INSERT OR REPLACE" if or_replace else "INSERT"
    cur = con.execute(f"{verb} INTO {table} ({cols}) VALUES ({qs})", tuple(row.values()))
    return cur.rowcount


def rows(con: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def one(con: sqlite3.Connection, sql: str, args: tuple = ()) -> dict | None:
    r = con.execute(sql, args).fetchone()
    return dict(r) if r else None


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, default=str)
