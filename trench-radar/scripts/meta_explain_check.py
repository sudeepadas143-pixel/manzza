"""Are the reasons the app gives for a meta's rank predictive, or only convincing?

For each theme of reasons (radar/analytics/explain.THEMES), take the shipped launch-edge model and,
for every meta-hour of a dataset (scripts/meta_dataset.py), the theme's contribution to the
meta's rank against the other metas of the same hour, exactly as the app computes it. Then
compare how the next coins graduated (against all coins then) for metas where the theme counted
*for* them (contribution >= +0.05, the threshold at which the app states the reason) with metas
where it counted *against* them (<= -0.05). Run it on periods the model never saw.

Usage: python scripts/meta_explain_check.py meta_sep.npz meta_oct.npz [--write]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar.analytics import explain as X  # noqa: E402
from radar.analytics import meta_model as mm  # noqa: E402

H = 3600


def theme_contributions(M: dict, model: mm.EdgeModel) -> dict:
    F = mm.transform({k: M[k] for k in M if M[k].dtype.kind == "f"})
    T = M["T"]
    cols = []
    for j, name in enumerate(model.names):
        v = F[name]
        miss = np.isnan(v)
        cols.append((np.where(miss, model.med[j], v) - model.mu[j]) / model.sd[j])
    ind = [((np.isnan(F[model.names[j]])).astype(float) - model.mu[len(model.names) + i]) / model.sd[len(model.names) + i]
           for i, j in enumerate(model.ind)]
    contrib = {}
    for j, name in enumerate(model.names):
        c = model.b[1 + j] * cols[j]
        if j in model.ind:
            i = model.ind.index(j)
            c = c + model.b[1 + len(model.names) + i] * ind[i]
        contrib[name] = c
    out = {}
    steps = np.unique(T)
    for th, ins in X.THEMES.items():
        c = sum(contrib[n] for n in ins)
        for s in steps:          # relative to the same hour's metas, as in the app
            m = T == s
            c[m] = c[m] - c[m].mean()
        out[th] = c
    return out


def check(path: Path, model: mm.EdgeModel, rng) -> dict:
    M = dict(np.load(path))
    k, n, gk, gn = M["y_k"], M["y_n"], M["gy_k"], M["gy_n"]
    ok = (n > 0) & (gn > 0)
    rate = np.where(ok, gk / np.maximum(gn, 1), 0)
    C = theme_contributions(M, model)
    blocks = (M["T"] // (3 * H)).astype(int)
    res = {}
    for th, c in C.items():
        r = {}
        for side, mask in (("for", ok & (c >= 0.05)), ("against", ok & (c <= -0.05))):
            e = (rate[mask] * n[mask]).sum()
            r[side] = {"meta_hours": int(mask.sum()), "ratio": round(float(k[mask].sum() / e), 3) if e else None}
        fa, ag = ok & (c >= 0.05), ok & (c <= -0.05)
        if fa.sum() and ag.sum():
            ub = np.unique(blocks[ok])
            d = []
            for _ in range(1000):
                bs = rng.choice(ub, len(ub))
                pick = np.concatenate([np.where(blocks == b)[0] for b in bs])
                f, a = pick[fa[pick]], pick[ag[pick]]
                ef, ea = (rate[f] * n[f]).sum(), (rate[a] * n[a]).sum()
                if ef > 0 and ea > 0:
                    d.append(k[f].sum() / ef - k[a].sum() / ea)
            r["difference_ci90"] = [round(float(np.percentile(d, 5)), 3), round(float(np.percentile(d, 95)), 3)]
            r["holds"] = bool(np.percentile(d, 5) > 0)
        res[th] = r
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path, nargs="+")
    ap.add_argument("--write", action="store_true", help="store the result in radar/data/meta_model.json")
    a = ap.parse_args()
    model = mm.EdgeModel.load()
    rng = np.random.default_rng(13)
    out = {p.stem: check(p, model, rng) for p in a.data}
    print(json.dumps(out, indent=1))
    if a.write:
        spec = json.loads(mm.MODEL_PATH.read_text())
        spec.setdefault("validation", {})["reasons_out_of_period"] = out
        mm.MODEL_PATH.write_text(json.dumps(spec, indent=1))


if __name__ == "__main__":
    main()
