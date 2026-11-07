"""Launch-window features and the quantitative launch score (docs/RESEARCH_QUANT.md).

Every pump.fun launch the stream sees is described at fixed ages after launch (60 s and 300 s;
900 s records the 2x label) with the same definitions as the corpus research dataset
(scripts/quant_dataset.py), so the model fitted there can be applied here and, as live outcomes
mature, re-validated on this app's own data. Rows go to token_early.

Point in time: a token's row at age A uses only trades stamped at or before launch + A, launches
before the token's own launch, and outcomes that had matured before it.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path

from .db import insert, rows
from .text import token_terms

H = 3600
AGES = (60, 300, 900)
SCORED = (60, 300)
LAUNCH_PRICE = 30.0 / 1_073_000_191         # pump.fun curve start: 30 virtual SOL / 1.073B virtual tokens
CAPTURE_DELAY_S = 10                         # wait for late-arriving trades before closing a window
MODEL_PATH = Path(__file__).with_name("data") / "quant_model.json"


class Context:
    """Rolling, point-in-time state shared by all launches: the meta (term) windows, creators,
    matured outcomes for the cohort base rate and each meta's track record."""

    def __init__(self):
        self.terms: dict[str, deque] = defaultdict(deque)        # term -> (t, mint, creator, name) for 6 h
        self.all_1h: deque = deque()
        self.buyers60: dict[str, float] = {}                     # mint -> distinct buyers in the first 60 s
        self.pending: deque = deque()                            # (matures_at, mint, created_at, terms)
        self.hist: dict[str, deque] = defaultdict(deque)         # term -> (t, graduated, x2) for 7 days
        self.hist_sum: dict[str, list] = defaultdict(lambda: [0, 0, 0])
        self.glob: deque = deque(); self.gsum = [0, 0, 0]
        self.scored: dict[int, deque] = {A: deque() for A in SCORED}   # (matures_at, mint, created_at)
        self.base: dict[int, deque] = {A: deque() for A in SCORED}     # (t, y) matured, 24 h
        self.x2: dict[str, bool] = {}
        self.creators: dict[str, int] = Counter()
        self.creator_grads: dict[str, int] = Counter()

    def on_launch(self, mint: str, t: int, name, symbol, creator) -> list[str]:
        tl = token_terms(name, symbol)[:6]
        for w in tl:
            self.terms[w].append((t, mint, creator, (name or "").strip().lower()))
        self.all_1h.append(t)
        self.pending.append((t + H, mint, t, tl))
        return tl

    def mature(self, now_t: int, graduated_at) -> None:
        """Move launches whose 1 h outcome is now known into the track-record and base-rate tallies.
        graduated_at(mint) -> unix seconds or None."""
        while self.pending and self.pending[0][0] <= now_t:
            tm, mint, t0, tl = self.pending.popleft()
            ga = graduated_at(mint)
            g = int(ga is not None and ga <= t0 + H)
            xx = int(self.x2.pop(mint, False))
            for w in tl:
                self.hist[w].append((tm, g, xx)); s = self.hist_sum[w]; s[0] += 1; s[1] += g; s[2] += xx
            self.glob.append((tm, g, xx)); self.gsum[0] += 1; self.gsum[1] += g; self.gsum[2] += xx
        for A, q in self.scored.items():
            while q and q[0][0] <= now_t:
                tm, mint, t0 = q.popleft()
                ga = graduated_at(mint)
                self.base[A].append((tm, int(ga is not None and ga <= t0 + H)))
        while self.glob and self.glob[0][0] < now_t - 86400:
            _, g, xx = self.glob.popleft(); self.gsum[0] -= 1; self.gsum[1] -= g; self.gsum[2] -= xx
        for A, q in self.base.items():
            while q and q[0][0] < now_t - 86400:
                q.popleft()

    def meta(self, t0: int, tl: list[str], name: str | None) -> dict:
        while self.all_1h and self.all_1h[0] < t0 - H:
            self.all_1h.popleft()
        best, best_n = None, -1
        for w in tl:
            dq = self.terms[w]
            while dq and dq[0][0] < t0 - 6 * H:
                dq.popleft()
            hq = self.hist[w]
            while hq and hq[0][0] < t0 - 7 * 86400:
                _, g, xx = hq.popleft(); s = self.hist_sum[w]; s[0] -= 1; s[1] -= g; s[2] -= xx
            n = sum(1 for x in dq if x[0] < t0)
            if n > best_n:
                best, best_n = w, n
        out = {"meta_term": best, "all_launch_1h": len(self.all_1h),
               "base_grad_24h": self.gsum[1] / self.gsum[0] if self.gsum[0] else None,
               "base_x2_24h": self.gsum[2] / self.gsum[0] if self.gsum[0] else None}
        if best is None:
            return out
        dq = [x for x in self.terms[best] if x[0] < t0]
        in1h = [x for x in dq if x[0] >= t0 - H]
        n1, n6 = len(in1h), len(dq)
        base = (n6 - n1) / 5.0
        nm = (name or "").strip().lower()
        s = self.hist_sum[best]
        out.update({"m_launch_1h": n1, "m_launch_6h": n6, "m_accel_z": (n1 - base) / math.sqrt(base + 1),
                    "m_share_1h": n1 / max(1, len(self.all_1h)),
                    "m_creator_conc": 1 - len({x[2] for x in in1h}) / n1 if n1 else None,
                    "m_dup_share": sum(x[3] == nm for x in in1h) / n1 if n1 else None,
                    "m_buyers_1h": sum(self.buyers60.get(x[1], 0) for x in in1h if x[0] + 60 <= t0),
                    "m_hist_n": s[0], "m_hist_grad": s[1], "m_hist_x2": s[2]})
        return out

    def base_rate(self, A: int, prior=(0.5, 50)) -> tuple[float, int]:
        q = self.base[A]
        k, n = sum(y for _, y in q), len(q)
        return (k + prior[0]) / (n + prior[0] + prior[1]), n


