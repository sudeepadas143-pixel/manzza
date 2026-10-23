# TRENCH//RADAR — architecture and plan

Research tool for deciding *whether* and *when* conditions favour launching a new
Solana / pump.fun memecoin. It observes, scores and explains. It never launches
tokens, signs transactions or trades.

## 1. What the reference repositories contributed

| Repo | License | What it is | What we took | What we left |
|---|---|---|---|---|
| `Chrisymcsoup/solana-launch-study` | MIT | Python measurement pipeline: launch listener, bonding-curve outcome tracker, causal report, backtest | **Code** (adapted, credited): Anchor discriminator check + `BondingCurve` decoder (reads `complete` before rejecting zero reserves), outcome buckets (dead/weak/alive/migrated), causal "creator prior launches" via sorted-timestamp bisect, drift guard for replayed checkpoints. **Findings** as product rules: 90% of launches die, graduation ≠ profit, look-ahead bias halved a headline effect. | Sniping/exit simulator (trading — out of scope). The WebSocket listener is not ported: it needs a paid WS RPC and only decoded 61–66% of creates. |
| `DoradoDevs/solana-narrative-scanner` | MIT | TypeScript service: Twitter/Reddit/Telegram/Discord/pump.fun adapters, Postgres + Redis + BullMQ, embeddings, virality score | **Ideas, re-implemented**: logistic velocity mapping with acceleration bonus, unique-author breadth tiers, near-duplicate fingerprinting for spam, bot heuristics, weighted-sum score with printed rationale. | The stack (Postgres + Redis + BullMQ + transformers.js) is heavy for a single-operator tool; tiered magic numbers were replaced by documented thresholds in one file. Its pump.fun adapter calls `frontend-api-v3.pump.fun`, which is behind a Cloudflare challenge from datacenter IPs (verified: HTTP 403). |
| `TINZY0612/openclaw-x-signal` | MIT | Playwright scraper over a logged-in X session + Binance/CoinGecko/DexScreener cross-checks + Telegram report | **Ideas**: tweet category lexicon (hype/bullish/bearish/panic/shill/news), "social attention must be confirmed by market data" framing, Telegram-sized report parts. | Browser scraping of X with a personal session (fragile, against X ToS, risks the account). We use the official X API v2 instead. |
| `bitquery/Pump-Fun-API` | none stated (docs only) | GraphQL query catalogue for Bitquery's Solana datasets | **Field names / dataset shapes** for our own query (`DEXTradeByTokens` buy/sell volume, buyers/sellers). No code copied. | Streams/Kafka (paid tier). |
| `mksglu/claude-context-mode` | Elastic 2.0 | Claude Code plugin: sandboxed execution so large outputs stay out of context | Development practice only (bounded output, summarise-then-read). | Not vendored — ELv2 and unrelated to the runtime. |
| `kmizu/token-saver-plugin` | none stated | Rust hooks that guard/truncate tool output | Development practice only. | Not vendored. |
| `egorfedorov/claude-context-optimizer` | MIT | Plugin that tracks wasted reads | Development practice only. | Not vendored. |

## 2. Data sources (verified from this environment on 2026-10-16)

| Source | Key? | Status | Used for |
|---|---|---|---|
| **Solana RPC websocket** (`logsSubscribe`, pump program) | no (public works) | ✅ verified 2026-10-21: ~53 trades/s, 1–3s lag, public server closes the socket every 10–30s | The live stream (`radar/stream.py`): every launch, trade (wallet, SOL, buy/sell, reserves) and curve completion. Replaced GeckoTerminal on 2026-10-21. |
| GeckoTerminal public API | no | retired 2026-10-21 | Was the launch and per-token stats source; sampled, rate-limited, and the same data anyone sees. Old rows are kept and still counted. |
| Solana JSON-RPC (public or your provider) | optional | ✅ 200 | `complete` flag of curves above 90% every 2 min (backs up the stream), outcome labels. |
| DexScreener | no | ✅ 200 | Paid "boosts" and token profiles (attention being bought), search. 60 req/min. |
| DefiLlama | no | ✅ 200 | 30-day daily volume for pump.fun launchpad and PumpSwap — macro regime. |
| pump.fun frontend API | no | retired (403 Cloudflare) | The stream supplies creators directly. |
| X API v2 (recent search) | **yes**, paid | ⛔ no key here | Posts, authors, follower counts, engagement → meta detection, independent accounts, influential posts, sentiment. |
| Reddit | optional OAuth | ⚠️ 403 unauthenticated from this IP | Secondary social source. |
| Bitquery | **yes** | ⛔ no key here | Optional: buy *volume* vs sell *volume* (true net flow in USD). |
| Anthropic API | **yes** | ⛔ no key here | AI analyst narrative. Deterministic rule-based analyst is the fallback. |
| Telegram Bot API | **yes** | reachable | Alerts and scheduled reports. |

