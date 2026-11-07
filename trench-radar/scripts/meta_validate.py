"""Walk-forward comparison of meta recommendation models (scripts/meta_dataset.py output).

Decision: at time T, which meta to launch into. Outcome: the graduation (within 1 h) of the
meta's launches in (T, T + 6 h]. Every model predicts the meta's *lift*: its log-odds against
all launches in the same window (the realised all-launch rate is the offset; it is common to
every choice at T, so it shifts no ranking). A meta-step is a binomial row (k of n).

Models, all fitted only on days before the test day (rows whose outcome window ends before the
test day starts), L2 strength chosen once on an inner split of the first fold:

  null          lift 0: any meta is as good as the market
  existing      the app's readiness score (logistic recalibration of score, so its ranking is kept)
  favorable     the app's verdict == favorable
  accelerating  launch acceleration z >= 2 (the RESEARCH_TUNING.md signal)
  popularity    launches in 6 h
  momentum / demand / saturation / history       each group alone
  full_nohist   momentum + demand + saturation + market
  full          the same + history (decayed, empirical-Bayes shrunk meta track record)

Promotion rule, fixed before results: a candidate replaces the existing score only if, on the
test days, (1) the launches of its top pick per step graduate more often than those of the
existing score's top pick, with the 90% day-block bootstrap interval of the difference above 0,
(2) its log loss beats both the existing score and null with intervals above 0, and (3) both
hold in direction in each regime (June 25 - July 1 and July 5 - 14).

Usage: python scripts/meta_validate.py meta.npz --out results.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar.analytics import meta_model as MM  # noqa: E402
from radar.analytics import quant as Q  # noqa: E402

H = 3600
LAMS = [1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0]
JUL2 = 1782950400
MIN_FUTURE_PICK = 3


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


MOMENTUM, DEMAND, SATURATION, MARKET = MM.MOMENTUM, MM.DEMAND, MM.SATURATION, MM.MARKET
HISTORY = ["hist_lift", "hist_x2_lift", "hist_n"]


def features(M: dict, k_grad: float, k_x2: float) -> dict:
    f = MM.transform({k: M[k] for k in M if M[k].dtype != object and M[k].dtype.kind != "U"})
    f.update({"score": M["score"], "favorable": (M["verdict"] == "favorable").astype(float),
              "accelerating": (np.nan_to_num(M["accel_z"], nan=-9) >= 2).astype(float),
              "hist_n": np.log1p(np.maximum(M["h_n_w"], 0))})
    for name, kk, num, base_num in (("hist_lift", k_grad, "h_k_w", "gh_k_w"), ("hist_x2_lift", k_x2, "h_x2_w", "gh_x2_w")):
        p0 = np.clip(M[base_num] / np.maximum(M["gh_n_w"], 1e-9), 1e-4, 0.9)
        shr = (M[num] + kk * p0) / (M["h_n_w"] + kk)
        f[name] = np.where(M["gh_n_w"] > 0, np.log(shr / p0), np.nan)
    return f


SPECS = {
    "existing": ["score"], "favorable": ["favorable"], "accelerating": ["accelerating"], "popularity": ["launches_6h"],
    "momentum": MOMENTUM, "demand": DEMAND, "saturation": SATURATION, "history": HISTORY,
    "full_nohist": MOMENTUM + DEMAND + SATURATION + MARKET, "full": MOMENTUM + DEMAND + SATURATION + MARKET + HISTORY,
}


def expand(rows, k, n, off):
    """Binomial rows as weighted Bernoulli rows: (y=1, w=k) and (y=0, w=n-k)."""
    r = np.r_[rows, rows]
    y = np.r_[np.ones(len(rows)), np.zeros(len(rows))]
    w = np.r_[k[rows], (n - k)[rows]]
    keep = w > 0
    return r[keep], y[keep], w[keep], np.r_[off[rows], off[rows]][keep]


def fit(F, names, k, n, off, tr, lam):
    X = np.column_stack([F[c][tr] for c in names])
    pr = Q.Prep().fit(X, names)
    r, y, w, o = expand(tr, k, n, off)
    pos = {v: i for i, v in enumerate(tr)}
    Xe = pr.transform(np.column_stack([F[c][r] for c in names]))
    b = Q.fit_logreg(Xe, y, lam, offset=o, w=w)
    return b, pr, pos


def predict(F, names, b, pr, rows):
    return b[0] + pr.transform(np.column_stack([F[c][rows] for c in names])) @ b[1:]


def binom_ll(k, n, eta):
    """Mean log-likelihood per launch."""
    return float((k * -np.logaddexp(0, -eta) + (n - k) * -np.logaddexp(0, eta)).sum() / n.sum())


TIERS = (("strongest", 0.0, 0.2), ("above average", 0.2, 0.5), ("below average", 0.5, 0.8), ("weakest", 0.8, 1.01))


def tier_of(lift, T, rows):
    """Tier of each row by its position in its own step's ranking, as the app assigns it."""
    out = {}
    for s in np.unique(T[rows]):
        r = rows[T[rows] == s]
        order = r[np.argsort(-lift[r], kind="stable")]
        for pos, i in enumerate(order):
            q = pos / max(len(order) - 1, 1)
            out[i] = next(name for name, lo, hi in TIERS if lo <= q < hi)
    return np.array([out[i] for i in rows])


