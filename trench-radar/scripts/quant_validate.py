"""Walk-forward validation of the quantitative score on the corpus dataset (scripts/quant_dataset.py).

Pre-registered before any result was seen:
  populations  eligible = launched on/after 2026-06-19 (no graduations were recorded before),
               label window clear of collection gaps, not graduated by the observation age A.
               active = eligible with >= 3 distinct buyers by A.
  outcomes     graduated within 5 min / 15 min / 1 h of launch; market cap reached 2x launch
               within 15 min (for tokens below 2x at A).
  models       base (cohort base rate only), buyers, formula (fixed-sign equal weights),
               logreg_token, logreg_meta, logreg_full (L2 logistic), hazard_full (discrete time)
  validation   walk-forward by UTC day: train on all earlier days minus a 1 h embargo, test on
               the day; lambda chosen per model on the last 3 training days of the first fold
               (earliest data only), then held fixed; min 6 training days.
  uncertainty  day-block bootstrap (1000 draws) of the pooled out-of-sample predictions.

Usage: python scripts/quant_validate.py DATASET.npz --out results.json [--ages 60 300]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar.analytics import quant as Q  # noqa: E402

JUN19 = 1781827200
H = 3600
LAMS = [0.1, 1.0, 10.0, 100.0, 1000.0]
ONLY_LABELS = None


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- features
TOKEN = ["buyers", "trades", "buy_share", "buy_sol", "net_sol", "mcap_ratio", "top_buyer_share", "snipers",
         "dumped_share", "creator_sold", "serial_share", "proven", "sellers"]
LAUNCH = ["dev_buy_pct", "top10_pct", "initial_buy_sol", "mayhem", "cashback"]
CREATOR = ["c_prior", "c_24h", "c_grads"]
META_MOM = ["m_launch_1h", "m_accel_z", "m_share", "m_creator_conc", "m_dup_share", "m_buyers_1h"]
META_HIST = ["m_hist_lift", "m_hist_x2_lift", "m_hist_n"]
BASE = ["base_logit"]


def features(D, A):
    f = {}
    g = lambda k: D[f"{k}_{A}"]  # noqa: E731
    f["buyers"] = np.log1p(g("uniq_buyers"))
    f["sellers"] = np.log1p(g("uniq_sellers"))
    f["trades"] = np.log1p(g("n_trades"))
    f["buy_share"] = Q.safe_div(g("n_buys"), g("n_trades"))
    f["buy_sol"] = np.log1p(g("buy_sol"))
    f["net_sol"] = Q.signed_log1p(g("buy_sol") - g("sell_sol"))
    f["mcap_ratio"] = np.log(np.where(np.isfinite(g("mcap_at")), g("mcap_at"), D["init_mcap"]) / D["init_mcap"])
    f["top_buyer_share"] = g("top_buyer_share")
    f["snipers"] = np.log1p(g("snipers"))
    f["dumped_share"] = g("dumped_share")
    f["creator_sold"] = g("creator_sold")
    f["serial_share"] = D[f"serial_share_{A}"]
    f["proven"] = np.log1p(D[f"proven_buyers_{A}"])
    f["dev_buy_pct"] = D["dev_buy_pct"]
    f["top10_pct"] = D["top10_pct"]
    f["initial_buy_sol"] = np.log1p(np.nan_to_num(D["initial_buy_sol"]))
    f["mayhem"] = np.nan_to_num(D["mayhem"])
    f["cashback"] = np.nan_to_num(D["cashback"])
    f["c_prior"] = np.log1p(D["c_prior_launches"])
    f["c_24h"] = np.log1p(D["c_launches_24h"])
    f["c_grads"] = np.log1p(D["c_prior_grads"])
    f["m_launch_1h"] = np.log1p(D["m_launch_1h"])
    f["m_accel_z"] = np.clip(D["m_accel_z"], -5, 20)
    f["m_share"] = np.log1p(1000 * D["m_share_1h"])
    f["m_creator_conc"] = D["m_creator_conc"]
    f["m_dup_share"] = D["m_dup_share"]
    f["m_buyers_1h"] = np.log1p(D["m_buyers_1h"])
    f["m_hist_n"] = np.log1p(D["m_hist_n"])
    f["base_logit"] = Q.logit(np.clip(np.nan_to_num(D["base_grad_24h"], nan=0.005), 1e-4, 0.5))
    return f


def track_lift(D, k, which="grad"):
    """log of the shrunk meta success rate over the cohort base rate (0 = no evidence either way)."""
    s, n = (D["m_hist_grad"], D["m_hist_n"]) if which == "grad" else (D["m_hist_x2"], D["m_hist_n"])
    p0 = np.clip(np.nan_to_num(D["base_grad_24h" if which == "grad" else "base_x2_24h"], nan=0.005), 1e-4, 0.9)
    s, n = np.nan_to_num(s), np.nan_to_num(n)
    return np.log(Q.shrunk_rate(s, n, p0, k) / p0)


# the transparent formula: equal weights, signs fixed in advance from the hypotheses, no fitting
# except a 2-parameter mapping to probability (and the base-rate term) on training data
FORMULA = {"buyers": +1, "buy_share": +1, "net_sol": +1, "mcap_ratio": +1, "top_buyer_share": -1, "dumped_share": -1,
           "creator_sold": -1, "serial_share": -1, "proven": +1, "m_accel_z": +1, "m_hist_lift": +1}

SPECS = {
    "base": BASE,
    "buyers": BASE + ["buyers"],
    "logreg_token": BASE + TOKEN + LAUNCH + CREATOR,
    "logreg_meta": BASE + META_MOM + META_HIST,
    "logreg_full": BASE + TOKEN + LAUNCH + CREATOR + META_MOM + META_HIST,
    # what the app can compute live with the corpus definitions (radar/early.py): no third-party
    # holder snapshot (top10), no dev-buy fields whose corpus derivation is undocumented
    "logreg_deploy": BASE + TOKEN + ["mayhem", "cashback"] + CREATOR + META_MOM + META_HIST,
    # ablations: which half of the meta score carries the signal, alone and on top of the token
    "meta_momentum": BASE + META_MOM,
    "meta_track": BASE + META_HIST,
    "token_only": BASE + TOKEN + ["mayhem", "cashback"] + CREATOR,
}
DEPLOY = SPECS["logreg_deploy"]


def trailing_rate(t0, y, idx, horizon_s, window_s=86400, prior=(0.5, 50)):
    """Cohort normalisation: for each row, the rate of this same outcome among this same
    population launched in [t0 - window - horizon, t0 - horizon), i.e. outcomes already known at
    t0. Jeffreys-style prior keeps early estimates finite."""
    o = idx[np.argsort(t0[idx], kind="stable")]
    ts, cy = t0[o], np.r_[0, np.cumsum(y[o])]
    hi = np.searchsorted(ts, t0[idx] - horizon_s, side="left")
    lo = np.searchsorted(ts, t0[idx] - horizon_s - window_s, side="left")
    n, k = hi - lo, cy[hi] - cy[lo]
    a, b = prior[0], prior[1]
    out = np.full(len(t0), np.nan)
    out[idx] = (k + a) / (n + a + b)
    return out


def within_day_auc(day, y, p):
    """Event-weighted mean of the AUC inside each day: how well a day's launches are ranked
    against each other, which is what the score is used for."""
    tot, w = 0.0, 0
    for d in np.unique(day):
        m = day == d
        e = int(y[m].sum())
        if 0 < e < m.sum():
            tot += Q.auc(y[m], p[m]) * e
            w += e
    return tot / w if w else float("nan")


def matrix(F, names, idx):
    return np.column_stack([F[k][idx] for k in names])


def fit_predict(F, names, y, tr, te, lam):
    pr = Q.Prep().fit(matrix(F, names, tr), names)
    b = Q.fit_logreg(pr.transform(matrix(F, names, tr)), y[tr], lam)
    return Q.predict_logreg(b, pr.transform(matrix(F, names, te))), b, pr


def choose_lam(F, names, y, tr, day):
    days = np.unique(day[tr])
    if len(days) < 5 or len(names) <= 2:
        return 1.0
    val = np.isin(day[tr], days[-3:])
    a, v = tr[~val], tr[val]
    if y[a].sum() < 10 or y[v].sum() < 5:
        return 10.0
    best, bl = None, None
    for lam in LAMS:
        p, _, _ = fit_predict(F, names, y, a, v, lam)
        ll = Q.logloss(y[v], p)
        if bl is None or ll < bl:
            best, bl = lam, ll
    return best


def formula_score(F, tr, te):
    """Mean of z-scores (training mean/sd) with fixed signs."""
    s_tr, s_te = 0, 0
    for k, sign in FORMULA.items():
        x_tr, x_te = F[k][tr], F[k][te]
        med = np.nanmedian(x_tr); x_tr = np.where(np.isnan(x_tr), med, x_tr); x_te = np.where(np.isnan(x_te), med, x_te)
        mu, sd = x_tr.mean(), x_tr.std() or 1.0
        s_tr = s_tr + sign * (x_tr - mu) / sd; s_te = s_te + sign * (x_te - mu) / sd
    n = len(FORMULA)
    return s_tr / n, s_te / n


def run(D, A, out):
    F = features(D, A)
    t0, day = D["t0"], (D["t0"] // 86400).astype(int)
    grad_s = D["grad_s"]
    base_pop = (t0 >= JUN19) & (D["gap"] == 0)
    elig = base_pop & ~(grad_s <= A)
    labels = {"grad_15m": grad_s <= 900, "grad_1h": grad_s <= H}
    if A < 300:
        labels = {"grad_5m": grad_s <= 300, **labels}
    below2x = np.where(np.isfinite(D[f"mcap_at_{A}"]), D[f"mcap_at_{A}"], D["init_mcap"]) < 2 * D["init_mcap"]
    labels["x2_15m"] = D["x2_15m"] == 1
    pops = {"eligible": elig, "active": elig & (D[f"uniq_buyers_{A}"] >= 3)}
    if ONLY_LABELS:
        labels = {k: v for k, v in labels.items() if k in ONLY_LABELS}
    res = {}
    for pname, pop in pops.items():
        for lname, lab in labels.items():
            P = pop & below2x if lname == "x2_15m" else pop
            idx = np.where(P)[0]
            y = np.zeros(len(t0)); y[idx] = lab[idx]
            hz = {"grad_5m": 300, "grad_15m": 900, "grad_1h": H, "x2_15m": 900}[lname]
            F["base_logit"] = Q.logit(np.nan_to_num(trailing_rate(t0, y, idx, hz), nan=0.5 / 50))
            days = np.unique(day[idx])
            preds = {k: np.full(len(t0), np.nan) for k in list(SPECS) + ["formula", "hazard_full"]}
            coefs = {k: [] for k in SPECS}
            lam_used = []
            lam_cache = {}       # lambda per model, chosen once on the first fold's inner split (earliest data only)
            for d in days[6:]:
                tr = idx[(day[idx] < d) & (t0[idx] <= d * 86400 - H)]
                te = idx[day[idx] == d]
                if y[tr].sum() < 20 or len(te) == 0:
                    continue
                # meta track record: shrinkage strength from training rows only
                hist_tr = tr[np.nan_to_num(D["m_hist_n"][tr]) > 0]
                k = Q.fit_beta_strength(np.nan_to_num(D["m_hist_grad"][hist_tr]), np.nan_to_num(D["m_hist_n"][hist_tr]),
                                        np.clip(np.nan_to_num(D["base_grad_24h"][hist_tr], nan=0.005), 1e-4, 0.9))
                kx = Q.fit_beta_strength(np.nan_to_num(D["m_hist_x2"][hist_tr]), np.nan_to_num(D["m_hist_n"][hist_tr]),
                                         np.clip(np.nan_to_num(D["base_x2_24h"][hist_tr], nan=0.05), 1e-4, 0.9))
                F["m_hist_lift"] = track_lift(D, k, "grad")
                F["m_hist_x2_lift"] = track_lift(D, kx, "x2")
                for name, cols in SPECS.items():
                    if name not in lam_cache:
                        lam_cache[name] = choose_lam(F, cols, y, tr, day) if len(cols) > 2 else 0.01
                    lam = lam_cache[name]
                    p, b, pr = fit_predict(F, cols, y, tr, te, lam)
                    preds[name][te] = p
                    coefs[name].append({"day": int(d), "lam": lam, "names": pr.out_names, "b": b.tolist(), "k": k})
                    if name == "logreg_full":
                        lam_used.append(lam)
                if "logreg_full" not in SPECS:
                    continue
                s_tr, s_te = formula_score(F, tr, te)
                Xf = np.column_stack([s_tr, F["base_logit"][tr]])
                b = Q.fit_logreg(Xf, y[tr], 0.0)
                preds["formula"][te] = Q.predict_logreg(b, np.column_stack([s_te, F["base_logit"][te]]))
                if lname.startswith("grad"):
                    cols = SPECS["logreg_full"]
                    pr = Q.Prep().fit(matrix(F, cols, tr), cols)
                    cuts = [c for c in (300.0, 900.0, 3600.0) if c > A]
                    tev = np.where(np.isfinite(grad_s), grad_s, np.nan)
                    bh = Q.fit_hazard(pr.transform(matrix(F, cols, tr)), tev[tr], cuts, lam_used[-1] if lam_used else 10.0)
                    cum = Q.hazard_cumulative(bh, pr.transform(matrix(F, cols, te)), cuts)
                    hz = {"grad_5m": 300.0, "grad_15m": 900.0, "grad_1h": 3600.0}[lname]
                    preds["hazard_full"][te] = cum[:, cuts.index(hz)]
            ok = ~np.isnan(preds["base"])
            if ok.sum() == 0:
                continue
            yy, dd = y[ok], day[ok]
            P_ = {k: v[ok] for k, v in preds.items() if not np.isnan(v[ok]).any()}
            summ = {k: Q.summary(yy, p) for k, p in P_.items()}
            for k, p in P_.items():
                summ[k]["auc_within_day"] = within_day_auc(dd, yy, p)
            base_brier = summ["base"]["brier"]
            for k in summ:
                summ[k]["brier_skill"] = 1 - summ[k]["brier"] / base_brier
            ci, draws = Q.day_bootstrap(dd, yy, P_, iters=1000)
            paired = {}
            for a_ in P_:
                for b_ in ("base", "formula", "logreg_token", "buyers"):
                    if a_ == b_ or b_ not in P_:
                        continue
                    da, db_ = np.array(draws[a_]["auc"]), np.array(draws[b_]["auc"])
                    la, lb = np.array(draws[a_]["logloss"]), np.array(draws[b_]["logloss"])
                    paired[f"{a_}>{b_}"] = {"auc_win": float((da > db_).mean()), "auc_diff": float(np.median(da - db_)),
                                            "logloss_win": float((la < lb).mean()), "logloss_diff": float(np.median(la - lb))}
            per_day = {}
            for d in np.unique(dd):
                m = dd == d
                per_day[int(d)] = {"n": int(m.sum()), "events": int(yy[m].sum()),
                                   **{k: (Q.auc(yy[m], p[m]) if yy[m].sum() and (~yy[m].astype(bool)).sum() else None) for k, p in P_.items()}}
            best = "logreg_full" if "logreg_full" in P_ else "base"
            res[f"{pname}/{lname}"] = {
                "summary": summ, "ci": ci, "paired": paired,
                "reliability": {k: Q.reliability(yy, P_[k], 10) for k in ("logreg_full", "formula", "base") if k in P_},
                "per_day_auc": per_day, "coefs": coefs, "lam_full": lam_used,
                "test_days": [int(x) for x in np.unique(dd)], "n_pop": int(len(idx)), "events_pop": int(lab[idx].sum())}
            s = summ.get("logreg_full", {})
            log(A, pname, lname, "n", int(ok.sum()), "events", int(yy.sum()),
                " | ".join(f"{k}: auc {v['auc']:.3f} wd {v['auc_within_day']:.3f} ap {v['ap']:.3f} bss {v['brier_skill']:+.3f}" for k, v in summ.items()))
    out[str(A)] = res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ages", type=int, nargs="+", default=[60, 300])
    ap.add_argument("--specs", nargs="+", help="run only these models (plus base)")
    ap.add_argument("--labels", nargs="+", help="run only these outcomes")
    a = ap.parse_args()
    D = dict(np.load(a.dataset))
    if a.specs:
        for k in list(SPECS):
            if k != "base" and k not in a.specs:
                del SPECS[k]
    global ONLY_LABELS
    ONLY_LABELS = a.labels
    out = {"created": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    for A in a.ages:
        run(D, A, out)
    a.out.write_text(json.dumps(out, default=lambda o: None if isinstance(o, float) and not np.isfinite(o) else o))
    log("saved", a.out)


if __name__ == "__main__":
    main()
