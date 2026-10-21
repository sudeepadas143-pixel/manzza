# Setup, costs and limitations

## Windows app (no Python needed)

1. On GitHub, open **Actions → "TrenchRadar Windows exe"**, pick the latest green run, and download
   the **TrenchRadar-windows** artifact (a zip containing `TrenchRadar.exe`).
2. Double-click `TrenchRadar.exe`. Windows SmartScreen will warn that the publisher is unknown,
   because the exe isn't code-signed: choose **More info → Run anyway**.
3. A console window opens and the dashboard opens in your browser at http://127.0.0.1:8787.
   Keep the window open to keep collecting; close it to stop. Data stays between runs.
4. Data and settings live in `%LOCALAPPDATA%\TrenchRadar`. To add API keys, edit `settings.env`
   there (same keys as `.env.example`) and restart.

The exe binds to 127.0.0.1 only, so other people can't reach it. It only collects while it's
running, and gaps show up as lower coverage and confidence on the dashboard. To build it yourself
on Windows: `pip install -r requirements.txt pyinstaller` and then `pyinstaller TrenchRadar.spec`.

## iPhone (private PWA)

The dashboard is a Progressive Web App: open it in Safari, then **Share → Add to Home Screen**.
It opens full-screen with a bottom tab bar and respects the notch and home indicator.

Your phone has to reach the machine running TRENCH//RADAR. The exe binds to 127.0.0.1 (the PC
only) on purpose. To use it from the phone, run from source with `DASHBOARD_HOST=0.0.0.0` and a
`DASHBOARD_TOKEN`, and connect over a private network such as Tailscale. Never expose it to the
public internet. Over plain `http://` (anything except localhost or HTTPS) iOS won't register the
service worker, so there's no offline shell, but everything else works. `tailscale serve` gives
you HTTPS on your private tailnet if you want the offline shell too.

The service worker caches only the app shell. API data is never cached, so an offline or stale
dashboard says so instead of showing old numbers as live.

Requires iOS/iPadOS 16+ (uses `dvh`, `inert`, `backdrop-filter`). The interface is dark only.

Display modes (System screen): **Auto** picks Low visual when the device reports reduced motion, Data Saver, ≤4 GB memory, ≤4 CPU threads or a 2G/3G connection; **Premium** and **Low visual** can be forced. See `docs/DESIGN.md`.

## Run it from source

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

Leave it running. The Live screen is useful at once. Narrative verdicts appear after about
7 hours: acceleration compares the last hour with the 6 hours before it, and every verdict
stays **insufficient data** until at least half of that baseline is collected. A 6-hour
baseline is more sensitive to time-of-day swings than a full day would be (an ordinary busy
evening can look like acceleration); that trade was made to get calls the same day. The
graduation rate still needs a 24–48h launch cohort, and the first backtest needs matured
outcomes on top of the baseline.

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
| `SOLANA_RPC_URL` / `SOLANA_WS_URL` | public mainnet RPC: the live stream works but the server closes it every 10–30s (a second or two lost each time) | a steadier live stream |
| `X_BEARER_TOKEN` | no social layer; attention is inferred from launch names | mentions, independent accounts, influential posts, sentiment |
| `REDDIT_CLIENT_ID/SECRET` | unauthenticated JSON, blocked from many datacenter IPs | OAuth app-only access |
| `BITQUERY_TOKEN` | net flow is a count proxy plus real SOL on curves | buy vs sell USD volume |
| `ANTHROPIC_API_KEY` | deterministic rules analyst | Claude writes the briefing from the evidence pack |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | alerts and reports stay in the dashboard | pushed to Telegram |

## API costs (checked 2026-10-16; confirm before budgeting)

| Source | Cost | This app's default usage |
|---|---|---|
| DexScreener, DefiLlama | free | a few calls per 10 and 60 min |
| Solana public RPC | free | 1 websocket (the live stream, **~0.3 MB/s ≈ 25 GB/day download**) + 1 batched call per 2 min for curves near graduation |
| Helius RPC (recommended) | free tier 1M credits/month at 10 rps; Developer $49/mo for 10M (per helius.dev) | ~2–4k credits/day at defaults, well inside the free tier |
| X API v2 | pay-per-use, ~$0.005 per post returned; legacy Basic/Pro closed to new signups | capped by `X_DAILY_READ_BUDGET` (default 1,000 posts/day ≈ $5/day ≈ $150/mo). Lower it to cut cost. |
| Reddit | free with OAuth app (personal use) | 4 subreddits per 30 min |
| Bitquery | free Developer tier with trial points; production volume is quoted by sales | 1 query per 5 min when enabled. Expect to need a paid plan for continuous use. |
| Anthropic (Claude Opus 5.5) | $4 / $20 per million input/output tokens | evidence pack ~6–10k tokens in, 1–4k out → roughly $0.05–0.12 per report; 2 scheduled reports/day ≈ $3–7/mo |
| Telegram Bot API | free | — |

