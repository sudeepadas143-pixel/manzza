"""Plain-language explanations of each meta and of its launch-edge rank.

The questions are kept apart: what the meta is, what is happening to it, why it is getting
attention, why the edge model ranks it where it does, what could go wrong, what to watch, and
how much to trust it. Every sentence is built from a measured value; nothing is generated freely.

The reasons for and against a rank come from the model itself. The launch edge is linear, so
each input's contribution is exact: coefficient x (this meta's standardised value - the average
of this read's metas); they add up to the meta's lift over the read's average (what SHAP reports
for a linear model, without the dependency). Inputs that move together (launch counts, buyers,
volume) are explained as themes, because their separate coefficients share information and only
their sum is meaningful. Every reason compares the meta with the median meta of the same read.
Confidence comes from how each tier actually did in back-tests and later months (radar/data/
meta_model.json), not from a label.
"""
from __future__ import annotations

import math

from . import meta_model as mm

H = 3600
HIST_S = 7 * 86400


def _isnum(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def _int(v) -> str:
    return f"{v:,.0f}" if _isnum(v) else "—"


def _pct(v, d=0) -> str:
    return f"{v * 100:.{d}f}%" if _isnum(v) else "—"


def _sol(v) -> str:
    return f"{v:+.1f} SOL" if _isnum(v) else "—"


def _usd(v) -> str:
    if not _isnum(v):
        return "—"
    return f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:.0f}k" if v >= 1e3 else f"${v:.0f}"


def _num(d):
    return lambda v: f"{v:.{d}f}" if _isnum(v) else "—"


# model input -> (plain label, how to show its raw value, inverse of its transform, what it measures)
CATALOG = {
    "launches_1h": ("New coins, last hour", _int, "log", "Coins on this idea launched in the past hour (launch factories left out)."),
    "launches_6h": ("New coins, last 6 hours", _int, "log", "Coins on this idea launched in the past 6 hours."),
    "accel_z": ("Launch speed-up", lambda v: f"{v:+.1f}" if _isnum(v) else "—", "id",
                "Launches in the last hour against the 6 hours before (above 2 = clearly speeding up)."),
    "share_6h": ("Share of all launches", lambda v: _pct(v, 1), "share", "This idea's share of every launch in the last 6 hours."),
    "growth_3h": ("Launches, last 3 h vs the 3 before", lambda v: f"{math.exp(v):.1f}×" if _isnum(v) else "—", "id",
                  "Whether launches have been climbing over the last few hours (above 1× = climbing)."),
    "hours_above_base": ("Hours above its usual pace", lambda v: f"{v:.0f} of 3" if _isnum(v) else "—", "id",
                         "How many of the last 3 hours had more launches than its 6-hour average."),
    "age_h": ("How long it has been around", lambda v: f"{v:.0f} h" if _isnum(v) else "—", "id",
              "Hours since its first launch in the 7-hour lookback (7 = at least that old)."),
    "creators_1h": ("Different creators, last hour", _int, "log", "Distinct wallets launching coins on this idea in the past hour."),
    "buyers_1h": ("Buyers, last hour", _int, "log", "Unique buyers across its coins in the past hour (summed per coin)."),
    "buyer_share": ("Wallets buying, not selling", _pct, "id", "Of the wallets trading its coins in the past hour, the share that bought."),
    "net_sol_1h": ("Money into the curves, last hour", _sol, "slog", "SOL bought minus sold on its coins' bonding curves in the past hour."),
    "top_progress": ("Closest coin to graduating", _pct, "id", "How far its leading coin is along the bonding curve."),
    "grads_24h": ("Coins that graduated, last 24 h", _int, "log", "Its coins that filled their bonding curve in the past day."),
    "vol_1h": ("Trading volume, last hour", _usd, "log", "Dollar volume across its coins in the past hour."),
    "tracked": ("Coins actively trading", _int, "log", "Its coins with fresh trading data: coins people are actually trading."),
    "smart_1h": ("Buys from proven wallets", _int, "log", "Buys in the past hour from wallets that got in early on earlier graduates."),
    "sat_index": ("Crowding score", _num(2), "id", "0 = fresh, 1 = crowded: the average of the crowding signals."),
    "dup_share": ("Copycat tickers", _pct, "id", "Share of recent coins reusing a ticker already used in this meta."),
    "winner_share": ("Biggest coin's share of volume", _pct, "id", "How much of the day's volume its biggest coin takes."),
    "buyers_per_launch": ("Buyers per new coin", _num(1), "log", "Buyers in the last hour for each coin launched in that hour."),
    "outpacing": ("Launches growing faster than buyers", lambda v: f"{v:+.2f}" if _isnum(v) else "—", "id",
                  "Launch growth minus buyer growth over the last hour (above 0 = new coins outrunning buyers)."),
    "serial_share": ("Creators who launch many coins", _pct, "id", "Share of its creators who launched 3+ coins in the day before."),
    "market": ("Whole-market temperature", _num(2), "id", "The app's market score, 0 cold to 1 hot; the same for every meta at a given time."),
}
RAW_KEY = {"buyers_per_launch": "sat_buyers_per_launch", "outpacing": "sat_launches_outpacing_buyers"}
# Inputs that move together are explained together; their separate coefficients share information.
THEMES = {
    "crowding": ["launches_1h", "launches_6h", "growth_3h", "hours_above_base", "accel_z", "share_6h", "age_h"],
    "creators": ["creators_1h", "serial_share"],
    "spread": ["tracked"],
    "copycats": ["dup_share"],
    "money_in": ["buyers_1h", "vol_1h", "buyers_per_launch", "buyer_share", "net_sol_1h", "smart_1h", "top_progress",
                 "grads_24h", "winner_share", "outpacing", "sat_index"],
}
THEME_LABEL = {"crowding": "How many new coins are piling in", "creators": "Who is launching", "spread": "How many coins trade",
               "copycats": "Copycat tickers", "money_in": "How much money is already in", "market": "Whole market"}
