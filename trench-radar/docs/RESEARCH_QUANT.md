# Launch-window score: a quantitative model, validated walk-forward

**Result.** A token's own first minute of trading predicts whether it graduates far better
than any simple baseline. Measures of the *meta* it belongs to, both current momentum and
the historical success of its tokens, add nothing once that first minute is known. On their
own they carry a weak, real signal.

The app ships the token model as the launch score: P(graduates within 1 hour | still on the
curve at 60 s). The meta measures are shown next to it as evidence but are not inputs.

Reproduce (pyarrow and the corpus from `python -m radar corpus-download corpus/`):

```
python scripts/quant_dataset.py corpus/ --out quant/dataset.npz          # about 7 min
python scripts/quant_validate.py quant/dataset.npz --ages 60 300 --out quant/results.json
python scripts/quant_validate.py quant/dataset.npz --ages 60 --labels grad_1h \
    --specs buyers logreg_deploy token_only meta_momentum meta_track --out quant/results_deploy60.json
python scripts/quant_fit.py quant/dataset.npz --results quant/results_deploy60.json --age 60
```

## Data and population

Pump.fun Memecoin Corpus (revision `bd8aed6`, CC BY 4.0): 798,430 launches and 33.6 M trades,
June 5 to July 14 2026, failed tokens included. Its KNOWN_ISSUES rules are applied:
- the non-human address `BwWK17…` is left out of every wallet count;
- trades whose SOL amount disagrees with price × tokens by more than 100× are left out of SOL sums;
- `entry_price_*` columns are never read, because they leak the label.

- **Start date June 19.** No token graduated from June 5 to 17, so outcomes there cannot be labelled.
- **Collection gaps.** 158 hours have no trades at all. Any token whose label window touches one is dropped.
- **Unit.** A token observed at a fixed age A (60 s or 300 s), using only trades at or before
  launch + A. It is *eligible* if it has not graduated by A: a token that already graduated
  cannot be scored, and keeping it would leak the label.
- **Active.** The subpopulation of eligible tokens with at least 3 unique buyers by A.
- **Instant graduations.** Half of all graduations happen within 48 s of launch (median 0.1 s
  from June 24 to July 2), so a 60 s score only covers the 2,159 graduations that came later.

## Outcomes (several horizons)

| Label | Definition |
|---|---|
| grad_5m / grad_15m / grad_1h | graduated within 5 min / 15 min / 1 h of launch (only 1 graduation in the corpus happens after 1 h) |
| x2_15m | peak trade market cap within 15 min ≥ 2× the launch market cap, among tokens below 2× at A |

Graduation is not profit; the 2× label is closer to it. Caveat on x2_15m: a token that touched
2× before A and fell back still counts as positive. The deployed model does not use this label.

## Features (all point-in-time)

The token window (first A seconds) uses the same definitions in the corpus
(`scripts/quant_dataset.py`) and live (`radar/early.py`). A test checks that both give
identical numbers on the same trades.

| Group | Features |
|---|---|
| Activity | log unique buyers, log unique sellers, log trades, buy share of trades, log buy SOL, signed-log net SOL, log price vs launch |
| Manipulation and quality | top buyer's share of buy SOL, log snipers (bought ≤ 3 s), share of buyers who sold ≥ 90 % of what they bought, creator sold (0/1), serial-buyer share (wallets that first-bought ≥ 10 tokens in the prior hour), log proven buyers (wallets with ≥ 2 early buys into tokens that had graduated *before* this moment) |
| Launch | mayhem mode, cashback (both from the CREATE event) |
| Creator | log earlier launches, log launches in the past 24 h, log earlier graduations (all before the launch) |
| Meta momentum | meta = the token's name term with the most launches in the past 6 h; log launches 1 h, launch acceleration z (1 h vs 6 h Poisson), share of all launches, creator concentration, duplicate-name share, log first-minute buyers across the meta's tokens |
| Meta track record | the meta's graduation and 2× rates over the past 7 days among outcomes *already known*, shrunk toward the base rate by empirical Bayes (beta prior, strength fitted by method of moments: k = 168), as log lift over the base rate; log matured count |

**Cohort normalisation.** `base_logit` is the logit of the same outcome's rate in the same
population over the trailing 24 h, among launches whose outcome was already known. It carries
the regime: graduation rates moved by more than 10× inside the sample. Every model gets it as
an input, and the "base" model is this rate alone.

**Missing values.** Median imputation from the training fold, plus an indicator for any feature
missing in more than 0.1% of training rows.
**Scaling.** Standardised on training-fold statistics.

## Models compared

