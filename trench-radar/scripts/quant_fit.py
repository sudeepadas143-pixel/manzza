"""Fit the deployable launch score on every labelled day of the corpus and write it for the app.

The model is the one validated walk-forward as `logreg_deploy` (scripts/quant_validate.py):
L2 logistic regression for P(graduates within 1 h of launch | still on the curve at age A),
with the cohort base rate as an input. Lambda is chosen exactly as in validation (inner split on
the last 3 days). Output: radar/data/quant_model.json, read by radar/early.py.

Usage: python scripts/quant_fit.py DATASET.npz --results results_60.json [--age 60]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import quant_validate as V  # noqa: E402
from radar.analytics import quant as Q  # noqa: E402

H = 3600


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--results", type=Path, required=True, help="walk-forward results to record with the model")
    ap.add_argument("--age", type=int, default=60)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "radar" / "data" / "quant_model.json")
    a = ap.parse_args()
    D = dict(np.load(a.dataset))
    A = a.age
    F = V.features(D, A)
    t0, day, g = D["t0"], (D["t0"] // 86400).astype(int), D["grad_s"]
    idx = np.where((t0 >= V.JUN19) & (D["gap"] == 0) & ~(g <= A))[0]
    y = np.zeros(len(t0)); y[idx] = g[idx] <= H
    F["base_logit"] = Q.logit(np.nan_to_num(V.trailing_rate(t0, y, idx, H), nan=0.01))
    hist = idx[np.nan_to_num(D["m_hist_n"][idx]) > 0]
    k = Q.fit_beta_strength(np.nan_to_num(D["m_hist_grad"][hist]), np.nan_to_num(D["m_hist_n"][hist]),
                            np.clip(np.nan_to_num(D["base_grad_24h"][hist], nan=0.005), 1e-4, 0.9))
    F["m_hist_lift"] = V.track_lift(D, k, "grad")
    kx = Q.fit_beta_strength(np.nan_to_num(D["m_hist_x2"][hist]), np.nan_to_num(D["m_hist_n"][hist]),
                             np.clip(np.nan_to_num(D["base_x2_24h"][hist], nan=0.05), 1e-4, 0.9))
    F["m_hist_x2_lift"] = V.track_lift(D, kx, "x2")
    cols = V.DEPLOY
    lam = V.choose_lam(F, cols, y, idx, day)
    pr = Q.Prep().fit(V.matrix(F, cols, idx), cols)
    b = Q.fit_logreg(pr.transform(V.matrix(F, cols, idx)), y[idx], lam)
    R = json.loads(a.results.read_text()).get(str(A), {})
    val = {}
    for key in ("eligible/grad_1h", "active/grad_1h"):
        r = R.get(key)
        if r and "logreg_deploy" in r["summary"]:
            s = r["summary"]["logreg_deploy"]
            val[key] = {m: s[m] for m in ("n", "events", "auc", "auc_within_day", "ap", "brier_skill", "logloss", "intercept", "slope", "lift10")}
            val[key]["auc_ci"] = r["ci"]["logreg_deploy"]["auc"]
            val[key]["base_auc_within_day"] = r["summary"]["base"]["auc_within_day"]
            if "buyers" in r["summary"]:
                val[key]["buyers_auc_within_day"] = r["summary"]["buyers"]["auc_within_day"]
    spec = {
        "version": f"quant-v1-a{A}-{time.strftime('%Y%m%d')}",
        "target": f"graduates within 1 h of launch, given still on the curve at {A} s",
        "age_s": A, "features": pr.names, "missing_indicators": pr.ind,
        "median": [float(x) for x in pr.med], "mean": [float(x) for x in pr.mu], "sd": [float(x) for x in pr.sd],
        "coef": [float(x) for x in b], "coef_names": ["intercept"] + pr.out_names, "lambda": lam, "shrink_k": k, "shrink_k_x2": kx,
        "min_base_n": 2000,
        "trained_on": {"dataset": "Pump.fun Memecoin Corpus (jocry/Pumpfun_Memecoin_Corpus @ bd8aed6), CC BY 4.0",
                       "from": time.strftime("%Y-%m-%d", time.gmtime(t0[idx].min())),
                       "to": time.strftime("%Y-%m-%d", time.gmtime(t0[idx].max())),
                       "rows": int(len(idx)), "events": int(y[idx].sum())},
        "walk_forward": val,
        "note": "Probabilities assume the live cohort base rate; until base_n reaches min_base_n they are a ranking only.",
    }
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k: spec[k] for k in ("version", "lambda", "shrink_k", "trained_on")}, indent=1))
    for n_, c in sorted(zip(spec["coef_names"][1:], b[1:]), key=lambda x: -abs(x[1])):
        print(f"  {n_:24s} {c:+.3f}")


if __name__ == "__main__":
    main()
