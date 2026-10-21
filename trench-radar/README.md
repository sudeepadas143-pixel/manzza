# TRENCH//RADAR

Launch research for Solana / pump.fun memecoins. It answers one question with
evidence: **do current conditions favour launching a token into a given meta now,
or is it better to wait?**

It does not launch tokens, sign transactions or trade.

```
python -m radar serve      →  http://127.0.0.1:8787
```

Setup, API keys, costs and limitations: [`docs/SETUP.md`](docs/SETUP.md).
Design, data sources and what was reused from the reference repos:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## What it does

| Capability | How |
|---|---|
| Meta detection | Terms from launch names/symbols and posts (concatenated names are split, e.g. `CatWifHat` → cat, wif, hat). Co-occurring terms are clustered, and acceleration is a Poisson z-score against a 24h baseline. Social adds independent accounts (copy-paste waves removed), influential posts and lexicon sentiment. |
| Live chain feed | Every pump.fun launch and bonding-curve trade read straight from Solana, about 1–3s behind the chain, with no aggregator in between. The Live screen shows the launch tape, tokens being bought in the last 5 minutes and fresh graduations, refreshed every 3 seconds. |
| Real buying demand | Per-token unique buyers and sellers, buy vs sell SOL and net flow, curve progress and graduations, from every trade. Wallet-level signals: buyers that aren't bots, buys from wallets with a proven early-entry record, creators selling their own token, and clone launches. Bundled launches (wallets buying in the launch block), top-10 and creator holdings, and 7,700 labelled smart-money and insider wallets from a public dataset. Also paid DexScreener boosts and serial-deployer share (computed causally). |
| Narrative sources | Launch metadata often links the X post a coin is about; posts linked by several launches are surfaced without reading X. Narratives are also grouped by meaning (cat/kitty) with a small local model. |
| Historical backtest | `docs/RESEARCH_CORPUS.md`: the app's walk-forward backtest over every pump.fun launch from 2026-06-05 to 07-14 (798k tokens, failed ones included; Pump.fun Memecoin Corpus). Result: no edge; the score stays "not validated". Optional backfill of recent hours from Shrine's free archive skips the baseline wait. |
| Evidence check | `docs/RESEARCH_DATA.md`: which early signals went with a 2x in 30,000 graduated tokens (June 2026), with bootstrap intervals. None was profitable to buy at detection. |
| Market readiness | 7d vs 30d launchpad volume, graduation rate of a 24–48h launch cohort, how the most-traded new tokens are doing, rotation into fresh launches, SOL trend. Every metric carries its coverage. |
| Saturation | Copycat tickers, buyers per new launch, launches outpacing buyers, winner concentration, fading mentions and volume, meta age. |
| Readiness score | 0–100 from attention (0.25), demand (0.35), market (0.15) and freshness (0.25). Components without data are dropped and the weights renormalised. Each score comes with confidence, a verdict, reasons, risks and the raw evidence. |
| Hype vs buying | Each meta is labelled: confirmed / hype without buyers / on-chain ahead of social / cold. |
| AI analyst | Claude writes from an evidence pack and may only cite numbers in it. With no key, a deterministic rules analyst does the job. The pack is stored next to each report. |
| Historical learning | Walk-forward backtest. Every step re-runs scoring `as_of` that moment and asserts nothing newer was read. Graduation lift and net-positive lift are measured separately, false positives are counted, and results are bootstrapped by day. |
| Scheduled intelligence | Reports at configured UTC times. Telegram alerts fire on verdict changes, large score moves, new top metas, market regime flips and data outages, with cooldowns. |
| Dashboard | Source freshness, market tiles, 30-day volume, the meta ranking, per-meta evidence (components, reasons, risks, top tokens, posts, saturation, score history), the analyst, backtest and alerts. |

## Layout

```
radar/
  config.py            env/.env settings, secret redaction
  db.py                SQLite schema (append-only, timestamped observations)
  stream.py            live chain stream: every launch and trade, wallet signals, snapshots
  sources/             pump_events (decoder), solana_rpc, misc (dexscreener, defillama, bitquery), social (x, reddit)
  collectors.py        jobs: call a source, record the run, append observations
  text.py              terms, sentiment, spam fingerprints
  analytics/           metas, demand, market, saturation, scoring, outcomes, backtest
  analyst.py           Claude / rules briefing
  alerts.py reports.py scheduler.py api.py __main__.py
web/                   static dashboard (no build step)
tests/                 offline tests: decoders, parsers, look-ahead invariance, backtest, failures, auth
```
