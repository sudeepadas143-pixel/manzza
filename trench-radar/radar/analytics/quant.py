"""Small, dependency-free statistics for the quantitative score (docs/RESEARCH_QUANT.md).

L2-regularised logistic regression fitted by Newton's method, a discrete-time hazard model
for time-to-event outcomes, and the evaluation metrics used in walk-forward validation.
NumPy only, so the fitted model can run inside the app and the exe.
"""
from __future__ import annotations

import math

import numpy as np


# ---------------------------------------------------------------- preprocessing
class Prep:
    """Median imputation with missing indicators, then standardisation, all fitted on training
    rows only. Indicators are kept only for columns that actually had missing values in training."""

    def fit(self, X: np.ndarray, names: list[str]) -> "Prep":
        self.names = list(names)
        miss = np.isnan(X)
        self.med = np.nanmedian(np.where(miss.all(0), 0, X), axis=0)
        self.med = np.where(np.isnan(self.med), 0, self.med)
        self.ind = [j for j in range(X.shape[1]) if miss[:, j].mean() > 0.001]
        Z = self._fill(X)
        self.mu = Z.mean(0)
        self.sd = Z.std(0)
        self.sd[self.sd < 1e-9] = 1.0
        return self

    def _fill(self, X):
        Z = np.where(np.isnan(X), self.med, X)
        if self.ind:
            Z = np.hstack([Z, np.isnan(X[:, self.ind]).astype(float)])
        return Z

    def transform(self, X):
        return (self._fill(X) - self.mu) / self.sd

    @property
    def out_names(self):
        return self.names + [f"{self.names[j]}_missing" for j in self.ind]


# ---------------------------------------------------------------- models
def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


def logit(p, eps=1e-6):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def fit_logreg(X: np.ndarray, y: np.ndarray, lam: float = 1.0, offset: np.ndarray | None = None,
               w: np.ndarray | None = None, iters: int = 50) -> np.ndarray:
    """Penalised maximum likelihood: sum w*loglik - lam/2 * ||beta[1:]||^2 (intercept unpenalised).
    Returns [intercept, coefficients...]."""
    n, k = X.shape
    A = np.hstack([np.ones((n, 1)), X])
    off = np.zeros(n) if offset is None else offset
    w = np.ones(n) if w is None else w
    b = np.zeros(k + 1)
    b[0] = logit(np.clip(np.average(y, weights=w), 1e-4, 1 - 1e-4))
    P = np.eye(k + 1) * lam
    P[0, 0] = 0.0

    def objective(beta):
        z = A @ beta + off
        # log-likelihood, written to stay finite for large |z|
        ll = np.sum(w * (y * z - np.logaddexp(0, z)))
        return ll - 0.5 * beta @ P @ beta

    cur = objective(b)
    for _ in range(iters):
        p = sigmoid(A @ b + off)
        g = A.T @ (w * (y - p)) - P @ b
        Hm = (A * (w * p * (1 - p))[:, None]).T @ A + P
        step = np.linalg.solve(Hm + 1e-9 * np.eye(k + 1), g)
        # damped Newton: halve the step until the penalised likelihood improves (rare events and
        # near-separable features make full steps overshoot)
        t = 1.0
        while t > 1e-4:
            nb = b + t * step
            new = objective(nb)
            if new >= cur - 1e-10:
                break
            t *= 0.5
        b, done = nb, abs(new - cur) < 1e-8 * (1 + abs(cur))
        cur = new
        if done or np.max(np.abs(t * step)) < 1e-7:
            break
    return b


def predict_logreg(b: np.ndarray, X: np.ndarray, offset: np.ndarray | None = None) -> np.ndarray:
    z = b[0] + X @ b[1:]
    if offset is not None:
        z = z + offset
    return sigmoid(z)


