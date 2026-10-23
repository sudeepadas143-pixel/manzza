# Third-party material

## Shipped with the app

**Wallet labels** (`radar/data/wallet_labels.csv.gz`) are derived from the Solana Memecoin
Dataset, https://github.com/ian05012/solana-memecoin-dataset (`data/wallets.parquet`),
built by `scripts/build_wallet_labels.py`. The labels in that dataset originally come from GMGN.

> MIT License
>
> Copyright (c) 2026
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software
> and associated documentation files (the "Software"), to deal in the Software without
> restriction, including without limitation the rights to use, copy, modify, merge, publish,
> distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
> Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or
> substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
> BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
> NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
> DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

**Fonts** in `web/fonts/` are under the SIL Open Font License; their licences sit next to them.

## Used for historical backtests (not shipped; downloaded on request)

**Pump.fun Memecoin Corpus** ("PumpFun Launch-to-Graduation Corpus"),
https://huggingface.co/datasets/jocry/Pumpfun_Memecoin_Corpus, by Slink Dev (slink21taken), 2026.
Revision used: `bd8aed6452fb81665a74e6c308323f2c825dc82a`. The dataset card lists MIT and the
README states CC BY 4.0; this project follows CC BY 4.0 (attribution) as the stricter of the two.
`radar/corpus.py` changes it as follows: it converts the token and trade tables into this app's
schema, aggregates trades per token per hour, and applies the exclusions from the corpus's own
KNOWN_ISSUES.md (non-human wallet, inconsistent or missing SOL amounts, out-of-range curve
values, the Jul 3 outage). No corpus data is distributed with the app.

## Optional live source

**Shrine trade data API**, https://shrine.trade/pump/data-api/overview/ (checked 2026-10-21):
free, no key for streams, REST or the hourly replay archive (`replay.shrine.trade`, archived
since 2026-09-14); limits of 3 REST requests per second per IP and one open stream per type per
IP. Only the replay archive is used, opt-in (`SHRINE_BACKFILL_HOURS`, `python -m radar backfill`,
`python -m radar check-coverage`). No terms of service beyond the API documentation were found.

## X post text (no key, no account)

For X posts that 2+ launches link to, the app reads the post through two public embed
endpoints (checked 2026-10-21): X's own `cdn.syndication.twimg.com/tweet-result` (the service
behind tweets embedded on websites) and FxTwitter's `api.fxtwitter.com` (an open-source embed
proxy, github.com/FxEmbed/FxEmbed), which adds follower and view counts. Neither is a
supported API; failures are recorded and skipped. `X_POST_TEXT=0` turns this off.
(`publish.twitter.com/oembed` redirected and `api.vxtwitter.com` was behind a Cloudflare
challenge, so they are not used.)

## Downloaded on first start

**all-MiniLM-L6-v2** (ONNX export, quantized), https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2,
Apache-2.0. Stored in the data folder under `models/`.

## Shipped in the web app

**League Gothic** (The League of Moveable Type, variable width), https://github.com/theleagueof/league-gothic,
SIL Open Font License 1.1, from the `@fontsource-variable/league-gothic` 5.3.0 package; licence in
`web/fonts/OFL-League-Gothic.txt`. Newsreader and IBM Plex are OFL as before.

Apache ECharts was evaluated and briefly shipped (2026-10-22), then removed: the hand-written SVG
charts in `web/charts.js` and `web/viz.js` draw the print style without a 1MB library.

## Libraries (installed from PyPI)

FastAPI (MIT), Uvicorn (BSD-3-Clause), httpx (BSD-3-Clause), websockets (BSD-3-Clause),
onnxruntime (MIT), tokenizers (Apache-2.0), NumPy (BSD-3-Clause), Pillow (MIT-CMU),
anthropic (MIT, optional). Research only: pyarrow (Apache-2.0), zstandard (BSD-3-Clause).

The image hash (`radar/images.py`) is a difference hash written for this app on Pillow; the
imagehash library (BSD-2-Clause) was considered but adds SciPy and PyWavelets for one function.

## Used as reference only (nothing copied)

| Repository | Licence | How it was used |
|---|---|---|
| pump-fun/pump-public-docs | none stated | Event, account and pricing layouts (IDL, docs) that the decoders follow. Interface facts, no code. |
| aethernet404/rugcheck | none stated | The idea of scoring top-10 holder concentration. Reimplemented from the trade stream; its RPC calls are blocked on free public endpoints. |
| killuawx3/pump-fun-research | none stated | Background figures (graduation rate ~1–1.7%). |
| nirholas/pump-fun-sdk | "All rights reserved" | Not used. |
| metaplex-foundation/mpl-token-metadata | Metaplex NFT licence | Not needed: the launch event already carries the metadata URI. |
| jito-foundation/jito-solana | Apache-2.0 | Validator software; not needed. Bundled launches are detected from same-block buys instead. |
| mlfoundations/open_clip | MIT | Not integrated: needs PyTorch (~2 GB) and downloading every token image. Same-picture links use the difference hash instead, which catches reposted pictures but not two different pictures of the same subject. |
| UKPLab/sentence-transformers | Apache-2.0 | Not installed (needs PyTorch); its MiniLM model runs through onnxruntime instead. |
| magicuidesign/magicui | MIT | Ideas only (number ticker). It is React + Tailwind; the app's frontend is plain JS with no build step. |
| ibelick/motion-primitives | MIT (stated in its README; the linked LICENSE.md was missing on 2026-10-22) | Ideas only: motion that follows data, marks that glide between states. Needs React and motion.dev. |
| tremorlabs/tremor | Apache-2.0 | Ideas only: the category bar and tracker. Needs React and Tailwind. |
| DavidHDev/react-bits | MIT + Commons Clause | Reviewed; nothing used. Its effects are decorative rather than data-driven. |
| JohannesBuchner/imagehash | BSD-2-Clause | The difference-hash idea, reimplemented in `radar/images.py` (see above). |
| NARRA (narrative-tracking reference supplied 2026-10-22) | none found | Ideas only: track a narrative's identity across runs and describe what drives it. No code copied. |
| mihailShumilov/narrative-detection | none stated | Ideas only: embed, cluster, then label clusters with class-based TF-IDF rather than a fixed keyword list. No code copied. |
| marchantdev/solana-narrative-detector | none stated | Ideas only: compare narrative activity with its own recent history rather than an absolute threshold. No code copied. |
| git-disl/MemeTrans → renamed git-disl/MELT | CC BY-NC 4.0 (non-commercial) | Research reference only. ~41k migrated tokens from early 2025 with high/low-risk labels; the raw transactions are on Google Drive. Not shipped or imported because of the non-commercial licence; its design (bundle traces, pre-migration features) informed the launch-block signal. |

Removed: **PumpArchive** (github.com/PumpArchive/PumpArchive). Its API (`api.pumparchive.com`)
and docs site returned HTTP 404 / "deployment not found" on 2026-10-21; replaced by the
Pump.fun Memecoin Corpus above.

Logo design references (method only, nothing installed, copied or shipped; `docs/BRAND.md`):
**mcpware/logoloom** (MIT), **neonwatty/logo-designer-skill** (MIT), **yakew7/DesignHub** (MIT).
The TRENCH//RADAR mark and wordmark are original geometry generated by `scripts/brand_assets.py`.
