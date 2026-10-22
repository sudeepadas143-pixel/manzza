"""Meta-level research dataset: what the app knew about each meta at a decision time, and what
the meta's next launches did.

Decision time T (hourly). At T the app's own pipeline runs unchanged (scoring.run_analysis with
as_of=T, which raises on any read newer than T) and every meta it detects is recorded with its
evidence and the current readiness score. To that are added, point-in-time:

  * history: the meta's earlier launches whose 1 h outcome was known by T (launched <= T - 1 h),
    from June 19 on (no token graduated June 5-17, so earlier outcomes are unusable), weighted by
    a 48 h half-life and over 7 days without decay; factory creators (10+ launches in the 7 h
    before their launch, as metas.SPAM_MODE) left out;
  * the same sums over all launches, for the base rate.

Outcome: every launch whose name/ticker shares a term with the meta (the backtest's matching)
in (T, T + 6 h]: graduated within 1 h of launch, 2x within 15 min (peak trade market cap vs
launch), and, for launches still on the curve at 60 s, the walk-forward out-of-sample
probability from the token model (scripts/quant_validate.py `token_only`), so the meta can be
tested after controlling for its coins' first minute. Steps whose lookback or outcome window
touches a collection gap or the July 2-5 break are skipped, as in `corpus-backtest`.

Usage: python scripts/meta_dataset.py RESEARCH.db --corpus CORPUS_DIR --quant QUANT_DATASET.npz --out meta.npz
       python scripts/meta_dataset.py SHRINE_REPLAY.db --out meta.npz     (graduation only, no 2x or
       token-model control; for an out-of-period check)
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import quant_validate as V  # noqa: E402
from radar import corpus  # noqa: E402
from radar.__main__ import CORPUS_GAPS  # noqa: E402
from radar.analytics import quant as Q  # noqa: E402
from radar.analytics.meta_model import raw  # noqa: E402
from radar.analytics.scoring import run_analysis  # noqa: E402
from radar.db import connect  # noqa: E402
from radar.text import token_terms  # noqa: E402

H = 3600
JUN19 = 1781827200
FOLLOW = 6 * H
HALF_LIFE = 48 * H
HIST_S = 7 * 86400
FACTORY_N, FACTORY_S = 10, 7 * H


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def token_oos(D, A=60, lam=100.0, min_days=6):
    """Walk-forward out-of-sample P(graduate within 1 h | on the curve at A) for every eligible
    token, trained only on earlier days (1 h embargo). NaN where no prediction exists."""
    F = V.features(D, A)
    t0, day, g = D["t0"], (D["t0"] // 86400).astype(int), D["grad_s"]
    idx = np.where((t0 >= JUN19) & (D["gap"] == 0) & ~(g <= A))[0]
    y = np.zeros(len(t0)); y[idx] = g[idx] <= H
    F["base_logit"] = Q.logit(np.nan_to_num(V.trailing_rate(t0, y, idx, H), nan=0.01))
    cols = V.SPECS["token_only"]
    p = np.full(len(t0), np.nan)
    days = np.unique(day[idx])
    for d in days[min_days:]:
        tr = idx[t0[idx] < d * 86400 - H]
        te = idx[day[idx] == d]
        p[te], _, _ = V.fit_predict(F, cols, y, tr, te, lam)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db", type=Path)
    ap.add_argument("--corpus", type=Path)
    ap.add_argument("--quant", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--step-hours", type=float, default=1.0)
    a = ap.parse_args()

    con = connect(a.db)
    if a.quant:
        D = dict(np.load(a.quant))
        t0 = D["t0"]
        n = len(t0)
        tk = pq.read_table(a.corpus / "tokens.parquet", columns=["mint", "name", "symbol", "creator"])
        assert tk.num_rows == n
        names, syms, creators = (tk[c].to_pylist() for c in ("name", "symbol", "creator"))
        log("token model, walk-forward")
        p_tok = token_oos(D)
        grad_s = D["grad_s"]
        x2 = D["x2_15m"] == 1
        exclude = CORPUS_GAPS + corpus.gaps(con)
        first_outcome = JUN19
    else:   # a replay database: launches and graduations only
        R = con.execute("""SELECT k.name, k.symbol, k.creator, k.created_at, MIN(g.graduated_at) - k.created_at
                           FROM tokens k LEFT JOIN graduations g ON g.mint = k.mint
                           WHERE k.created_at IS NOT NULL AND k.source = 'shrine_replay'
                           GROUP BY k.mint ORDER BY k.created_at""").fetchall()
        names, syms, creators = [r[0] for r in R], [r[1] for r in R], [r[2] for r in R]
        t0 = np.array([r[3] for r in R], float)
        grad_s = np.array([np.nan if r[4] is None else r[4] for r in R], float)
        n = len(t0)
        p_tok = np.full(n, np.nan)
        x2 = np.zeros(n, bool)
        exclude = []
        first_outcome = int(t0.min())
    grad = np.isfinite(grad_s) & (grad_s <= H) & (grad_s >= 0)
    instant = np.isfinite(grad_s) & (grad_s <= 60)
    # factory creators, point in time: 10+ launches (this one included) in the 7 h before
    factory = np.zeros(n, bool)
    order = np.lexsort((t0, np.array([hash(c) for c in creators])))
    cs = [creators[i] for i in order]
    ts = t0[order]
    lo = 0
    for j in range(n):
        if j and cs[j] != cs[j - 1]:
            lo = j
        while ts[lo] < ts[j] - FACTORY_S:
            lo += 1
        factory[order[j]] = (j - lo + 1) >= FACTORY_N and cs[j] is not None
    log("factory launches", int(factory.sum()))
    # term index: term -> token indices sorted by launch time
    by_t = np.argsort(t0, kind="stable")
    index: dict[str, list[int]] = {}
    for i in by_t:
        for w in set(token_terms(names[i], syms[i])):
            index.setdefault(w, []).append(int(i))
    index = {w: np.array(v) for w, v in index.items()}
    tsorted = t0[by_t]
    log("terms", len(index))

    def members(terms, lo_t, hi_t):
        parts = []
        for w in terms:
            ix = index.get(w)
            if ix is None:
                continue
            tt = t0[ix]
            parts.append(ix[np.searchsorted(tt, lo_t, "right"):np.searchsorted(tt, hi_t, "right")])
        return np.unique(np.concatenate(parts)) if parts else np.zeros(0, int)

    def span(lo_t, hi_t):
        return by_t[np.searchsorted(tsorted, lo_t, "right"):np.searchsorted(tsorted, hi_t, "right")]

    def hist(ix, T):
        ix = ix[~factory[ix]]
        age = T - t0[ix]
        w = 0.5 ** (age / HALF_LIFE)
        return {"n_w": float(w.sum()), "k_w": float((w * grad[ix]).sum()), "x2_w": float((w * x2[ix]).sum()),
                "n": int(len(ix)), "k": int(grad[ix].sum()), "x2": int(x2[ix].sum())}

    def outcome(ix):
        nf = ix[~factory[ix]]
        el = ix[~instant[ix] & np.isfinite(p_tok[ix])]
        return {"n": int(len(ix)), "k": int(grad[ix].sum()), "x2": int(x2[ix].sum()), "inst": int(instant[ix].sum()),
                "n_nf": int(len(nf)), "k_nf": int(grad[nf].sum()),
                "n_el": int(len(el)), "k_el": int(grad[el].sum()), "p_el": float(p_tok[el].sum())}

    start, end = first_outcome + 7 * H, int(t0.max()) - FOLLOW - H
    rows_out, steps, skipped = [], 0, 0
    for T in range(start, end, int(a.step_hours * H)):
        if any(x < T + FOLLOW + H and T - 7 * H < y for x, y in exclude):
            skipped += 1
            continue
        res = run_analysis(con, T, persist=False, max_metas=10_000)
        assert res["lineage"]["max_ts"] <= T
        steps += 1
        hlo = max(T - HIST_S, first_outcome)
        g_hist = hist(span(hlo, T - H), T)
        g_out = outcome(span(T, T + FOLLOW))
        for m in res["metas"]:
            fut = members(m["terms"], T, T + FOLLOW)
            past = members(m["terms"], hlo, T - H)
            rows_out.append({"T": T, "meta": m["meta_key"], "terms": m["terms"], **raw(m, res["market"]),
                             **{f"h_{k}": v for k, v in hist(past, T).items()},
                             **{f"gh_{k}": v for k, v in g_hist.items()},
                             **{f"y_{k}": v for k, v in outcome(fut).items()},
                             **{f"gy_{k}": v for k, v in g_out.items()}})
        if steps % 50 == 0:
            log("steps", steps, "rows", len(rows_out), time.strftime("%m-%d %H:%M", time.gmtime(T)))
    log("done: steps", steps, "skipped", skipped, "rows", len(rows_out))
    keys = [k for k in rows_out[0] if k not in ("terms",)]
    out = {}
    for k in keys:
        vals = [r[k] for r in rows_out]
        if k in ("meta", "verdict"):
            out[k] = np.array([str(v) for v in vals])
        else:
            out[k] = np.array([np.nan if v is None else float(v) for v in vals])
    out["terms"] = np.array([json.dumps(r["terms"]) for r in rows_out])
    np.savez_compressed(a.out, **out)
    log("saved", a.out)


if __name__ == "__main__":
    main()
