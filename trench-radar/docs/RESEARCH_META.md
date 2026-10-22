# Meta recommendation: launch edge vs the readiness score

**Result.** A fitted ranking of metas ("launch edge") picked metas whose next launches graduated
more often than the existing readiness score's picks did:
- on unseen days of the June–July corpus;
- in both of its market regimes;
- in two later months (September and October 2026).

It now orders the metas in the app. The readiness score and verdict stay on every meta as the
baseline.

Three things did **not** hold up:
- **The size of the predicted lift.** It was miscalibrated in the later months, so the app shows
  only a rank and a tier.
- **Launch acceleration on its own.** No reliable edge; see the correction below.
- **The meta's historical success rate.** It added nothing once current activity was known.

Reproduce:

```
python scripts/meta_dataset.py research.db --corpus corpus/ --quant quant/dataset.npz --out meta/meta_corpus.npz
python scripts/meta_dataset.py tune/shrine_tune.db --out meta/meta_sep.npz      # September replay
python scripts/meta_dataset.py tune/shrine_test.db --out meta/meta_oct.npz      # October replay
python scripts/meta_validate.py meta/meta_corpus.npz --outcome grad --out meta/res_grad.json \
    --external meta/meta_sep.npz meta/meta_oct.npz           # also: grad_nf, x2, grad_el
python scripts/meta_fit.py meta/meta_corpus.npz --results meta/res_grad.json --results-nf meta/res_grad_nf.json
```

## The question, the decision time and the target

- **Decision time.** Every hour, T.
- **Candidates.** Every meta the app detects at T, from its own pipeline run unchanged with
  `as_of = T` (`scoring.run_analysis`). The pipeline raises if anything newer than T is read.
  The usual cap of 25 metas is lifted, so the readiness score is not only judged on its own top 25.
- **Outcome.** The meta's launches in (T, T + 6 h], matched by shared name/ticker terms as in the
  existing backtest: did each graduate within 1 h of launch?
- **Comparison.** Against every launch in the same 6 hours. That market-wide rate is common to
  every option at T, so models predict the meta's *lift* over it.

Secondary outcomes:
- the same outcome among non-factory launches (creators with fewer than 10 launches in the
  prior 7 h): the fair comparison for a person launching one coin;
- 2× peak market cap within 15 min;
- graduation of launches still on the curve at 60 s, against the token model's own walk-forward
  prediction for each coin (the coin-level control).

## Data audit

- **Corpus.** June 20 – July 14 2026. 350 hourly decision times; 252 more were skipped because
  their lookback or outcome window touched a collection gap or the July 2–5 break. 10,244
  meta-steps.
- **Starting date.** No graduations exist before June 19, so meta history starts there.
- **Factory launches.** 41% of all launches (329,715) come from creators with 10+ launches in
  7 hours.
- **The market rate is dragged down by factories.** Any detected meta looks good against it. In
  the replays, detected metas beat all launches by 1.2–2 points whether accelerating or not.
  That is why the non-factory outcome matters.
- **Price data is thin.** Only 1,533 of 798k corpus tokens have a 24 h return, so market-cap
  success is measured by the 2× label from trades.
- **No social data.** Neither the corpus nor the replays contain any, so social signals cannot
  be tested and are not in the model. The readiness score still uses them when connected.
- **The replays lack bonding-curve reads.** Net SOL into curves and curve progress are missing
  there and imputed. September and October are therefore a harder test than live use.

## Features, all known at T

| Group | Features (from the readiness evidence) |
|---|---|
| Momentum | launches 1 h and 6 h, acceleration z, share of all launches, growth over the last 3 h vs the 3 before, hours above the baseline, meta age, distinct creators in 1 h |
| Demand | buyers 1 h, buyer share, net SOL into curves, top curve progress, graduations in 24 h, volume, tokens trading, proven-wallet buys |
| Saturation | saturation index, reused tickers, winner's share of volume, buyers per launch, launches outpacing buyers, serial-deployer share |
| Market | market score |
| History | the meta's past graduation and 2× rates over 7 days, 48 h half-life, empirical-Bayes shrunk toward the base rate (strength fitted on training folds only), as log lift; decayed launch count. Factory launches left out. Only launches whose outcome was known at T. |