### Repositories evaluated on 2026-10-21

Licences, availability and what was used are recorded in [`THIRD_PARTY.md`](../THIRD_PARTY.md).
In short: the MIT Solana Memecoin Dataset supplies wallet labels and the evidence check in
[`RESEARCH_DATA.md`](RESEARCH_DATA.md); pump.fun's public IDL and docs define the event and
pool layouts; all-MiniLM-L6-v2 groups narratives by meaning through onnxruntime. Code from
unlicensed or "all rights reserved" repositories was not copied. open_clip was not integrated
(PyTorch and an image download per launch are too heavy for a desktop app), and PumpArchive's
API is offline.

### Narrative intelligence (2026-10-22)

`radar/analytics/narratives.py`, every 5 minutes on its own connection, as of a point in time:

1. **Documents.** Each launch from the last 6 hours (factory creators left out) becomes
   "name (ticker)", plus its description when it says more than launchpad boilerplate, plus the
   text of the X post it links to. Post text and pictures count only if fetched by `as_of`.
2. **Grouping.** MiniLM embeddings, leader clustering (most-bought launches seed first), then
   hard links: same X post, same picture (difference hash ≤ 6 bits), same name. A narrative
   needs 3+ launches from 2+ creators. Each grouping reason is counted and shown.
3. **Labels and categories.** Class-based TF-IDF picks the words that set a group apart. The
   category is the closest of 11 written category descriptions by meaning; a narrative near
   none of them is "novel", and once it reaches 5+ launches from 3+ creators its centre is
   stored as a new category that later narratives can match.
4. **Identity over time.** Each run's narratives are matched to the active ones by centre
   similarity; two old ones joining is a merge, one old one feeding two is a split. History
   (`narrative_obs`) gives growth, persistence and novelty against earlier narratives.
5. **Assessment.** Popularity (launches, creators), traction (non-bot buyers, buyers per launch,
   net SOL) and saturation (copycat share, buyers per launch falling, top-token concentration,
   bundles, insiders, creator dumps) are computed separately. The state comes from these with
   its reasons listed; the drivers name the post, account, picture or wallets behind it.
   Opportunity is not scored: see `docs/RESEARCH_NARRATIVES.md`.

## 3. Architecture

```
            ┌───────────── scheduler (asyncio, per-job intervals) ─────────────┐
            │                                                                   │
  stream.py  live chain websocket ─► in-memory 1h trade window ─► token_obs/curve_obs every 2 min
  sources/  pump_events  solana_rpc  dexscreener  defillama  x_api  reddit  bitquery
            │   each returns rows or raises SourceUnavailable; every call is
            │   recorded in source_runs (status, latency, items, error)
            ▼
  collectors.py ── append-only, timestamped observations ──► SQLite (WAL) shared DB
            │                                                 tokens, token_obs, social_posts,
            │                                                 market_obs, meta_obs, scores,
            │                                                 token_outcomes, alerts, reports
            ▼
  analytics/  text (terms, sentiment, spam) → metas (detect + acceleration)
              demand (buyers, flow, curve, graduations per meta)
              market (regime) · saturation (copycats, decline, concentration)
              scoring (readiness score, confidence, reasons, risks)
              backtest (point-in-time replay, outcomes, false positives)
            ▼
  analyst.py (Claude or rules) · alerts.py (Telegram, material change) · reports.py
            ▼
  api.py (FastAPI JSON) + web/ dashboard (static, no build step)
```

Design rules:

1. **Observations are append-only and timestamped** (`observed_at` = when *we*
   saw it, `created_at` = when the chain/post says it happened). Every metric is a
   function of `as_of`; live scoring is just `as_of = now`. This is what makes the
   backtest honest.
2. **Every source can fail.** A failure is recorded and surfaced as stale/
   unavailable on the dashboard; the score drops the dependent component,
   renormalises weights, and **lowers confidence** rather than inventing a value.
3. **No number without provenance.** Score components carry the raw inputs they
   were computed from, the source, and the freshness of that source.
