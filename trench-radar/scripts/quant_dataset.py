"""Build the token-level research dataset for the quantitative score (docs/RESEARCH_QUANT.md).

One row per pump.fun launch in the Pump.fun Memecoin Corpus. Every feature is computed from what
was knowable at the observation time (launch + A seconds, A = 60 and 300); every label from what
happened afterwards. Handling follows the corpus's KNOWN_ISSUES.md:

  - concentration fields: the *_corrected columns; rows flagged top10_pct_suspect -> missing
  - the System Program address is excluded from every wallet feature
  - SOL amounts with sol / (tokens * price) outside [0.01, 100] are left out of SOL sums
  - curve depletion is clipped to [0, 100]
  - entry_price_* fields are never read (near-perfect label proxies)
  - creator history is recomputed point-in-time from the corpus, not taken from creator_past_*

Usage: python scripts/quant_dataset.py --corpus DIR --out FILE.npz
"""
import argparse
import bisect
import glob
import math
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar.text import token_terms  # noqa: E402

SYSTEM = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
AGES = (60, 300)
LABEL_MAX_S = 900          # trades kept up to 15 minutes after launch (labels need 2x-in-15m)
H = 3600


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_tokens(corpus: Path) -> dict:
    cols = ["mint", "detected_at", "name", "symbol", "creator", "is_mayhem_mode", "is_cashback_enabled",
            "dev_buy_pct_corrected", "initial_top10_pct_corrected", "initial_top1_pct_corrected", "top10_pct_suspect",
            "initial_buy_sol", "initial_market_cap_sol", "seconds_to_graduation", "launch_snipe_delta_sol"]
    t = pq.read_table(corpus / "tokens.parquet", columns=cols)
    out = {c: t[c] for c in cols}
    out["t0"] = t["detected_at"].cast(pa.int64()).to_numpy() / 1e6
    return out


def num(col, fill=np.nan):
    a = col.to_numpy(zero_copy_only=False)
    return np.where(a == None, fill, a).astype(float) if a.dtype == object else a.astype(float)  # noqa: E711


