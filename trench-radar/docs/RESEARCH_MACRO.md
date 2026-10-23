# Macro, intraday, rotation and meta health

The **Macro · Today** view of the Meta screen answers four questions:
- **This week (macro):** which categories have actually produced successful coins.
- **Today (intraday):** which categories are busier or quieter than usual right now.
- **Tomorrow's outlook (rotation):** where buying is moving. It shows two lists with different
  records: *working this week* and *busy today*.
- **Meta health:** what has already changed in categories that had an edge.

Everything is computed from data the app already collects (`radar/analytics/macro.py`). There
are no paid sources and no Telegram.

**Results in short (preliminary, about two weeks of one period):**
- Only one signal had a positive next-day record: "working this week". Even that rests on a
  single category.
- "Busy today", the original watchlist rule, was followed by *worse* next days.
- Meta health describes decline already under way. It is not an early warning.

Full numbers are in *Results*. Every call the app makes is now also logged and scored on later,
unseen data (*Forward validation*).

Reproduce:

```
cp research.db replay.db
python scripts/meta_replay.py replay.db MODEL_DIR --fresh     # hourly narrative reads over the corpus
python scripts/macro_check.py replay.db --write                # writes radar/data/macro_check.json
```

## Definitions

- **Success.** A coin graduates (fills its bonding curve) within 24 hours of launch. Graduations
  inside the first minute are excluded: those are the creator's own wallets buying out the
  curve.
- **Drew buyers.** 50+ unique buyers in some hour of the coin's first day.
- **Factory coins.** A creator with 10+ launches in 7 hours (24 hours for the rotation's
  early-cohort count) is a factory. Its coins are left out everywhere.
- **Category.** Each coin keeps the category of the first narrative it joined
  (`token_narrative`). Categories are either described seeds ("Characters & creatures", …) or
  ones the app formed from novel narratives. The latter are labelled in the watchlist.

## This week (macro)

- **What is counted.** Coins launched in the last 7 days, judged only once their first day is
  over (`token_summary`). The 14- and 30-day windows give context, and are shown only when
  collection covered enough of those hours.
- **How categories are ranked.** By breadth, not launch counts. The rate is the category's
  graduation rate against every coin launched in the same days, recomputed with its single
  best coin left out. The ranking uses the lower end of that rate's range (Beta posterior,
  shrunk toward the market).
- **"Working"** needs that lower end at or above the market, and successes from 3+ different
  creators.
- **"One coin"** means a single success carries the category.
- **What each row also reports:**
  - the trend against last week;
  - whether the newest 3 days did worse than the 4 before;
  - crowding (more launches with worse results);
  - buyers, holders, market cap and liquidity of its successes.

## Today (intraday)

Each category's buyers in the last hour (summed over its live narratives) are compared with its
**usual level at the same time of day**: narrative reads within ±2 hours of now's time of day
over the previous 6 days.
- An earlier version compared with the all-day average, so every category read "cooling" at
  night and "heating" at the evening peak.
- A read in which the category had no live narrative counts as zero buyers, not as missing.

Launches use the same 6 hours of the previous days. Graduations use the daily average (they
are too few to split by hour).

| Status | Rule |
|---|---|
| heating | buyers ≥ 1.5× usual |
| cooling | buyers ≤ 0.6× usual |
| new | no usual level (under 3 days of reads, or none for this category) |

**Standout coins** have 3× the buyers of their narrative's median coin and 20+ buyers. They are
coins working inside a narrative, which is not the same as the narrative working.

## Week and day together

Each category gets one finding, with the evidence for it and anything that argues against it:

| Finding | What it means |
|---|---|
| Confirmed | Working all week and still active today |
| Lagging new launches | Strong week, but the newest coins are doing worse |
| New, no record | Drawing buyers today with no week to judge |
| Busy, no record | Heating today while its week is average, lagging, or one coin |
| Saturating | More launches, not more successes |
| Fading | Its rate fell against last week and it is cooling today |
| Quiet today | Worked this week, cooling today |

**Moving together:**
- Hour-to-hour changes in each pair of categories' buyers are correlated, after removing the
  median move of all *other* categories (the market).