4. **Graduation ≠ profit.** Outcomes record both, and backtest reports both.
5. **Secrets only from environment / `.env`**, never stored in the DB, never
   returned by the API, redacted from logs and error strings.

## 4. Scoring model (v1, hand-set weights — not fitted)

Per meta (a cluster of name/symbol/post terms):

| Component | Inputs | Weight |
|---|---|---|
| Social momentum | mention acceleration (z-score vs prior windows), independent authors, influential posts, sentiment | 0.25 |
| Demand confirmation | unique buyers, buy/sell balance, real-SOL inflow on curves, curve progress, graduations, volume — for tokens in the meta | 0.35 |
| Market conditions | launchpad volume trend, graduation rate, new-token survival | 0.15 |
| Freshness (1 − saturation) | copycat rate, launches-vs-buyers growth, winner concentration, attention decline, meta age | 0.25 |

`score = 100 × Σ wᵢ·cᵢ / Σ wᵢ` over components that have data. Confidence is
the share of weight with data × a sample-size factor × a freshness factor. A
meta with confidence < 0.35 is labelled **insufficient data** whatever its score.

Weights are priors. The backtest exists to check them; until it has enough
resolved outcomes (default ≥ 30 metas-windows per bucket) the dashboard says
"unvalidated" next to every score.

### Launch edge (fitted ranking of metas — `docs/RESEARCH_META.md`)

`radar/analytics/meta_model.py` reads the evidence `score_meta` already gathered for each meta
(launch momentum, demand, saturation, market) and ranks the metas with an L2 logistic model
fitted on the corpus (`radar/data/meta_model.json`, `scripts/meta_fit.py`). `run_analysis`
orders metas by it and attaches `edge` (rank, tier); the readiness score above stays on every
meta as the baseline, and without the model file the old order returns. The backtest reports
both models' top picks so the ranking keeps being checked on live history.

### Macro, intraday and rotation (`docs/RESEARCH_MACRO.md`)

`radar/analytics/macro.py`, run by `metamap_job` every 10 minutes (`EVERY_METAMAP_S`) and served
at `GET /api/meta/map`.
- **Inputs.**
  - Each coin's first narrative and category (`token_narrative`, written by the narrative read).
  - A one-row summary of each coin once its first day is over (`token_summary`).
  - The hourly narrative history (`narrative_obs`).
- **Week.** Per category: graduation rate against the market with its best coin left out, breadth
  of creators, trend, crowding.
- **Today.** Buyers, launches and graduations against the same time of day on the previous days.
- **Links.** One finding per category from the week and the day together.
- **Moving together.** Co-moving categories beyond the market.
- **Rotation.** Signals per category and Tomorrow's watchlist (stage, evidence, risks,
  confirm/invalidate).
- **Track record.** How each signal did on replayed history, read from
  `radar/data/macro_check.json`, written by `scripts/macro_check.py`.
### Launch-window score (fitted, validated — `docs/RESEARCH_QUANT.md`)

Separate from the meta score above, and per token rather than per meta. `radar/early.py`
keeps each new token's first 15 minutes of trades (from `stream.py`) and closes windows at
60 s, 5 min and 15 min into `token_early`. At 60 s, an L2 logistic regression fitted on the
Pump.fun Memecoin Corpus (`radar/data/quant_model.json`, written by `scripts/quant_fit.py`)
gives P(graduates within 1 h). The cohort base rate is learned live from matured outcomes,
and graduations credit first-minute buyers in `wallet_credits` (the "proven buyers" input).
Meta momentum and track record were tested as inputs and dropped (no gain); they are
stored with each row for display and re-validation.

## 5. Implementation plan (as executed)

1. Shared core: config (env, redaction), SQLite schema + migrations, HTTP client
   with timeouts/retries/rate-limit, source-run bookkeeping.
2. Source adapters + collectors (live chain stream, RPC, DexScreener, DefiLlama,
   X, Reddit, Bitquery, pump.fun) with fixtures for offline tests.
3. Analytics: text → metas → demand → market → saturation → score.
4. Outcomes labeller + point-in-time backtest with look-ahead assertions.
5. Analyst (Claude with evidence-only prompt; rules fallback), reports,
   Telegram alerts with material-change detection and cooldowns.
6. FastAPI + dashboard with freshness indicators.
7. Tests (unit + mocked integrations) and live smoke test against the free sources.
