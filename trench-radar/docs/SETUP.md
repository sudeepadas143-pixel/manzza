# Setup, costs and limitations

## Run it

Python 3.12+ (uses `statistics.correlation(method="ranked")`).

```bash
cd trench-radar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # optional: add keys
.venv/bin/python -m radar init
.venv/bin/python -m radar collect          # one pass over every free source
.venv/bin/python -m radar serve            # dashboard + scheduler on http://127.0.0.1:8787
```

Other commands:

| Command | What it does |
|---|---|
| `python -m radar status` | freshness of every source, table sizes, which integrations are configured |
| `python -m radar analyze` | score metas now and print the ranking (`--json` for the full evidence) |
| `python -m radar report [--send]` | write a pre-launch report; `--send` also posts it to Telegram |
| `python -m radar backtest --days 3` | walk-forward backtest over stored history |
| `python -m radar run` | scheduler without the web UI |
| `python -m pytest -q` | test suite (offline; uses fabricated fixtures and stub servers) |

Leave it running. The first useful verdicts appear after about 30 hours: acceleration
needs a 24h baseline, and every verdict stays **insufficient data** until then. The first
backtest needs at least a day of matured outcomes on top of that.

The SQLite file (`data/radar.db`, WAL mode) is the shared database. Dashboard, CLI and
scheduler can all use it at the same time.

## Credentials

Everything is optional. A missing key shows as "not configured" on the dashboard,
and the analysis drops whatever depended on it and lowers confidence. Keys are read
from the environment or `.env`. They are never stored in the database or returned
by the API, and they are redacted from logs and error messages
(`Settings.redact`). If you bind the dashboard to anything other than
`127.0.0.1`, set `DASHBOARD_TOKEN`.

| Key | Without it | With it |
|---|---|---|
| `SOLANA_RPC_URL` | public mainnet RPC (rate-limited; deployer lookups often 429) | reliable curve reads and deployer lookups |
| `X_BEARER_TOKEN` | no social layer; attention is inferred from launch names | mentions, independent accounts, influential posts, sentiment |
| `REDDIT_CLIENT_ID/SECRET` | unauthenticated JSON, blocked from many datacenter IPs | OAuth app-only access |
| `BITQUERY_TOKEN` | net flow is a count proxy plus real SOL on curves | buy vs sell USD volume |
| `ANTHROPIC_API_KEY` | deterministic rules analyst | Claude writes the briefing from the evidence pack |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | alerts and reports stay in the dashboard | pushed to Telegram |

## API costs (checked 2026-10-16; confirm before budgeting)

| Source | Cost | This app's default usage |
|---|---|---|
| GeckoTerminal public API | free; documented 30 req/min, shared per IP | ~8 req/min at 4s spacing |
| DexScreener, DefiLlama | free | a few calls per 10 and 60 min |
| Solana public RPC | free, aggressively rate-limited | 1 batched call per 5 min plus deployer lookups |
| Helius RPC (recommended) | free tier 1M credits/month at 10 rps; Developer $49/mo for 10M (per helius.dev) | ~2–4k credits/day at defaults, well inside the free tier |
| X API v2 | pay-per-use, ~$0.005 per post returned; legacy Basic/Pro closed to new signups | capped by `X_DAILY_READ_BUDGET` (default 1,000 posts/day ≈ $5/day ≈ $150/mo). Lower it to cut cost. |
| Reddit | free with OAuth app (personal use) | 4 subreddits per 30 min |
| Bitquery | free Developer tier with trial points; production volume is quoted by sales | 1 query per 5 min when enabled. Expect to need a paid plan for continuous use. |
| Anthropic (Claude Opus 5.5) | $4 / $20 per million input/output tokens | evidence pack ~6–10k tokens in, 1–4k out → roughly $0.05–0.12 per report; 2 scheduled reports/day ≈ $3–7/mo |
| Telegram Bot API | free | — |

The minimum useful setup costs nothing: GeckoTerminal + public RPC + DexScreener +
DefiLlama, with the rules analyst. The social layer is the most expensive addition.

## What each source is used for

- **GeckoTerminal**: launches (`new_pools`, 9 pages ≈ the last 4 minutes), the most-traded
  bonding-curve tokens, PumpSwap pools (graduations), and per-token buys/sells/**unique
  buyers/sellers** for 1h/24h. Responses are Cloudflare-cached for about 60s.
- **Solana RPC**: BondingCurve accounts → progress, real SOL committed, `complete`. The pool
  address GeckoTerminal reports for the `pump-fun` dex *is* the curve PDA (verified).
  Deployer = fee payer of the create transaction (2 calls, so top tokens only).
- **DexScreener**: paid boosts and profiles — attention someone is buying.
- **DefiLlama**: 30-day daily volume for the pump.fun launchpad and PumpSwap.

## Limitations — read before trusting a score

1. **The score is unvalidated until the backtest says otherwise.** The weights are
   hand-set priors (`MODEL_VERSION v1-priors-2026-10`). The dashboard shows "not
   validated" until a backtest has ≥30 favorable signals whose graduation lift has a
   positive 90% lower bound. Nothing here claims predictive accuracy.
2. **Graduation is not profit.** The published study this builds on found that
   graduation could be predicted from creation-time features, and that none of 48
   tested trading rules was profitable. Outcomes record both measures separately.
3. **Launch coverage is sampled.** GeckoTerminal's free tier exposes only the last few
   minutes of new pools, so gaps in collection mean missed launches. Launch counts are
   reported with their coverage, rates are coverage-adjusted, and the graduation rate
   is a lower bound.
4. **Unique buyers are per-token.** Meta totals sum per-token unique buyers, so a wallet
   that buys three tokens in a meta counts three times. Wash trading and bundled buys
   also inflate these counts.
5. **Meta detection is lexical.** It works on terms in names, symbols and posts, with
   concatenated-name splitting and co-occurrence merging. Image-only or inside-joke
   metas that share no words are missed. This is deliberate, because it keeps every
   detection explainable.
6. **Social signals are manipulable.** Copy-paste fingerprints and new-account filters
   catch crude shilling, not paid KOL campaigns. Sentiment is a lexicon, not a model.
7. **Net flow.** Without Bitquery, "net flow" is the buy/sell count balance plus the
   change in real SOL on bonding curves (fees ignored). Curve flow does not cover
   graduated tokens.
8. **Not verified live in the build environment:** X API, Reddit OAuth, Bitquery,
   Telegram delivery and live Claude calls. No credentials were available, and
   pump.fun's own API is behind a Cloudflare challenge from datacenter IPs. Their
   parsers and request shapes are tested against recorded or stub responses (the
   Claude call goes through the real SDK against a local stub). The Bitquery query is
   written against the schema documented in `bitquery/Pump-Fun-API` and has not been
   executed.
9. **Deployer field.** Newer 166-byte BondingCurve accounts carry a pubkey at offset 49.
   On three sampled tokens it did *not* match the create transaction's signer, so it is
   not used as the deployer.
10. **Out of scope by design:** launching tokens, signing transactions, trading, and
    browser-scraping X with a personal session.
