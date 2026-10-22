"""Fit the launch-edge model (`full_nohist` in scripts/meta_validate.py) on every labelled meta-step
of the corpus and write radar/data/meta_model.json for the app (radar/analytics/meta_model.py).

Usage: python scripts/meta_fit.py meta_corpus.npz --results res_grad.json --results-nf res_grad_nf.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import meta_validate as MV  # noqa: E402
from radar.analytics import meta_model as MM  # noqa: E402
from radar.analytics import quant as Q  # noqa: E402

SPEC = "full_nohist"


def summary(R: dict) -> dict:
    keep = ("null", "existing", "accelerating", SPEC, "full")
    out = {"test_days": len(R["days"]), "meta_steps": R["rows"], "launches": R["launches"], "graduations": R["events"],
           "top1_ratio": {m: round(R["all"][m]["top1_ratio"], 3) for m in keep},
           "top1_ratio_by_regime": {r: {m: round(R[r][m]["top1_ratio"], 3) for m in keep}
                                    for r in ("jun25_jul1", "jul5_14")},
           "ll_gain_per_1000_launches": {m: round(R["all"][m]["ll_gain_per_1000"], 3) for m in keep},
           "top1_minus_existing_ci90": R["ci"][SPEC]["top1_ratio_minus_existing"],
           "ll_minus_existing_ci90": R["ci"][SPEC]["ll_minus_existing"],
           "history_adds_ll_ci90": R["ci"]["full"]["ll_minus_full_nohist"]}
    ext = R.get("external") or {}
    out["later_periods"] = {Path(p).stem: {"top1_ratio": {m: round(v[m]["top1_ratio"], 3) for m in ("existing", SPEC)},
                                           "top1_minus_existing_ci90": v[SPEC]["top1_minus_existing"],
                                           "ll_minus_existing_ci90": v[SPEC]["ll_minus_existing"]}
                            for p, v in ext.items() if v}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--results-nf", type=Path)
    ap.add_argument("--out", type=Path, default=MM.MODEL_PATH)
    a = ap.parse_args()
    M = dict(np.load(a.data))
    R = json.loads(a.results.read_text())
    k, n, gk, gn = M["y_k"], M["y_n"], M["gy_k"], M["gy_n"]
    rows = np.where((n > 0) & (gn > 0) & (gk > 0))[0]
    off = Q.logit(np.clip(gk / np.maximum(gn, 1), 1e-5, 1 - 1e-5))
    F = MV.features(M, 1.0, 1.0)
    cols = MV.SPECS[SPEC]
    assert cols == MM.FEATURES
    lam = R["lambda"][SPEC]
    b, pr, _ = MV.fit(F, cols, k, n, off, rows, lam)
    T = M["T"][rows]
    spec = {
        "version": f"meta-edge-v1-{time.strftime('%Y%m%d')}",
        "target": "log-odds that a meta's launches in the next 6 h graduate within 1 h, against all launches then",
        "use": "ranking only: the ordering held in later months, the size of the lift did not",
        "features": pr.names, "missing_indicators": pr.ind,
        "median": [float(x) for x in pr.med], "mean": [float(x) for x in pr.mu], "sd": [float(x) for x in pr.sd],
        "coef": [float(x) for x in b], "coef_names": ["intercept"] + pr.out_names, "lambda": lam,
        "trained_on": {"dataset": "Pump.fun Memecoin Corpus (jocry/Pumpfun_Memecoin_Corpus @ bd8aed6), CC BY 4.0",
                       "from": time.strftime("%Y-%m-%d", time.gmtime(T.min())),
                       "to": time.strftime("%Y-%m-%d", time.gmtime(T.max())),
                       "meta_steps": int(len(rows)), "launches": int(n[rows].sum()), "graduations": int(k[rows].sum())},
        "validation": {"all_launches": summary(R)},
    }
    if a.results_nf:
        spec["validation"]["non_factory_launches"] = summary(json.loads(a.results_nf.read_text()))
    a.out.write_text(json.dumps(spec, indent=1))
    print(json.dumps({k_: spec[k_] for k_ in ("version", "lambda", "trained_on")}, indent=1))
    for nm, c in sorted(zip(spec["coef_names"][1:], b[1:]), key=lambda x: -abs(x[1]))[:12]:
        print(f"  {nm:26s} {c:+.3f}")


if __name__ == "__main__":
    main()