| Model | What |
|---|---|
| base | cohort base rate only |
| buyers | base + unique buyers (the obvious single signal) |
| formula | transparent baseline: equal-weight sum of z-scores with signs fixed in advance (no fitting), mapped to a probability by a 1-D logistic fit |
| logreg_token / token_only | L2 logistic regression on activity, manipulation, launch and creator features |
| logreg_meta, meta_momentum, meta_track | the meta features alone (both halves, momentum only, track record only) |
| logreg_full / logreg_deploy | token and meta features together |
| hazard_full | discrete-time survival model (intervals to 5 min / 15 min / 1 h), all features |

## Validation

- **Walk-forward by UTC day.** Train on every earlier day, with a 1 h embargo so no training
  label overlaps the test day; test on that day; repeat.
- **Training floor.** At least 6 training days.
- **λ.** Chosen once on an inner split (the last 3 training days of the first fold), then frozen.
- **Uncertainty.** Day-block bootstrap (resamples whole days, 90% intervals), with paired
  comparisons between models.
- **Within-day AUC.** The event-weighted AUC inside each day: how well the score ranks
  launches against each other on the same day. This is what the score is used for. Pooled AUC
  also rewards tracking the day's base rate.

### Graduate within 1 h, scored at 60 s (the shipped target)

Eligible population: 491,345 token-minutes; 18 test days; 2,088 test events.

| Model | Pooled AUC (90% CI) | Within-day AUC | Avg precision | Brier skill | Calib. intercept / slope | Lift top 10% / 1% |
|---|---|---|---|---|---|---|
| base | 0.753 (0.661–0.833) | 0.473 | 0.011 | 0 | +0.13 / 0.98 | 2.4 / 2.1 |
| buyers | 0.878 (0.840–0.911) | 0.800 | 0.036 | +0.010 | +0.12 / 0.96 | 5.9 / 11.0 |
| meta_momentum | 0.789 (0.715–0.855) | 0.594 | 0.014 | +0.001 | | 2.9 / 2.1 |
| meta_track | 0.779 (0.701–0.847) | 0.577 | 0.014 | +0.001 | | 2.9 / 3.6 |
| logreg_deploy (token + meta) | 0.954 (0.945–0.960) | 0.927 | 0.141 | +0.075 | −0.13 / 1.01 | 9.0 / 30.5 |
| **token_only (shipped)** | **0.954 (0.945–0.960)** | **0.928** | **0.142** | **+0.077** | **−0.11 / 1.01** | **9.0 / 30.6** |

- **Active population** (≥ 3 buyers by 60 s; 145,204 rows): token_only scores 0.925, within-day
  0.872, against 0.555 for buyers alone.
- **Against baselines.** The model beats the base rate and buyers-only in 100% of paired
  bootstrap draws, on AUC and log loss alike.
- **Calibration.** A slope near 1 and an intercept near 0 mean the probabilities can be read as
  probabilities when the base rate is known.

### Other ages and horizons (eligible)

| Age, label | base | buyers | formula | token logreg | token + meta | hazard |
|---|---|---|---|---|---|---|
| 60 s, grad_5m | 0.466 | 0.805 | 0.758 | 0.936 | 0.935 | 0.935 |
| 60 s, grad_15m | 0.475 | 0.802 | 0.760 | 0.935 | 0.934 | 0.934 |
| 300 s, grad_15m | 0.472 | 0.869 | 0.755 | 0.965 | 0.966 | 0.966 |
| 300 s, grad_1h | 0.470 | 0.864 | 0.752 | 0.968 | 0.969 | 0.969 |
| 300 s, x2_15m | 0.496 | 0.884 | 0.700 | 0.964 | 0.964 | n/a |

These are within-day AUCs. At 300 s the token model's lift in the top 1% is 60× the base rate,
with Brier skill +0.110 and calibration slope 1.00.

**Meta adds nothing.** With and without the meta features, every metric agrees within 0.001–0.003
at every age and horizon. The survival model also matches the logistic model, so the
simpler model ships.

**Transparent formula.** It beats the base rate and buyers-only on pooled AUC, but trails the
fitted model by 0.17–0.26 within-day AUC. Hand-set equal weights leave most of the signal unused.

### By regime: where the numbers come from

| Test days | Events | base | buyers | token_only |
|---|---|---|---|---|
| Jun 25 – Jul 1 (instant-buyout period) | 55 | 0.44 | 0.68 | 0.75 |
| Jul 2 – Jul 14 | 2,033 | 0.47 | 0.80 | 0.93 |