Missing values are imputed at training medians, with indicators. Features are standardised on
training data. The same code computes them live and in research (`radar/analytics/meta_model.py`),
and a test checks the two give identical numbers.

## Models and validation

- **Walk-forward by day.** Train on every earlier day whose outcome windows had closed (a 7 h
  embargo), test on the next day; 15 test days.
- **Model form.** Binomial L2 logistic regression with the market rate as offset. Penalty chosen
  once on an inner split of the first fold.
- **Baselines:**
  - null (any meta is the market);
  - the readiness score (recalibrated, ranking unchanged);
  - its "favorable" verdict;
  - acceleration z ≥ 2;
  - launch count.
- **Metrics:**
  - log-likelihood gain per 1,000 launches over null;
  - the top-ranked meta per hour: how its next launches graduated against the market (ratio;
    candidates need ≥ 3 next launches to be measurable, the same filter for every model; ties
    broken at random);
  - 90% intervals from a day-block bootstrap, paired between models.

**Promotion rule, fixed before results:**
1. The candidate's top pick beats the readiness score's, with the interval above 0.
2. Its log-likelihood beats both the readiness score and null, with intervals above 0.
3. Both hold in direction in each regime.

### Results: graduation within 1 h, all launches (corpus, unseen days)

| Model | Top meta vs market | Log-lik gain / 1000 launches |
|---|---|---|
| null (random pick) | 0.89× | 0 |
| accelerating (z ≥ 2) | 0.78× | −0.03 |
| readiness "favorable" | 1.16× | +0.24 |
| **readiness score (existing)** | **1.34×** | **+0.55** |
| launch count | 1.48× | +0.28 |
| momentum | 1.45× | +0.13 |
| demand | 1.59× | +1.11 |
| saturation | 1.53× | +1.25 |
| history alone | 1.59× | +1.75 |
| **momentum + demand + saturation + market (launch edge)** | **1.69×** | **+1.42** |
| the same + history | 1.61× | +1.59 |

- **Launch edge vs readiness:** top pick +0.34 (90% interval +0.11 to +0.54); log-likelihood
  +0.87 (+0.24 to +1.53).
- **By regime:** June 25 – July 1, 1.62× vs 1.41×; July 5–14, 1.71× vs 1.30×.
- **The rule is met.**

### Other outcomes (corpus)

| Outcome | Readiness top pick | Launch edge top pick | Difference (90%) |
|---|---|---|---|
| Graduation, non-factory launches | 1.46× | 1.89× | +0.41 (+0.18 to +0.62) |
| 2× within 15 min | 0.98× | 1.11× | +0.13 (+0.06 to +0.19) |
| Graduation after the coin's first minute (vs the token model) | 0.86× | 0.97× | +0.11 (+0.04 to +0.19); random 1.09× |

**After controlling for each coin's first minute, no meta model adds anything.** Every model's
log-likelihood is at or below null. Metas matter *before* a coin exists, because the right meta
draws first-minute buyers. Once a coin's first minute is known, its own trading says more than
its meta (consistent with `RESEARCH_QUANT.md`).

### Historical meta success: tested, not added

- **On its own, history is the strongest single group:** +1.75 log-likelihood, 1.59× top pick.
- **On top of current activity it adds nothing:**
  - log-likelihood +0.18 (−0.02 to +0.38);
  - top pick −0.07 (−0.15 to +0.05);
  - for non-factory launches, −0.05 (−0.30 to +0.19).
- **It also breaks when history is short.** In the September and October replays, with under a
  day of history, models with it fell apart (log-likelihood −40 to −63). The live app is in that
  state for its first week.