def window_features(ms, A: int, live) -> dict:
    """Corpus definitions (scripts/quant_dataset.per_token_window) over trades at or before launch + A."""
    from .stream import NON_TRADERS
    t_end = ms.created_at + A
    tr = [x for x in ms.ew if x[0] <= t_end]
    n_tr = len(tr)
    buys = [x for x in tr if x[2]]
    buyers, sellers, wsol, bought, sold = set(), set(), Counter(), Counter(), Counter()
    snipers = set()
    buy_sol = sell_sol = 0.0
    creator_sold = False
    for ts, w, buy, sol, tok, _ in tr:
        human = w not in NON_TRADERS
        if buy:
            buy_sol += sol
            if human:
                buyers.add(w); wsol[w] += sol; bought[w] += tok
                if ts - ms.created_at <= 3:
                    snipers.add(w)
        else:
            sell_sol += sol
            if human:
                sellers.add(w); sold[w] += tok
            if ms.creator and w == ms.creator:
                creator_sold = True
    price = next((x[5] for x in reversed(tr) if x[5]), None)
    nb = len(buyers)
    firsts = [ms.ew_first[w] for w in buyers if w in ms.ew_first and ms.ew_first[w][0] <= t_end]
    proven = sum(1 for w in buyers if live.credit_count(w, t_end) >= 2)
    return {"n_trades": n_tr, "n_buys": len(buys), "n_sells": n_tr - len(buys), "buy_sol": buy_sol, "sell_sol": sell_sol,
            "uniq_buyers": nb, "uniq_sellers": len(sellers),
            "mcap_ratio": (price / LAUNCH_PRICE) if price else 1.0,
            "top_buyer_share": (max(wsol.values()) / buy_sol) if buy_sol > 0 and wsol else None,
            "snipers": len(snipers),
            "dumped_share": (sum(1 for w in buyers if bought[w] > 0 and sold[w] >= 0.9 * bought[w]) / nb) if nb else None,
            "creator_sold": int(creator_sold),
            "serial_share": (sum(1 for _, c in firsts if c >= 10) / len(firsts)) if firsts else None,
            "proven_buyers": proven, "max_price": max((x[5] for x in tr if x[5]), default=None)}


# ---------------------------------------------------------------- model
class Model:
    """The fitted model shipped in radar/data/quant_model.json (see scripts/quant_fit.py)."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.version = spec["version"]
        self.age = spec["age_s"]
        self.names = spec["features"]
        self.med, self.mu, self.sd = spec["median"], spec["mean"], spec["sd"]
        self.ind = spec["missing_indicators"]
        self.b = spec["coef"]

    @classmethod
    def load(cls) -> "Model | None":
        try:
            return cls(json.loads(MODEL_PATH.read_text()))
        except (OSError, ValueError, KeyError):
            return None

    def predict(self, x: dict) -> float:
        vals = [x.get(k) for k in self.names]
        filled = [self.med[j] if v is None or (isinstance(v, float) and math.isnan(v)) else v for j, v in enumerate(vals)]
        filled += [1.0 if vals[j] is None or (isinstance(vals[j], float) and math.isnan(vals[j])) else 0.0 for j in self.ind]
        z = self.b[0] + sum(bj * (v - m) / s for bj, v, m, s in zip(self.b[1:], filled, self.mu, self.sd))
        return 1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, z))))


def model_inputs(raw: dict, ctx_meta: dict, creator: dict, base_rate: float, k: float, mayhem, cashback,
                 kx: float | None = None) -> dict:
    """Transform raw counts into the model's inputs (scripts/quant_validate.features)."""
    lg = math.log1p
    slog = lambda v: math.copysign(math.log1p(abs(v)), v)  # noqa: E731
    nt = raw["n_trades"]
    p0 = min(max(ctx_meta.get("base_grad_24h") or 0.005, 1e-4), 0.9)
    s, n = ctx_meta.get("m_hist_grad") or 0, ctx_meta.get("m_hist_n") or 0
    shr = (s + k * p0) / (n + k)
    px0 = min(max(ctx_meta.get("base_x2_24h") or 0.05, 1e-4), 0.9)
    sx = ctx_meta.get("m_hist_x2") or 0
    kx = k if kx is None else kx
    shx = (sx + kx * px0) / (n + kx)
    br = min(max(base_rate, 1e-6), 1 - 1e-6)
    return {
        "buyers": lg(raw["uniq_buyers"]), "sellers": lg(raw["uniq_sellers"]), "trades": lg(nt),
        "buy_share": raw["n_buys"] / nt if nt else None, "buy_sol": lg(raw["buy_sol"]),
        "net_sol": slog(raw["buy_sol"] - raw["sell_sol"]), "mcap_ratio": math.log(raw["mcap_ratio"]),
        "top_buyer_share": raw["top_buyer_share"], "snipers": lg(raw["snipers"]), "dumped_share": raw["dumped_share"],
        "creator_sold": raw["creator_sold"], "serial_share": raw["serial_share"], "proven": lg(raw["proven_buyers"]),
        "mayhem": float(bool(mayhem)), "cashback": float(bool(cashback)),
        "c_prior": lg(creator["prior"]), "c_24h": lg(creator["24h"]), "c_grads": lg(creator["grads"]),
        "m_launch_1h": lg(ctx_meta["m_launch_1h"]) if "m_launch_1h" in ctx_meta else None,
        "m_accel_z": min(max(ctx_meta["m_accel_z"], -5), 20) if "m_accel_z" in ctx_meta else None,
        "m_share": lg(1000 * ctx_meta["m_share_1h"]) if "m_share_1h" in ctx_meta else None,
        "m_creator_conc": ctx_meta.get("m_creator_conc"), "m_dup_share": ctx_meta.get("m_dup_share"),
        "m_buyers_1h": lg(ctx_meta["m_buyers_1h"]) if "m_buyers_1h" in ctx_meta else None,
        "m_hist_n": lg(n), "m_hist_lift": math.log(shr / p0), "m_hist_x2_lift": math.log(shx / px0),
        "base_logit": math.log(br / (1 - br)),
    }


