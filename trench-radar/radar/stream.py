"""Real-time pump.fun feed straight from the chain.

One websocket (`logsSubscribe` mentioning the pump program) delivers every launch, every
bonding-curve trade with the trader's wallet, and every curve completion, about 1s after
it happens. Nothing here depends on an aggregator such as GeckoTerminal.

What is kept where:
  in memory   the last hour of trades per token (to count unique wallets), hourly volume
              buckets for 24h, the live tape served by /api/live
  SQLite      tokens (every launch), graduations, the first 20 buyers of every token
              (early_buyers, for wallet track records), and every `snapshot_every_s` a
              token_obs + curve_obs row for each token with real activity — the same tables
              the analytics already read, so scoring and the backtest work unchanged.

Wallet-level signals this adds (none of them are visible on public terminals):
  organic buyers  unique buyers minus wallets that traded 15+ different tokens in the
                  last hour (sniper and volume bots)
  smart buyers    buyers whose early-entry record shows >=2 graduated tokens and a
                  graduation hit rate >=10% over the last 7 days (base rate is ~1%),
                  computed only from graduations seen before now, so there is no look-ahead
  dev sold        SOL the token's creator has sold back into the curve
  clones          the same name launched by several wallets within 15 minutes
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque

from .db import insert, now, one, rows
from .wallet_labels import WalletLabels
from .sources.base import SourceUnavailable, record_run
from .sources.pump_events import PUMP_PROGRAM, parse_notification, progress_from_real_tokens

log = logging.getLogger("radar.stream")

H = 3600
EARLY_N = 20                 # first N distinct buyers recorded per token
BOT_MINTS_PER_H = 15         # a wallet trading this many tokens in an hour is treated as a bot
MIN_BUYERS_TO_SNAPSHOT = 5   # below this a token gets no token_obs row (keeps the DB small)
SMART_MIN_GRADS, SMART_MIN_HIT, SMART_LOOKBACK_S = 2, 0.10, 7 * 86400
SUPPLY = 1_000_000_000       # pump.fun tokens: 1B supply


class MintState:
    __slots__ = ("mint", "name", "symbol", "creator", "created_at", "pool", "amm_pool", "init_tokens",
                 "sol_paired", "create_slot", "block_buyers", "block_tokens", "holdings", "trades", "hours", "price",
                 "price_hist", "real_sol", "real_tokens", "last_ts", "dev_sold", "early",
                 "graduated", "snap_ts")

    def __init__(self, mint: str):
        self.mint = mint
        self.name = self.symbol = self.creator = None
        self.created_at = self.pool = self.amm_pool = self.init_tokens = self.create_slot = None
        self.sol_paired = True              # False: paired with another token, amounts aren't SOL
        self.block_buyers: set[str] = set() # wallets (not the creator) buying in the launch block
        self.block_tokens = 0.0             # tokens they bought there
        # tokens each wallet holds, from the trades seen (exact for tokens launched while the
        # stream was running, except wallet-to-wallet transfers, which are not trades)
        self.holdings: dict[str, float] = defaultdict(float)
        self.trades: deque = deque()          # (ts, wallet, is_buy, sol) for the last hour
        self.hours: dict[int, list] = {}      # hour -> [buys, sells, buy_sol, sell_sol, first price]
        self.price = None                     # SOL per token
        self.price_hist: deque = deque()      # (ts, price) about every 5 min, 2h kept
        self.real_sol = self.real_tokens = None
        self.last_ts = 0
        self.dev_sold = 0.0
        self.early: list[str] = []
        self.graduated = False
        self.snap_ts = 0


class Live:
    """Everything the stream knows right now. One instance per process (LIVE)."""

    def __init__(self):
        self.mints: dict[str, MintState] = {}
        self.launches: deque = deque(maxlen=400)
        self.launch_minutes: dict[int, int] = defaultdict(int)
        self.grads: deque = deque(maxlen=200)
        self.names: dict[str, deque] = defaultdict(deque)       # lowercase name -> (ts, creator)
        self.creators: dict[str, deque] = defaultdict(deque)    # creator -> launch ts (24h)
        self.smart: set[str] = set()                            # learned from graduations seen
        self.labels = WalletLabels.load()                       # shipped labels (see wallet_labels.py)
        self.smart_computed_at = 0
        self.connected = False
        self.connected_since = None
        self.last_event_at = 0.0
        self.last_error: str | None = None
        self.down_since: float | None = None
        self.endpoint: str | None = None          # host of the websocket in use
        self.lag_s: float | None = None
        self.events = 0                 # decoded events since the last heartbeat
        self.connected_s = 0.0          # seconds connected since the last heartbeat
        self._mark: float | None = None # when the current connection (or window) started
        self.reconnects = 0             # since the last heartbeat
        self.total_events = 0
        self.pending: dict[str, list] = {"tokens": [], "early": [], "grads": [], "pools": []}
        self.meta_queue: deque = deque(maxlen=600)   # (mint, uri) awaiting a metadata fetch
        self.x_posts: dict[str, str] = {}            # mint -> X post its metadata links

    def set_connected(self, on: bool, t: float | None = None) -> None:
        t = t or time.time()
        if on and not self.connected:
            self._mark = t
            self.connected_since = self.connected_since or int(t)
        elif not on and self.connected:
            self.connected_s += t - (self._mark or t)
            self._mark = None
            self.reconnects += 1
            self.down_since = t
        if on:
            self.down_since = None
        self.connected = on

    def take_window(self, t: float | None = None) -> tuple[int, float, int]:
        """(events, seconds connected, reconnects) since the last call."""
        t = t or time.time()
        if self.connected and self._mark:
            self.connected_s += t - self._mark
            self._mark = t
        out = (self.events, self.connected_s, self.reconnects)
        self.events, self.connected_s, self.reconnects = 0, 0.0, 0
        return out

    # ------------------------------------------------------------------ ingest
    def on_raw(self, raw: str) -> None:
        evs = parse_notification(raw)
        if not evs:
            return
        for ev in evs:
            self.on_event(ev)

    def on_event(self, ev: dict, t: float | None = None) -> None:
        t = t or time.time()
        self.events += 1
        self.total_events += 1
        self.last_event_at = t
        if ev.get("ts"):
            lag = max(0.0, t - ev["ts"])
            self.lag_s = lag if self.lag_s is None else 0.9 * self.lag_s + 0.1 * lag
        kind = ev["type"]
        if kind == "create":
            self._on_create(ev, int(t))
        elif kind == "trade":
            self._on_trade(ev)
        elif kind == "complete":
            self._graduate(self._state(ev["mint"]), ev["ts"])
        elif kind == "migration":
            ms = self._state(ev["mint"])
            ms.amm_pool = ev["pool"]
            self._graduate(ms, ev["ts"])
            self.pending["pools"].append((ev["pool"], ev["mint"]))

    def _state(self, mint: str) -> MintState:
        ms = self.mints.get(mint)
        if ms is None:
            ms = self.mints[mint] = MintState(mint)
        return ms

    def _on_create(self, ev: dict, t: int) -> None:
        ms = self._state(ev["mint"])
        ms.name, ms.symbol, ms.creator, ms.created_at = ev["name"], ev["symbol"], ev["creator"], ev["ts"]
        ms.pool = ev["bonding_curve"]
        ms.init_tokens, ms.sol_paired, ms.create_slot = ev.get("initial_real_tokens"), ev.get("sol_paired", True), ev.get("slot")
        key = (ev["name"] or "").strip().lower()
        same = self.names[key]
        while same and same[0][0] < ev["ts"] - 900:
            same.popleft()
        same.append((ev["ts"], ev["creator"]))
        dq = self.creators[ev["creator"]]
        while dq and dq[0] < ev["ts"] - 86400:
            dq.popleft()
        dq.append(ev["ts"])
        self.launches.append({"mint": ev["mint"], "name": ev["name"], "symbol": ev["symbol"],
                              "creator": ev["creator"], "ts": ev["ts"],
                              "clones": len({c for _, c in same}), "creator_launches_24h": len(dq)})
        self.launch_minutes[ev["ts"] // 60 * 60] += 1
        if ev.get("uri"):
            self.meta_queue.append((ev["mint"], ev["uri"]))
        self.pending["tokens"].append({
            "mint": ev["mint"], "name": ev["name"], "symbol": ev["symbol"], "creator": ev["creator"],
            "uri": ev["uri"], "pool": ev["bonding_curve"], "launchpad": "pump-fun",
            "created_at": ev["ts"], "first_seen_at": t, "source": "chain"})

    def _on_trade(self, ev: dict) -> None:
        ms = self._state(ev["mint"])
        ts, sol, buy, user = ev["ts"], ev["sol"], ev["is_buy"], ev["user"]
        ms.creator = ms.creator or ev.get("creator")
        if not ev.get("sol_paired", True):
            ms.sol_paired, sol = False, 0.0         # amounts are in another token; count wallets only
        if (buy and ms.create_slot is not None and ev.get("slot") is not None
                and ev["slot"] <= ms.create_slot + 1 and user != ms.creator):
            ms.block_buyers.add(user)               # same block as the launch: bundled or sniped
            ms.block_tokens += ev["tokens"]
        ms.trades.append((ts, user, buy, sol))
        if ev["v_tokens"] and ms.sol_paired:
            ms.price = ev["v_sol"] / ev["v_tokens"]
        b = ms.hours.setdefault(ts // H * H, [0, 0, 0.0, 0.0, ms.price])
        if buy:
            b[0] += 1; b[2] += sol
        else:
            b[1] += 1; b[3] += sol
        if ev["v_tokens"] and ms.sol_paired:
            if not ms.price_hist or ts - ms.price_hist[-1][0] >= 300:
                ms.price_hist.append((ts, ms.price))
        ms.real_sol, ms.real_tokens = ev["real_sol"], ev["real_tokens"]
        ms.last_ts = max(ms.last_ts, ts)
        if buy and len(ms.early) < EARLY_N and user != ms.creator and user not in ms.early:
            ms.early.append(user)
            self.pending["early"].append({"mint": ms.mint, "wallet": user, "ts": ts, "sol": sol,
                                          "rank": len(ms.early)})
        if not buy and ms.creator and user == ms.creator:
            ms.dev_sold += sol
        ms.holdings[user] += ev["tokens"] if buy else -ev["tokens"]
        if ms.holdings[user] <= 1e-6:
            del ms.holdings[user]
        if ev["real_tokens"] == 0 and not ms.graduated:
            self._graduate(ms, ts)

    def near_complete(self, t: int, min_progress: float = 0.9) -> list[MintState]:
        """Curves close to completion. The completing transaction's logs are sometimes
        truncated by the RPC, so these are also checked directly (see check_curves)."""
        return [ms for ms in self.mints.values()
                if not ms.graduated and ms.real_tokens is not None and ms.last_ts > t - 6 * H
                and progress_from_real_tokens(ms.real_tokens, ms.init_tokens) >= min_progress]

    def _graduate(self, ms: MintState, ts: int) -> None:
        if ms.graduated:
            return
        ms.graduated = True
        self.grads.append({"mint": ms.mint, "name": ms.name, "symbol": ms.symbol, "ts": ts})
        self.pending["grads"].append({"mint": ms.mint, "detected_at": now(), "graduated_at": ts,
                                      "source": "chain", "pool": None})

    # ------------------------------------------------------------------ persistence
    def flush(self, con) -> int:
        """Write buffered launches, early buyers and graduations in one transaction."""
        p, self.pending = self.pending, {"tokens": [], "early": [], "grads": [], "pools": []}
        n = sum(len(v) for v in p.values())
        if not n:
            return 0
        con.execute("BEGIN")
        try:
            for r in p["tokens"]:
                insert(con, "tokens", r, or_ignore=True)
                # a token first seen via trades got a placeholder row; fill in what the launch says
                con.execute("""UPDATE tokens SET name=COALESCE(name,?), symbol=COALESCE(symbol,?),
                               creator=COALESCE(creator,?), pool=COALESCE(pool,?),
                               created_at=COALESCE(created_at,?) WHERE mint=?""",
                            (r["name"], r["symbol"], r["creator"], r["pool"], r["created_at"], r["mint"]))
            for r in p["early"]:
                insert(con, "early_buyers", r, or_ignore=True)
            for r in p["grads"]:
                insert(con, "graduations", r, or_ignore=True)
            for pool, mint in p["pools"]:
                con.execute("UPDATE graduations SET pool=? WHERE mint=? AND pool IS NULL", (pool, mint))
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        return n

    @staticmethod
    def top10(ms: MintState) -> float | None:
        """Top-10 wallets' share of supply. Only for tokens whose launch the stream saw."""
        if ms.create_slot is None:
            return None
        return round(sum(sorted(ms.holdings.values(), reverse=True)[:10]) / SUPPLY, 4)

    @staticmethod
    def dev_holds(ms: MintState) -> float | None:
        if ms.create_slot is None or not ms.creator:
            return None
        return round(ms.holdings.get(ms.creator, 0.0) / SUPPLY, 4)

    def bots(self, t: int) -> set[str]:
        seen: dict[str, set] = defaultdict(set)
        for ms in self.mints.values():
            for ts, w, _, _ in ms.trades:
                if ts > t - H:
                    seen[w].add(ms.mint)
        return {w for w, m in seen.items() if len(m) >= BOT_MINTS_PER_H}

    def window(self, ms: MintState, since: int, bots: set | None = None) -> dict:
        buyers, sellers = set(), set()
        buys = sells = 0
        bsol = ssol = 0.0
        for ts, w, buy, sol in reversed(ms.trades):
            if ts <= since:
                break
            if buy:
                buys += 1; bsol += sol; buyers.add(w)
            else:
                sells += 1; ssol += sol; sellers.add(w)
        out = {"buys": buys, "sells": sells, "buyers": len(buyers), "sellers": len(sellers),
               "buy_sol": bsol, "sell_sol": ssol, "smart": len(buyers & self.smart),
               "labelled": len(buyers & self.labels.smart), "insider": len(buyers & self.labels.insider)}
        if bots is not None:
            out["organic"] = len(buyers - bots)
        return out

    def snapshot(self, con, sol_usd: float | None, t: int | None = None) -> int:
        """token_obs + curve_obs rows for tokens with real activity since their last snapshot."""
        t = t or now()
        for ms in self.mints.values():
            while ms.trades and ms.trades[0][0] <= t - H:
                ms.trades.popleft()
            while ms.price_hist and ms.price_hist[0][0] < t - 2 * H:
                ms.price_hist.popleft()
        bots = self.bots(t)
        usd = (lambda x: x * sol_usd) if sol_usd else (lambda x: None)
        n = 0
        con.execute("BEGIN")
        try:
            for ms in list(self.mints.values()):
                if ms.last_ts <= ms.snap_ts or not ms.trades:
                    continue
                h1 = self.window(ms, t - H, bots)
                if h1["buyers"] < MIN_BUYERS_TO_SNAPSHOT:
                    continue
                m5 = self.window(ms, t - 300)
                hrs = {h: v for h, v in ms.hours.items() if h > t - 25 * H}
                ms.hours = hrs
                def vol(hours):
                    return sum(v[2] + v[3] for h, v in hrs.items() if h >= t - hours * H)
                old = next((p for ts, p in ms.price_hist if ts >= t - H - 300), None)
                first24 = next((v[4] for h, v in sorted(hrs.items()) if h >= t - 24 * H and v[4]), None)
                if not one(con, "SELECT 1 AS x FROM tokens WHERE mint=?", (ms.mint,)):
                    insert(con, "tokens", {"mint": ms.mint, "name": ms.name, "symbol": ms.symbol,
                                           "creator": ms.creator, "uri": None, "pool": None,
                                           "launchpad": "pump-fun", "created_at": ms.created_at,
                                           "first_seen_at": t, "source": "chain_trade"}, or_ignore=True)
                usd_t = usd if ms.sol_paired else (lambda x: None)
                sol_t = (lambda x: round(x, 4)) if ms.sol_paired else (lambda x: None)
                price_usd = usd_t(ms.price) if ms.price else None
                insert(con, "token_obs", {
                    "mint": ms.mint, "observed_at": t, "source": "chain", "dex": "pump-fun", "pool": None,
                    "price_usd": price_usd, "mcap_usd": price_usd * SUPPLY if price_usd else None,
                    "liquidity_usd": usd_t(ms.real_sol) if ms.real_sol is not None else None,
                    "vol_m5": usd_t(m5["buy_sol"] + m5["sell_sol"]),
                    "vol_h1": usd_t(h1["buy_sol"] + h1["sell_sol"]), "vol_h6": usd_t(vol(6)), "vol_h24": usd_t(vol(24)),
                    "buys_h1": h1["buys"], "sells_h1": h1["sells"],
                    "buyers_h1": h1["buyers"], "sellers_h1": h1["sellers"],
                    "buys_h24": sum(v[0] for v in hrs.values()), "sells_h24": sum(v[1] for v in hrs.values()),
                    "chg_h1": round((ms.price / old - 1) * 100, 2) if old and ms.price else None,
                    "chg_h24": round((ms.price / first24 - 1) * 100, 2) if first24 and ms.price else None,
                    "buy_vol_h1": usd_t(h1["buy_sol"]), "sell_vol_h1": usd_t(h1["sell_sol"]),
                    "net_sol_h1": sol_t(h1["buy_sol"] - h1["sell_sol"]),
                    "organic_buyers_h1": h1["organic"], "smart_buyers_h1": h1["smart"],
                    "labelled_buyers_h1": h1["labelled"], "insider_buyers_h1": h1["insider"],
                    "dev_sold_sol": sol_t(ms.dev_sold),
                    "launch_block_buyers": len(ms.block_buyers) if ms.create_slot is not None else None,
                    "launch_block_pct": round(ms.block_tokens / SUPPLY, 4) if ms.create_slot is not None else None,
                    "top10_pct": self.top10(ms), "dev_holds_pct": self.dev_holds(ms),
                    "sol_paired": int(ms.sol_paired)})
                if ms.real_tokens is not None:
                    insert(con, "curve_obs", {
                        "mint": ms.mint, "observed_at": t, "real_sol": ms.real_sol,
                        "real_token_reserves": ms.real_tokens, "complete": int(ms.graduated),
                        "progress": progress_from_real_tokens(ms.real_tokens, ms.init_tokens), "price_sol": ms.price})
                ms.snap_ts = t
                n += 1
            self._market_stats(con, t)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        # forget tokens with no trades for a day
        for mint in [m for m, ms in self.mints.items() if ms.last_ts < t - 24 * H and (ms.created_at or 0) < t - 24 * H]:
            del self.mints[mint]
        for k in [k for k in self.launch_minutes if k < t - 3 * H]:
            del self.launch_minutes[k]
        for d in (self.names, self.creators):
            for k in [k for k, v in d.items() if not v or (v[-1][0] if isinstance(v[-1], tuple) else v[-1]) < t - 86400]:
                del d[k]
        return n

    def _market_stats(self, con, t: int, top: int = 80) -> None:
        """The most-traded bonding-curve tokens of the last 24h: how have they moved, and how
        many are under a day old (rotation into new launches)? Feeds analytics/market.py."""
        act = []
        for ms in self.mints.values():
            hrs = sorted((h, v) for h, v in ms.hours.items() if h >= t - 24 * H)
            if not hrs or ms.graduated or not ms.price:
                continue
            vol = sum(v[2] + v[3] for _, v in hrs)
            first = next((v[4] for _, v in hrs if v[4]), None)
            act.append((vol, ms, (ms.price / first - 1) if first else None))
        act = sorted(act, key=lambda a: a[0], reverse=True)[:top]
        if len(act) < 20:
            return
        chg = sorted(c * 100 for _, _, c in act if c is not None)
        young = sum(1 for _, ms, _ in act if ms.created_at and ms.created_at > t - 24 * H)
        sol = one(con, "SELECT value FROM market_obs WHERE metric='sol_price_usd' ORDER BY id DESC LIMIT 1")
        for metric, value in (("active_median_chg_h24", chg[len(chg) // 2] if chg else None),
                              ("active_share_under_24h", young / len(act)),
                              ("active_top80_vol_h24", sum(a[0] for a in act) * sol["value"] if sol else None)):
            if value is not None:
                insert(con, "market_obs", {"observed_at": t, "metric": metric, "value": value, "source": "chain",
                                           "detail": f"n={len(act)}"})

    def refresh_smart(self, con, t: int | None = None) -> int:
        t = t or now()
        found = rows(con, """
            SELECT e.wallet, COUNT(*) AS n, SUM(g.mint IS NOT NULL) AS g
            FROM early_buyers e LEFT JOIN graduations g ON g.mint = e.mint AND g.detected_at <= ?
            WHERE e.ts > ? GROUP BY e.wallet HAVING g >= ?""", (t, t - SMART_LOOKBACK_S, SMART_MIN_GRADS))
        self.smart = {r["wallet"] for r in found if r["g"] / r["n"] >= SMART_MIN_HIT}
        self.smart_computed_at = t
        return len(self.smart)

    def source_posts(self, con, t: int, window_s: int = 3 * H, top: int = 10) -> list[dict]:
        """X posts that launches link to, ranked by launches; with live buying in those coins."""
        found = rows(con, """SELECT x_post, COUNT(*) AS launches, COUNT(DISTINCT creator) AS creators,
                                    MIN(created_at) AS first_at, MAX(created_at) AS last_at,
                                    GROUP_CONCAT(mint) AS mints
                             FROM tokens WHERE x_post IS NOT NULL AND created_at > ?
                             GROUP BY x_post HAVING launches >= 2
                             ORDER BY launches DESC, last_at DESC LIMIT ?""", (t - window_s, top))
        for p in found:
            mints = p.pop("mints").split(",")
            buyers = set()
            net = 0.0
            for m in mints:
                ms = self.mints.get(m)
                if ms:
                    for ts, w, buy, sol in ms.trades:
                        if ts > t - H:
                            if buy:
                                buyers.add(w); net += sol
                            else:
                                net -= sol
            p.update(buyers_1h=len(buyers), net_sol_1h=round(net, 2),
                     account=p["x_post"].split("/", 1)[0], url="https://x.com/" + p["x_post"])
        return found

    # ------------------------------------------------------------------ live view
    def view(self, t: float | None = None, top: int = 20) -> dict:
        t = int(t or time.time())
        hot = []
        for ms in self.mints.values():
            if ms.last_ts <= t - 300 or ms.graduated and ms.last_ts <= t - 60:
                continue
            w = self.window(ms, t - 300)
            if w["buyers"] < 3:
                continue
            hot.append({"mint": ms.mint, "name": ms.name, "symbol": ms.symbol,
                        "age_s": t - ms.created_at if ms.created_at else None,
                        "buyers_5m": w["buyers"], "sellers_5m": w["sellers"], "buys_5m": w["buys"],
                        "sells_5m": w["sells"],
                        "net_sol_5m": round(w["buy_sol"] - w["sell_sol"], 3) if ms.sol_paired else None,
                        "vol_sol_5m": round(w["buy_sol"] + w["sell_sol"], 3) if ms.sol_paired else None,
                        "smart_5m": w["smart"], "labelled_5m": w["labelled"], "insider_5m": w["insider"],
                        "launch_block_buyers": len(ms.block_buyers) if ms.create_slot is not None else None,
                        "launch_block_pct": round(ms.block_tokens / SUPPLY, 3) if ms.create_slot is not None else None,
                        "top10_pct": self.top10(ms), "dev_holds_pct": self.dev_holds(ms),
                        "sol_paired": ms.sol_paired,
                        "progress": progress_from_real_tokens(ms.real_tokens, ms.init_tokens) if ms.real_tokens is not None else None,
                        "real_sol": ms.real_sol, "dev_sold_sol": round(ms.dev_sold, 3),
                        "graduated": ms.graduated})
        hot.sort(key=lambda h: (h["smart_5m"] + h["labelled_5m"], h["buyers_5m"], h["net_sol_5m"] or 0), reverse=True)
        tape = []
        for launch in list(self.launches)[-30:][::-1]:
            ms = self.mints.get(launch["mint"])
            tape.append({**launch, "launch_block_buyers": len(ms.block_buyers) if ms else None,
                         "launch_block_pct": round(ms.block_tokens / SUPPLY, 3) if ms else None})
        mins = [[m, self.launch_minutes.get(m, 0)] for m in range((t // 60 - 59) * 60, (t // 60 + 1) * 60, 60)]
        return {
            "now": t,
            # the public RPC drops the socket every 10-30s and it reconnects in ~1s; only a
            # gap longer than 10s is reported as disconnected
            "stream": {"connected": self.connected or (self.down_since is not None and t - self.down_since < 10),
                       "since": self.connected_since, "reconnecting": not self.connected,
                       "lag_s": round(self.lag_s, 1) if self.lag_s is not None else None,
                       "last_event_age_s": round(t - self.last_event_at, 1) if self.last_event_at else None,
                       "error": None if self.connected or (self.down_since and t - self.down_since < 10) else self.last_error,
                       "smart_wallets": len(self.smart), "labelled_wallets": len(self.labels.smart),
                       "insider_wallets": len(self.labels.insider), "endpoint": self.endpoint,
                       "tokens_in_memory": len(self.mints)},
            "launches_per_min": mins,
            "launches": tape,
            "hot": hot[:top],
            "graduations": list(self.grads)[-12:][::-1],
        }


LIVE = Live()


# Free public websockets that serve logsSubscribe without a key (checked 2026-10-21).
# mainnet-beta closes the socket every 10-30s but has always delivered; publicnode sometimes
# acknowledges the subscription and then sends nothing, so it is the fallback.
PUBLIC_WS = ("wss://api.mainnet-beta.solana.com", "wss://solana-rpc.publicnode.com")


def ws_urls(settings) -> list[str]:
    """Your own endpoint first when configured, then the free public ones as fallbacks."""
    from .config import DEFAULT_RPC
    own = settings.solana_ws_url
    u = settings.solana_rpc_url
    if not own and u and u != DEFAULT_RPC:
        own = "wss://" + u.split("://", 1)[1] if u.startswith("https://") else u.replace("http://", "ws://", 1)
    return ([own] if own else []) + [w for w in PUBLIC_WS if w != own]


async def run_stream(ctx, live: Live = LIVE) -> None:
    """Keep one subscription alive forever. The free public RPC closes websockets every
    10-30s, so a connection that lived a while is reopened at once; only repeated quick
    failures back off. 60s of silence counts as a dead connection (pump.fun never goes a
    minute without a trade)."""
    import websockets
    urls, k = ws_urls(ctx.s), 0
    sub = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                      "params": [{"mentions": [PUMP_PROGRAM]}, {"commitment": "confirmed"}]})
    backoff, fails = 1.0, 0
    while True:
        opened, events_before = time.time(), live.total_events
        url = urls[k % len(urls)]
        live.endpoint = url.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
        try:
            async with websockets.connect(url, open_timeout=20, ping_interval=20, ping_timeout=30,
                                          max_size=2 ** 23, max_queue=8192) as ws:
                await ws.send(sub)
                ack = json.loads(await asyncio.wait_for(ws.recv(), 20))
                if "error" in ack:
                    raise SourceUnavailable(f"subscribe refused: {ack['error']}")
                if not live.connected_since:
                    log.info("live chain stream connected")
                live.set_connected(True)
                live.last_error = None
                while True:
                    live.on_raw(await asyncio.wait_for(ws.recv(), 30))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # network drop, RPC limit, server close: always reconnect
            live.set_connected(False)
            live.last_error = ctx.s.redact(f"{type(exc).__name__}: {exc}")[:300]
            if live.total_events == events_before:
                live.last_error = f"{live.endpoint} sent no events ({live.last_error})"
            elif time.time() - opened > 10:
                backoff, fails = 1.0, 0
                await asyncio.sleep(0.2)
                continue
            fails += 1
            k += 1                                   # quick failure: try the next endpoint
            if fails == 3:
                log.warning("live chain stream can't stay connected (%s); retrying with backoff", live.last_error)
            await asyncio.sleep(backoff)
            backoff = min(60.0, backoff * 2)


async def check_curves(ctx, live: Live) -> int:
    """Read the on-chain `complete` flag of curves above 90% (one batched RPC call)."""
    from .sources import solana_rpc
    cands = live.near_complete(now())
    if not cands:
        return 0
    pools = {ms.mint: ms.pool for ms in cands if ms.pool}
    missing = [ms.mint for ms in cands if not ms.pool]
    if missing:
        qs = ",".join("?" * len(missing))
        pools.update({r["mint"]: r["pool"] for r in rows(
            ctx.con, f"SELECT mint, pool FROM tokens WHERE pool IS NOT NULL AND mint IN ({qs})", tuple(missing))})
    curves = await solana_rpc.bonding_curves(ctx.http, ctx.s.solana_rpc_url, pools)
    n = 0
    for mint, c in curves.items():
        if c.get("complete"):
            live._graduate(live.mints[mint], now())
            n += 1
    return n


async def fill_names(ctx, live: Live, limit: int = 60) -> int:
    """Names for active tokens launched before the stream started (one DexScreener call per 30)."""
    from .sources import misc
    todo = [ms for ms in live.mints.values() if ms.name is None and ms.snap_ts]
    todo = sorted(todo, key=lambda ms: ms.last_ts, reverse=True)[:limit]
    if not todo:
        return 0
    qs = ",".join("?" * len(todo))
    known = {r["mint"]: r for r in rows(ctx.con, f"SELECT mint, name, symbol, created_at, creator FROM tokens "
                                                 f"WHERE name IS NOT NULL AND mint IN ({qs})", tuple(ms.mint for ms in todo))}
    for ms in todo:
        if ms.mint in known:
            k = known[ms.mint]
            ms.name, ms.symbol = k["name"], k["symbol"]
            ms.created_at = ms.created_at or k["created_at"]
    todo = [ms for ms in todo if ms.mint not in known]
    if not todo:
        return 0
    found = await misc.dexscreener_names(ctx.http, [ms.mint for ms in todo])
    for ms in todo:
        name, symbol = found.get(ms.mint, ("", ""))   # "" = looked up, unknown; not retried
        ms.name, ms.symbol = name, symbol or None
        if name:
            ctx.con.execute("UPDATE tokens SET name=COALESCE(name,?), symbol=COALESCE(symbol,?) WHERE mint=?",
                            (name, symbol, ms.mint))
    return len(found)


async def track_pools(ctx, window_s: int = 48 * H) -> int:
    """Price of recently graduated tokens on their PumpSwap pool (2-4 batched RPC calls)."""
    from .sources import solana_rpc
    due = {r["mint"]: r["pool"] for r in rows(ctx.con, """SELECT mint, pool FROM graduations
            WHERE pool IS NOT NULL AND COALESCE(graduated_at, detected_at) > ?""", (now() - window_s,))}
    if not due:
        return 0
    prices = await solana_rpc.pumpswap_prices(ctx.http, ctx.s.solana_rpc_url, due)
    t = now()
    ctx.con.execute("BEGIN")
    for mint, p in prices.items():
        insert(ctx.con, "pool_obs", {"mint": mint, "observed_at": t, **p})
    ctx.con.execute("COMMIT")
    return len(prices)


async def run_maintenance(ctx, live: Live = LIVE, snapshot_every_s: int = 120) -> None:
    """Flush buffered writes every 5s, record a heartbeat every 60s, snapshot activity,
    refresh the smart-wallet set every 30 min, prune raw tables daily."""
    last_beat = last_snap = last_smart = last_prune = last_curves = last_pools = time.time()
    await asyncio.sleep(5)
    while True:
        try:
            live.flush(ctx.con)
            t = time.time()
            if t - last_beat >= 60:
                last_beat = t
                events, up_s, reconnects = live.take_window()
                # launch coverage reads this: the share of the minute the stream was listening
                insert(ctx.con, "market_obs", {"observed_at": now(), "metric": "stream_connected_s",
                                               "value": round(min(60.0, up_s), 1), "source": "chain",
                                               "detail": f"reconnects={reconnects}"})
                async with record_run(ctx.con, ctx.s, "chain", "pump_stream") as run:
                    run.items = events
                    if up_s < 30 or not events:
                        raise SourceUnavailable(live.last_error or "no events in the last minute")
            if t - last_smart >= 1800 or not live.smart_computed_at:
                last_smart = t
                n = live.refresh_smart(ctx.con)
                log.info("smart wallets: %d with a proven early-entry record", n)
            if t - last_snap >= snapshot_every_s:
                last_snap = t
                sol = one(ctx.con, "SELECT value FROM market_obs WHERE metric='sol_price_usd' "
                                   "AND observed_at > ? ORDER BY id DESC LIMIT 1", (now() - 3 * H,))
                async with record_run(ctx.con, ctx.s, "chain", "snapshot") as run:
                    run.items = live.snapshot(ctx.con, sol["value"] if sol else None)
            if t - last_curves >= 120:
                last_curves = t
                try:
                    await fill_names(ctx, live)
                except SourceUnavailable as exc:
                    log.debug("name lookup skipped: %s", exc)
                try:
                    await check_curves(ctx, live)
                except SourceUnavailable as exc:
                    log.debug("curve check skipped: %s", exc)
            if t - last_pools >= 600:
                last_pools = t
                async with record_run(ctx.con, ctx.s, "chain", "pumpswap_pools") as run:
                    run.items = await track_pools(ctx)
            if t - last_prune >= 86400:
                last_prune = t
                prune(ctx.con)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("stream maintenance failed; continuing")
        await asyncio.sleep(5)


async def run_metadata(ctx, live: Live = LIVE) -> None:
    """Fetch launch metadata (description, links, the X post a coin cites) in the background."""
    from . import metadata
    async with metadata.httpx.AsyncClient(headers={"User-Agent": "trench-radar/0.2 (+research)"},
                                          follow_redirects=True) as client:
        while True:
            batch = [live.meta_queue.popleft() for _ in range(min(24, len(live.meta_queue)))]
            if not batch:
                await asyncio.sleep(5)
                continue
            try:
                live.flush(ctx.con)                   # the token rows must exist before the UPDATE
                got = await metadata.fetch_many(client, batch)
                ctx.con.execute("BEGIN")
                for mint, m in got.items():
                    if m is None:
                        ctx.con.execute("UPDATE tokens SET meta_status='failed' WHERE mint=?", (mint,))
                        continue
                    ctx.con.execute("""UPDATE tokens SET description=?, twitter=?, website=?, telegram=?, image=?,
                                       x_post=?, x_account=?, meta_status='ok' WHERE mint=?""",
                                    (m["description"], m["twitter"], m["website"], m["telegram"], m["image"],
                                     m["x_post"], m["x_account"], mint))
                    if m["x_post"]:
                        live.x_posts[mint] = m["x_post"]
                ctx.con.execute("COMMIT")
            except asyncio.CancelledError:
                raise
            except Exception:
                if ctx.con.in_transaction:
                    ctx.con.execute("ROLLBACK")
                log.exception("metadata batch failed; continuing")
            await asyncio.sleep(1)


def prune(con, keep_obs_days: int = 21, keep_early_days: int = 30) -> None:
    t = now()
    con.execute("DELETE FROM token_obs WHERE source='chain' AND observed_at < ?", (t - keep_obs_days * 86400,))
    con.execute("DELETE FROM curve_obs WHERE observed_at < ?", (t - keep_obs_days * 86400,))
    con.execute("DELETE FROM pool_obs WHERE observed_at < ?", (t - keep_obs_days * 86400,))
    con.execute("DELETE FROM early_buyers WHERE ts < ?", (t - keep_early_days * 86400,))