- Each pair is tested against 300 circular time shifts, which keep each series' own rhythm.
- The set of pairs is corrected for multiple testing (Benjamini–Hochberg, 10%), and r ≥ 0.25 is
  required.
- Shared early-buyer wallets and shared X posts are shown as supporting evidence.
- Correlation is not causation, and the screen says so.

## Rotation signals and Tomorrow's outlook

All of these are computed at the time of the read, from data available then.

| Signal | Rule |
|---|---|
| Buyers up | buyers ≥ 1.5× its usual at this time of day |
| Money in up | net SOL into its coins this hour > 0 and ≥ 1.5× usual (usual floored at 0.5 SOL) |
| Share up / down | its share of all category buying vs its usual share: ≥ 1.25× and +1 point up, or ≤ 0.75× and −1 point down. This is the rotation: buyers moving from one category to another |
| New coins already graduating | coins launched in the last 24 h with 2+ graduations from 2+ creators, where a Poisson test against what its own last week and today's market predict gives p < 0.1 |
| Broad | 3+ coins with 20+ buyers in the last hour, no coin above 60% of the category's buying |
| One coin | one coin ≥ 60% of the category's buying (with 50+ buyers) |
| Crowding | launches in 6 h ≥ 1.5× usual (usual ≥ 3), and buyers per launch below usual |
| Holders up | 60%+ of its live coins gained holders in the last hour. **Live installs only**: the corpus has no holder counts, so this signal is untested and the screen says so when it is missing |

**The early-cohort comparison.** Coins launched in the last day have had less than a full day
to graduate. The category is therefore compared with the market *on the same coins*, which
cancels that. Its usual rate against the market comes from coins launched 2–7 days earlier,
shrunk toward the market when it has few coins.

**Busy-today rule** (set before the backtest as the "watchlist" rule, and not changed after it):
buyers up **and** share up **and** broad **and not** crowding.

**Why "watchlist" became "busy today".** On history, categories meeting this rule had *worse*
next days (see *Results*). The app therefore shows them as what is happening now, labelled with
that record, and never as tomorrow's picks.

Tomorrow's outlook puts them beside a separate list, **working this week**: the categories the
weekly view marks "working". That was the only signal with a positive next-day record, and it is
labelled *preliminary* because that record rests on one category.

**Stage of each item:**

| Stage (shown as) | When |
|---|---|
| Week working | its week already reads "working" |
| Record improving | its weekly rate is improving against last week, or its new coins are already graduating |
| No record | nothing behind it but today's buying |

Each busy item lists its evidence and its risks: no record, concentration, launches rising too,
money in not rising, no new coin graduating yet, coins not adding holders, and its health.

**Other lists:**
- categories gaining or losing share;
- weakening categories (share down or weekly rate losing, with buyers ≤ 0.8× usual);
- one-coin categories ("a coin working, not the category");
- crowding categories.

No confidence score is attached to any item. The only numbers about what follows are each list's
measured record on history and its forward record, both shown next to it.

## Meta health: decay and exhaustion

The question: has a category that *had* an edge started losing it, and can we tell while there
is still time to react?

**Which categories are tracked.** Only those that had an edge. Over the 11 days before the last 3,
their coins drew 50+ buyers (or graduated) at 1.2× the market or more, with 60+ coins and
successes from 3+ creators. Everything else reads "no edge to lose" and is not shown.

**Market-relative throughout.**
- Every rate is against all coins launched in the same days.
- Every demand measure is a share of all category buying or of SOL flowing in.
- So a market-wide sell-off moves the baseline with it, and alone does not read as one
  category's decay.
- The screen also says when the whole market is down.

**Six families of evidence**, each the category's last days against its own baseline:

