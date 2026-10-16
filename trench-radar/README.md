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
| Real buying demand | Per-token unique buyers and sellers, buys vs sells, volume, net SOL into bonding curves (from account state), curve progress, graduations, paid DexScreener boosts, and serial-deployer share (computed causally). |
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
  sources/             geckoterminal, solana_rpc, misc (dexscreener, defillama, pumpfun, bitquery), social (x, reddit)
  collectors.py        jobs: call a source, record the run, append observations
  text.py              terms, sentiment, spam fingerprints
  analytics/           metas, demand, market, saturation, scoring, outcomes, backtest
  analyst.py           Claude / rules briefing
  alerts.py reports.py scheduler.py api.py __main__.py
web/                   static dashboard (no build step)
tests/                 offline tests: decoders, parsers, look-ahead invariance, backtest, failures, auth
```
