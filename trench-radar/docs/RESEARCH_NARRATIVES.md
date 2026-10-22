# What the narrative states predicted

The Narratives view (Metas → Narratives) gives every narrative a state: new, accelerating,
heating, bought, saturating, steady or fading. This page records what those states did on
past data, so they are read as descriptions and not as buy signals.

## Method

`scripts/narrative_backtest.py`, run 2026-10-22 on the two research databases built by
`scripts/tune_metas.py` from Shrine's free hourly archive (see `RESEARCH_TUNING.md`).

- **Walk-forward.** Every hour the narrative read runs exactly as live, as of that hour, on
  data the app could have seen by then. It keeps its own history, as the live app does.
- **Outcome.** Every launch from the hour before that is not yet graduated: did it graduate
  within the next 6 hours? Failed launches count. Factory wallets (10+ launches in 6 hours)
  are left out of both sides, as the live read does.
- **Comparison.** The graduation rate of launches in narratives of each state, minus the
  rate of launches in no narrative during the same hours. The 90% intervals come from
  resampling whole hours (2,000 draws).
- **Weakest form of the read.** The archive has names, tickers and trades only: no
  descriptions, X posts or pictures. The live app also reads those, and this test does not
  cover them.

## Results

Lift is in percentage points against launches outside any narrative.

| State | Sept 16 (24h, 21,174 launches) | Oct 15 (24h, 26,369 launches) |
|---|---|---|
| Outside any narrative (baseline) | 2.08% graduated | 0.35% graduated |
| accelerating | 0.81%, **−1.27** (−1.76 to −0.75) | 0.35%, **0.00** (−0.23 to +0.24) |
| bought | 2.52%, **+0.44** (−0.36 to +1.41) | 1.05%, **+0.70** (+0.27 to +1.10) |
| heating | 1.18%, **−0.90** (−1.45 to −0.33) | 0.57%, **+0.22** (−0.04 to +0.54) |
| new | 1.04%, **−1.04** (−1.41 to −0.63) | 0.40%, **+0.05** (−0.10 to +0.25) |
| saturating | 2.99%, **+0.91** (+0.39 to +1.48) | 0.37%, **+0.01** (−0.23 to +0.28) |
| steady | 2.48%, **+0.40** (−0.57 to +1.47) | 0.50%, **+0.15** (−0.12 to +0.46) |
| fading | 1.77%, −0.31 (113 launches) | 0.00%, −0.35 (106 launches) |

## What this means

- **A launch rush is not an edge for the next launch.** In "accelerating" narratives
  (launches well above their own recent rate), new launches graduated less often in
  September and no more often in October. Most of a rush is copies, and copies split the buyers.
- **Buyers matter more than launches.** "Bought" (buyers up 30%+ on an hour earlier, 20+ buyers,
  launches not accelerating) was above the baseline in both periods, and the only state
  whose interval excluded zero in October ("steady" was also slightly above in both, with
  intervals including zero). That is a small effect over two days of data, and the September
  interval includes zero.
- **States disagree between periods.** Saturating, heating and new flipped sign between
  September and October. Two 24-hour periods cannot separate a real effect from a change in
  market conditions; October's base rate was a sixth of September's.
- **No profit claim.** Graduation is not profit (see `RESEARCH_DATA.md`). Nothing here says
  that buying a token in any state made money.

The app shows these findings next to each narrative's opportunity line and does not use them
to score or rank anything. The states and their thresholds were set before this test and were
not changed afterwards.

## Reproduce

```
python scripts/tune_metas.py --workdir research/          # builds the two databases
python scripts/narrative_backtest.py research/shrine_tune.db research/shrine_test.db \
    --models <data folder>/models --out narratives_backtest.json
```
