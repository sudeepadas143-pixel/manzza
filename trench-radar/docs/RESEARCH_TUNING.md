# Tuning meta detection out of sample

> **Correction (2026-10-22, `RESEARCH_META.md`).** The October lift below was measured against
> *all* launches, a baseline dragged down by launch-factory spam. Other detected metas beat it
> by about as much: accelerating minus other metas was −1.74 pts in September (90% −3.02 to
> −0.42), +0.65 in October (−0.82 to +2.54) and +0.08 in the June–July corpus (−0.02 to +0.21).
> Acceleration itself has no reliable edge. Excluding factory creators from detection is kept;
> the claim that it made *accelerating* narratives graduate more often is withdrawn.

**Change made:** narrative detection now ignores launches by creators with 10+ launches in the
7-hour lookback (`metas.SPAM_MODE = "exclude"`). Launch factories (two wallets made ~700 of
3,000 launches in one hour) were drowning out real narratives.

Reproduce: `python scripts/tune_metas.py --workdir research/` (Shrine archive, ~17 GB of download).

## Method

- Data: Shrine's free hourly archive, replayed as a live run would have seen it. Tuning period
  2026-09-16 00:00–18:00 UTC; test period 2026-10-15 00:00–18:00 UTC (each with 7 h before for
  the baseline and 12 h after for outcomes). Every launch is labelled, failed ones included.
- Graduation: the archive's own graduation events, plus a token's first PumpSwap trade (the
  September archive lacks most graduation events; only tokens whose launch the replay saw).
- The app's walk-forward backtest, hourly steps, 6-hour follow window, 6-hour horizon. 90%
  intervals from a 3-hour block bootstrap.
- Three variants: count every launch (old), count distinct creators, exclude factory creators.
  The variant was **chosen on September only**; October was run once afterwards.

## Results: graduation lift of accelerating narratives (z ≥ 2) over all launches

| Variant | September (tuning) | October (test) |
|---|---|---|
| Count every launch (old) | +0.58 pts (−0.60 to +1.52) | +0.41 pts (−0.16 to +1.07) |
| Distinct creators | +0.79 pts (−0.08 to +1.86) | +1.31 pts (+0.42 to +2.38) |
| **Exclude factory creators (chosen)** | **+1.25 pts (+0.22 to +2.48)** | **+1.45 pts (+0.76 to +2.10)** |

October, chosen variant: accelerating narratives' next launches graduated 3.5% of the time
against 2.1% for all launches in the same windows.

## Caveats

- One 18-hour window per period, about 100 accelerating signals each. It is a real
  out-of-sample confirmation, but a small one; more periods would make it firmer.
- It is about graduation, not profit. The corpus backtest (`RESEARCH_CORPUS.md`) found
  favorable calls were *less* often net positive; nothing here changes that.
- The overall score is still "not validated": the corpus backtest result stands, and the score
  weights were not changed.
