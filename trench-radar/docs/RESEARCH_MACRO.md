# Macro, intraday and rotation: what has worked, what is moving, what to watch

The **Macro · Today** view of the Meta screen answers three questions:
- **This week (macro):** which categories have actually produced successful coins.
- **Today (intraday):** which categories are busier or quieter than usual right now.
- **Tomorrow's watchlist (rotation):** where buying is moving, and which categories might work next.
- **Meta health:** whether a category that had an edge is losing it, early enough to react.

Everything is computed from data the app already collects (`radar/analytics/macro.py`). There
are no paid sources and no Telegram. Every signal was measured on replayed history before being
described as useful (see *How much each part says about what comes next*).

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

## Tomorrow's watchlist (rotation)

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

**Watchlist rule** (set before the backtest): buyers up **and** share up **and** broad **and
not** crowding.

**Stage of each item:**

| Stage | When |
|---|---|
| Confirmed | its week already reads "working" |
| Emerging | its weekly rate is improving against last week, or its new coins are already graduating |
| Speculative | nothing behind it but today's buying |

**Each item lists:**
- the evidence;
- the risks (no record, concentration, launches rising too, money in not rising, no new coin
  graduating yet, coins not adding holders);
- what would **confirm** it: buyers stay at 1.5×+ over 3+ coins, and more graduations from
  different creators in the next 24 h;
- what would **invalidate** it: buyers fall back below usual, one coin takes 60%+, or crowding.

**Other lists:**
- categories gaining or losing share;
- weakening categories (share down or weekly rate losing, with buyers ≤ 0.8× usual);
- one-coin categories ("a coin working, not the category");
- crowding categories.

No confidence score is attached to any item. The only number about the future is each signal's
measured record on history, shown next to it.

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

| Status | When |
|---|---|
| Decay confirmed | 2+ families now, including a slow one, and 2+ the day before too |
| Early weakening | 2+ families |
| Recovering | was weakening in either of the last two days, now at most one family |
| Cooling off | the last day's share of buying ≤ 0.75× baseline, but 3-day demand and results hold up |
| Healthy | at most one family, none slow |
| Too little data | under 30 recent coins |

**What each category shows:**
- how many consecutive days it has been flagged;
- whether the evidence is strengthening or easing against a day ago;
- each family's evidence, with sample sizes and windows;
- what argues against it;
- what would confirm recovery or further decay;
- every measure, recent against before, in the category sheet.

A watchlist item whose category is weakening says so first among its risks.

**What the corpus cannot test:**
- **Holder retention and liquidity milestones.** The corpus has no holder counts or liquidity,
  so these are live-only.
- **Faster sell-offs.** These are approximated by the share of hours with net selling.
- **The length of each coin's momentum.** Not measured: the coin summaries keep peaks, not
  durations.

## How much each part says about what comes next

*Being measured: the replay of the corpus is still running. This section is filled in from `scripts/macro_check.py` once it finishes.*

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
- **Overlapping outcomes.** Reads every 6 hours with 24-hour outcomes overlap. The bootstrap
  resamples whole days, but neighbouring days still share some outcome hours, so ranges are if
  anything too narrow.
- **No holder or wallet data in the corpus.** Holder growth and shared-wallet evidence work
  only on a live install, and are untested.
- **Corpus market cap** is the price × 1e9 supply.
- **Categories come from the narrative read.** A coin that never joined a narrative has no
  category. App-formed categories appear and disappear with the narratives that formed them.
- **A fresh install needs time.** It needs 3+ days for "today against usual" and the rotation,
  and 7 days for the week. Until then the screen says so instead of guessing.