# discrete-time hazard: one row per token per interval at risk; the hazard of graduating in each
# interval is logistic in the covariates plus an interval baseline
def hazard_rows(X: np.ndarray, t_event: np.ndarray, cuts: list[float]):
    """cuts are interval ends after the observation time, e.g. [300, 900, 3600] seconds from
    launch. t_event = seconds to the event from launch (nan = no event, observed to the last cut)."""
    rows, ys, ks = [], [], []
    lo = None
    for k, hi in enumerate(cuts):
        at_risk = np.isnan(t_event) | (t_event > (cuts[k - 1] if k else -np.inf))
        idx = np.where(at_risk)[0]
        ev = (~np.isnan(t_event[idx])) & (t_event[idx] <= hi)
        rows.append(idx); ys.append(ev.astype(float)); ks.append(np.full(len(idx), k))
        lo = hi
    idx = np.concatenate(rows)
    D = np.zeros((len(idx), len(cuts)))
    D[np.arange(len(idx)), np.concatenate(ks)] = 1.0
    return np.hstack([D[:, 1:], X[idx]]), np.concatenate(ys)


def fit_hazard(X, t_event, cuts, lam=1.0):
    Xh, yh = hazard_rows(X, t_event, cuts)
    return fit_logreg(Xh, yh, lam)


def hazard_cumulative(b, X, cuts) -> np.ndarray:
    """P(event by each cut) for every row: 1 - prod(1 - h_k). Shape (n, len(cuts))."""
    n = X.shape[0]
    surv = np.ones(n)
    out = np.zeros((n, len(cuts)))
    for k in range(len(cuts)):
        d = np.zeros(len(cuts) - 1)
        if k:
            d[k - 1] = 1.0
        h = sigmoid(b[0] + d @ b[1:len(cuts)] + X @ b[len(cuts):])
        surv = surv * (1 - h)
        out[:, k] = 1 - surv
    return out


