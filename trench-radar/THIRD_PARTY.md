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

## Downloaded on first start

**all-MiniLM-L6-v2** (ONNX export, quantized), https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2,
Apache-2.0. Stored in the data folder under `models/`.

## Libraries (installed from PyPI)

FastAPI (MIT), Uvicorn (BSD-3-Clause), httpx (BSD-3-Clause), websockets (BSD-3-Clause),
onnxruntime (MIT), tokenizers (Apache-2.0), NumPy (BSD-3-Clause), anthropic (MIT, optional).

## Used as reference only (nothing copied)

| Repository | Licence | How it was used |
|---|---|---|
| pump-fun/pump-public-docs | none stated | Event, account and pricing layouts (IDL, docs) that the decoders follow. Interface facts, no code. |
| aethernet404/rugcheck | none stated | The idea of scoring top-10 holder concentration. Reimplemented from the trade stream; its RPC calls are blocked on free public endpoints. |
| killuawx3/pump-fun-research | none stated | Background figures (graduation rate ~1–1.7%). |
| nirholas/pump-fun-sdk | "All rights reserved" | Not used. |
| metaplex-foundation/mpl-token-metadata | Metaplex NFT licence | Not needed: the launch event already carries the metadata URI. |
| jito-foundation/jito-solana | Apache-2.0 | Validator software; not needed. Bundled launches are detected from same-block buys instead. |
| mlfoundations/open_clip | MIT | Not integrated: needs PyTorch (~2 GB) and downloading every token image. |
| UKPLab/sentence-transformers | Apache-2.0 | Not installed (needs PyTorch); its MiniLM model runs through onnxruntime instead. |
| PumpArchive/PumpArchive | none stated | Its API and docs site are offline (HTTP 404, 2026-10-21). |
