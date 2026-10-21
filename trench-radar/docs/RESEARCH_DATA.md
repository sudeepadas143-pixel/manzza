# Dataset check: which early signals went with a 2x

Source: Solana Memecoin Dataset (MIT), 44,460 snapshots -> 30,215 tokens (first detection each), 2026-06-10 to 2026-06-29 (20 days).
Base rate: 8.7% of tokens reached 2x within 24h of detection.

| Signal (dataset column) | TRENCH//RADAR equivalent | n bottom / top | 2x rate, bottom fifth | 2x rate, top fifth | top − bottom (90% CI, by day) | staged exit, mean: bottom / top |
|---|---|---|---|---|---|---|
| `unique_buyers` | unique buyers (buyers_h1) | 6,476 / 17,266 | 7.0% | 8.7% | +1.7% (-0.2% to +4.0%) | 0.27x / 0.26x |
| `net_flow_usd` | net buy flow (net_flow_usd_h1) | 6,044 / 6,043 | 6.8% | 1.4% | -5.4% (-6.6% to -3.7%) ** | 0.35x / 0.03x |
| `trade_buy_sell_ratio` | buy/sell balance (buyer_share_h1) | 6,056 / 6,069 | 9.0% | 0.8% | -8.3% (-9.4% to -6.8%) ** | 0.40x / 0.02x |
| `smart_buy_1h` | smart-money buys, 1h (proven / labelled buyers) | 12,386 / 6,661 | 6.2% | 17.4% | +11.2% (+8.7% to +13.9%) ** | 0.22x / 0.50x |
| `smart_money_count` | smart-money holders | 26,029 / 4,185 | 6.4% | 23.3% | +17.0% (+14.6% to +19.3%) ** | 0.21x / 0.75x |
| `kol_buy_1h` | KOL buys, 1h | 22,683 / 7,532 | 5.2% | 19.4% | +14.3% (+12.3% to +15.8%) ** | 0.15x / 0.70x |
| `bundler_ratio` | bundler share of active wallets (launch-block buyers) | 6,510 / 6,044 | 1.8% | 16.7% | +14.9% (+13.1% to +16.6%) ** | 0.05x / 0.57x |
| `sniper_count` | snipers (launch-block buyers) | 12,774 / 7,005 | 12.2% | 12.0% | -0.2% (-1.4% to +1.2%) | 0.43x / 0.32x |
| `top10_holder_pct` | top-10 holder share (top10_pct) | 6,201 / 6,051 | 0.2% | 16.1% | +16.0% (+14.3% to +17.7%) ** | 0.03x / 0.51x |
| `dev_remaining_pct` | creator still holds (dev_holds_pct) | 22,493 / 6,063 | 9.1% | 5.3% | -3.8% (-4.7% to -2.2%) ** | 0.30x / 0.17x |
| `insider_pct_holders` | insider share of holders (insider buyers) | 8,934 / 6,042 | 0.2% | 15.5% | +15.3% (+14.5% to +16.5%) ** | 0.01x / 0.57x |
| `crew_cohesion` | coordinated buyer crew | 5,950 / 5,949 | 14.8% | 1.3% | -13.4% (-14.6% to -12.2%) ** | 0.52x / 0.03x |
| `fresh_wallet_pct` | fresh wallets among holders | 8,573 / 6,048 | 3.2% | 17.7% | +14.5% (+12.8% to +16.1%) ** | 0.10x / 0.60x |
| `has_twitter` | has an X link (metadata) | 12,172 / 18,043 | 4.0% | 11.9% | +7.9% (+7.0% to +8.7%) ** | 0.12x / 0.40x |
| `is_boosted` | paid DexScreener boost | 30,131 / 84 | 8.7% | 25.0% | +16.3% (+7.4% to +22.7%) ** | 0.29x / 0.92x |
| `time_since_launch_sec` | token age at detection | 6,047 / 6,029 | 6.9% | 10.9% | +4.1% (+3.3% to +5.3%) ** | 0.21x / 0.43x |
| `price_change_1h` | 1h price change at detection | 16,187 / 6,044 | 2.3% | 17.6% | +15.3% (+13.1% to +17.2%) ** | 0.07x / 0.56x |

** = the 90% interval excludes zero. Staged exit = the dataset's simulated sell-in-stages return (1.00x = break-even, before fees); all tokens: 0.29x.

Reproduce: `python scripts/research_dataset.py <dataset>/data/tokens.parquet` (needs pyarrow).

## What this says, and what it doesn't

**Read with care.** These are tokens that had already graduated or were trending on GMGN,
over a single 20-day stretch in June 2026, and "reached 2x" is a peak, not an exit anyone
could reliably take. It is not the population TRENCH//RADAR scores (narratives across all
launches), so nothing here changed the score weights.

1. **Buying at detection lost money on average.** The simulated staged exit averaged
   0.29x across all tokens, and no fifth of any signal broke even. That matches the earlier
   solana-launch-study finding that none of 48 trading rules was profitable. A signal that
   "goes with 2x" is not a trade.
2. **Smart-money and KOL buying go with higher 2x rates** (17–23% vs 6% base) and the
   smallest losses (0.50–0.75x). This supports showing proven and labelled wallets as
   evidence. They are still not weighted in the score.
3. **One-sided buying at detection goes with *fewer* 2x outcomes.** The most buy-heavy fifth
   reached 2x in 0.8% of cases (vs 9%) and averaged 0.02x. The dashboard now adds a risk note
   when a narrative's buyer share is 80% or more. The score still rewards a buyer share above
   55%. That component predates this check; whether to change it is a modelling decision,
   and narrative-level data from this app's own backtest should make it.
4. **Concentration, bundlers, insiders and fresh wallets go with *higher* 2x rates.** They
   mark coordinated, volatile tokens that pump, not safe ones (tokens with no insiders almost
   never 2x'd: 0.2%). The app keeps them as risk flags because they predict who is in control,
   not which way the price goes.
5. **Coordinated buyer crews go strongly with *fewer* 2x outcomes** (1.3% vs 14.8%). The app
   does not measure crew cohesion yet. It is the strongest negative signal here and a
   candidate for later work (it needs cross-token buyer overlap from the stream).
6. **Snipers made no difference**, and the number of unique buyers barely did (+1.7 points,
   interval includes zero).