def capture(con, live, now_t: int, model: "Model | None") -> int:
    """Close every window that has ended; write token_early rows and update the context."""
    from .stream import MintState  # noqa: F401  (type of live.mints values)
    ctx = live.early_ctx
    ctx.mature(now_t, live.graduated_at)
    n = 0
    for ms in list(live.mints.values()):
        if ms.created_at is None or ms.ew is None:
            continue
        for A in AGES:
            if A in ms.captured or now_t < ms.created_at + A + CAPTURE_DELAY_S:
                continue
            ms.captured.add(A)
            if ms.graduated and ms.graduated_ts is not None and ms.graduated_ts <= ms.created_at + A:
                if A == 900:
                    ms.ew = None
                continue                                  # graduated before this age: not a candidate
            raw = window_features(ms, A, live)
            if A == 60:
                ctx.buyers60[ms.mint] = raw["uniq_buyers"]
            if A == 900:
                ctx.x2[ms.mint] = bool(raw["max_price"] and raw["max_price"] >= 2 * LAUNCH_PRICE)
                ms.ew = None                              # window history no longer needed
                insert(con, "token_early", {"mint": ms.mint, "age_s": A, "observed_at": now_t, "launched_at": ms.created_at,
                                            "features": json.dumps(raw), "source": live.source}, or_ignore=True)
                n += 1
                continue
            meta = ctx.meta(ms.created_at, ms.terms or [], ms.name)
            creator = live.creator_history(con, ms.creator, ms.created_at)
            base, nbase = ctx.base_rate(A)
            row = {"mint": ms.mint, "age_s": A, "observed_at": now_t, "launched_at": ms.created_at, "source": live.source}
            p = None
            if model is not None and model.age == A:
                x = model_inputs(raw, meta, creator, base, model.spec.get("shrink_k", 50.0), ms.mayhem, ms.cashback,
                                 model.spec.get("shrink_k_x2"))
                p = model.predict(x)
                row.update({"model": model.version, "p_grad": round(p, 6),
                            "calibrated": int(nbase >= model.spec.get("min_base_n", 2000))})
            row["features"] = json.dumps({**raw, **meta, "creator": creator, "base_rate": base, "base_n": nbase,
                                          "mayhem": ms.mayhem, "cashback": ms.cashback})
            insert(con, "token_early", row, or_ignore=True)
            if A in SCORED:
                ctx.scored[A].append((ms.created_at + H, ms.mint, ms.created_at))
            n += 1
    return n


def latest(con, mint: str) -> list[dict]:
    out = rows(con, "SELECT age_s, observed_at, model, p_grad, calibrated, features FROM token_early WHERE mint=? ORDER BY age_s", (mint,))
    for r in out:
        try:
            r["features"] = json.loads(r["features"])
        except (TypeError, ValueError):
            r["features"] = {}
    return out


_CARD: dict | None = None


def model_card() -> dict | None:
    """What the shipped model predicts, what it was fitted on and how it validated (for the UI)."""
    global _CARD
    if _CARD is None:
        try:
            spec = json.loads(MODEL_PATH.read_text())
        except (OSError, ValueError):
            return None
        _CARD = {k: spec.get(k) for k in ("version", "target", "age_s", "trained_on", "walk_forward", "note", "min_base_n")}
    return _CARD