# ---------------------------------------------------------------- metrics
def auc(y, s):
    """Rank-based ROC AUC with ties averaged."""
    y = np.asarray(y, bool)
    npos, nneg = y.sum(), (~y).sum()
    if npos == 0 or nneg == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ss = s[order]
    ranks = np.empty(len(s))
    i = 0
    r = np.arange(1, len(s) + 1, dtype=float)
    # average ranks of ties
    starts = np.r_[0, np.where(np.diff(ss) != 0)[0] + 1]
    ends = np.r_[starts[1:], len(ss)]
    avg = (r[starts] + r[ends - 1]) / 2
    ranks[order] = np.repeat(avg, ends - starts)
    del i
    return float((ranks[y].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def average_precision(y, s):
    y = np.asarray(y, bool)
    if y.sum() == 0:
        return float("nan")
    order = np.argsort(-s, kind="mergesort")
    yy = y[order]
    tp = np.cumsum(yy)
    prec = tp / np.arange(1, len(yy) + 1)
    return float(prec[yy].sum() / y.sum())


def brier(y, p):
    return float(np.mean((p - y) ** 2))


def logloss(y, p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration(y, p):
    """Calibration intercept (calibration-in-the-large, slope fixed at 1) and slope: 0 and 1
    are perfect. Fitted by logistic regression of the outcome on logit(p)."""
    z = logit(p)
    slope_fit = fit_logreg(z[:, None], y, lam=0.0)
    inter = fit_logreg(np.zeros((len(y), 0)), y, lam=0.0, offset=z)
    return {"intercept": float(inter[0]), "slope": float(slope_fit[1])}


def reliability(y, p, bins=10):
    """Mean prediction against observed rate in equal-count bins of the prediction."""
    order = np.argsort(p)
    out = []
    for chunk in np.array_split(order, bins):
        if len(chunk):
            out.append({"n": int(len(chunk)), "pred": float(p[chunk].mean()), "obs": float(y[chunk].mean())})
    return out


def lift_at(y, s, frac=0.1):
    """Event rate in the top `frac` of scores divided by the overall rate."""
    k = max(1, int(len(s) * frac))
    top = np.argsort(-s)[:k]
    base = y.mean()
    return float(y[top].mean() / base) if base > 0 else float("nan")


def summary(y, p):
    y = np.asarray(y, float)
    return {"n": int(len(y)), "events": int(y.sum()), "rate": float(y.mean()), "auc": auc(y, p),
            "ap": average_precision(y, p), "brier": brier(y, p), "logloss": logloss(y, p),
            "lift10": lift_at(y, p, 0.1), "lift1": lift_at(y, p, 0.01), **calibration(y, p)}


class Sorted:
    """Scores sorted once, so weighted AUC and average precision cost O(n) per bootstrap draw.
    A day-block bootstrap is a set of integer row weights (how often each day was drawn)."""

    def __init__(self, y, s):
        o = np.argsort(s, kind="mergesort")
        self.o, self.y, self.s = o, np.asarray(y, float)[o], np.asarray(s, float)[o]
        self.starts = np.r_[0, np.where(np.diff(self.s) != 0)[0] + 1]   # tie groups (ascending)

    def auc(self, w):
        w = w[self.o]
        wp, wn = w * self.y, w * (1 - self.y)
        gp, gn = np.add.reduceat(wp, self.starts), np.add.reduceat(wn, self.starts)
        below = np.cumsum(gn) - gn                     # negative weight strictly below each group
        P, N = gp.sum(), gn.sum()
        return float((gp * (below + 0.5 * gn)).sum() / (P * N)) if P > 0 and N > 0 else float("nan")

    def ap(self, w):
        w = w[self.o][::-1]
        yy = self.y[::-1]
        tp = np.cumsum(w * yy)
        allw = np.cumsum(w)
        P = tp[-1]
        return float((w * yy * tp / np.maximum(allw, 1e-12)).sum() / P) if P > 0 else float("nan")


def weighted_logloss(y, p, w):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-(w * (y * np.log(p) + (1 - y) * np.log(1 - p))).sum() / w.sum())


def day_bootstrap(day: np.ndarray, y: np.ndarray, preds: dict[str, np.ndarray], iters=1000, seed=7):
    """Resample whole days with replacement. Returns per model {metric: (point, lo5, hi95)} and the
    raw draws, so pairs of models can be compared draw by draw (paired bootstrap)."""
    rng = np.random.default_rng(seed)
    days, inv = np.unique(day, return_inverse=True)
    S = {k: Sorted(y, p) for k, p in preds.items()}
    draws = {k: {"auc": [], "ap": [], "logloss": []} for k in preds}
    for _ in range(iters):
        cnt = np.bincount(rng.integers(0, len(days), len(days)), minlength=len(days)).astype(float)
        w = cnt[inv]
        if (w * y).sum() == 0:
            continue
        for k, p in preds.items():
            draws[k]["auc"].append(S[k].auc(w)); draws[k]["ap"].append(S[k].ap(w)); draws[k]["logloss"].append(weighted_logloss(y, p, w))
    ones = np.ones(len(y))
    out = {}
    for k, p in preds.items():
        point = {"auc": S[k].auc(ones), "ap": S[k].ap(ones), "logloss": weighted_logloss(y, p, ones)}
        out[k] = {m: (point[m], float(np.nanpercentile(draws[k][m], 5)), float(np.nanpercentile(draws[k][m], 95))) for m in point}
    return out, draws


def shrunk_rate(successes, n, prior_rate, k):
    """Beta-binomial (empirical Bayes) estimate: the meta's past success rate pulled toward the
    cohort base rate with the weight of k pseudo-observations."""
    return (successes + k * prior_rate) / (n + k)


def fit_beta_strength(successes: np.ndarray, n: np.ndarray, rates: np.ndarray) -> float:
    """Method-of-moments prior strength k for shrinking per-meta rates toward the base rate:
    k = p(1-p)/var_between - 1, where var_between is the excess variance of observed rates
    over binomial noise. Floors at 1."""
    m = n > 0
    if m.sum() < 30:
        return 50.0
    obs = successes[m] / n[m]
    p = np.clip(rates[m], 1e-6, 1 - 1e-6)
    resid = (obs - p) ** 2 - p * (1 - p) / n[m]
    var_b = max(np.average(resid, weights=n[m]), 1e-9)
    pbar = float(np.average(p, weights=n[m]))
    return float(max(1.0, pbar * (1 - pbar) / var_b - 1))


def signed_log1p(x):
    return np.sign(x) * np.log1p(np.abs(x))


def safe_div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0, a / np.where(b > 0, b, 1), np.nan)


__all__ = ["Prep", "fit_logreg", "predict_logreg", "fit_hazard", "hazard_cumulative", "hazard_rows", "auc",
           "average_precision", "brier", "logloss", "calibration", "reliability", "lift_at", "summary",
           "day_bootstrap", "Sorted", "weighted_logloss", "shrunk_rate", "fit_beta_strength", "sigmoid", "logit", "signed_log1p", "safe_div", "math"]