def tier_table(lift, T, rows, k, n, rate, blocks, rng, boot=1000):
    """How the next launches of metas in each tier graduated against all launches then:
    pooled observed / expected, with a block-bootstrap 90% interval."""
    tiers = tier_of(lift, T, rows)
    ub = np.unique(blocks[rows])
    res = {}
    for name, _, _ in TIERS:
        r = rows[tiers == name]
        if not len(r):
            continue
        e = (rate[r] * n[r]).sum()
        draws = []
        by_b = {b: r[blocks[r] == b] for b in ub}
        for _ in range(boot):
            rr = np.concatenate([by_b[b] for b in rng.choice(ub, len(ub))])
            ee = (rate[rr] * n[rr]).sum()
            if ee > 0:
                draws.append(k[rr].sum() / ee)
        res[name] = {"meta_hours": int(len(r)), "launches": int(n[r].sum()), "graduations": int(k[r].sum()),
                     "ratio": round(float(k[r].sum() / e), 3) if e else None,
                     "ci90": [round(float(np.percentile(draws, 5)), 3), round(float(np.percentile(draws, 95)), 3)]}
    return res


def external(M, rows, k, n, off, lam_of, path, outcome):
    """Fit each model on every row of the training data, then score a later, separate period
    (a Shrine replay). Bootstrap over 3-hour blocks: a replay spans under a day."""
    E = dict(np.load(path))
    if outcome == "grad":
        ke, ne, gke, gne = E["y_k"], E["y_n"], E["gy_k"], E["gy_n"]
    elif outcome == "grad_nf":
        ke, ne, gke, gne = E["y_k_nf"], E["y_n_nf"], E["gy_k_nf"], E["gy_n_nf"]
    else:
        return None
    er = np.where((ne > 0) & (gne > 0) & (gke > 0))[0]
    rate_e = np.clip(gke / np.maximum(gne, 1), 1e-5, 1 - 1e-5)
    off_e = Q.logit(rate_e)
    hist_rows = rows[M["h_n_w"][rows] > 0]
    kg = Q.fit_beta_strength(M["h_k_w"][hist_rows], M["h_n_w"][hist_rows],
                             np.clip(M["gh_k_w"][hist_rows] / M["gh_n_w"][hist_rows], 1e-4, 0.9))
    kx = Q.fit_beta_strength(M["h_x2_w"][hist_rows], M["h_n_w"][hist_rows],
                             np.clip(M["gh_x2_w"][hist_rows] / M["gh_n_w"][hist_rows], 1e-4, 0.9))
    F, Fe = features(M, kg, kx), features(E, kg, kx)
    TE = E["T"]
    tie = np.random.default_rng(3).random(len(TE))
    lifts = {"null": np.zeros(len(TE))}
    for m, cols in SPECS.items():
        b, pr, _ = fit(F, cols, k, n, off, rows, lam_of[m])
        lifts[m] = predict(Fe, cols, b, pr, np.arange(len(TE)))
    steps = np.unique(TE[er])
    picks = {}
    for m, lift in lifts.items():
        pk = []
        for s in steps:
            cand = er[(TE[er] == s) & (ne[er] >= MIN_FUTURE_PICK)]
            if len(cand):
                pk.append(cand[np.lexsort((tie[cand], -lift[cand]))][0])
        picks[m] = np.array(pk)
    blocks = (TE // (3 * H)).astype(int)
    ub = np.unique(blocks[er])
    rng = np.random.default_rng(5)
    out = {"rows": int(len(er)), "steps": int(len(steps)), "events": int(ke[er].sum())}
    draws = {m: {"ll": [], "top1": []} for m in lifts}
    for it in range(1001):
        bs = ub if it == 0 else rng.choice(ub, len(ub))
        R = np.concatenate([er[blocks[er] == b_] for b_ in bs])
        base = binom_ll(ke[R], ne[R], off_e[R])
        for m, lift in lifts.items():
            P = np.concatenate([picks[m][blocks[picks[m]] == b_] for b_ in bs])
            ll = 1000 * (binom_ll(ke[R], ne[R], off_e[R] + lift[R]) - base)
            t1 = ke[P].sum() / max((rate_e[P] * ne[P]).sum(), 1e-9)
            if it == 0:
                out[m] = {"ll_gain_per_1000": ll, "top1_ratio": t1,
                          "top1_rate": float(ke[P].sum() / max(ne[P].sum(), 1))}
            else:
                draws[m]["ll"].append(ll); draws[m]["top1"].append(t1)
    for m in lifts:
        if m == "existing":
            continue
        for key in ("ll", "top1"):
            d_ = np.array(draws[m][key]) - np.array(draws["existing"][key])
            out[m][f"{key}_minus_existing"] = [float(np.percentile(d_, 5)), float(np.mean(d_)), float(np.percentile(d_, 95))]
    out["tiers"] = tier_table(lifts["full_nohist"], TE, er, ke, ne, rate_e, blocks, np.random.default_rng(9))
    log("external", path.name, " | ".join(f"{m}: ll {out[m]['ll_gain_per_1000']:+.2f} top1 x{out[m]['top1_ratio']:.2f}"
                                          for m in lifts))
    for m in ("full_nohist", "full", "demand", "history"):
        log("external ci", path.name, m, json.dumps({kk: [round(x, 3) for x in v] for kk, v in out[m].items()
                                                     if isinstance(v, list)}))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--outcome", default="grad", choices=["grad", "x2", "grad_el", "grad_nf"])
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--external", type=Path, nargs="*", help="later replay datasets: fit on every training row, test there")
    a = ap.parse_args()
    M = dict(np.load(a.data))
    T = M["T"]
    day = (T // 86400).astype(int)
    if a.outcome == "grad":
        k, n, gk, gn = M["y_k"], M["y_n"], M["gy_k"], M["gy_n"]
    elif a.outcome == "x2":
        k, n, gk, gn = M["y_x2"], M["y_n"], M["gy_x2"], M["gy_n"]
    elif a.outcome == "grad_nf":
        k, n, gk, gn = M["y_k_nf"], M["y_n_nf"], M["gy_k_nf"], M["gy_n_nf"]
    else:   # coin-level control: launches on the curve at 60 s, offset = token model's expectation
        k, n, gk, gn = M["y_k_el"], M["y_n_el"], M["y_p_el"], M["y_n_el"]
    ok = (n > 0) & (gn > 0) & (gk > 0)
    rate = np.clip(gk / np.maximum(gn, 1), 1e-5, 1 - 1e-5)
    off = Q.logit(rate)
    rows = np.where(ok)[0]
    tie = np.random.default_rng(3).random(len(T))   # tie-break carrying no information
    days = np.unique(day[rows])
    log(a.outcome, "rows", len(rows), "steps", len(np.unique(T[rows])), "days", len(days), "events", int(k[rows].sum()))

    eta = {m: np.full(len(T), np.nan) for m in ["null"] + list(SPECS)}
    lam_of, coefs = {}, {m: [] for m in SPECS}
    for d in days[6:]:
        d0 = d * 86400
        tr = rows[T[rows] + 7 * H <= d0]
        te = rows[day[rows] == d]
        hist_rows = tr[M["h_n_w"][tr] > 0]
        kg = Q.fit_beta_strength(M["h_k_w"][hist_rows], M["h_n_w"][hist_rows],
                                 np.clip(M["gh_k_w"][hist_rows] / M["gh_n_w"][hist_rows], 1e-4, 0.9))
        kx = Q.fit_beta_strength(M["h_x2_w"][hist_rows], M["h_n_w"][hist_rows],
                                 np.clip(M["gh_x2_w"][hist_rows] / M["gh_n_w"][hist_rows], 1e-4, 0.9))
        F = features(M, kg, kx)
        eta["null"][te] = off[te]
        for m, cols in SPECS.items():
            if m not in lam_of:   # once, on the first fold's last 3 training days
                tdays = np.unique(day[tr])
                fit_rows, val = tr[day[tr] < tdays[-3]], tr[day[tr] >= tdays[-3]]
                best = None
                for lam in (LAMS if len(cols) > 1 else [0.1]):
                    b, pr, _ = fit(F, cols, k, n, off, fit_rows, lam)
                    ll = binom_ll(k[val], n[val], off[val] + predict(F, cols, b, pr, val))
                    if best is None or ll > best[0]:
                        best = (ll, lam)
                lam_of[m] = best[1]
            b, pr, _ = fit(F, cols, k, n, off, tr, lam_of[m])
            eta[m][te] = off[te] + predict(F, cols, b, pr, te)
            coefs[m].append({"day": int(d), "coef": dict(zip(["intercept"] + pr.out_names, map(float, b)))})
        log("day", time.strftime("%m-%d", time.gmtime(d0)), "train rows", len(tr), "test rows", len(te),
            "k_hist", round(kg, 1))

    test = rows[np.isfinite(eta["null"][rows])]
    models = ["null"] + list(SPECS)
    tdays = np.unique(day[test])
    steps = np.unique(T[test])

    def evaluate(sel_days):
        """Per model: log-likelihood gain per launch vs null, top-1 / top-3 pick graduation lift,
        and the paired gain of top-1 over the existing score's pick; on rows of the given days."""
        R = test[np.isin(day[test], sel_days)]
        out = {}
        for m in models:
            ll = binom_ll(k[R], n[R], eta[m][R]) - binom_ll(k[R], n[R], eta["null"][R])
            out[m] = {"ll_gain_per_1000": 1000 * ll}
        for m in models:
            picks = {1: [0.0, 0.0, 0.0], 3: [0.0, 0.0, 0.0]}  # k, n, expected under market rate
            for s in np.unique(T[R]):
                cand = R[(T[R] == s) & (n[R] >= MIN_FUTURE_PICK)]
                if len(cand) == 0:
                    continue
                score = eta[m][cand] - off[cand] if m != "null" else np.zeros(len(cand))
                order = cand[np.lexsort((tie[cand], -score))]   # ties: arbitrary, not future size
                for top in (1, 3):
                    c = order[:top]
                    picks[top][0] += k[c].sum(); picks[top][1] += n[c].sum(); picks[top][2] += (rate[c] * n[c]).sum()
            for top in (1, 3):
                kk, nn, ee = picks[top]
                out[m][f"top{top}_rate"] = kk / nn if nn else None
                out[m][f"top{top}_market_rate"] = ee / nn if nn else None
                out[m][f"top{top}_ratio"] = kk / ee if ee else None
        return out

    res = {"outcome": a.outcome, "rows": int(len(test)), "steps": int(len(steps)), "days": [int(x) for x in tdays],
           "events": int(k[test].sum()), "launches": int(n[test].sum()), "lambda": lam_of,
           "all": evaluate(tdays),
           "jun25_jul1": evaluate(tdays[tdays * 86400 < JUL2]), "jul5_14": evaluate(tdays[tdays * 86400 >= JUL2])}

    # day-block bootstrap of the comparisons that decide promotion
    rng = np.random.default_rng(11)
    by_day = {d: test[day[test] == d] for d in tdays}
    pick_rows = {}
    for m in models:
        pr_ = []
        for s in steps:
            cand = test[(T[test] == s) & (n[test] >= MIN_FUTURE_PICK)]
            if len(cand):
                score = eta[m][cand] - off[cand] if m != "null" else np.zeros(len(cand))
                pr_.append(cand[np.lexsort((tie[cand], -score))][0])
        pick_rows[m] = np.array(pr_)
    draws = {m: {"ll": [], "top1_ratio": []} for m in models}
    for _ in range(a.boot):
        ds = rng.choice(tdays, len(tdays))
        R = np.concatenate([by_day[d] for d in ds])
        base = binom_ll(k[R], n[R], eta["null"][R])
        for m in models:
            draws[m]["ll"].append(1000 * (binom_ll(k[R], n[R], eta[m][R]) - base))
            P = np.concatenate([pick_rows[m][np.isin(day[pick_rows[m]], [d])] for d in ds])
            draws[m]["top1_ratio"].append(k[P].sum() / max((rate[P] * n[P]).sum(), 1e-9))
    ci = {}
    for m in models:
        ci[m] = {}
        for key in ("ll", "top1_ratio"):
            v = np.array(draws[m][key])
            ci[m][key] = [float(np.percentile(v, 5)), float(np.percentile(v, 95))]
        for ref in ("existing", "null"):
            if m == ref:
                continue
            for key in ("ll", "top1_ratio"):
                d_ = np.array(draws[m][key]) - np.array(draws[ref][key])
                ci[m][f"{key}_minus_{ref}"] = [float(np.percentile(d_, 5)), float(np.mean(d_)), float(np.percentile(d_, 95))]
    for m_, ref in (("full", "full_nohist"), ("full_nohist", "demand"), ("full_nohist", "saturation")):
        for key in ("ll", "top1_ratio"):
            d_ = np.array(draws[m_][key]) - np.array(draws[ref][key])
            ci[m_][f"{key}_minus_{ref}"] = [float(np.percentile(d_, 5)), float(np.mean(d_)), float(np.percentile(d_, 95))]
    res["ci"] = ci
    # calibration of the predicted lift: deciles of predicted vs observed graduations
    cal = {}
    for m in ("existing", "full_nohist", "full", "accelerating"):
        lift = eta[m][test] - off[test]
        q = np.quantile(lift, np.linspace(0, 1, 6))
        bins = []
        for lo_, hi_ in zip(q[:-1], q[1:]):
            s = test[(lift >= lo_) & (lift <= hi_)]
            exp_ = (Q.sigmoid(eta[m][s]) * n[s]).sum()
            bins.append({"pred_lift": float(np.exp(np.median(lift[(lift >= lo_) & (lift <= hi_)]))),
                         "expected": float(exp_), "observed": int(k[s].sum()), "launches": int(n[s].sum())})
        cal[m] = bins
    res["calibration"] = cal
    res["tiers"] = {m: tier_table(eta[m] - off, T, test, k, n, rate, day, np.random.default_rng(9), a.boot)
                    for m in ("existing", "full_nohist")}
    log("tiers", json.dumps(res["tiers"]))
    res["coefs_last"] = {m: coefs[m][-1] if coefs[m] else None for m in SPECS}
    if a.external:
        res["external"] = {str(p): external(M, rows, k, n, off, lam_of, p, a.outcome) for p in a.external}
    a.out.write_text(json.dumps(res, indent=1))

    def fmt(e):
        return " | ".join(f"{m}: ll {e[m]['ll_gain_per_1000']:+.2f} top1 x{(e[m]['top1_ratio'] or 0):.2f} "
                          f"top3 x{(e[m]['top3_ratio'] or 0):.2f}" for m in models)
    for key in ("all", "jun25_jul1", "jul5_14"):
        log(key, fmt(res[key]))
    for m in models:
        log("ci", m, json.dumps({kk: [round(x, 3) for x in v] for kk, v in ci[m].items()}))


if __name__ == "__main__":
    main()