STRENGTHEN = {"creators": "more different people keep launching on it", "spread": "more of its coins start trading, not just one",
              "crowding": "the flood of new coins slows down while buyers stay", "copycats": "fewer copycat tickers appear",
              "money_in": "buying holds steady instead of rushing in all at once"}
WEAKEN = {"creators": "launches start coming from a few wallets instead of many people",
          "spread": "trading narrows to one or two coins", "crowding": "new coins start piling in, hour after hour",
          "copycats": "copycat tickers start piling up",
          "money_in": "a rush of money and buyers arrives all at once (often the late part of a move)"}


def _inverse(kind: str, v: float) -> float:
    if kind == "log":
        return math.expm1(v)
    if kind == "share":
        return math.expm1(v) / 1000
    if kind == "slog":
        return math.copysign(math.expm1(abs(v)), v)
    return v


def _med(vals):
    v = sorted(x for x in vals if _isnum(x))
    return v[len(v) // 2] if v else None


def contributions(scored: list[dict], market: dict, model: mm.EdgeModel) -> list[list[dict]]:
    """Per meta, each input's exact share of its lift over the read's average meta."""
    z_all = []
    for s in scored:
        x = mm.transform(mm.raw(s, market))
        vals = [float(x[k]) for k in model.names]
        miss = [math.isnan(v) for v in vals]
        z = [((model.med[j] if miss[j] else v) - model.mu[j]) / model.sd[j] for j, v in enumerate(vals)]
        z += [((1.0 if miss[j] else 0.0) - model.mu[len(vals) + i]) / model.sd[len(vals) + i] for i, j in enumerate(model.ind)]
        z_all.append((z, miss))
    n = len(z_all)
    mean_z = [sum(z[j] for z, _ in z_all) / n for j in range(len(z_all[0][0]))] if n else []
    out = []
    for z, miss in z_all:
        items = [{"input": name, "contribution": model.b[1 + j] * (z[j] - mean_z[j]), "missing": miss[j],
                  "z": None if miss[j] else z[j]} for j, name in enumerate(model.names)]
        for i, j in enumerate(model.ind):   # "this input was missing" indicators count toward that input
            col = len(model.names) + i
            items[j]["contribution"] += model.b[1 + col] * (z[col] - mean_z[col])
        out.append(items)
    return out


def _narrative_for(mints: list[str], narratives: list[dict], term: str | None = None) -> dict | None:
    """The narrative describing this meta: among narratives that mention the meta's word, the one
    sharing most of its recent coins (3+); failing that, one holding 3+ coins and a third of them."""
    if not mints or not narratives:
        return None
    ms = set(mints)
    best, best_n = None, 0
    tier = {1: (None, 0), 2: (None, 0)}   # 1: the word is in its title, 2: only in its terms
    t = (term or "").lower()
    for nar in narratives:
        k = len(ms & set(nar.get("members") or ()))
        if k > best_n:
            best, best_n = nar, k
        lvl = 1 if t and t in (nar.get("title") or "").lower() else \
            2 if t and any(t in w.lower() for w in nar.get("terms") or ()) else 0
        if lvl and k > tier[lvl][1]:
            tier[lvl] = (nar, k)
    for lvl in (1, 2):
        if tier[lvl][1] >= 3:
            return tier[lvl][0]
    return best if best is not None and best_n >= max(3, len(ms) / 3) else None


def _names(ex: list[dict], k: int = 4) -> str:
    seen, out = set(), []
    for e in ex:
        nm = (e.get("name") or e.get("symbol") or "").strip()
        if nm and nm.lower() not in seen:
            seen.add(nm.lower())
            out.append(nm)
        if len(out) == k:
            break
    return ", ".join(out)


def concept(s: dict, nar: dict | None) -> dict:
    L, D = s["evidence"]["launch"], s["evidence"]["demand"]
    terms = s["terms"]
    toks = D.get("top_tokens") or []
    if nar:
        rep = nar["represents"]
        ex = _names([e for e in rep.get("examples") or [] if (e.get("name") or "").strip().lower() != nar["title"].strip().lower()]) \
            or _names(toks)
        text = [f"Coins about “{terms[0]}”. The most typical one is “{nar['title']}”" + (f"; others include {ex}." if ex else ".")]
        if rep.get("post"):
            p = rep["post"]
            text.append(f"{p['tokens']} of them point to the same X post by @{p['author']}: “{p['text'][:200]}”")
        elif rep.get("description"):
            text.append(f"Their creators describe it as: “{rep['description'][:200]}”")
        cat = nar.get("category") or {}
        if cat.get("primary"):
            sec = cat.get("secondary") or []
            kind = cat["primary"].lower()
            text.append(f"It reads as {'an' if kind[:1] in 'aeiou' else 'a'} {kind} meta" + (f", with some {', '.join(sec).lower()}" if sec else "") + ".")
        cl = nar.get("closest")
        if cl and cl.get("similarity", 0) >= 0.5 and cl.get("distinct_terms"):
            text.append(f"What sets it apart from the similar “{cl['title']}” coins: {', '.join(cl['distinct_terms'])}.")
        source = "post" if rep.get("post") else "description" if rep.get("description") else "names"
    else:
        ex = _names(toks)
        also = f", often together with {', '.join(terms[1:4])}" if len(terms) > 1 else ""
        text = [f"Coins whose names use “{terms[0]}”{also}" + (f", such as {ex}." if ex else ".")]
        text.append("No description or linked post explains the idea yet, so this is read from the names alone.")
        source = "names"
    return {"text": text, "source": source,
            "narrative": {"label": nar["label"], "title": nar["title"], "state": nar.get("state")} if nar else None,
            "connects": f"Grouped because their names share “{terms[0]}”"
                        + (f" (with {', '.join(terms[1:4])})" if len(terms) > 1 else "")
                        + f": {L['launches_6h']} coins in the last 6 hours, from {L['creators_1h']} different creators in the last hour."}


PLAIN_SIGNAL = {"copycat_tickers": lambda v: f"{v:.0%} of recent coins reuse a ticker already used here",
                "buyers_per_launch": lambda v: f"only {v:.0f} buyer{'s' if round(v) != 1 else ''} an hour for each new coin",
                "launches_outpacing_buyers": lambda v: "new coins are growing faster than buyers",
                "winner_concentration": lambda v: f"one coin has {v:.0%} of the day's volume",
                "volume_fading": lambda v: "trading volume is dropping",
                "social_fading": lambda v: "people are posting about it less",
                "meta_age": lambda v: f"it has been running for {v:.0f}+ hours"}


def happening(s: dict, buyers_prev: float | None) -> dict:
    L, D, S = s["evidence"]["launch"], s["evidence"]["demand"], s["evidence"]["saturation"]
    per_h, now = L["launches_6h"] / 6, L["launches_1h"]
    b1 = D.get("unique_buyers_h1_sum") or 0
    text = []
    if now >= 1.3 * per_h and now >= 3:
        text.append(f"More coins based on this idea are appearing: {now} in the last hour, against about {per_h:.0f} an hour over the past 6 hours.")
    elif now <= 0.7 * per_h:
        text.append(f"Fewer new coins are appearing: {now} in the last hour, against about {per_h:.0f} an hour over the past 6 hours.")
    else:
        text.append(f"New coins are arriving at a steady pace: {now} in the last hour, about its 6-hour average.")
    growth = (b1 / buyers_prev) if buyers_prev else None
    if growth is not None and buyers_prev >= 10:
        if growth >= 1.2:
            text.append(f"Buyer interest is growing: {b1:,.0f} buyers in the last hour, up from {buyers_prev:,.0f} the hour before.")
        elif growth <= 0.8:
            text.append(f"Buyer interest is cooling: {b1:,.0f} buyers in the last hour, down from {buyers_prev:,.0f} the hour before.")
        else:
            text.append(f"Buyer interest is holding: {b1:,.0f} buyers in the last hour, about the same as the hour before.")
    elif b1:
        text.append(f"{b1:,.0f} buyers across its coins in the last hour.")
    else:
        text.append("Nobody is buying its coins yet, as far as the app can see.")
    net = D.get("curve_net_sol_1h")
    if _isnum(net) and abs(net) >= 0.5:
        text.append(f"Buyers are putting money in: {net:+.1f} SOL net into these coins' curves in the last hour." if net > 0
                    else f"Money is leaving: {net:+.1f} SOL net out of these coins' curves in the last hour.")
    crowded = (S["index"] or 0) >= 0.6
    hot = [PLAIN_SIGNAL[k](v["value"]) for k, v in S["signals"].items() if v["s"] >= 0.6 and k in PLAIN_SIGNAL]
    if hot:
        text.append(("It is getting crowded: " if crowded else "Signs of crowding: ") + "; ".join(hot) + ".")
    if (L.get("first_seen_in_window_h") or 99) < 2:
        status = "new"
    elif crowded:
        status = "crowded"
    elif (now >= 1.3 * per_h and now >= 3) or (growth or 0) >= 1.2:
        status = "growing"
    elif now <= 0.7 * per_h and (growth is None or growth <= 0.8):
        status = "fading"
    else:
        status = "steady"
    return {"status": status, "text": text}


def attention(s: dict, nar: dict | None, social_measured: bool) -> list[str]:
    ev = s["evidence"]
    D, So, A = ev["demand"], ev["social"], ev.get("attention_purchased") or {}
    out = []
    if nar and nar["represents"].get("post") and nar["represents"]["post"]["tokens"] >= 2:
        p = nar["represents"]["post"]
        out.append(f"An X post is spawning coins: {p['tokens']} launches cite @{p['author']}"
                   + (f" ({p['followers']:,} followers)" if p.get("followers") else "") + ".")
    if social_measured and So.get("mentions_6h"):
        out.append(f"People are posting about it: {So['mentions_1h']} mentions in the last hour, {So['mentions_6h']} in 6 hours, "
                   f"from {So['independent_authors_6h']} independent accounts.")
    toks = D.get("top_tokens") or []
    if toks and (toks[0].get("buyers_h1") or 0) >= 10:
        t = toks[0]
        out.append(f"A leading coin is drawing buyers: ${t.get('symbol') or t.get('name')} had {t['buyers_h1']:,} buyers in the last hour.")
    if D.get("graduations_24h"):
        out.append(f"{D['graduations_24h']} of its coins graduated in the last day, which tends to pull in copies.")
    if D.get("smart_buyers_h1_sum"):
        out.append(f"Wallets with a record of early entries made {D['smart_buyers_h1_sum']} buys in the last hour.")
    if A.get("boosts_24h") or A.get("profiles_24h"):
        out.append(f"Some of it is paid for: {A.get('boosts_24h', 0)} coin(s) bought DexScreener boosts in the last day.")
    if not out:
        out.append("No outside trigger is visible: no linked post" + ("" if social_measured else ", no social data connected")
                   + ", no standout coin. The attention shows up only as people launching coins with these words.")
    return out


def risks(s: dict, buyers_prev: float | None, market: dict) -> list[str]:
    ev = s["evidence"]
    L, D, S, C = ev["launch"], ev["demand"], ev["saturation"], ev.get("creators") or {}
    out = []
    dup = L.get("duplicate_symbol_share_6h")
    if _isnum(dup) and dup >= 0.5:
        out.append(f"Lots of copycats: {dup:.0%} of recent coins reuse a ticker already used here.")
    top = D.get("top_token_share_vol24")
    if _isnum(top) and top >= 0.6 and (D.get("vol_h24_usd") or 0) > 5000:
        out.append(f"One coin is carrying the whole trend ({top:.0%} of the day's volume); if it dumps, the meta may go with it.")
    b1 = D.get("unique_buyers_h1_sum") or 0
    if buyers_prev and buyers_prev >= 10 and b1 < 0.7 * buyers_prev:
        out.append(f"Buyers are disappearing: {b1:,.0f} in the last hour, down from {buyers_prev:,.0f}.")
    sig = S["signals"]
    if "volume_fading" in sig and sig["volume_fading"]["s"] >= 0.5:
        out.append("Interest is fading: trading volume in the last hour is well below its 6-hour average.")
    if "launches_outpacing_buyers" in sig and sig["launches_outpacing_buyers"]["s"] >= 0.5:
        out.append("New coins are arriving faster than new buyers.")
    if "buyers_per_launch" in sig and sig["buyers_per_launch"]["s"] >= 0.7:
        v = sig["buyers_per_launch"]["value"]
        out.append(f"Thin demand per coin: about {v:.0f} buyer{'s' if round(v) != 1 else ''} an hour for each new coin.")
    bs = D.get("buyer_share_h1")
    if _isnum(bs) and bs < 0.45:
        out.append(f"Sellers are winning: only {bs:.0%} of wallets trading it in the last hour were buying.")
    if _isnum(bs) and bs >= 0.8:
        out.append(f"Buying is very one-sided ({bs:.0%} of wallets buying); in past data that often marked late entries near a top.")
    if D.get("tokens_dev_sold"):
        out.append(f"Creators sold into {D['tokens_dev_sold']} of its active coins.")
    if D.get("tokens_bundled"):
        out.append(f"{D['tokens_bundled']} of its coins were bundled at launch (several wallets buying in the first block).")
    if D.get("organic_buyers_h1_sum") is not None and b1 and D["organic_buyers_h1_sum"] < 0.5 * b1:
        out.append(f"Much of the buying looks automated: only {D['organic_buyers_h1_sum']} of {b1:,.0f} buyers are not bot wallets.")
    if D.get("insider_buyers_h1_sum"):
        out.append(f"{D['insider_buyers_h1_sum']} buyer(s) are wallets labelled insiders in a public dataset.")
    if _isnum(C.get("serial_share")) and C["serial_share"] >= 0.5:
        out.append(f"{C['serial_share']:.0%} of its creators launched 3+ coins the day before; serial launchers graduate far less often.")
    if (D.get("tokens_tracked") or 0) < 3:
        k = D.get("tokens_tracked") or 0
        out.append(f"Thin evidence: only {k} of its coins {'has' if k == 1 else 'have'} trading data.")
    if market.get("regime") == "cold":
        out.append("The whole market is cold right now.")
    out.append("Graduation is not profit: most coins in any meta still go to zero.")
    return out


def _neutral(theme: str, c: float, items: list[dict], raw: dict, others: dict) -> str:
    """A theme whose measurements point different ways: state the ones that moved it, without a story."""
    subs = sorted((i for i in items if i["input"] in THEMES[theme] and not i["missing"] and i["contribution"] * c > 0),
                  key=lambda i: -abs(i["contribution"]))[:2]
    parts = []
    for i in subs:
        label, fmt, _, _ = CATALOG[i["input"]]
        key = RAW_KEY.get(i["input"], i["input"])
        parts.append(f"{label.lower()}: {fmt(raw.get(key))} (most metas: {fmt(others.get(key))})")
    return f"{THEME_LABEL[theme]} {'helps' if c > 0 else 'hurts'} its rank, mainly through " + "; ".join(parts) + "." if parts else \
        f"{THEME_LABEL[theme]} {'helps' if c > 0 else 'hurts'} its rank."


def theme_sentences(raw: dict, others: dict, contrib: dict, items: list[dict] | None = None) -> tuple[list, list, list, list]:
    """(for, against, themes for, themes against): one sentence per theme whose summed
    contribution matters, comparing this meta with the median meta of the same read."""
    g = lambda k: raw.get(RAW_KEY.get(k, k))  # noqa: E731
    m = lambda k: others.get(RAW_KEY.get(k, k))  # noqa: E731
    pos, neg = [], []

    def add(theme, up, down, consistent=lambda c: True):
        """`consistent(c)`: whether the story sentence matches the measurements; if not, say it neutrally."""
        c = contrib.get(theme, 0)
        if abs(c) >= 0.05:
            text = (up if c > 0 else down) if consistent(c) or items is None else _neutral(theme, c, items, raw, others)
            (pos if c > 0 else neg).append((abs(c), theme, text))

    def side(key, c):     # the meta is on the side of the median that the story claims
        v, med = g(key), m(key)
        return _isnum(v) and _isnum(med) and ((v < med) if c > 0 else (v > med))

    up_x, down_x = [], []
    if _isnum(g("growth_3h")):
        if g("growth_3h") <= 0.2:
            up_x.append("launches are not climbing hour after hour")
        else:
            down_x.append(f"launches have climbed for hours ({math.exp(g('growth_3h')):.1f}× the 3 hours before)")
    if _isnum(g("age_h")) and g("age_h") >= 6.5:
        down_x.append("it has been running for 7 hours or more")
    elif _isnum(g("age_h")) and g("age_h") < 3:
        up_x.append(f"it appeared only about {g('age_h'):.0f} h ago")
    add("crowding",
        f"Fewer new coins are crowding in than for most metas right now ({_int(g('launches_1h'))} in the last hour; most metas: "
        f"{_int(m('launches_1h'))})" + "".join("; " + x for x in up_x) + ", so a new coin is less likely to get lost.",
        f"More new coins are crowding in than for most metas ({_int(g('launches_1h'))} in the last hour; most metas: "
        f"{_int(m('launches_1h'))})" + "".join("; " + x for x in down_x) + ". Each new coin competes with more others.",
        lambda c: side("launches_1h", c))
    add("creators",
        f"More different people are launching on it than on most metas ({_int(g('creators_1h'))} creators in the last hour; "
        f"most metas: {_int(m('creators_1h'))}), not a few wallets spamming.",
        f"Fewer different people are behind it than most metas ({_int(g('creators_1h'))} creators in the last hour; "
        f"most metas: {_int(m('creators_1h'))}).", lambda c: side("creators_1h", -c))
    add("spread",
        f"More of its coins are actually trading than for most metas ({_int(g('tracked'))}; most metas: {_int(m('tracked'))}), "
        "so interest is not stuck on one coin.",
        f"Fewer of its coins are trading than for most metas ({_int(g('tracked'))}; most metas: {_int(m('tracked'))}).",
        lambda c: side("tracked", -c))
    add("copycats",
        f"Fewer copycat tickers than most metas ({_pct(g('dup_share'))} of recent coins reuse a ticker; most metas: {_pct(m('dup_share'))}).",
        f"More copycat tickers than most metas ({_pct(g('dup_share'))} of recent coins reuse a ticker; most metas: {_pct(m('dup_share'))}).",
        lambda c: side("dup_share", c))
    add("money_in",
        f"Less money has rushed in than for most metas ({_usd(g('vol_1h'))} traded and {_int(g('buyers_1h'))} buyers in the last hour; "
        f"most metas: {_usd(m('vol_1h'))}, {_int(m('buyers_1h'))}), so it is not yet a crowded trade.",
        f"More money has already rushed in than for most metas ({_usd(g('vol_1h'))} traded and {_int(g('buyers_1h'))} buyers in the "
        f"last hour; most metas: {_usd(m('vol_1h'))}, {_int(m('buyers_1h'))}). In the back-tests, metas this busy left less room for new coins.",
        lambda c: side("vol_1h", c) and side("buyers_1h", c))
    pos.sort(reverse=True)
    neg.sort(reverse=True)
    return [t for *_, t in pos], [t for *_, t in neg], [th for _, th, _ in pos], [th for _, th, _ in neg]


def evidence_table(items: list[dict], raw: dict, model: mm.EdgeModel, others: dict) -> list[dict]:
    out = []
    for it in sorted(items, key=lambda i: -abs(i["contribution"])):
        name = it["input"]
        label, fmt, kind, meaning = CATALOG[name]
        key = RAW_KEY.get(name, name)
        out.append({"input": name, "label": label, "theme": next((t for t, ins in THEMES.items() if name in ins), "market"),
                    "value": "not measured yet" if it["missing"] else fmt(raw.get(key)),
                    "most_metas_now": fmt(others.get(key)),
                    "typical_in_training": fmt(_inverse(kind, model.med[model.names.index(name)])),
                    "meaning": meaning, "effect": round(it["contribution"], 3),
                    "reads": ("no data: treated as typical" if it["missing"] else
                              "supports the rank" if it["contribution"] > 0.02 else
                              "weakens the rank" if it["contribution"] < -0.02 else "little effect"),
                    "unusual": it["z"] is not None and abs(it["z"]) > 4})
    return out


PERIODS = {"corpus_walk_forward": "June–July 2026 (walk-forward, unseen days)", "meta_sep": "September 16 (a later month)",
           "meta_oct": "October 15 (a later month)"}


def confidence(s: dict, items: list[dict], model: mm.EdgeModel) -> dict:
    tier = s["edge"]["tier"]
    T = ((model.spec.get("validation") or {}).get("all_launches") or {}).get("tiers") or {}
    periods, text = [], []
    for key, label in PERIODS.items():
        t = T.get(key) or {}
        if tier in t:
            r = t[tier]
            periods.append({"period": label, "ratio": r["ratio"], "ci90": r["ci90"], "meta_hours": r["meta_hours"],
                            "launches": r["launches"], "graduations": r["graduations"],
                            "strongest": (t.get("strongest") or {}).get("ratio"), "weakest": (t.get("weakest") or {}).get("ratio")})
            text.append(f"{label}: the next coins of metas ranked “{tier}” graduated {r['ratio']:.2f}× as often as all coins "
                        f"(90% range {r['ci90'][0]:.2f}–{r['ci90'][1]:.2f}; {r['meta_hours']:,} meta-hours, {r['launches']:,} coins).")
    tested = [k for k in PERIODS if "strongest" in (T.get(k) or {}) and "weakest" in (T.get(k) or {})]
    separated = [k for k in tested if T[k]["strongest"]["ci90"][0] > T[k]["weakest"]["ci90"][1]]
    if tested:
        text.append(f"Metas ranked strongest beat those ranked weakest clearly in {len(separated)} of {len(tested)} periods tested"
                    + ("." if len(separated) == len(tested) else
                       f"; not in {', '.join(PERIODS[k] for k in tested if k not in separated)}, where the tiers barely differed."))
    big = {n for n, b in zip(model.names, model.b[1:]) if abs(b) >= 0.08}
    gaps = [CATALOG[i["input"]][0].lower() for i in items if i["missing"] and i["input"] in big]
    unusual = [CATALOG[i["input"]][0].lower() for i in items if i["z"] is not None and abs(i["z"]) > 4]
    L, D = s["evidence"]["launch"], s["evidence"]["demand"]
    thin = (D.get("tokens_tracked") or 0) < 3 or L["launches_6h"] < 5
    notes = []
    if gaps:
        notes.append("Missing for this meta: " + ", ".join(gaps) + ". The model treats missing inputs as typical.")
    if unusual:
        notes.append("Outside what the model was trained on: " + ", ".join(unusual) + ". Treat the rank with extra caution.")
    if thin:
        notes.append(f"Small sample: {L['launches_6h']} coins in 6 hours, {D.get('tokens_tracked') or 0} with trading data.")
    notes.append("It compares metas with each other right now. It does not say how your own coin will do: once a coin is live, "
                 "its first minute of trading tells you far more than its meta.")
    level = "low" if (gaps or unusual or thin) else "moderate" if tested and len(separated) == len(tested) else "mixed"
    summary = {"low": "Low: the evidence for this particular meta is thin, missing or unusual.",
               "mixed": f"Mixed: the ranking helped in {len(separated)} of {len(tested)} periods tested, not all.",
               "moderate": "Moderate: the ranking helped in every period tested, by varying amounts."}[level]
    track = (f"Metas ranked “{tier}” saw their next coins graduate "
             + ", ".join(f"{p['ratio']:.2f}×" for p in periods[:-1]) + (" and " if len(periods) > 1 else "")
             + f"{periods[-1]['ratio']:.2f}× as often as all coins in the {len(periods)} periods tested.") if periods else None
    return {"level": level, "summary": summary, "track": track, "periods": periods, "text": text, "notes": notes}


def history(s: dict, live, now_t: int) -> dict | None:
    """The meta's own record while the app was running (live stream only)."""
    ctx = getattr(live, "early_ctx", None)
    if ctx is None:
        return None
    q = [x for x in ctx.hist.get(s["terms"][0], ()) if x[0] >= now_t - HIST_S]
    if not q:
        return None
    n, g = len(q), sum(x[1] for x in q)
    gn, gg = ctx.gsum[0], ctx.gsum[1]
    return {"launches": n, "graduated": g, "rate": g / n, "all_rate_24h": (gg / gn) if gn else None, "all_launches_24h": gn,
            "note": "Coins whose names use this word, launched while the app was running, whose 1-hour outcome is known. "
                    "Not used for the ranking: in testing, a meta's track record added nothing once its current activity was known."}


def _popular_vs_promising(s: dict, others: dict, pos_th: list[str]) -> str | None:
    """Say so when popularity and the edge rank point different ways."""
    L, D = s["evidence"]["launch"], s["evidence"]["demand"]
    busy = L["launches_6h"] >= 2 * (others.get("launches_6h") or 1) or \
        (D.get("unique_buyers_h1_sum") or 0) >= 2 * (others.get("buyers_1h") or 1)
    tier = s["edge"]["tier"]
    if busy and tier in ("below average", "weakest"):
        return ("Popular, but not promising for a new coin: far more launches or buyers than most metas, which in the back-tests "
                "meant new coins mostly got lost in the crowd.")
    if not busy and tier == "strongest":
        good = {"copycats": "few copycats", "money_in": "its buying signals", "crowding": "not too many new coins piling in",
                "creators": "many different creators", "spread": "trading spread across its coins"}
        why = " and ".join(good[t] for t in pos_th[:2])
        return ("Not one of the busiest ideas right now; it ranks high mainly because of " + why + "." if why else
                "Not one of the busiest ideas right now, yet it ranks among the strongest.")
    return None


def reliability(model: mm.EdgeModel) -> dict:
    """Per theme: did this kind of reason, on its own, go with better outcomes in periods the model
    never saw? (scripts/meta_explain_check.py, stored with the model)."""
    R = (model.spec.get("validation") or {}).get("reasons_out_of_period") or {}
    out = {}
    for th in THEMES:
        tested = [p for p in R.values() if th in p and "holds" in p[th]]
        held = sum(1 for p in tested if p[th]["holds"])
        if not tested:
            note = "Not yet checked on its own."
        elif held == len(tested):
            note = f"On its own, this kind of reason held up in {'both' if held == 2 else f'all {held}'} later checks."
        elif held:
            note = f"On its own, this kind of reason held up in {held} of {len(tested)} later checks."
        else:
            note = "On its own, this kind of reason did not hold up in later checks; it only counts alongside the other signals."
        out[th] = {"held": held, "tested": len(tested), "note": note}
    return out


def explain(s: dict, items: list[dict], model: mm.EdgeModel, market: dict, nar: dict | None, buyers_prev,
            social_measured: bool, live, now_t: int, others: dict) -> dict:
    raw = mm.raw(s, market)
    contrib = {th: sum(i["contribution"] for i in items if i["input"] in ins) for th, ins in THEMES.items()}
    fors, againsts, pos_th, neg_th = theme_sentences(raw, others, contrib, items)
    rel = reliability(model)
    fors = [{"text": t, "theme": th, "reliability": rel[th]} for t, th in zip(fors, pos_th)]
    againsts = [{"text": t, "theme": th, "reliability": rel[th]} for t, th in zip(againsts, neg_th)]
    e = s["edge"]
    stance = {"strongest": "Worth a close look", "above average": "Better than most right now",
              "below average": "Weaker than most right now", "weakest": "Among the weakest right now"}[e["tier"]]
    watch = [f"Its rank would rise if {STRENGTHEN[t]}." for t in neg_th][:2] + [f"Its rank would fall if {WEAKEN[t]}." for t in pos_th][:2]
    if not watch:
        watch.append("Its rank would move most with how many different people launch on it and how many of its coins trade.")
    return {
        "concept": concept(s, nar),
        "happening": happening(s, buyers_prev),
        "attention": attention(s, nar, social_measured),
        "recommendation": {"stance": stance, "rank": e["rank"], "of": e["of"], "tier": e["tier"],
                           "for": fors, "against": againsts,
                           "conflict": bool(pos_th and neg_th and -sum(contrib[t] for t in neg_th)
                                            >= 0.5 * sum(contrib[t] for t in pos_th)),
                           "drivers": [{"theme": t, "label": THEME_LABEL[t], "effect": round(v, 3)}
                                       for t, v in sorted(contrib.items(), key=lambda x: -abs(x[1]))]},
        "risks": risks(s, buyers_prev, market),
        "watch": watch,
        "confidence": confidence(s, items, model),
        "evidence": evidence_table(items, raw, model, others),
        "history": history(s, live, now_t),
        "popular_vs_promising": _popular_vs_promising(s, others, pos_th),
    }


def attach(result: dict, narratives: dict | None, live=None, model: mm.EdgeModel | None = None) -> list[dict]:
    """The read's metas, each with `explain` (None when there is no edge model)."""
    from .scoring import EDGE_MODEL
    model = model or EDGE_MODEL
    metas = result["metas"]
    if model is None or not metas or metas[0].get("edge") is None:
        return [{**m, "explain": None} for m in metas]
    contribs = contributions(metas, result["market"], model)
    raws = [mm.raw(m, result["market"]) for m in metas]
    others = {k: _med([r.get(k) for r in raws]) for k in raws[0] if k != "verdict"}
    nars = (narratives or {}).get("narratives") or []
    mints = result.get("meta_mints") or {}
    prev = result.get("buyers_prev") or {}
    return [{**m, "explain": explain(m, items, model, result["market"], _narrative_for(mints.get(m["meta_key"]) or [], nars, m["terms"][0]),
                                     prev.get(m["meta_key"]), result.get("social_measured", False), live, result["as_of"], others)}
            for m, items in zip(metas, contribs)]


def monitor(metas: list[dict]) -> dict:
    """Input drift, in the spirit of Evidently but light: how many live inputs fall outside the
    range the model was trained on, and how many are missing."""
    rows_ = [r for m in metas if m.get("explain") for r in m["explain"]["evidence"]]
    if not rows_:
        return {"inputs": 0}
    by: dict[str, int] = {}
    for r in rows_:
        if r["unusual"]:
            by[r["label"]] = by.get(r["label"], 0) + 1
    return {"inputs": len(rows_), "unusual_share": round(sum(by.values()) / len(rows_), 3),
            "missing_share": round(sum(1 for r in rows_ if r["value"] == "not measured yet") / len(rows_), 3),
            "unusual_by_input": dict(sorted(by.items(), key=lambda x: -x[1])[:5])}