def load_trades(corpus: Path, mint_index: dict):
    """Trades within LABEL_MAX_S of launch, as integer arrays; plus trades per UTC hour (for gaps)."""
    parts, hours = [], Counter()
    for f in sorted(glob.glob(str(corpus / "trades" / "*.parquet"))):
        pf = pq.ParquetFile(f)
        for rg in range(pf.metadata.num_row_groups):
            t = pf.read_row_group(rg, columns=["mint", "event_time", "seconds_since_launch", "is_buy", "sol_amount",
                                               "token_amount", "price_sol", "user_wallet", "market_cap_sol"])
            et = t["event_time"].cast(pa.int64()).to_numpy() // 1_000_000
            hours.update(Counter((et // H).tolist()))
            ssl = t["seconds_since_launch"].to_numpy(zero_copy_only=False).astype(float)
            keep = np.where((ssl >= -5) & (ssl <= LABEL_MAX_S))[0]
            t = t.take(pa.array(keep))
            parts.append((t, ssl[keep]))
        log("read", Path(f).name, sum(len(p[1]) for p in parts))
    tab = pa.concat_tables([p[0] for p in parts])
    ssl = np.concatenate([p[1] for p in parts])
    mints = tab["mint"].combine_chunks().dictionary_encode()
    mdict = mints.dictionary.to_pylist()
    lookup = np.array([mint_index.get(m, -1) for m in mdict], dtype=np.int64)
    tok = lookup[mints.indices.to_numpy()]
    w = tab["user_wallet"].combine_chunks().dictionary_encode()
    wdict = w.dictionary.to_pylist()
    wid = w.indices.to_numpy().astype(np.int64)
    system_id = wdict.index(SYSTEM) if SYSTEM in wdict else -1
    sol = num(tab["sol_amount"]); amt = num(tab["token_amount"]); price = num(tab["price_sol"])
    ratio = sol / (amt * price)
    sol_ok = np.isfinite(ratio) & (ratio >= 0.01) & (ratio <= 100)
    d = {"tok": tok, "ssl": ssl, "buy": tab["is_buy"].to_numpy(zero_copy_only=False).astype(bool), "sol": np.where(sol_ok, sol, 0.0),
         "amt": np.nan_to_num(amt), "wallet": wid, "mcap": num(tab["market_cap_sol"]),
         "abs": tab["event_time"].cast(pa.int64()).to_numpy() / 1e6}
    m = d["tok"] >= 0
    d = {k: v[m] for k, v in d.items()}
    return d, wdict, system_id, hours


def per_token_window(tr: dict, n_tok: int, A: int, creator_wid: np.ndarray, system_id: int) -> dict:
    """Aggregates over each token's trades with ssl <= A."""
    m = tr["ssl"] <= A
    tok, buy, sol, amt, wal, ssl, mcap = (tr[k][m] for k in ("tok", "buy", "sol", "amt", "wallet", "ssl", "mcap"))
    f = {}
    f["n_trades"] = np.bincount(tok, minlength=n_tok).astype(float)
    f["n_buys"] = np.bincount(tok, weights=buy, minlength=n_tok)
    f["n_sells"] = f["n_trades"] - f["n_buys"]
    f["buy_sol"] = np.bincount(tok, weights=sol * buy, minlength=n_tok)
    f["sell_sol"] = np.bincount(tok, weights=sol * ~buy, minlength=n_tok)
    # market cap at A: the last trade at or before A
    order = np.lexsort((ssl, tok))
    last = np.full(n_tok, -1)
    last[tok[order]] = order
    f["mcap_at"] = np.where(last >= 0, mcap[np.maximum(last, 0)], np.nan)
    # wallet-level (System Program excluded)
    hum = wal != system_id
    tw = tok[hum].astype(np.int64) * 10_000_000 + wal[hum]
    bmask = buy[hum]
    ub, ub_first = np.unique(tw[bmask], return_index=True)
    f["uniq_buyers"] = np.bincount((ub // 10_000_000).astype(int), minlength=n_tok).astype(float)
    us = np.unique(tw[~bmask])
    f["uniq_sellers"] = np.bincount((us // 10_000_000).astype(int), minlength=n_tok).astype(float)
    # largest single buyer's share of buy SOL (whale / bundle concentration)
    keys, inv = np.unique(tw[bmask], return_inverse=True)
    wsol = np.bincount(inv, weights=sol[hum][bmask])
    ktok = (keys // 10_000_000).astype(int)
    mx = np.zeros(n_tok); np.maximum.at(mx, ktok, wsol)
    f["top_buyer_share"] = np.where(f["buy_sol"] > 0, mx / np.maximum(f["buy_sol"], 1e-12), np.nan)
    # launch-block snipers: distinct buyers in the first 3 seconds
    sn = np.unique(tw[bmask & (ssl[hum] <= 3)])
    f["snipers"] = np.bincount((sn // 10_000_000).astype(int), minlength=n_tok).astype(float)
    # holder retention: buyers who have sold >= 90% of what they bought by A
    bought = np.bincount(np.searchsorted(keys, tw[bmask]), weights=amt[hum][bmask], minlength=len(keys))
    sidx = np.searchsorted(keys, tw[~bmask]); ok = (sidx < len(keys)) & (keys[np.minimum(sidx, len(keys) - 1)] == tw[~bmask])
    sold = np.bincount(sidx[ok], weights=amt[hum][~bmask][ok], minlength=len(keys))
    dumped = (bought > 0) & (sold >= 0.9 * bought)
    f["dumped_share"] = np.where(f["uniq_buyers"] > 0, np.bincount(ktok, weights=dumped, minlength=n_tok) / np.maximum(f["uniq_buyers"], 1), np.nan)
    # creator sold within the window
    cs = (~buy) & (wal == creator_wid[tok])
    f["creator_sold"] = (np.bincount(tok, weights=cs, minlength=n_tok) > 0).astype(float)
    return f


def wallet_history(tr: dict, n_tok: int, t0: np.ndarray, grad_abs: np.ndarray, system_id: int):
    """Point-in-time wallet features for each token's first-A buyers.

    serial: the wallet first-bought >= 10 other tokens in the hour before this purchase (bot-like)
    proven: the wallet was an early (first 60s) buyer of >= 2 tokens that had graduated before
            this token's observation time."""
    m = tr["buy"] & (tr["wallet"] != system_id) & (tr["ssl"] <= max(AGES))
    tok, wal, ab, ssl = tr["tok"][m], tr["wallet"][m], tr["abs"][m], tr["ssl"][m]
    key = wal.astype(np.int64) * 10_000_000 + tok
    order = np.lexsort((ab, key))
    key, tok, wal, ab, ssl = key[order], tok[order], wal[order], ab[order], ssl[order]
    first = np.r_[True, key[1:] != key[:-1]]          # first buy of each (wallet, token)
    tok, wal, ab, ssl = tok[first], wal[first], ab[first], ssl[first]
    # serial: per wallet, count of first-buys in [ab - 1h, ab)
    o = np.lexsort((ab, wal)); wal_s, ab_s = wal[o], ab[o]
    K = np.int64(1 << 31)                            # wallet * 2^31 + whole seconds: exact in int64
    abi = ab_s.astype(np.int64)
    comp = wal_s.astype(np.int64) * K + abi
    lo = np.searchsorted(comp, wal_s.astype(np.int64) * K + abi - H, side="left")
    pos = np.arange(len(comp))
    serial = np.empty(len(comp)); serial[o] = pos - lo
    # proven: credits at graduation time for early (<=60s) buys of tokens that graduated
    cm = (ssl <= 60) & np.isfinite(grad_abs[tok])
    cw, ct = wal[cm], grad_abs[tok][cm]
    co = np.lexsort((ct, cw)); cw, ct = cw[co], ct[co]
    ccomp = cw.astype(np.int64) * K + ct.astype(np.int64)
    out = {}
    for A in AGES:
        q = (ssl <= A)
        qt = t0[tok[q]] + A
        lo_w = np.searchsorted(ccomp, wal[q].astype(np.int64) * K, side="left")
        hi_w = np.searchsorted(ccomp, wal[q].astype(np.int64) * K + qt.astype(np.int64), side="left")
        credits = hi_w - lo_w
        n = np.bincount(tok[q], minlength=n_tok).astype(float)
        out[f"serial_share_{A}"] = np.where(n > 0, np.bincount(tok[q], weights=serial[q] >= 10, minlength=n_tok) / np.maximum(n, 1), np.nan)
        out[f"proven_buyers_{A}"] = np.bincount(tok[q], weights=credits >= 2, minlength=n_tok).astype(float)
    return out


def meta_and_creator(T: dict, early_buyers60: np.ndarray, grad_s: np.ndarray, x2: np.ndarray, gap: np.ndarray):
    """One pass in launch order. For token i at t0 the meta is its term with the most launches in
    the previous 6h; features use launches before t0 and outcomes matured before t0 only."""
    n = len(T["t0"])
    order = np.argsort(T["t0"], kind="stable")
    names = T["name"].to_pylist(); syms = T["symbol"].to_pylist(); creators = T["creator"].to_pylist()
    t0 = T["t0"]
    feats = {k: np.full(n, np.nan) for k in (
        "m_launch_1h", "m_launch_6h", "m_accel_z", "m_share_1h", "m_creator_conc", "m_dup_share", "m_buyers_1h",
        "m_hist_n", "m_hist_grad", "m_hist_x2", "base_grad_24h", "base_x2_24h", "all_launch_1h",
        "c_prior_launches", "c_launches_24h", "c_prior_grads")}
    win = defaultdict(deque)                # term -> deque of (t, i) launches in the last 6h
    hist = defaultdict(deque)               # term -> deque of (t_matured, graduated, x2) over 7 days
    hist_sum = defaultdict(lambda: [0, 0, 0])
    pending = deque()                       # (t0+H, i) awaiting maturity
    glob_launch = deque(); glob_hist = deque(); gsum = [0, 0, 0]
    cre_all = Counter(); cre_win = defaultdict(deque); cre_grads = Counter()
    terms_of = {}
    W7 = 7 * 86400
    for step, i in enumerate(order):
        t = t0[i]
        # mature outcomes (1h labels; all graduations in the corpus happen within 1h)
        while pending and pending[0][0] <= t:
            tm, j = pending.popleft()
            if gap[j]:
                continue
            g = int(np.isfinite(grad_s[j]) and grad_s[j] <= H); xx = int(x2[j])
            for w in terms_of[j]:
                hist[w].append((tm, g, xx)); s = hist_sum[w]; s[0] += 1; s[1] += g; s[2] += xx
            glob_hist.append((tm, g, xx)); gsum[0] += 1; gsum[1] += g; gsum[2] += xx
            if g:
                cre_grads[creators[j]] += 1
        while glob_hist and glob_hist[0][0] < t - 86400:
            _, g, xx = glob_hist.popleft(); gsum[0] -= 1; gsum[1] -= g; gsum[2] -= xx
        while glob_launch and glob_launch[0] < t - H:
            glob_launch.popleft()
        tl = token_terms(names[i], syms[i])[:6]
        terms_of[i] = tl
        best, best_n = None, -1
        for w in tl:
            dq = win[w]
            while dq and dq[0][0] < t - 6 * H:
                dq.popleft()
            hq = hist[w]
            while hq and hq[0][0] < t - W7:
                _, g, xx = hq.popleft(); s = hist_sum[w]; s[0] -= 1; s[1] -= g; s[2] -= xx
            if len(dq) > best_n:
                best, best_n = w, len(dq)
        if best is not None:
            dq = win[best]
            in1h = [j for (tj, j) in dq if tj >= t - H]
            n1, n6 = len(in1h), len(dq)
            base = (n6 - n1) / 5.0
            feats["m_launch_1h"][i] = n1; feats["m_launch_6h"][i] = n6
            feats["m_accel_z"][i] = (n1 - base) / math.sqrt(base + 1)
            feats["m_creator_conc"][i] = 1 - len({creators[j] for j in in1h}) / n1 if n1 else np.nan
            nm = (names[i] or "").strip().lower()
            feats["m_dup_share"][i] = sum((names[j] or "").strip().lower() == nm for j in in1h) / n1 if n1 else np.nan
            # early buyers of the meta's tokens whose 60s window closed before t
            feats["m_buyers_1h"][i] = sum(early_buyers60[j] for (tj, j) in dq if tj >= t - H and tj + 60 <= t)
            s = hist_sum[best]
            feats["m_hist_n"][i], feats["m_hist_grad"][i], feats["m_hist_x2"][i] = s
        feats["all_launch_1h"][i] = len(glob_launch)
        feats["m_share_1h"][i] = feats["m_launch_1h"][i] / max(1, len(glob_launch)) if best is not None else np.nan
        feats["base_grad_24h"][i] = gsum[1] / gsum[0] if gsum[0] else np.nan
        feats["base_x2_24h"][i] = gsum[2] / gsum[0] if gsum[0] else np.nan
        c = creators[i]
        cq = cre_win[c]
        while cq and cq[0] < t - 86400:
            cq.popleft()
        feats["c_prior_launches"][i] = cre_all[c]; feats["c_launches_24h"][i] = len(cq); feats["c_prior_grads"][i] = cre_grads[c]
        # add this launch
        for w in tl:
            win[w].append((t, i))
        glob_launch.append(t); cre_all[c] += 1; cq.append(t)
        pending.append((t + H, i))
        if step % 100000 == 0:
            log("meta pass", step)
    return feats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    T = load_tokens(a.corpus)
    n = len(T["t0"])
    mint_list = T["mint"].to_pylist()
    mint_index = {m: i for i, m in enumerate(mint_list)}
    log("tokens", n)
    tr, wdict, system_id, hours = load_trades(a.corpus, mint_index)
    log("early trades", len(tr["tok"]))
    wpos = {w: k for k, w in enumerate(wdict)}
    creator_wid = np.array([wpos.get(c, -2) for c in T["creator"].to_pylist()], dtype=np.int64)
    t0 = T["t0"]
    grad_s = num(T["seconds_to_graduation"])
    grad_abs = t0 + grad_s
    init_mcap = num(T["initial_market_cap_sol"])
    # 2x label: peak trade market cap within 15 minutes >= 2x the launch market cap
    pk = np.full(n, -np.inf); np.maximum.at(pk, tr["tok"], np.nan_to_num(tr["mcap"], nan=-np.inf))
    x2 = (pk >= 2 * init_mcap).astype(float)
    # collection gaps: hours with no trades inside the covered span; a label window touching one is unobserved
    hs = sorted(hours); span = range(hs[0], hs[-1] + 1)
    gap_hours = [h for h in span if hours.get(h, 0) == 0]
    gh = np.array(gap_hours, dtype=float) * H
    gap = np.zeros(n, bool)
    for g in gh:
        gap |= (t0 > g - H) & (t0 < g + H)
    gap |= t0 > (hs[-1] * H - H)                      # final hour: labels not mature
    log("gap hours", len(gap_hours), [time.strftime("%m-%d %H", time.gmtime(g)) for g in gh[:40]])
    out = {"t0": t0, "grad_s": grad_s, "x2_15m": x2, "gap": gap.astype(float), "init_mcap": init_mcap,
           "mayhem": num(T["is_mayhem_mode"]), "cashback": num(T["is_cashback_enabled"]),
           "dev_buy_pct": num(T["dev_buy_pct_corrected"]),
           "top10_pct": np.where(num(T["top10_pct_suspect"]) == 1, np.nan, num(T["initial_top10_pct_corrected"])),
           "top1_pct": np.where(num(T["top10_pct_suspect"]) == 1, np.nan, num(T["initial_top1_pct_corrected"])),
           "initial_buy_sol": num(T["initial_buy_sol"]), "snipe_delta_sol": num(T["launch_snipe_delta_sol"])}
    for A in AGES:
        f = per_token_window(tr, n, A, creator_wid, system_id)
        for k, v in f.items():
            out[f"{k}_{A}"] = v
        log("window", A)
    out.update(wallet_history(tr, n, t0, grad_abs, system_id))
    log("wallet history")
    out.update(meta_and_creator(T, out["uniq_buyers_60"], grad_s, x2, gap))
    log("meta pass done")
    np.savez_compressed(a.out, **out)
    log("saved", a.out, len(out), "arrays")


if __name__ == "__main__":
    main()