97% of test events fall in the last 11 days. In the instant-buyout week the model still beats
the baselines, but on 55 events the interval is wide and the AUC is around 0.75. Expect the
live figure to depend on how pump.fun launches are behaving.

## The shipped model

`radar/data/quant_model.json` (version `quant-v1-a60-20261022`).
- **Fit.** All eligible tokens from June 19 to July 14: 491,345 rows, 2,140 graduations within 1 h. λ = 100.
- **Score.** p = σ(−8.16 + Σ βⱼ·zⱼ), where zⱼ is the feature standardised on the training data.
  Coefficients are per standard deviation:

| Feature | β | Feature | β |
|---|---|---|---|
| mayhem mode | +1.058 | earlier launches by creator | −0.216 |
| log trades | +0.954 | cashback | −0.195 |
| cohort base rate (logit) | +0.868 | creator's earlier graduations | +0.170 |
| log proven buyers | +0.526 | serial-buyer share | −0.137 |
| net SOL inflow | +0.413 | snipers | −0.053 |
| buyers who dumped | −0.310 | buy share of trades | −0.052 |
| log unique sellers | −0.270 | log buy SOL | +0.047 |
| creator sold | −0.264 | log unique buyers | +0.032 |
| creator launches in 24 h | −0.249 | price vs launch | +0.019 |

Missing-value indicators: buy share +0.142, top buyer share +0.192, dumped share −0.094,
serial share −0.094. These mostly mark tokens with no trades at all.

Reading the coefficients:
- Raw buyer count barely matters once trades, sellers and inflow are known.
- Tokens that attract wallets with a record of early buys into graduates do better.
- Serial deployers, creators who sell, and buyers who flip right away all lower the odds.
- Mayhem tokens graduated 2× as often as other tokens on June 19 – July 1 and 6× as often on
  July 2 – 14. The direction is stable; the size depends on the regime.

## Live

- **Capture.** `radar/early.py` closes each launch window at 60 s, 5 min and 15 min for every
  token the chain stream saw being born, and writes the measurements to `token_early`.
  - At 60 s it also writes the score.
  - Tokens that graduated before the window closed get no row.
  - Graduations credit the token's first-minute buyers in `wallet_credits`, the live source of
    "proven buyers".
- **Display.** The token dossier shows the score, its multiple of the current base rate, the
  measurements and the meta's momentum and track record.
- **Base rate.** It is learned live from tokens whose 1 h outcome is known. Until it rests on
  2,000 matured launches (about 3–4 h of stream), the score is labelled a ranking only.

## Limitations

- **Six weeks of one platform.** The corpus covers June–July 2026. pump.fun changed mechanics
  inside it (mayhem rollout, instant buyouts), and live behaviour in October may differ again.
  Coefficients tied to mechanics (mayhem, cashback) are the most likely to drift.
- **Warm-up.** Proven buyers and creator history start from zero when the app is installed and
  build up as it runs. In the corpus they had up to 25 days of history. Early live scores
  under-use these features.
- **Coverage.** Scores exist only for tokens whose launch the app saw. A gap in the stream leaves
  holes in every rolling count.
- **Graduation is not profit.** A high score says the token is likely to fill its curve, not that
  buying it at 60 s makes money. Earlier work (`RESEARCH_DATA.md`) found no early signal that
  paid at detection.
- **Not a launch recommendation.** The score ranks tokens already launched by their first minute
  of trading. It does not say which meta to launch into. The meta measures that would answer
  that question were weak here: within-day AUC 0.58–0.59 on their own, nothing on top.
- **x2_15m label overlap.** Pre-A peaks count as positives (see Outcomes).

## Strongest next improvement

**Re-validate on the app's own live data.** Every 60 s row in `token_early` is a frozen,
point-in-time prediction, and its outcome is known an hour later. After a few weeks of running,
the same walk-forward evaluation on those rows tests the model under current pump.fun
mechanics, with the live stream's exact feature pipeline. That is the only test that can
confirm or retire this model.

## Reference repositories reviewed

- **HyperFrequency/skills** (no licence file found) and **shakeebshaan/claude-code-quant-skills** (MIT):
  - Adopted: walk-forward validation, an embargo between train and test, reporting against naive
    baselines, block bootstrap.
  - Not adopted: Optuna-style hyperparameter search and AutoML. With about 2,000 positive
    events they would overfit.
- **HKUDS/Vibe-Trading** (MIT): its look-ahead and overfitting checks informed the point-in-time
  tests. Its trading backtests and tearsheets do not apply, because nothing here trades.
- **wshobson/agents** (MIT): general agent definitions, nothing specific used.

No code was copied from any of them.