- **It is left out of the model.**

### Later months (fitted on the whole corpus, tested once)

| Period, outcome | Readiness top pick | Launch edge top pick | Top-pick difference (90%) | Log-lik difference vs readiness |
|---|---|---|---|---|
| Sep 16, all launches | 1.78× | 3.59× | +1.85 (−0.06 to +3.82) | −3.0 (−5.1 to −1.2) |
| Sep 16, non-factory | 1.88× | 4.86× | +2.96 (+1.05 to +4.80) | +0.4 (−2.6 to +3.2) |
| Oct 15, all launches | 0.97× | 1.38× | +0.42 (+0.08 to +0.83) | −4.7 (−6.3 to −3.4) |
| Oct 15, non-factory | 0.88× | 1.11× | +0.20 (−0.28 to +0.62) | −1.6 (−3.9 to −0.1) |

Each replay covers 18 hours (23 decision times, bootstrap over 3-hour blocks), so these are small
samples:
- **The ranking held** in all four, significantly in two.
- **The probabilities did not:** in three of four, log-likelihood was worse than the readiness
  score's.

Hence the app shows rank and tier ("strongest", "above average", "below average", "weakest"
within the current read), not an expected lift.

### What the model learned

Per standard deviation:

| Feature | Coefficient |
|---|---|
| launches in the last hour | −0.59 |
| tokens trading | +0.47 |
| distinct creators in 1 h | +0.38 |
| reused tickers | −0.28 |
| volume | −0.21 |
| buyers 1 h | −0.17 |
| 3 h growth | −0.13 |
| 6 h launches | −0.12 |
| market | −0.10 |
| acceleration z | +0.10 |

Holding the rest fixed, a meta does better when many different creators are launching into it
and many of its tokens are trading. It does worse when crowded with fresh launches and reused
tickers, or when it has already been growing for hours. Those are signs of a late, saturated meta.

## Correction: accelerating narratives (`RESEARCH_TUNING.md`)

The October result, accelerating narratives' next launches graduating 3.5% vs 2.1% for all
launches, was measured against **all** launches. Other detected metas beat that baseline by
about as much:

| Period | Accelerating minus other detected metas, graduation lift (90%) |
|---|---|
| September 16 | −1.74 points (−3.02 to −0.42) |
| October 15 | +0.65 points (−0.82 to +2.54) |
| Corpus, 348 steps | +0.08 points (−0.02 to +0.21) |

- **The original lift came mostly from comparing named themes with a market full of factory
  spam.** It did not come from acceleration.
- **As a ranking signal on its own, acceleration picked no better than chance** in the corpus
  (0.78× vs null 0.89×).
- **Factory exclusion stays in meta detection.** It still makes the metas cleaner, and the
  launch edge is measured with it.

## Limitations

- **Six weeks plus two 18-hour windows.** The ranking held in every period tested; how large the
  edge is depends on the period (1.38× to 3.59× in the later months).
- **Ranking only.** The predicted lift is not calibrated outside the training period.
- **The candidate filter uses the outcome.** Only metas with ≥ 3 next launches can be scored, the
  same for every model. A meta nobody launches into next has no measurable outcome.
- **Shared launches.** A launch can match several metas, and adjacent hours share outcome
  windows. The day-block bootstrap accounts for the second, not perfectly for the first.
- **Social signals untested.** No historical social data exists here.
- **Graduation is not profit.** The 2× edge is small (1.11×).
- **No coin-level information.** The edge does not tell you how your coin will do once it is
  live. Its first minute does that (the launch-window score).

## Next step

**Re-validate on the app's own data.** Every read stores each meta's edge with its score.
`backtest` (and the System page) now reports the edge model's top pick against the readiness
score's on live history. After a few weeks this tests the ranking under current pump.fun
conditions, with live bonding-curve and social data. That is also where a calibrated lift, or
meta history with enough days behind it, could be re-tested.
