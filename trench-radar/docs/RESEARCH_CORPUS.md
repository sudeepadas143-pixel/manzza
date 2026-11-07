# Backtest on the Pump.fun Memecoin Corpus

**Result: the readiness score is not validated, and it showed no edge on this history.**
Narratives called *favorable* went on to produce tokens that graduated no more often than
any launch in the same hours, and were less often net positive.

Reproduce: `python -m radar corpus-download corpus/ && python -m radar corpus-build corpus/
--db research.db && python -m radar corpus-backtest --db research.db --step-hours 3`
(needs pyarrow; about 6 GB of download, 2 minutes to build, 8 minutes to run).

## Data

Pump.fun Memecoin Corpus (huggingface.co/datasets/jocry/Pumpfun_Memecoin_Corpus, revision
`bd8aed6`, CC BY 4.0): every pump.fun launch seen between 2026-06-05 and 2026-07-14.

| Check | Result |
|---|---|
| Launches / graduations | 798,430 / 5,689 (0.71%) |
| Trades | 33,581,765 (matches the corpus README) |
| Trades by the non-human address BwWK17… excluded from wallet counts | 6,690,901 (matches KNOWN_ISSUES §3.3 to the row) |
| Trades left out of SOL sums (amount inconsistent or price missing, §3.1–3.2) | 3,496,382 (= 1,136,321 + 2,360,061, as documented) |
| `graduated_at` vs `migrations.migrated_at` | identical to the second for all 5,689 (the files use different UTC offsets; both convert correctly) |
| Graduation before launch | 0 |
| **Collection gaps** | **192 of 943 hours have no launch at all, in 10 runs (longest 48 h)** |

The README describes the collection as uninterrupted and KNOWN_ISSUES lists only the Jul 3
outage. pump.fun never goes an hour without a launch, so every empty hour is treated as an
outage: the backtest finds them from the data and skips any step whose 7-hour lookback or
6-hour follow window touches one (107 of 312 steps).

## Method

The app's own walk-forward backtest (`radar/analytics/backtest.py`) on a separate research
database. Every 3 hours the full scoring is re-run *as of* that moment, reading only rows that
existed then; a step that reads anything newer is discarded (none were). For each narrative,
the label is how its launches in the next 6 hours fared within 24 hours, against **all**
launches in the same 6 hours, failed and abandoned tokens included:

- *graduation lift*: the narrative's graduation rate minus the all-launch rate;
- *net-positive lift*: the same for the share of tokens whose price 24 h later (on the curve)
  was above the first trade by more than a 3% round-trip cost.

Point-in-time checks on the research database: tokens seen before launch 0, graduations
before launch 0, hourly rows before their token existed 0, outcomes evaluated before their
horizon 0.

## Results (205 steps, 4,155 narrative signals)

| Verdict | Signals | Graduation lift | 90% lower bound | Beat the base rate | Net-positive lift |
|---|---|---|---|---|---|
| Favorable | 115 | −0.02 pts | −0.32 pts | 37% (63% false positives) | **−22.1 pts** |
| Mixed | 1,065 | +0.04 pts | −0.11 pts | 22% | −3.1 pts |
| Unfavorable | 2,427 | −0.05 pts | −0.15 pts | 7% | −4.6 pts |
| Insufficient data | 548 | −0.43 pts | −0.67 pts | 4% | −2.9 pts |

Rank correlation between score and graduation lift: −0.03.

Launch acceleration on its own (the attention part of the score):

| Narrative launches in the last hour vs the 6 before | Signals | Later graduation rate | All launches | Lift (90% interval) |
|---|---|---|---|---|
| Accelerating (z ≥ 2) | 1,157 | 0.57% | 0.67% | −0.11 pts (−0.23 to +0.03) |
| Flat (0 ≤ z < 2) | 492 | 0.82% | 0.76% | +0.06 pts (−0.12 to +0.23) |
| Cooling (z < 0) | 2,471 | 0.63% | 0.72% | −0.10 pts (−0.21 to +0.04) |

## What it means

1. **No edge on graduation.** Whether a narrative was accelerating, or scored favorable,
   made no measurable difference to whether its next launches graduated.
2. **Favorable calls were worse on price.** Tokens in favorable narratives were 22 points
   less often net positive. That fits the Solana Memecoin Dataset check
   (`RESEARCH_DATA.md`): the demand signals the score rewards (heavy, one-sided buying) tend to
   mark late entries near a top.
3. **What this test could not see.** The corpus has no social data and none of the stream's
   wallet signals (proven/labelled wallets, bot filtering, launch-block buyers, X posts linked
   in metadata), so those parts are untested here. The semantic grouping was off (lexical
   narratives only). Hourly rows need 3+ buyers. Five regime changes inside the window
   (KNOWN_ISSUES §5) and 20% missing hours make this one noisy 39-day sample, not a verdict
   for all time.

## What to do with it

The dashboard keeps showing scores as *not validated*, now with this backtest named. The
score weights were **not** changed to fit these results: tuning on the same history it is
tested on would only manufacture a validation. A fair next step is to fit any new weighting
on June and test it on July (or on fresh data from the live stream), and to test the wallet
signals once enough live history exists.