| Family | Speed | Signal |
|---|---|---|
| Buyers and money in | fast | share of all category buying ≤ 0.75× baseline over 3 days *and* ≤ 0.8× in the last day (a one-day dip alone is not enough); or share of SOL in ≤ 0.7× with net selling in 15+ points more of the hours |
| Crowding | fast | share of categorised launches ≥ 1.3× baseline while buyers per launch ≤ 0.7× |
| Concentration | fast | two coins hold 60%+ of recent buying, and the rest draw buyers at ≤ 0.6× their earlier rate |
| Results | slow | coins drawing 50+ buyers against the market, recent vs baseline: P(recent better) ≤ 0.15. Graduations count the same way, but only when drawing buyers is not holding up too (graduations are rare) |
| Breadth | slow | different creators with a winner per day ≤ 0.6× baseline relative to the market's change; or coins reaching half the curve ≤ 0.7× |
| Follow-through | slow | of coins that drew buyers, the share going on to half the curve or graduation ≤ 0.6× baseline; or holders kept after a day ≤ 0.8× (live only) |

"Slow" families use coins whose first day is over, so they confirm a day or more after the
fast ones move.

**Comparing rates.** Recent and baseline rates are compared with a weak prior (strength 20). A
strong prior pulled the short recent window toward the market harder than the long baseline;
in a test with a market-wide fall, that read as a decline when nothing had changed.

**Statuses:**

| Status (shown as) | When |
|---|---|
| Deteriorated | 2+ families now, including a slow one, and 2+ the day before too |
| Weakening signs | 2+ families |
| Improving | was weakening in either of the last two days, now at most one family |
| Quiet today | the last day's share of buying ≤ 0.75× baseline, but 3-day demand and results hold up |
| Holding up | at most one family, none slow |
| Too little data | under 30 recent coins |

The rules were fixed before the backtest. Only the names changed after it: the old names
("decay confirmed", "early weakening") sounded like forecasts. The backtest found that these
statuses describe decline already under way and do not reliably anticipate it.

**What each category shows:**
- how many consecutive days it has been flagged;
- whether the evidence is strengthening or easing against a day ago;
- each family's evidence, with sample sizes and windows;
- what argues against it;
- what would confirm recovery or further decay;
- every measure, recent against before, in the category sheet.

A busy-today item whose category reads "weakening signs" or "deteriorated" says so among its risks.

**What the corpus cannot test:**
- **Holder retention and liquidity milestones.** The corpus has no holder counts or liquidity,
  so these are live-only.
- **Faster sell-offs.** These are approximated by the share of hours with net selling.
- **The length of each coin's momentum.** Not measured: the coin summaries keep peaks, not
  durations.

## Results

> **Preliminary.** About two weeks (2026-06-19 to 2026-07-14) of one market period from one
> corpus, with no out-of-period test. Treat these as a baseline for independent testing, not proof.
> The signal rules were fixed before this test and have not been changed since. Only the display
> names changed.

**Method** (`scripts/macro_check.py`, results in `radar/data/macro_check.json`):
- **Replay.** The corpus is replayed hour by hour through the app's own narrative pipeline
  (`scripts/meta_replay.py`). Each view is computed using only data available at that hour.
- **Comparison.** At each reading, flagged categories are compared with unflagged ones on the
  coins launched *afterwards*: next day for the weekly view and rotation, next 6 hours for
  heating, next 3 days for decay. Each is measured against all coins launched in the same window.
- **Ranges.** 90% ranges come from a **moving-block bootstrap over days**: 2-day blocks, and
  4-day blocks for 3-day outcomes. Readings 6 hours apart share outcome coins, so resampling
  single readings, or even single days, would overstate certainty.

**Audit checks**, after a first pass resampled single days:
- **Distinct categories.** Each comparison reports how many distinct categories it rests on,
  the largest one's share, and the result with that category left out. Categories differ
  hugely in size.
- **Decline episodes.** Decay results count separate decline episodes as well as readings,
  since one decline spans several readings.
- **Multiple testing.** 23 comparisons were run, so one range just clear of
  zero is weak evidence.

### Next-day record of each signal

Each entry is coins after a flagged reading vs after unflagged ones, both against the market
(graduations). The difference has a 90% range.