The minimum useful setup costs nothing: the live chain stream on the public RPC + DexScreener +
DefiLlama, with the rules analyst. Mind the stream's bandwidth on a metered connection:
the public RPC cannot filter out failed bot transactions, so about three quarters of what it
sends is discarded. `LIVE_STREAM=0` turns it off (and with it most of the app). The social layer is the most expensive addition.

## What each source is used for

- **Live chain stream** (`radar/stream.py`): one `logsSubscribe` websocket on the pump.fun
  program. Every launch (name, symbol, creator), every bonding-curve trade (wallet, SOL,
  buy/sell, curve reserves) and curve completions arrive about 1–3s after they happen. From
  these the app keeps, per token: buyers and sellers (1h, 5m), buy and sell SOL, net flow,
  curve progress, price, and these wallet-level signals:
  - *organic buyers*: unique buyers minus wallets that traded 15+ tokens in the past hour
    (sniper and volume bots);
  - *proven wallets*: wallets that were among the first 20 buyers of 2+ tokens that went on
    to graduate, with a 10%+ hit rate over 7 days (the base rate is about 1%). Built only from
    graduations already seen, so there is no look-ahead. Evidence only; not in the score
    weights until a backtest says it helps;
  - *creator sold*: SOL the token's creator sold back into its own curve;
  - *clones*: the same name launched by several wallets within 15 minutes.
  Every 2 minutes a row per active token (5+ buyers in the hour) goes into `token_obs` and
  `curve_obs`, which the analytics and backtest read.
- **Solana RPC**: every 2 minutes, the `complete` flag of curves above 90% (the completing
  transaction's logs are sometimes truncated by the RPC, so the stream alone can miss one).
- **DefiLlama**: SOL/USD every 5 minutes, and launchpad volume.
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
3. **Launch coverage.** The stream sees every launch while it is connected. The free public
   RPC closes the connection every 10–30s and the second or two until it reconnects is lost.
   Each minute the app records how long it was connected; counts are reported with that
   coverage and the graduation rate is a lower bound. Before 2026-10-21 launches came from
   GeckoTerminal's sampled `new_pools`; that history is kept and still counted.
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
   Telegram delivery and live Claude calls. No credentials were available. Their
   parsers and request shapes are tested against recorded or stub responses (the
   Claude call goes through the real SDK against a local stub). The Bitquery query is
   written against the schema documented in `bitquery/Pump-Fun-API` and has not been
   executed.
9. **Deployer.** The creator comes from the launch event itself. Tokens launched before the
   app started have no creator until their next snapshot names one from trade events.
10. **Event layouts.** The pump.fun event layouts were verified against live mainnet traffic
   on 2026-10-21. A program upgrade that reorders fields would break decoding; one that only
   appends fields would not.
11. **Out of scope by design:** launching tokens, signing transactions, trading, and
    browser-scraping X with a personal session.

## Free 24/7 server (Oracle Cloud) with phone access

1. Create an Oracle Cloud account (cloud.oracle.com, Free Tier). It asks for a card to verify you;
   Always Free resources aren't charged.
2. **Compute → Instances → Create instance.** Image: **Ubuntu 24.04**. Shape: **Ampere
   VM.Standard.A1.Flex**, 1 OCPU and 6 GB is plenty (marked "Always Free eligible"). Download the SSH key
   it offers. If it says "out of capacity", try another availability domain or try again later.
3. Connect: `ssh -i <key-file> ubuntu@<public-ip>` (on Windows, use PowerShell or the cloud console's
   "Cloud Shell").
4. Run:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/sudeepadas143-pixel/manzza/claude/trench-radar/trench-radar/deploy/oracle-setup.sh -o setup.sh
   bash setup.sh
   ```
   It installs the app as a service (it restarts after crashes and reboots), creates a dashboard
   password, and sets up Tailscale. When it prints a Tailscale login link, open it and sign in.
5. Install Tailscale on your iPhone and PC and sign in with the same account. Open the `https://…ts.net`
   address the script printed and enter the password. On iPhone: **Share → Add to Home Screen**.

Nothing is opened to the public internet; only your Tailscale devices can reach the dashboard.
Re-run `bash setup.sh` at any time to update to the latest version (settings and data are kept).
