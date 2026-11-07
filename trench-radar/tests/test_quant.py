"""The statistics behind the quantitative score, checked on synthetic data with known answers."""
import numpy as np

from radar.analytics import quant as Q


def test_logreg_recovers_known_coefficients():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(20000, 3))
    true = np.array([-2.0, 1.0, -0.5, 0.0])
    y = (rng.random(20000) < Q.sigmoid(true[0] + X @ true[1:])).astype(float)
    b = Q.fit_logreg(X, y, lam=0.0)
    assert np.allclose(b, true, atol=0.08)
    # a strong penalty shrinks the slopes but never the intercept toward zero
    bs = Q.fit_logreg(X, y, lam=1e6)
    assert np.all(np.abs(bs[1:]) < 0.01) and abs(Q.sigmoid(bs[0]) - y.mean()) < 0.01


def test_offset_is_respected():
    rng = np.random.default_rng(1)
    off = rng.normal(size=5000)
    y = (rng.random(5000) < Q.sigmoid(off)).astype(float)
    b = Q.fit_logreg(np.zeros((5000, 0)), y, lam=0.0, offset=off)
    assert abs(b[0]) < 0.1


def test_auc_matches_pairwise_definition():
    rng = np.random.default_rng(2)
    y = rng.random(400) < 0.2
    s = rng.integers(0, 20, 400).astype(float) + y * 3          # ties on purpose
    pos, neg = s[y], s[~y]
    brute = ((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg))
    assert abs(Q.auc(y, s) - brute) < 1e-12
    assert Q.auc(y, s) > 0.5 and abs(Q.auc(y, -s) - (1 - Q.auc(y, s))) < 1e-12


def test_metrics_on_perfect_and_uninformative_scores():
    y = np.array([0, 0, 1, 1, 0, 1], float)
    assert Q.auc(y, y) == 1.0 and Q.average_precision(y, y) == 1.0
    p = np.full(6, 0.5)
    assert abs(Q.brier(y, p) - 0.25) < 1e-12 and abs(Q.logloss(y, p) - np.log(2)) < 1e-12


def test_calibration_of_a_calibrated_model():
    rng = np.random.default_rng(3)
    p = Q.sigmoid(rng.normal(-2, 1, 50000))
    y = (rng.random(50000) < p).astype(float)
    c = Q.calibration(y, p)
    assert abs(c["intercept"]) < 0.05 and abs(c["slope"] - 1) < 0.05
    c2 = Q.calibration(y, Q.sigmoid(2 * Q.logit(p)))              # overconfident: slope below 1
    assert c2["slope"] < 0.6


def test_hazard_model_gives_consistent_cumulative_probabilities():
    rng = np.random.default_rng(4)
    n = 30000
    x = rng.normal(size=(n, 1))
    cuts = [300.0, 900.0, 3600.0]
    t = np.full(n, np.nan)
    surv = np.ones(n, bool)
    for k, hi in enumerate(cuts):
        h = Q.sigmoid(-3 + 0.3 * k + 0.8 * x[:, 0])
        ev = surv & (rng.random(n) < h)
        t[ev] = hi - 1
        surv &= ~ev
    b = Q.fit_hazard(x, t, cuts, lam=0.0)
    assert abs(b[-1] - 0.8) < 0.08
    P = Q.hazard_cumulative(b, x, cuts)
    assert np.all(np.diff(P, axis=1) >= -1e-12)                  # monotone in the horizon
    for k, hi in enumerate(cuts):                                # matches the observed share
        assert abs(P[:, k].mean() - (~np.isnan(t) & (t <= hi)).mean()) < 0.01


def test_prep_imputes_from_training_and_flags_missing():
    X = np.array([[1.0, np.nan], [3.0, 2.0], [5.0, 4.0]])
    pr = Q.Prep().fit(X, ["a", "b"])
    Z = pr.transform(np.array([[np.nan, np.nan]]))
    assert pr.out_names == ["a", "b", "b_missing"]
    assert Z.shape == (1, 3) and abs(Z[0, 0]) < 1e-9             # imputed at the training median (= mean here)


def test_shrinkage_toward_the_base_rate():
    assert Q.shrunk_rate(0, 0, 0.01, 50) == 0.01
    assert abs(Q.shrunk_rate(5, 10, 0.01, 50) - (5 + 0.5) / 60) < 1e-12
    rng = np.random.default_rng(5)
    true = rng.beta(2, 198, 500)                                 # between-meta spread around 1%
    n = rng.integers(20, 400, 500)
    s = rng.binomial(n, true)
    k = Q.fit_beta_strength(s.astype(float), n.astype(float), np.full(500, 0.01))
    assert 50 < k < 600                                          # true strength 200 (alpha+beta)


def test_weighted_metrics_match_resampling():
    rng = np.random.default_rng(6)
    y = (rng.random(3000) < 0.1).astype(float)
    s = np.round(rng.normal(size=3000) + y, 1)                   # ties on purpose
    S = Q.Sorted(y, s)
    assert abs(S.auc(np.ones(3000)) - Q.auc(y, s)) < 1e-12
    su = s + rng.random(3000) * 1e-6                            # untied copy: AP is order-defined
    assert abs(Q.Sorted(y, su).ap(np.ones(3000)) - Q.average_precision(y, su)) < 1e-9
    w = rng.integers(0, 3, 3000).astype(float)                   # integer weights = duplicated rows
    rep = np.repeat(np.arange(3000), w.astype(int))
    assert abs(S.auc(w) - Q.auc(y[rep], s[rep])) < 1e-12
    p = Q.sigmoid(s - 2)
    assert abs(Q.weighted_logloss(y, p, w) - Q.logloss(y[rep], p[rep])) < 1e-12
    out, draws = Q.day_bootstrap(rng.integers(0, 20, 3000), y, {"a": s, "b": -s}, iters=50)
    assert out["a"]["auc"][1] <= out["a"]["auc"][0] <= out["a"]["auc"][2] and out["b"]["auc"][0] < 0.5


def test_damped_newton_is_stable_on_rare_near_separable_data():
    rng = np.random.default_rng(8)
    n = 200000
    X = rng.normal(size=(n, 6))
    X[:, 5] = X[:, 0] * 0.999 + rng.normal(scale=0.01, size=n)          # nearly collinear
    z = -7 + 2.5 * X[:, 0] + 1.0 * X[:, 1]
    y = (rng.random(n) < Q.sigmoid(z)).astype(float)                    # ~0.5% events
    b = Q.fit_logreg(X, y, lam=10.0)
    assert np.all(np.isfinite(b)) and np.abs(b[1:]).max() < 6
    assert Q.auc(y, Q.predict_logreg(b, X)) > 0.9