| Signal | Flagged vs rest | Difference (90%) | Sample | Categories behind it | Verdict |
|---|---|---|---|---|---|
| Marked “working” this week | 1.15× vs 0.90× | +0.25 (+0.17 to +0.31) | 11/12 days, 13 readings, 401 grads | 3 (100% largest); rests on one category; without it -0.85 | better |
| “heating” today | 1.11× vs 0.93× | +0.18 (-0.03 to +0.38) | 10/11 days, 155 readings, 84 grads | 40 (52% largest); without it -0.04 | no clear difference |
| Busy today (the former watchlist rule) | 0.82× vs 0.98× | -0.16 (-0.59 to -0.10) | 10/11 days, 48 readings, 108 grads | 17 (41% largest); without it -0.17 | **worse** |
| Busy today, no record | 0.72× vs 0.98× | -0.26 (-0.56 to -0.15) | 10/11 days, 45 readings, 54 grads | 17 (37% largest); without it -0.30 | **worse** |
| Busy today, record improving | — | — | — | — | too few to test |
| Busy today, week working | — | — | — | — | too few to test |
| Buyers at 1.5× usual | 0.96× vs 0.96× | +0.00 (-0.23 to +0.09) | 10/11 days, 173 readings, 232 grads | 44 (50% largest); without it -0.04 | no clear difference |
| Money in above usual | 1.06× vs 0.95× | +0.11 (-0.09 to +0.33) | 11/11 days, 160 readings, 75 grads | 69 (35% largest); without it +0.23 | no clear difference |
| Share of buying rising | 0.89× vs 0.98× | -0.09 (-0.20 to +0.01) | 11/11 days, 209 readings, 195 grads | 101 (38% largest); without it -0.11 | no clear difference |
| Share of buying falling | 0.98× vs 0.95× | +0.03 (-0.20 to +0.14) | 11/11 days, 170 readings, 340 grads | 14 (33% largest); without it +0.14 | no clear difference |
| Buying spread over 3+ coins | 1.01× vs 0.81× | +0.20 (-0.22 to +0.30) | 11/11 days, 180 readings, 745 grads | 36 (68% largest); without it +0.03 | no clear difference |
| Buyers up on one coin | 0.91× vs 0.96× | -0.06 (-0.39 to +0.99) | 10/11 days, 42 readings, 18 grads | 20 (24% largest); without it -0.24 | no clear difference |
| Broad momentum (against single-coin momentum) | 0.97× vs 0.91× | +0.06 (-0.74 to +0.35) | 10/10 days, 67 readings, 209 grads | 17 (56% largest); without it -0.15 | no clear difference |
| Launches outpacing buyers | 1.05× vs 0.94× | +0.12 (-0.01 to +0.19) | 10/11 days, 111 readings, 220 grads | 15 (72% largest); rests on one category; without it -0.03 | no clear difference |
| New coins already graduating | 0.71× vs 0.96× | -0.26 (-0.86 to -0.05) | 6/11 days, 10 readings, 12 grads | 4 (59% largest); without it -0.69 | **worse** |

**What the table says:**
- **Working this week** is the one positive record, and it is preliminary twice over:
  - It rests entirely on **Characters & creatures**, the largest category, which was marked
    "working" on 9 of 12 days.
  - The other two categories ever marked working had 4 readings and no graduations between
    them. With Characters & creatures left out, the difference is -0.85.
  - So the data cannot yet separate "the label works" from "that category did well that
    fortnight".
- **Busy today** (the former watchlist rule) was followed by *worse* next days. This was spread
  across categories (the largest is 41% of flagged coins) and held in
  both halves of the period.
- **Ranking categories by their week:** +0.04 rank correlation with the
  next day (90% range -0.12 to +0.20, 12 days), no better than
  chance.
- **Heating** and the individual rotation signals made no clear difference.
- **New coins already graduating** was followed by worse days, but on 12 graduations it is weak
  evidence.
- **Launches outpacing buyers** looked slightly positive when resampling single days. With 2-day
  blocks its range includes zero, and it rests mostly on one category.

### Meta health

379 readings of 14 categories that had an edge, over 14 days.
54 declining readings make up 16 separate decline
episodes. A decline means drawing 50+ buyers at 0.6× its own pre-read baseline or less, within 3
days.

| Status / rule | Readings | Declined after | Declined otherwise | Difference (90%) | False alarms | Declines caught |
|---|---|---|---|---|---|---|
| Weakening signs or deteriorated (a warning) | 111 | 20% | 12% | +0.08 (-0.01 to +0.17) | 80% | 41% |
| Deteriorated | 63 | 21% | 13% | +0.08 (-0.07 to +0.86) | 79% | 24% |
| Weakening signs | 48 | 19% | 14% | +0.05 (+0.00 to +0.14) | 81% | 17% |
| Quiet today | 20 | 0% | 15% | -0.15 (-0.18 to -0.07) | 100% | 0% |
| Improving | 54 | 0% | 17% | -0.17 (-0.20 to -0.07) | 100% | 0% |
| Holding up | 194 | 16% | 12% | +0.05 (-0.06 to +0.13) | 84% | 59% |
| Family flagged: buyers and money in | 117 | 16% | 13% | +0.03 (-0.09 to +0.12) | 84% | 35% |
| Family flagged: results already falling | 143 | 29% | 5% | +0.24 (+0.09 to +0.29) | 71% | 78% |
| Family flagged: crowding | 12 | 0% | 15% | -0.15 (-0.18 to -0.06) | 100% | 0% |

- **Overall:** warnings are not clear of chance, 80% are false alarms, and they catch 41% of
  declining readings.
- **The early-warning question.** Of the 292 readings taken before a decline showed in
  matured results, 19 went on to decline. Warned readings declined
  8% of the time against 6% without a warning
  (90% range -0.01 to +0.10). That is **no reliable early warning**.
- **Lead time.** Of 22 collapses, 10 had a warning first, a median
  0.9 days ahead.
- **The one strong piece is "results already falling"**. It describes deterioration already
  under way, which tends to continue. It is not a forecast.
- **"Improving" and "quiet today"** were not followed by declines in this period: 0 of
  54 and 0 of 20 readings.

## Forward validation

From this version, the app logs a call about every category every 6 hours (`forecast_log`):
- whether it is working this week;
- whether it is busy today;
- each tracked category's health.

Each row stores the time, the call, the category's baseline and the market state (down / normal /
up, from category buying against its 11-day level). Once every coin launched in the call's window
has finished its first day, the call is scored on those coins, which the app had not seen when it
made the call:
- **Working and busy today:** graduations against the market the next day.
- **Health:** a decline within 3 days, same definition as above.

Macro · Today ("How much to trust this") shows:
- the forward record: flagged vs not flagged, false alarms and declines caught;
- the same split by market state;
- the number of calls and days behind it.

No verdict is shown before 14 days of scored calls. Rules stay fixed while this runs, so the
forward record is an independent test of the baseline above.

## Reference projects reviewed

- **co-numina/narra-app** (no licence file, so ideas only, no code). Two ideas carried over:
  - keep each coin's narrative assignment persistent (here: `token_narrative`);
  - tag standout coins with their narrative (here: coins outrunning their narrative).
- **DoradoDevs/solana-narrative-scanner** (MIT). Its idea of narratives linked through shared
  wallets became the shared early-buyer evidence on co-moving pairs. Its Telegram and paid
  data sources were not used.

## Limitations

- **One corpus.** The history is June 19 – July 14 2026, about 25 days. The September and
  October replays are 36 hours each, too short for the 3-day baseline rotation needs, so the
  rotation signals have **no out-of-period test**. Agreement between the corpus's two halves is
  reported instead.
- **Overlapping outcomes.** Reads every 6 hours with 24-hour or 3-day outcomes overlap. The
  moving-block bootstrap (2- and 4-day blocks) allows for that, but with 11–14 days of data the
  ranges are themselves rough.
- **Uneven categories.** One category is a large share of all categorised coins, and the only
  positive result rests on it. Ranges describe variation over days, not over categories.
- **Multiple comparisons.** Many signals were tested on the same days. A single range just clear
  of zero, such as "weakening signs" or "new coins already graduating", is weak evidence.
- **No holder or wallet data in the corpus.** Holder growth and shared-wallet evidence work
  only on a live install, and are untested.
- **Corpus market cap** is the price × 1e9 supply.
- **Categories come from the narrative read.** A coin that never joined a narrative has no
  category. App-formed categories appear and disappear with the narratives that formed them.
- **A fresh install needs time.** It needs 3+ days for "today against usual" and the rotation,
  and 7 days for the week. Until then the screen says so instead of guessing.
