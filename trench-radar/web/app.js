// TRENCH//RADAR client. Token names, posts and URLs come from strangers:
// every data-derived string goes through esc() before reaching innerHTML.
"use strict";

const { esc, hhmm, dayhm } = Charts;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const wide = () => matchMedia("(min-width: 820px)").matches;

// ---------------------------------------------------------------- formatting
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const nf = (v, d = 0) => (isNum(v) ? v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }) : "—");
const compact = (v, d = 1) => {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  return a >= 1e9 ? nf(v / 1e9, d) + "B" : a >= 1e6 ? nf(v / 1e6, d) + "M" : a >= 1e4 ? nf(v / 1e3, 0) + "k" : a >= 1e3 ? nf(v / 1e3, d) + "k" : nf(v, a < 10 && a % 1 ? 2 : 0);
};
const usd = (v, d = 1) => (isNum(v) ? (v < 0 ? "−$" : "$") + compact(Math.abs(v), d) : "—");
const pct = (v, d = 0) => (isNum(v) ? nf(v * 100, d) + "%" : "—");
const signed = (v, d = 1, suf = "") => (isNum(v) ? (v > 0 ? "+" : v < 0 ? "−" : "") + nf(Math.abs(v), d) + suf : "—");
const ago = (s) => (!isNum(s) ? "never" : s < 60 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 172800 ? `${nf(s / 3600, s < 36000 ? 1 : 0)}h ago` : `${Math.round(s / 86400)} days ago`);
const age = (h) => (!isNum(h) ? "—" : h < 1 ? `${Math.max(1, Math.round(h * 60))}m` : h < 48 ? `${nf(h, h < 10 ? 1 : 0)}h` : `${Math.round(h / 24)}d`);
const nowS = () => Math.floor(Date.now() / 1000);
const short = (a) => (a && a.length > 12 ? `${a.slice(0, 4)}…${a.slice(-4)}` : a || "—");
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

const VERDICT = {
  favorable: { tone: "pos", g: "●", label: "Favorable" }, mixed: { tone: "warn", g: "▲", label: "Mixed" },
  unfavorable: { tone: "neg", g: "✕", label: "Unfavorable" }, "insufficient data": { tone: "mute", g: "○", label: "Insufficient evidence" },
};
const vinfo = (v) => VERDICT[v] || VERDICT["insufficient data"];
const st = (tone, g, label) => `<span class="st ${tone}"><b aria-hidden="true">${g}</b>${esc(label)}</span>`;
const vst = (v) => { const x = vinfo(v); return st(x.tone, x.g, x.label); };
const meter = (v, cls = "", thr) => `<span class="meter ${cls}" role="img" aria-label="${isNum(v) ? nf(v, 2) : "no data"}"><i style="width:${isNum(v) ? Math.max(0, Math.min(1, v)) * 100 : 0}%"></i>${isNum(thr) ? `<span class="thr" style="left:${thr * 100}%"></span>` : ""}</span>`;
const CONF_BAR = 0.35;   // scoring.py: confidence below this is always "insufficient data"

// ---------------------------------------------------------------- display modes
const Perf = {
  signals() {
    const n = navigator, c = n.connection || {}, out = [];
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) out.push("reduced motion is on");
    if (c.saveData) out.push("Data Saver is on");
    if (/(^|-)2g|3g/.test(c.effectiveType || "")) out.push(`a ${c.effectiveType} connection`);
    if (n.deviceMemory && n.deviceMemory <= 4) out.push(`${n.deviceMemory} GB device memory`);
    if (n.hardwareConcurrency && n.hardwareConcurrency <= 4) out.push(`${n.hardwareConcurrency} CPU threads`);
    return out;
  },
  pref() { try { return localStorage.getItem("radar-perf") || "auto"; } catch (_) { return "auto"; } },
  resolved() { const p = this.pref(); return p === "auto" ? (this.signals().length ? "low" : "premium") : p; },
  apply() { document.documentElement.dataset.perf = this.resolved(); },
  set(p) { try { localStorage.setItem("radar-perf", p); } catch (_) { /* ignore */ } this.apply(); S.sig = null; render(); schedule(); },
  low() { return this.resolved() === "low"; },
};
Perf.apply();

// ---------------------------------------------------------------- api + state
const S = { ov: null, charts: {}, tokens: null, reports: null, report: null, range: 24, tab: "overview", sel: null,
  metaFilter: "all", metaSort: "score", tok: { key: "vol_h1", dir: -1, filter: "all", q: "" }, cmp: null, error: null, lastOk: 0, sig: null };
let token = null;
try { token = localStorage.getItem("radar-token"); } catch (_) { /* ignore */ }

async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: token ? { "x-radar-token": token } : {} });
  if (r.status === 401) { const e = new Error("unauthorized"); e.auth = true; throw e; }
  if (!r.ok) throw new Error(`the server answered ${r.status}`);
  return r.json();
}
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.classList.add("on");
  clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove("on"), 2600);
}

// ---------------------------------------------------------------- collection status (rail, phone bar, banner)
function baseline() {
  const h = S.ov?.context?.history || {};
  const need = h.needed_h || 7, hrs = isNum(h.collected_h) ? h.collected_h : (h.launch_coverage_6h || 0) * 6;
  return { hrs, need, ready: (h.launch_coverage_baseline || 0) >= 0.5, label: hrs < 1 ? `${Math.max(1, Math.round(hrs * 60))} min` : `${nf(hrs, 1)}h` };
}
function liveState() {
  if (!S.ov) return { cls: S.error ? "err" : "", text: S.error ? "Offline" : "Loading" };
  const lag = nowS() - S.ov.as_of;
  const bad = Object.values(S.ov.freshness).filter((x) => ["chain/pump_stream", "chain/snapshot"].includes(`${x.source}/${x.job}`) && x.state !== "fresh");
  if (S.error) return { cls: "err", text: "Offline", lag, bad };
  if (lag > 1200 || bad.length) return { cls: "stale", text: "Stale", lag, bad };
  return { cls: "ok", text: "Collecting", lag, bad };
}
function renderStatus() {
  const L = liveState(), b = baseline();
  const fr = S.ov ? Object.values(S.ov.freshness) : [];
  $("#railstat").innerHTML = S.ov ? `<div><div class="row1"><span class="dot ${L.cls}"></span>${esc(L.text)}</div>
      <small>Analysis ${esc(ago(L.lag))}. ${fr.filter((x) => x.state === "fresh").length} of ${fr.length} sources fresh.</small></div>
    ${b.ready ? "" : `<div><div>Baseline ${esc(b.label)} of ~${b.need}h</div><div class="bar" style="margin-top:6px"><i style="width:${Math.min(100, (b.hrs / b.need) * 100)}%"></i></div>
      <small>Calls stay "insufficient evidence" until about ${b.need} hours have been collected.</small></div>`}`
    : `<div class="row1"><span class="dot ${L.cls}"></span>${esc(L.text)}</div>`;
  $("#mstat").innerHTML = `<span class="dot ${L.cls}"></span>${S.ov && !b.ready && L.cls === "ok" ? `Baseline ${esc(b.label.replace(" min", "m"))} of ${b.need}h` : esc(L.text)}`;
  let html = "";
  if (S.ov && S.error) html = `<div class="alert neg" role="status"><div><b>Couldn’t refresh.</b> Showing the analysis from ${esc(hhmm(S.ov.as_of))}. ${esc(cap(S.error))}.</div></div>`;
  else if (L.cls === "stale") html = `<div class="alert" role="status"><div><b>Data is stale.</b> ${L.bad.length ? esc(L.bad.map((x) => `${x.source}/${x.job} is ${x.state}`).join("; ")) + "." : `The last analysis ran ${esc(ago(L.lag))}.`} Scores may lag the market.</div></div>`;
  $("#banner").innerHTML = html;
}

// ---------------------------------------------------------------- loading
let refreshTimer;
function schedule() { clearInterval(refreshTimer); refreshTimer = setInterval(() => { if (document.visibilityState === "visible") load({ quiet: true }); }, Perf.low() ? 60000 : 30000); liveSchedule(); }

async function load({ quiet = false } = {}) {
  setBusy(true);
  try {
    const [ov, ch, tk] = await Promise.all([api("/api/overview"), api(`/api/charts?hours=${S.range}`), api("/api/tokens?limit=120")]);
    const sig = JSON.stringify([ov.as_of, ov.db, ov.metas.length, ch.launches.at(-1), ch.launches.length, tk.tokens.map((t) => t.observed_at).join()]);
    const same = sig === S.sig;
    S.ov = ov; S.charts = { [S.range]: ch }; S.tokens = tk; S.error = null; S.lastOk = Date.now(); S.sig = sig;
    renderStatus();
    if (same && quiet) return;            // nothing new: skip the re-render
  } catch (e) {
    if (e.auth) return askToken();
    S.error = e.message || "network error";
    if (!quiet) toast("Refresh failed");
    renderStatus();
  } finally { setBusy(false); }
  render();
}
function setBusy(on) { $$("[data-refresh]").forEach((b) => b.classList.toggle("spin", on)); }

function askToken() {
  setHead("Locked", "Enter the dashboard token to continue.");
  $$(".screen").forEach((s) => (s.hidden = s.dataset.screen !== "overview"));
  $(".screen[data-screen=overview]").innerHTML = `<div class="plane" style="max-width:420px;padding:28px">
    <h3 class="serif" style="margin:0 0 6px;font-size:22px;font-weight:500">This dashboard is locked</h3>
    <p class="i2" style="margin:0 0 16px">Enter the value of <span class="mono">DASHBOARD_TOKEN</span> from your settings file.</p>
    <form id="tokform" style="display:grid;gap:10px"><label class="sr" for="tokin">Dashboard token</label>
      <input id="tokin" type="password" autocomplete="current-password" required><button class="btn solid">Unlock</button></form></div>`;
  $("#tokform").addEventListener("submit", (e) => {
    e.preventDefault(); token = $("#tokin").value;
    try { localStorage.setItem("radar-token", token); } catch (_) { /* ignore */ }
    load();
  });
}

// ---------------------------------------------------------------- router + page head
const TITLES = { overview: "Overview", live: "Live", metas: "Metas", tokens: "Tokens", analyst: "Analyst", system: "System" };
function go(tab, { keepScroll = false } = {}) {
  if (!TITLES[tab]) tab = "overview";
  S.tab = tab;
  $$(".tab").forEach((t) => t.setAttribute("aria-current", t.dataset.go === tab ? "page" : "false"));
  $$(".screen").forEach((s) => (s.hidden = s.dataset.screen !== tab));
  history.replaceState(null, "", `#/${tab}`);
  try { localStorage.setItem("radar-tab", tab); } catch (_) { /* ignore */ }
  if (!keepScroll) window.scrollTo({ top: 0 });
  render();
  liveSchedule();
  if (tab === "live") pollLive();
}
$$(".tab").forEach((t) => t.addEventListener("click", () => go(t.dataset.go)));
const REFRESH = `<button class="btn" data-refresh><svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>Refresh</button>`;
function setHead(title, ctx, tools = REFRESH) {
  $("#title").textContent = title;
  $("#ctx").innerHTML = ctx;
  $("#tools").innerHTML = tools;
  $$("[data-refresh]", $("#tools")).forEach((b) => b.addEventListener("click", () => load()));
}

function render() {
  if (S.tab === "live") return renderLive();
  if (!S.ov) return renderLoadingOrError();
  ({ overview: renderOverview, metas: renderMetas, tokens: renderTokens, analyst: renderAnalyst, system: renderSystem })[S.tab]();
}
function renderLoadingOrError() {
  const el = $(`.screen[data-screen=${S.tab}]`);
  setHead(TITLES[S.tab], S.error ? "" : "Loading the latest analysis");
  if (S.error) {
    el.innerHTML = `<div class="empty"><h3>Can’t reach the radar server</h3>${esc(cap(S.error))}. Check that <span class="mono">python -m radar serve</span> or TrenchRadar.exe is running.
      <div><button class="btn" id="retry">Try again</button></div></div>`;
    $("#retry").addEventListener("click", () => load());
    return;
  }
  el.innerHTML = `<div class="lead"><div><div class="sk" style="height:110px"></div><div class="sk" style="height:48px;margin-top:16px;width:80%"></div></div>
    <div class="sk" style="height:220px"></div></div><div class="sk sec" style="height:260px"></div>`;
}

// ---------------------------------------------------------------- shared builders
const isProv = (m) => m.verdict === "insufficient data";
function insight() {
  const ov = S.ov, m = ov.market, metas = ov.metas;
  const fav = metas.filter((x) => x.verdict === "favorable"), mix = metas.filter((x) => x.verdict === "mixed");
  const head = { hot: "The pump.fun market is running hot", neutral: "The pump.fun market is steady", cold: "The pump.fun market is cold" }[m.regime]
    || "Market conditions are still being measured";
  const tail = fav.length ? `, and ${fav.length === 1 ? `${fav[0].meta_key} shows` : `${fav.length} narratives show`} attention and buying together.`
    : mix.length ? `, with ${mix.length} narrative${mix.length > 1 ? "s" : ""} showing partial support.`
    : metas.length ? ", but no narrative has earned a call yet." : ", and no narrative has formed yet.";
  const byBuyers = [...metas].sort((a, b) => b.evidence.demand.unique_buyers_h1_sum - a.evidence.demand.unique_buyers_h1_sum)[0];
  const x = m.metrics, b = baseline();
  const bits = [];
  if (byBuyers) bits.push(`Most buying is in <b>${esc(byBuyers.meta_key)}</b>: ${compact(byBuyers.evidence.demand.unique_buyers_h1_sum)} buyers an hour across ${byBuyers.evidence.demand.tokens_tracked} tokens.`);
  if (isNum(x.pumpfun_launchpad_vol_7d_vs_30d)) bits.push(`Launchpad volume is ${x.pumpfun_launchpad_vol_7d_vs_30d >= 1 ? "up" : "down"} ${nf(Math.abs(x.pumpfun_launchpad_vol_7d_vs_30d - 1) * 100, 0)}% on its 30-day average.`);
  if (!b.ready) bits.push(`Calls need about ${b.need} hours of history; ${esc(b.label)} is collected.`);
  return { head: head + tail, sub: bits.join(" ") };
}
function narrativeRow(m, i) {
  const d = m.evidence.demand, l = m.evidence.launch;
  return `<button class="nrow" data-meta="${esc(m.meta_key)}"><span class="rk">${i + 1}</span>
    <span style="min-width:0"><div class="nm">${esc(m.meta_key)}</div><div class="tm">${esc(m.terms.length > 1 ? `with ${m.terms.slice(1, 5).join(", ")}` : `${l.launches_6h} launches in 6h, ${pct(d.buyer_share_h1)} of traders buying`)}</div></span>
    <span class="sc ${isProv(m) ? "prov" : ""}">${isNum(m.score) ? Math.round(m.score) : "—"}<small>${isProv(m) ? "provisional" : esc(vinfo(m.verdict).label)}</small></span>
    <span class="cf">${meter(m.confidence, m.confidence < CONF_BAR ? "cau" : "", CONF_BAR)}<span>confidence ${nf(m.confidence, 2)}</span></span>
    <span class="by">${compact(d.unique_buyers_h1_sum)}<small>buyers/h</small></span></button>`;
}
function bindNarratives(root) {
  $$("[data-meta]", root).forEach((b) => b.addEventListener("click", () => pickMeta(b.dataset.meta, { from: "list" })));
}
function pickMeta(key, { from } = {}) {
  S.sel = key;
  if (!wide()) { const m = S.ov.metas.find((x) => x.meta_key === key); if (m) openMetaSheet(m); return; }
  if (S.tab !== "metas") go("metas"); else renderMetas({ keepMap: from === "list" });
}
function tokenFlags(t, now = nowS()) {
  const out = [];
  const ageH = t.created_at ? (now - t.created_at) / 3600 : null;
  if (isNum(ageH) && ageH < 1 && !t.graduated) out.push(["", "Under 1h old"]);
  if ((t.sellers_h1 || 0) > (t.buyers_h1 || 0)) out.push(["neg", "More sellers"]);
  if (isNum(t.liquidity_usd) && t.liquidity_usd < 5000) out.push(["", "Thin liquidity"]);
  if ((t.deployer_launches_24h || 0) >= 3) out.push(["neg", "Serial deployer"]);
  if ((t.dev_sold_sol || 0) >= 0.5) out.push(["neg", `Creator sold ${nf(t.dev_sold_sol, 1)} SOL`]);
  if (isNum(t.organic_buyers_h1) && t.buyers_h1 >= 5 && t.organic_buyers_h1 < 0.5 * t.buyers_h1) out.push(["", "Bot-heavy buying"]);
  if ((t.launch_block_buyers || 0) >= 3) out.push(["neg", `Bundled launch (${t.launch_block_buyers} wallets)`]);
  if ((t.insider_buyers_h1 || 0) >= 1) out.push(["neg", "Labelled insiders buying"]);
  if (isNum(t.top10_pct) && t.top10_pct >= 0.3) out.push(["", `Top 10 hold ${pct(t.top10_pct)}`]);
  if (t.observed_at && now - t.observed_at > 1800) out.push(["", "Stale stats"]);
  return out;
}
const flagsHtml = (fl) => (fl.length ? `<span class="flags">${fl.map(([c, l]) => `<span class="flag ${c}">${esc(l)}</span>`).join("")}</span>` : `<span class="flag ok">None detected</span>`);
const bsr = (b = 0, s = 0) => { const t = b + s || 1; return `<span class="bsr"><span class="bsb"><i style="width:${(b / t) * 100}%"></i><u style="width:${(s / t) * 100}%"></u></span><span>${compact(b)} / ${compact(s)}</span></span>`; };
const curveCell = (t) => (t.graduated ? `<span class="i2">Graduated</span>` : isNum(t.progress) ? `<span class="curve">${meter(t.progress, "dem")}<span>${pct(t.progress)}</span></span>` : `<span class="i3">—</span>`);
const seg = (name, opts, cur, attr = "data-v") => `<div class="seg" role="group" aria-label="${esc(name)}">${opts.map(([v, l]) => `<button ${attr}="${v}" aria-pressed="${String(v) === String(cur)}">${esc(l)}</button>`).join("")}</div>`;

// ---------------------------------------------------------------- OVERVIEW
const DRIVERS = [["launchpad_volume_trend", "Launchpad volume trend"], ["new_token_performance", "New tokens with traction"],
  ["graduation_rate", "Graduation rate"], ["fresh_rotation", "Rotation into new launches"], ["sol_trend", "SOL trend"]];
function renderOverview() {
  const el = $(".screen[data-screen=overview]"), ov = S.ov, m = ov.market, x = m.metrics, ch = S.charts[S.range];
  setHead("Overview", `Analysis as of ${esc(hhmm(ov.as_of))}. Scores are hand-weighted priors${ov.backtest?.validated ? ", validated by the latest backtest" : ov.backtest ? `. The latest backtest${ov.backtest.dataset ? ` (${esc(ov.backtest.dataset)})` : ""} found no edge: treat them as a structured read, not a prediction` : " and have not been validated against outcomes yet"}.`);
  const ins = insight();
  const regimeWord = m.regime ? cap(m.regime) : "Unknown";
  const tone = { hot: "pos", neutral: "warn", cold: "neg" }[m.regime] || "mute";
  const drivers = DRIVERS.map(([k, label]) => {
    const v = m.components[k];
    return `<div class="drv"><span>${esc(label)}</span>${isNum(v) ? `${meter(v)}<span class="v">${nf(v, 2)}</span>` : `<span class="na">${k === "graduation_rate" ? "needs 24h of launches" : "no data yet"}</span>`}</div>`;
  }).join("");
  const metas = ov.metas.slice(0, 6);
  const toks = (S.tokens?.tokens || []).slice(0, 6);
  let daily = [];
  try { daily = JSON.parse((x.pumpfun_launchpad_daily_series || "[]").replace(/'/g, '"')); } catch (_) { daily = []; }
  el.innerHTML = `
    <div class="lead">
      <h2>${esc(ins.head)}</h2><p>${ins.sub}</p>
      <div class="plane regime" aria-label="Market regime">
        <div class="top"><span class="word"><span class="st ${tone}" style="font-size:14px;vertical-align:5px;margin-right:8px"><b aria-hidden="true">${{ pos: "●", warn: "▲", neg: "✕", mute: "○" }[tone]}</b></span>${esc(regimeWord)}</span>
          <span class="score">${isNum(m.score) ? `score ${nf(m.score, 2)}, from ${pct(m.coverage)} of inputs` : "not enough data"}</span></div>
        <div class="scale" aria-hidden="true"><div class="track"><i class="${m.regime === "cold" ? "on" : ""}"></i><i class="${m.regime === "neutral" ? "on" : ""}"></i><i class="${m.regime === "hot" ? "on" : ""}"></i></div>
          ${isNum(m.score) ? `<span class="mk" style="left:${m.score * 100}%"></span>` : ""}</div>
        <div class="scale-l"><span>Cold</span><span>Neutral</span><span>Hot</span></div>
        <div class="drivers">${drivers}</div>
      </div>
    </div>
    <div class="sec plane flow">
      <div class="figs">
        <div class="fig"><div class="k">Launches per hour</div><div class="v">${isNum(x.launches_est_per_h) ? compact(x.launches_est_per_h) : compact(x.launches_observed_1h)}</div>
          <div class="c">${isNum(x.launches_est_per_h) ? `estimated from ${pct(x.launch_coverage_1h)} coverage` : `seen in the last hour, ${pct(x.launch_coverage_1h)} coverage`}</div></div>
        <div class="fig"><div class="k">Graduation rate</div><div class="v sm">${isNum(x.graduation_rate_24_48h_cohort) ? pct(x.graduation_rate_24_48h_cohort, 2) : "—"}</div>
          <div class="c">${x.graduation_cohort_n ? `launches 24 to 48h old, n=${compact(x.graduation_cohort_n)}` : "needs a day of launches"}</div></div>
        <div class="fig"><div class="k">Launchpad volume, 7-day average</div><div class="v sm">${usd(x.pumpfun_launchpad_vol_7d_avg_usd)}</div>
          <div class="c">${isNum(x.pumpfun_launchpad_vol_7d_vs_30d) ? `<span class="${x.pumpfun_launchpad_vol_7d_vs_30d >= 1 ? "up" : "down"}">${signed((x.pumpfun_launchpad_vol_7d_vs_30d - 1) * 100, 0, "%")}</span> against the 30-day average` : ""}</div></div>
      </div>
      <div class="charts">
        <div class="chart-h"><h3>Launch flow</h3><span class="note">pump.fun launches per ${S.range === 6 ? "5 minutes" : S.range === 24 ? "15 minutes" : "hour"}, local time</span>
          <span class="legend"><span><i style="background:var(--attention)"></i>launches</span><span><i style="background:url(#)" class="hatchkey"></i></span></span>
          <span class="end">${seg("Time range", [[6, "6H"], [24, "24H"], [72, "3D"]], S.range)}</span></div>
        <div class="chart" id="flow"></div>
        <div class="chart-h" style="margin-top:14px"><h3>Graduations to PumpSwap</h3><span class="note">per hour; hatched areas mean the collector was not running</span></div>
        <div class="chart" id="grads"></div>
      </div>
    </div>
    <div class="sec split">
      <div><div class="sec-h"><h2>Narratives to watch</h2><span class="note">ranked by readiness score; buyers are per-token sums</span>
        <span class="end"><button class="linkbtn" data-goto="metas">All ${ov.metas.length} narratives</button></span></div>
        <div id="lead-n">${metas.length ? metas.map(narrativeRow).join("") : `<div class="empty"><h3>No narratives yet</h3>A narrative appears once several launches or posts share a theme.</div>`}</div>
        <div class="chart-h" style="margin-top:28px"><h3>Launchpad volume by day</h3><span class="note">pump.fun, DefiLlama, last 30 days; today is partial</span></div>
        <div class="chart" id="daily"></div></div>
      <div>
        <div class="sec-h"><h2>Where the buying is</h2><span class="note">last hour</span><span class="end"><button class="linkbtn" data-goto="tokens">All tokens</button></span></div>
        <table class="tbl" id="buying"><thead><tr><th>Token</th><th class="r">Volume</th><th>Buyers / sellers</th><th class="r hide-s">Curve</th></tr></thead>
          <tbody>${toks.map((t, i) => `<tr data-tok="${i}"><td><span class="tk"><b>${esc(t.symbol || short(t.mint))}</b><span>${esc(t.name || "")}</span></span></td>
            <td class="r">${usd(t.vol_h1)}</td><td>${bsr(t.buyers_h1, t.sellers_h1)}</td><td class="r hide-s">${t.graduated ? "Graduated" : pct(t.progress)}</td></tr>`).join("")
            || `<tr><td colspan="4" class="i3">No token has fresh stats yet.</td></tr>`}</tbody></table>
        <div class="sec-h" style="margin-top:28px"><h2>Market conditions</h2></div>
        <div class="ledger">
          <div class="li"><span class="k">SOL</span><span class="v">${isNum(x.sol_price_usd) ? "$" + nf(x.sol_price_usd, 2) : "—"}</span>
            <span class="c">${isNum(x.sol_chg_24h) ? `${signed(x.sol_chg_24h * 100, 1, "%")} over 24 hours` : "24-hour change appears after a day"}</span></div>
          <div class="li"><span class="k">Median 24h move, most-traded curve tokens</span><span class="v ${x.active_median_chg_h24_pct >= 0 ? "up" : "down"}">${isNum(x.active_median_chg_h24_pct) ? signed(x.active_median_chg_h24_pct, 0, "%") : "—"}</span></div>
          <div class="li"><span class="k">Most-traded tokens under a day old</span><span class="v">${pct(x.active_share_under_24h)}</span>
            <span class="c">a high share means money is rotating into new launches</span></div>
          <div class="li"><span class="k">PumpSwap volume, 7-day against 30-day</span><span class="v">${isNum(x.pumpswap_vol_7d_vs_30d) ? signed((x.pumpswap_vol_7d_vs_30d - 1) * 100, 0, "%") : "—"}</span></div>
        </div>
      </div>
    </div>`;
  $$(".seg button", el).forEach((b) => b.addEventListener("click", async () => {
    S.range = +b.dataset.v;
    if (!S.charts[S.range]) { try { S.charts[S.range] = await api(`/api/charts?hours=${S.range}`); } catch (_) { toast("Couldn’t load that range"); } }
    renderOverview();
  }));
  $$("[data-goto]", el).forEach((b) => b.addEventListener("click", () => go(b.dataset.goto)));
  bindNarratives($("#lead-n"));
  $$("#buying tr[data-tok]", el).forEach((r) => r.addEventListener("click", () => openToken(toks[+r.dataset.tok].mint)));
  const leg = $(".hatchkey", el);
  if (leg) leg.parentElement.innerHTML = `<i style="background:repeating-linear-gradient(45deg,#2b2f35 0 2px,transparent 2px 5px)"></i>not observed`;
  if (ch) {
    const to = ch.now, from = to - ch.hours * 3600;
    Charts.timeBars($("#flow"), { data: ch.launches, from, to, step: ch.step_s, observed: ch.observed_buckets, height: wide() ? 200 : 160, fmtY: (v) => compact(v, 0), unit: "launches", label: "Launches over time" });
    Charts.timeBars($("#grads"), { data: ch.graduations, from, to, step: ch.graduation_step_s, height: 78, cls: "dem", fmtY: (v) => compact(v, 0), unit: "graduations", label: "Graduations over time" });
  }
  Charts.catBars($("#daily"), { data: daily, height: 120, fmtY: (v) => usd(v, 0), fmtX: (t) => new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric" }), label: "Daily launchpad volume" });
}

// ---------------------------------------------------------------- LIVE (chain stream, polled every few seconds)
const LV = { data: null, err: null, timer: null };
function liveSchedule() {
  clearInterval(LV.timer);
  if (S.tab !== "live") return;
  LV.timer = setInterval(() => { if (document.visibilityState === "visible" && S.tab === "live") pollLive(); }, Perf.low() ? 6000 : 3000);
}
async function pollLive() {
  try { LV.data = await api("/api/live"); LV.err = null; }
  catch (e) { if (e.auth) return askToken(); LV.err = e.message || "network error"; }
  if (S.tab === "live" && !$("#sheet").classList.contains("on")) renderLive();
}
const ordinal = (n) => n + ((n % 100 >= 11 && n % 100 <= 13) ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");
const secs = (s) => (!isNum(s) ? "—" : s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${nf(s / 3600, 1)}h`);
function renderLive() {
  const el = $(".screen[data-screen=live]"), d = LV.data;
  if (!d) {
    setHead("Live", LV.err ? esc(cap(LV.err)) : "Connecting to the live feed", "");
    el.innerHTML = LV.err ? `<div class="empty"><h3>Can’t reach the radar server</h3>${esc(cap(LV.err))}.</div>` : `<div class="sk" style="height:220px"></div>`;
    return;
  }
  const s = d.stream, now = d.now;
  const status = !s.enabled ? "The live stream runs with the collector; start the app normally (not with --no-scheduler)."
    : s.connected ? `Read straight from the Solana chain, about ${nf(s.lag_s ?? 0, 1)}s behind. Updates every ${Perf.low() ? 6 : 3} seconds.`
    : `Reconnecting to the chain${s.error ? `: ${esc(s.error)}` : ""}.`;
  setHead("Live", `<span class="dot ${s.connected ? "ok" : "stale"}" style="display:inline-block;margin-right:6px;vertical-align:1px"></span>${status}`, "");
  const per = d.launches_per_min, last60 = per.reduce((a, b) => a + b[1], 0), last5 = per.slice(-6, -1).reduce((a, b) => a + b[1], 0);
  const hot = d.hot, flag = (c, t) => `<span class="flag ${c}">${esc(t)}</span>`;
  el.innerHTML = `
    <div class="sec plane flow" style="margin-top:0">
      <div class="figs">
        <div class="fig"><div class="k">Launches, last 60 min</div><div class="v">${compact(last60)}</div><div class="c">${nf(last5 / 5, 1)} per minute over the last 5 minutes</div></div>
        <div class="fig"><div class="k">Tokens being bought now</div><div class="v sm">${hot.length}${hot.length >= 20 ? "+" : ""}</div><div class="c">3+ distinct buyers in the last 5 minutes</div></div>
        <div class="fig"><div class="k">Proven wallets tracked</div><div class="v sm">${compact(s.smart_wallets + s.labelled_wallets)}</div><div class="c">${compact(s.smart_wallets)} learned here (early into 2+ graduates, 10%+ hit rate), ${compact(s.labelled_wallets)} from a June 2026 dataset</div></div>
      </div>
      <div class="charts"><div class="chart-h"><h3>Launches per minute</h3><span class="note">last hour, local time; the current minute is partial</span></div><div class="chart" id="lpm"></div></div>
    </div>
    <div class="sec">
      <div class="sec-h"><h2>Being bought right now</h2><span class="note">last 5 minutes; sorted by proven wallets, then distinct buyers</span></div>
      <table class="tbl" id="hot"><thead><tr><th>Token</th><th class="r hide-s">Age</th><th>Buyers / sellers</th><th class="r">Net SOL</th><th class="r" title="Buyers with a proven early-entry record (learned here) or labelled smart money (June 2026 dataset)">Proven</th><th class="hide-s">Curve</th><th class="hide-s">Flags</th></tr></thead>
        <tbody>${hot.map((h, i) => {
          const fl = [];
          if (h.dev_sold_sol >= 0.5) fl.push(flag("neg", `Creator sold ${nf(h.dev_sold_sol, 1)} SOL`));
          if (h.launch_block_buyers >= 3) fl.push(flag("neg", `Bundled: ${h.launch_block_buyers} wallets in launch block`));
          if (h.insider_5m) fl.push(flag("neg", `${h.insider_5m} labelled insider${h.insider_5m > 1 ? "s" : ""}`));
          if (isNum(h.top10_pct) && h.top10_pct >= 0.3) fl.push(flag("", `Top 10 hold ${pct(h.top10_pct)}`));
          if (h.sellers_5m > h.buyers_5m) fl.push(flag("neg", "More sellers"));
          if (h.graduated) fl.push(flag("ok", "Graduated"));
          return `<tr data-h="${i}"><td><span class="tk"><b>${esc(h.symbol || short(h.mint))}</b><span>${esc(h.name || "")}</span></span></td>
            <td class="r hide-s">${secs(h.age_s)}</td><td>${bsr(h.buyers_5m, h.sellers_5m)}</td>
            <td class="r ${h.net_sol_5m > 0 ? "up" : h.net_sol_5m < 0 ? "down" : ""}">${signed(h.net_sol_5m, 1)}</td>
            <td class="r ${h.smart_5m + h.labelled_5m ? "up" : "i3"}" title="learned ${h.smart_5m}, dataset-labelled ${h.labelled_5m}">${h.smart_5m + h.labelled_5m || "—"}</td>
            <td class="hide-s">${h.graduated ? `<span class="i2">Graduated</span>` : curveCell(h)}</td>
            <td class="hide-s">${fl.length ? `<span class="flags">${fl.join("")}</span>` : ""}</td></tr>`;
        }).join("") || `<tr><td colspan="7"><div class="empty"><h3>Nothing yet</h3>Tokens show up here once three or more wallets buy within five minutes.</div></td></tr>`}</tbody></table>
    </div>
    <div class="sec split">
      <div><div class="sec-h"><h2>Launch tape</h2><span class="note">newest 15; flags clone waves, serial creators and bundled launches</span></div>
        <table class="tbl tapetbl" id="tape"><thead><tr><th>Token</th><th class="r">When</th><th>Signals</th></tr></thead><tbody>
        ${d.launches.slice(0, 15).map((l, i) => `<tr data-l="${i}"><td><span class="tk"><b>${esc(l.symbol || short(l.mint))}</b><span>${esc(l.name || "")}</span></span></td>
          <td class="r">${secs(now - l.ts)} ago</td>
          <td><span class="flags">${[l.clones >= 2 ? flag("", `${l.clones} wallets, same name, 15 min`) : "", l.creator_launches_24h >= 3 ? flag("neg", `Creator's ${ordinal(l.creator_launches_24h)} launch today`) : "",
            l.launch_block_buyers >= 3 ? flag("neg", `${l.launch_block_buyers} wallets bought in the launch block`) : ""].join("")}</span>${l.clones < 2 && l.creator_launches_24h < 3 && !(l.launch_block_buyers >= 3) ? `<span class="i3">—</span>` : ""}</td></tr>`).join("")
          || `<tr><td colspan="3" class="i3">Waiting for the first launch.</td></tr>`}</tbody></table></div>
      <div><div class="sec-h"><h2>Posts spawning coins</h2><span class="note">X posts linked by 2+ launches in 3 hours</span></div>
        <div class="ledger">${(d.source_posts || []).map((p) => `<div class="li"><span class="k"><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer nofollow">@${esc(p.account)}</a> <span class="i3">post</span></span>
          <span class="v">${p.launches} launches</span><span class="c">${p.text ? `“${esc(p.text.length > 160 ? p.text.slice(0, 157) + "…" : p.text)}” ` : ""}${p.creators} creator${p.creators === 1 ? "" : "s"}, ${p.buyers_1h} buyers in the last hour, ${signed(p.net_sol_1h, 1)} SOL net${isNum(p.likes) ? ` · ${compact(p.likes)} likes` : ""}${isNum(p.views) ? `, ${compact(p.views)} views` : ""}${isNum(p.followers) ? ` · author ${compact(p.followers)} followers` : ""}</span></div>`).join("")
          || `<div class="li"><span class="k i3">No post has been linked by two launches yet.</span></div>`}</div>
        <div class="sec-h" style="margin-top:28px"><h2>Same picture, different names</h2><span class="note">tokens being bought, last 24h</span></div>
        <div class="ledger">${(d.image_groups || []).map((g) => `<div class="li"><span class="k">${esc(g.names.slice(0, 4).join(", "))}${g.names.length > 4 ? "…" : ""}</span>
          <span class="v">${g.tokens} tokens</span><span class="c">first ${esc(secs(d.now - g.first_at))} ago, latest ${esc(secs(d.now - g.last_at))} ago</span></div>`).join("")
          || `<div class="li"><span class="k i3">No shared picture among traded tokens yet.</span></div>`}</div>
        <div class="sec-h" style="margin-top:28px"><h2>Just graduated</h2><span class="note">bonding curve completed</span></div>
        <div class="ledger">${d.graduations.map((g) => `<div class="li"><span class="k">${esc(g.symbol ? "$" + g.symbol : short(g.mint))} <span class="i3">${esc(g.name || "")}</span></span><span class="v">${secs(now - g.ts)} ago</span></div>`).join("")
          || `<div class="li"><span class="k i3">No graduation since the app started.</span></div>`}</div></div>
    </div>`;
  Charts.timeBars($("#lpm"), { data: per, from: per[0][0], to: per[per.length - 1][0] + 60, step: 60, height: wide() ? 150 : 120, fmtY: (v) => compact(v, 0), unit: "launches", label: "Launches per minute" });
  $$("#hot tr[data-h]", el).forEach((r) => r.addEventListener("click", () => openToken(hot[+r.dataset.h].mint)));
  $$("#tape tr[data-l]", el).forEach((r) => r.addEventListener("click", () => openToken(d.launches[+r.dataset.l].mint)));
}

// ---------------------------------------------------------------- NARRATIVES (metas)
const MSORT = { score: (m) => m.score ?? -1, confidence: (m) => m.confidence, buyers: (m) => m.evidence.demand.unique_buyers_h1_sum,
  launches: (m) => m.evidence.launch.launches_1h, saturation: (m) => -(m.evidence.saturation.index ?? 1) };
function renderMetas({ keepMap = false } = {}) {
  const el = $(".screen[data-screen=metas]"), all = S.ov.metas;
  setHead("Metas", `${all.length} narratives detected in the last 6 hours, ranked by readiness. Select one to read its evidence.`);
  if (!all.length) { el.innerHTML = `<div class="empty"><h3>No narratives detected yet</h3>A narrative appears once several launches or posts share a theme. The first ones usually show up within a few collection cycles.</div>`; return; }
  if (!S.sel || !all.some((m) => m.meta_key === S.sel)) S.sel = all[0].meta_key;
  const count = (v) => all.filter((m) => m.verdict === v).length;
  const filters = [["all", "All", all.length], ["favorable", "Favorable", count("favorable")], ["mixed", "Mixed", count("mixed")],
    ["unfavorable", "Unfavorable", count("unfavorable")], ["insufficient data", "Insufficient", count("insufficient data")]];
  const list = all.filter((m) => S.metaFilter === "all" || m.verdict === S.metaFilter).sort((a, b) => MSORT[S.metaSort](b) - MSORT[S.metaSort](a));
  const sel = all.find((m) => m.meta_key === S.sel);
  const rows = list.map((m) => {
    const d = m.evidence.demand, l = m.evidence.launch, sat = m.evidence.saturation.index;
    return `<tr data-k="${esc(m.meta_key)}" class="${m.meta_key === S.sel ? "sel" : ""}" aria-selected="${m.meta_key === S.sel}">
      <td class="nmc">${esc(m.meta_key)}<small>${esc(m.terms.length > 1 ? `with ${m.terms.slice(1, 4).join(", ")}` : d.top_tokens?.[0]?.symbol ? `led by ${d.top_tokens[0].symbol}` : `${d.tokens_tracked} tokens trading`)}</small></td>
      <td class="r scc ${isProv(m) ? "prov" : ""}">${isNum(m.score) ? Math.round(m.score) : "—"}</td>
      <td class="hide-s"><span class="cfc">${meter(m.confidence, m.confidence < CONF_BAR ? "cau" : "", CONF_BAR)}<span>${nf(m.confidence, 2)}</span></span></td>
      <td><span class="lc"><span class="hide-s">${Charts.spark(l.launch_hourly_12h, 52, 18)}</span><span>${l.launches_1h}<span class="i3"> / ${l.launches_6h}</span></span></span></td>
      <td class="r">${compact(d.unique_buyers_h1_sum)}</td>
      <td class="r wide-only">${pct(d.buyer_share_h1)}</td>
      <td class="r wide-only ${isNum(d.curve_net_sol_1h) ? (d.curve_net_sol_1h >= 0 ? "up" : "down") : ""}">${isNum(d.curve_net_sol_1h) ? signed(d.curve_net_sol_1h, 1) : "—"}</td>
      <td class="r hide-s ${isNum(sat) && sat >= 0.6 ? "warn" : ""}">${isNum(sat) ? nf(sat, 2) : "—"}</td></tr>`;
  }).join("");
  el.innerHTML = `<div class="md">
    <div>
      <div class="plane mapwrap">
        <div class="chart-h"><h3>Narrative map</h3><span class="note">Does the buying confirm the attention?</span>
          <span class="end legend"><span><i style="border:1.5px solid var(--ink-2);border-radius:50%"></i>not enough evidence</span>
            <span><i style="background:var(--demand);border-radius:50%"></i>favorable</span><span><i style="border:1.2px dashed var(--caution);border-radius:50%"></i>crowded</span>
            <span class="i3">size = buyers/h</span></span></div>
        <div class="chart" id="map"></div>
      </div>
      <div class="sec" style="margin-top:20px">
        <div class="toolbar"><div class="chips" role="group" aria-label="Filter by verdict">${filters.map(([v, l, n]) => `<button class="chip" data-f="${esc(v)}" aria-pressed="${S.metaFilter === v}">${l}<span class="ct">${n}</span></button>`).join("")}</div>
          <span class="end"><label class="sr" for="msort">Sort</label><select id="msort">${[["score", "Readiness score"], ["confidence", "Confidence"], ["buyers", "Buyers"], ["launches", "Launches"], ["saturation", "Least crowded"]]
            .map(([v, l]) => `<option value="${v}" ${S.metaSort === v ? "selected" : ""}>Sort by ${l.toLowerCase()}</option>`).join("")}</select></span></div>
        <table class="tbl ledgertbl"><thead><tr><th>Narrative</th><th class="r">Score</th><th class="hide-s">Confidence</th><th>Launches<span class="hide-s"> 1h / 6h, last 12h</span></th><th class="r">Buyers/h</th><th class="r wide-only">Buyer share</th><th class="r wide-only">Curve SOL 1h</th><th class="r hide-s">Crowding</th></tr></thead>
          <tbody id="mrows">${rows || `<tr><td colspan="9" class="i3" style="padding:24px 12px">No narrative has this verdict right now.</td></tr>`}</tbody></table>
      </div>
    </div>
    <aside class="dossier swap" id="dossier" aria-label="Selected narrative">${sel ? dossierHtml(sel) : ""}</aside>
  </div>`;
  const pts = all.filter((m) => isNum(m.components.attention) && isNum(m.components.demand)).map((m) => ({
    key: m.meta_key, label: m.meta_key, x: m.components.attention, y: m.components.demand, buyers: m.evidence.demand.unique_buyers_h1_sum,
    tone: vinfo(m.verdict).tone, verdict: vinfo(m.verdict).label, conf: m.confidence, confident: !isProv(m), score: m.score,
    crowded: (m.evidence.saturation.index ?? 0) >= 0.6, social: S.ov.social_measured }));
  if (pts.length) Charts.narrativeMap($("#map"), { points: pts, selected: S.sel, height: wide() ? 340 : 300, onPick: (p) => pickMeta(p.key) });
  $$("#mrows tr[data-k]").forEach((r) => r.addEventListener("click", () => pickMeta(r.dataset.k, { from: "list" })));
  $$("[data-f]", el).forEach((b) => b.addEventListener("click", () => { S.metaFilter = b.dataset.f; renderMetas(); }));
  $("#msort").addEventListener("change", (e) => { S.metaSort = e.target.value; renderMetas(); });
  if (sel && wide()) bindDossier($("#dossier"), sel);
}

function coverage(m) {
  const e = m.evidence, d = e.demand, l = e.launch, cf = m.confidence_factors, b = baseline();
  return [
    ["6-hour launch baseline", isNum(l.launch_accel_z), "ready", `${b.label} of ~${b.need}h collected`],
    ["Social attention", cf.social_measured, "connected", "no X or Reddit source"],
    ["Fresh trading stats", d.tokens_tracked >= 3, `${d.tokens_tracked} tokens`, `${d.tokens_tracked} token${d.tokens_tracked === 1 ? "" : "s"} only`],
    ["Bonding-curve flow", isNum(d.curve_net_sol_1h), `${d.curve_tokens_compared} curves`, "no curve history yet"],
    ["Net USD flow", isNum(d.net_flow_usd_h1), "Bitquery", "needs a Bitquery key"],
    ["Creator history", (e.creators?.known || 0) > 0, `${e.creators?.known} known`, "no creators seen yet"],
    ["Validated against outcomes", !!m.validated, "backtest passed", "no validated backtest yet"],
  ];
}
function dossierHtml(m) {
  const e = m.evidence, d = e.demand, l = e.launch, s = e.social, cf = m.confidence_factors, sat = e.saturation;
  const cov = coverage(m), miss = cov.filter((c) => !c[1]);
  const lowConf = m.confidence < CONF_BAR;
  const parts = (o) => Object.entries(o || {}).map(([k, v]) => `${esc(k.replaceAll("_", " "))} ${nf(v, 2)}`).join(", ");
  const comp = (k, label) => {
    const v = m.components[k];
    return `<span>${esc(label)} <span class="w">×${m.weights[k]}</span></span>${isNum(v) ? meter(v, k === "demand" ? "dem" : k === "attention" ? "att" : "") : `<span class="na">no data, left out</span>`}<span class="v">${isNum(v) ? nf(v, 2) : ""}</span>`;
  };
  const fresh = S.ov.freshness;
  const srcs = [["chain/pump_stream", "Live chain stream"], ["chain/snapshot", "Trading stats from the chain"],
    ["dexscreener/boosts_profiles", "DexScreener promotion"], ["x_api/recent_search", "X"], ["reddit/new_posts", "Reddit"]]
    .filter(([k]) => fresh[k]).map(([k, n]) => `${n} (${fresh[k].state}${isNum(fresh[k].age_s) ? `, ${ago(fresh[k].age_s)}` : ""})`);
  const toks = d.top_tokens || [];
  return `
    <div class="d-id"><div>${vst(m.verdict)}</div><h2 style="margin-top:8px">${esc(m.meta_key)}</h2>
      <div class="terms">${esc(m.terms.length > 1 ? `Matches ${m.terms.join(", ")}` : `${l.launches_6h} launches in 6 hours, ${d.tokens_tracked} tokens trading`)}</div>
      ${e.merged_by_meaning?.length ? `<div class="terms i3">Grouped by meaning: ${esc(e.merged_by_meaning.map(([w, s]) => `${w} (${nf(s, 2)})`).join(", "))}</div>` : ""}
      <div class="hype">${esc(cap(m.hype_check))}.</div></div>
    <div class="verdict">
      <div class="${isProv(m) ? "prov" : ""}"><div class="k">Readiness score</div><div class="big">${isNum(m.score) ? Math.round(m.score) : "—"}<small> / 100</small></div>
        <div class="c">${isProv(m) ? "Provisional. Not a call: confidence is below the bar." : `${vinfo(m.verdict).label}.`}${m.validated ? "" : " The weights have not been validated against outcomes."}</div></div>
      <div class="${lowConf ? "low" : ""}"><div class="k">Confidence</div><div class="big">${nf(m.confidence, 2)}</div>
        ${meter(m.confidence, lowConf ? "cau" : "", CONF_BAR)}
        <div class="c" style="margin-top:8px">A call needs ${CONF_BAR}. Built from data coverage ${pct(cf.weight_coverage)}, sample ${nf(cf.sample, 2)}, freshness ${nf(cf.freshness, 2)}, history ${nf(cf.history, 2)}.</div></div>
    </div>
    ${miss.length ? `<div class="missing"><h3>${isProv(m) ? "Not enough evidence for a call" : "Missing evidence lowers confidence"}</h3><ul class="cov">
      ${cov.map(([name, have, ht, mt]) => `<li class="${have ? "have" : "miss"}"><span class="g">${have ? "●" : "○"}</span><span>${esc(name)}</span><em>${esc(have ? ht : mt)}</em></li>`).join("")}</ul></div>` : ""}
    <div class="dsec"><h3>Evidence for</h3>${m.reasons.length ? `<ul class="ev pos">${m.reasons.map((r) => `<li><span class="g">●</span><span>${esc(r)}</span></li>`).join("")}</ul>` : `<p class="notes" style="margin:0">No strong positive signal.</p>`}</div>
    <div class="dsec"><h3>Buying activity<span class="note">last hour, per-token sums</span></h3>
      <div class="facts">
        <div><div class="k">Buyers</div><div class="v">${compact(d.unique_buyers_h1_sum)}</div></div>
        <div><div class="k">Sellers</div><div class="v">${compact(d.unique_sellers_h1_sum)}</div></div>
        <div><div class="k">Buyer share</div><div class="v ${d.buyer_share_h1 >= 0.55 ? "up" : d.buyer_share_h1 < 0.45 ? "down" : ""}">${pct(d.buyer_share_h1)}</div></div>
        <div><div class="k">Volume</div><div class="v">${usd(d.vol_h1_usd)}</div></div>
        <div><div class="k">Net SOL into curves</div><div class="v ${isNum(d.curve_net_sol_1h) ? (d.curve_net_sol_1h >= 0 ? "up" : "down") : ""}">${isNum(d.curve_net_sol_1h) ? signed(d.curve_net_sol_1h, 1) : "—"}<small> SOL</small></div></div>
        <div><div class="k">Graduated, 24h</div><div class="v">${d.graduations_24h}</div></div></div>
      <div class="chart-h" style="margin-top:18px"><h3 style="font-weight:500">Launches per hour</h3><span class="note">last 12 hours</span></div>
      <div class="chart" id="d-launch"></div>
      <p class="notes">${d.tokens_tracked} tokens with fresh stats. One wallet buying three tokens counts three times. Top token holds ${pct(d.top_token_share_vol24)} of 24-hour volume. Net USD flow ${isNum(d.net_flow_usd_h1) ? usd(d.net_flow_usd_h1) : "needs Bitquery"}.</p></div>
    <div class="dsec"><h3>Saturation<span class="note">${isNum(sat.index) ? `index ${nf(sat.index, 2)}, 1 = crowded` : "not enough data"}</span></h3>
      ${Object.entries(sat.signals).map(([k, v]) => `<div class="sig"><span>${esc(cap(k.replaceAll("_", " ")))}</span>${meter(v.s, v.s >= 0.6 ? "cau" : "")}<span style="text-align:right">${nf(v.s, 2)}</span><span class="why">${esc(cap(v.why))}</span></div>`).join("")
        || `<p class="notes" style="margin:0">No saturation signal has enough data yet.</p>`}
      <p class="notes">Reused tickers ${pct(l.duplicate_symbol_share_6h)}. Serial deployers ${isNum(e.creators?.serial_share) ? pct(e.creators.serial_share) : "unknown"}. Paid DexScreener promotion: ${e.attention_purchased?.boosts_24h ?? 0} boosted, ${e.attention_purchased?.profiles_24h ?? 0} profiled.</p></div>
    <div class="dsec"><h3>Risks</h3><ul class="ev neg">${m.risks.map((r, i) => `<li class="${i === m.risks.length - 1 ? "base" : ""}"><span class="g">▲</span><span>${esc(r)}</span></li>`).join("")}</ul></div>
    <div class="dsec"><h3>Score breakdown<span class="note">${pct(cf.weight_coverage)} of the weight has data</span></h3>
      <div class="bd">${comp("attention", "Attention")}<span class="parts">${parts(m.component_parts.attention)}</span>${comp("demand", "Demand")}<span class="parts">${parts(m.component_parts.demand)}</span>${comp("market", "Market")}${comp("freshness", "Freshness")}</div></div>
    <div class="dsec"><h3>Score history<span class="note">last 48 hours</span></h3><div class="chart" id="d-hist"><div class="chart-empty">Loading…</div></div></div>
    <div class="dsec"><h3>Social</h3>${cf.social_measured ? `<p class="notes" style="margin:0 0 8px">${s.mentions_1h} mentions in the last hour, ${s.mentions_6h} in 6 hours, from ${s.independent_authors_6h} independent accounts. ${s.copy_paste_posts_6h} copy-paste posts. Sentiment ${isNum(s.sentiment_6h) ? nf(s.sentiment_6h, 2) : "—"} on a −1 to 1 scale.</p>
      <div class="posts">${(s.influential_posts || []).map((p) => `<div class="post"><div class="by">@${esc(p.author || "?")}, ${compact(p.followers)} followers, ${compact(p.engagement)} engagement. <a href="${esc(/^https:\/\//.test(p.url) ? p.url : "#")}" target="_blank" rel="noopener noreferrer">Open post</a></div>${esc(p.text)}</div>`).join("")}</div>`
      : `<p class="notes" style="margin:0">Not measured. No X or Reddit source is connected, so attention comes from launch names alone.</p>`}</div>
    <div class="dsec"><h3>Top tokens in this narrative</h3>
      <table class="tbl"><thead><tr><th>Token</th><th class="r">Volume 1h</th><th>Buyers / sellers</th><th class="r">Curve</th></tr></thead><tbody>
      ${toks.map((t, i) => `<tr data-dt="${i}"><td><span class="tk"><b>${esc(t.symbol || short(t.mint))}</b><span>${esc(t.name || "")}${isNum(t.age_h) ? `, ${esc(age(t.age_h))} old` : ""}</span></span></td><td class="r">${usd(t.vol_h1)}</td>
        <td>${bsr(t.buyers_h1, t.sellers_h1)}</td><td class="r">${t.graduated ? "Graduated" : pct(t.progress)}</td></tr>`).join("") || `<tr><td colspan="4" class="i3">No token in this narrative has fresh stats.</td></tr>`}</tbody></table></div>
    <p class="attr">Computed ${esc(dayhm(S.ov.as_of))} by model ${esc(S.ov.model_version)}. Sources: ${esc(srcs.join("; "))}.</p>`;
}
async function bindDossier(root, m) {
  const l = m.evidence.launch, to = S.ov.as_of, hr = Math.floor(to / 3600) * 3600;
  $$("tr[data-dt]", root).forEach((r) => r.addEventListener("click", () => openToken(m.evidence.demand.top_tokens[+r.dataset.dt].mint)));
  Charts.timeBars($("#d-launch", root), { data: l.launch_hourly_12h.map((v, i) => [hr - (11 - i) * 3600, v]), from: hr - 11 * 3600, to: hr + 3600, step: 3600,
    height: 96, fmtY: (v) => compact(v, 0), unit: "launches", label: "Launches per hour" });
  try {
    const h = await api(`/api/metas/${encodeURIComponent(m.meta_key)}/history?hours=48`);
    const el = $("#d-hist", root);
    if (el) Charts.timeLine(el, { data: h.filter((r) => isNum(r.score)).map((r) => [r.computed_at, r.score]), yMin: 0, yMax: 100, height: 130,
      fmtY: (v) => nf(v, 0), refs: [{ v: 65, label: "favorable from 65" }, { v: 45, label: "mixed from 45" }], label: "Score history" });
  } catch (_) { const el = $("#d-hist", root); if (el) el.innerHTML = `<div class="chart-empty">Score history is unavailable.</div>`; }
}

// ---------------------------------------------------------------- sheet / side panel
let lastFocus = null;
function openSheet(title, sub, body, onReady) {
  lastFocus = document.activeElement;
  $("#sheet-title").textContent = title;
  $("#sheet-sub").innerHTML = sub;
  $("#sheet-body").innerHTML = body;
  $("#sheet-body").scrollTop = 0;
  const sh = $("#sheet");
  sh.style.transform = "";
  $("#backdrop").classList.add("on"); sh.classList.add("on");
  document.body.style.overflow = "hidden";
  $(".app").inert = true;
  setTimeout(() => sh.focus({ preventScroll: true }), 30);
  onReady && onReady($("#sheet-body"));
}
function closeSheet() {
  const sh = $("#sheet");
  if (!sh.classList.contains("on")) return;
  sh.classList.remove("on"); sh.style.transform = "";
  $("#backdrop").classList.remove("on");
  document.body.style.overflow = ""; $(".app").inert = false;
  Charts.hideTip();
  if (lastFocus) lastFocus.focus({ preventScroll: true });
}
$("#sheet-close").addEventListener("click", closeSheet);
$("#backdrop").addEventListener("click", closeSheet);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });
(() => {   // drag the phone sheet's grabber down to dismiss
  const g = $("#grab"), sh = $("#sheet");
  let y0 = 0, t0 = 0, dy = 0, on = false;
  g.addEventListener("pointerdown", (e) => { on = true; y0 = e.clientY; t0 = performance.now(); dy = 0; sh.classList.add("dragging"); g.setPointerCapture(e.pointerId); });
  g.addEventListener("pointermove", (e) => { if (on) { dy = Math.max(0, e.clientY - y0); sh.style.transform = `translateY(${dy}px)`; } });
  const end = () => { if (!on) return; on = false; sh.classList.remove("dragging"); if (dy > 110 || dy / Math.max(1, performance.now() - t0) > 0.6) closeSheet(); else sh.style.transform = ""; };
  g.addEventListener("pointerup", end); g.addEventListener("pointercancel", end);
})();
function openMetaSheet(m) { openSheet(m.meta_key, "", dossierHtml(m), (root) => bindDossier(root, m)); }

// ---------------------------------------------------------------- token dossier
let tokState = { mint: null, metric: "mcap", hours: 24 };
async function openToken(mint) {
  tokState = { ...tokState, mint };
  if (!$("#sheet").classList.contains("on")) openSheet("Loading", "", `<div class="sk" style="height:120px"></div><div class="sk" style="height:180px;margin-top:12px"></div>`);
  let t;
  try { t = await api(`/api/tokens/${encodeURIComponent(mint)}?hours=${tokState.hours}`); }
  catch (e) { $("#sheet-title").textContent = "Token"; $("#sheet-body").innerHTML = `<div class="empty"><h3>Couldn’t load this token</h3>${esc(cap(e.message))}.</div>`; return; }
  if (tokState.mint !== mint) return;
  const k = t.token, last = t.observations[t.observations.length - 1] || {}, curve = t.curve[t.curve.length - 1];
  const ageH = k.created_at ? (t.now - k.created_at) / 3600 : null, graduated = !!t.graduation || !!curve?.complete;
  const flags = tokenFlags({ ...last, created_at: k.created_at, graduated, deployer_launches_24h: t.deployer?.launches_seen_24h }, t.now);
  if (!t.observations.length) flags.push(["", "No trading observations in this range"]);
  const out = t.outcomes.map((o) => `<tr><td>${o.horizon_h}h</td><td>${o.graduated ? "Graduated" : esc(cap(o.bucket || "—"))}</td><td class="r">${isNum(o.ret_end) ? signed(o.ret_end * 100, 0, "%") : "—"}</td><td class="r">${isNum(o.ret_max) ? signed(o.ret_max * 100, 0, "%") : "—"}</td></tr>`).join("");
  $("#sheet-title").textContent = k.symbol ? `$${k.symbol}` : short(k.mint);
  $("#sheet-sub").textContent = `${k.name || ""}${isNum(ageH) ? `, launched ${age(ageH)} ago` : ""}${graduated ? ", graduated" : ""}`;
  const root = $("#sheet-body");
  root.innerHTML = `
    <div class="addr"><span>${esc(k.mint)}</span><button class="btn" id="copy">Copy address</button></div>
    <div class="links"><a href="https://pump.fun/coin/${encodeURIComponent(k.mint)}" target="_blank" rel="noopener noreferrer">pump.fun</a>
      <a href="https://dexscreener.com/solana/${encodeURIComponent(k.mint)}" target="_blank" rel="noopener noreferrer">DexScreener</a>
      <a href="https://solscan.io/token/${encodeURIComponent(k.mint)}" target="_blank" rel="noopener noreferrer">Solscan</a></div>
    ${aboutHtml(k, t.same_x_post_24h)}
    <div class="dsec"><h3>Risk flags</h3>${flags.length ? `<ul class="ev cau">${flags.map(([c, f]) => `<li><span class="g" style="color:var(--${c === "neg" ? "sell" : "caution"})">▲</span><span>${esc(f)}</span></li>`).join("")}</ul>`
      : `<p class="notes" style="margin:0">None of the automatic checks fired. They do not detect rugs, bundled buys or insider wallets.</p>`}</div>
    <div class="dsec"><h3>Now<span class="note">${last.observed_at ? `observed ${esc(ago(t.now - last.observed_at))}` : "no recent observation"}</span></h3>
      <div class="facts"><div><div class="k">Market cap</div><div class="v">${usd(last.mcap_usd)}</div></div><div><div class="k">Liquidity</div><div class="v">${usd(last.liquidity_usd)}</div></div>
        <div><div class="k">Curve</div><div class="v">${graduated ? "Graduated" : curve ? pct(curve.progress) : "—"}</div></div>
        <div><div class="k">Volume 1h</div><div class="v">${usd(last.vol_h1)}</div></div><div><div class="k">Volume 24h</div><div class="v">${usd(last.vol_h24)}</div></div>
        <div><div class="k">Buyers / sellers 1h</div><div class="v">${last.buyers_h1 ?? "—"}<small> / ${last.sellers_h1 ?? "—"}</small></div></div>
        ${isNum(last.smart_buyers_h1) ? `<div><div class="k">Proven wallets buying 1h</div><div class="v ${last.smart_buyers_h1 ? "up" : ""}">${last.smart_buyers_h1}</div></div>
        <div><div class="k">Buyers that aren’t bots 1h</div><div class="v">${last.organic_buyers_h1 ?? "—"}</div></div>
        <div><div class="k">Net SOL in 1h</div><div class="v ${last.net_sol_h1 > 0 ? "up" : last.net_sol_h1 < 0 ? "down" : ""}">${signed(last.net_sol_h1, 1)}</div></div>
        <div><div class="k">Creator sold</div><div class="v ${last.dev_sold_sol >= 0.5 ? "down" : ""}">${isNum(last.dev_sold_sol) ? nf(last.dev_sold_sol, 2) + " SOL" : "—"}</div></div>
        <div><div class="k">Labelled smart / insider buyers 1h</div><div class="v">${last.labelled_buyers_h1 ?? "—"}<small> / ${last.insider_buyers_h1 ?? "—"}</small></div></div>
        <div><div class="k">Wallets buying in the launch block</div><div class="v ${last.launch_block_buyers >= 3 ? "down" : ""}">${last.launch_block_buyers ?? "—"}${isNum(last.launch_block_pct) ? `<small> · ${pct(last.launch_block_pct, 1)} of supply</small>` : ""}</div></div>
        <div><div class="k">Top 10 wallets / creator hold</div><div class="v">${isNum(last.top10_pct) ? pct(last.top10_pct) : "—"}<small> / ${isNum(last.dev_holds_pct) ? pct(last.dev_holds_pct, 1) : "—"}</small></div></div>` : ""}</div>
      ${last.sol_paired === 0 ? `<p class="notes">Paired with a token other than SOL: SOL and USD figures are left out.</p>` : ""}</div>
    <div class="dsec"><div class="chart-h">${seg("Metric", [["mcap", "Market cap"], ["buyers", "Buyers per hour"], ["curve", "Curve progress"]], tokState.metric, "data-m")}
      <span class="end">${seg("Range", [[6, "6H"], [24, "24H"], [72, "3D"]], tokState.hours, "data-h")}</span></div><div class="chart" id="tchart"></div></div>
    <div class="dsec"><h3>Creator<span class="note">${t.deployer ? esc(short(t.deployer.wallet)) : "unknown"}</span></h3>
      ${t.deployer ? `<div class="ledger"><div class="li"><span class="k">Launches we saw in 24 hours</span><span class="v ${t.deployer.launches_seen_24h >= 3 ? "down" : ""}">${t.deployer.launches_seen_24h}</span></div>
        ${t.deployer.label ? `<div class="li"><span class="k">Dataset label</span><span class="v ${t.deployer.label === "insider" ? "down" : ""}">${t.deployer.label === "insider" ? "Insider" : "Smart money"}</span><span class="c">June 2026 wallet labels</span></div>` : ""}
        ${t.deployer.activity ? `<div class="li"><span class="k">SOL balance</span><span class="v">${isNum(t.deployer.activity.sol_balance) ? nf(t.deployer.activity.sol_balance, 2) : "—"}</span></div>` : ""}</div>`
        : `<p class="notes" style="margin:0">This token launched before the app started listening, so its creator wasn't seen.</p>`}</div>
    ${out ? `<div class="dsec"><h3>Outcomes<span class="note">measured after launch</span></h3><table class="tbl"><thead><tr><th>Horizon</th><th>Result</th><th class="r">Return</th><th class="r">Peak</th></tr></thead><tbody>${out}</tbody></table>
      <p class="notes">Return runs from the first observed candle and ignores fees. Graduation and profit are separate outcomes.</p></div>` : ""}
    <p class="attr">Trading stats: live chain stream, ${t.observations.length} snapshots in range${t.pool?.length ? `; ${t.pool.length} PumpSwap pool readings after graduation` : ""}. Curve: Solana RPC account state${curve ? `, read ${esc(ago(t.now - curve.observed_at))}` : ", not read"}.${t.attention.length ? ` Paid DexScreener ${esc(t.attention[0].kind)} seen.` : ""}</p>`;
  $("#copy", root).addEventListener("click", async () => { try { await navigator.clipboard.writeText(k.mint); toast("Address copied"); } catch (_) { toast("Copying isn’t allowed here"); } });
  const draw = () => {
    const first = Math.min(...[k.created_at, t.observations[0]?.observed_at, t.curve[0]?.observed_at].filter(isNum));
    const el = $("#tchart", root), from = Math.max(t.now - tokState.hours * 3600, isFinite(first) ? first - 120 : 0);
    if (tokState.metric === "curve") return Charts.timeLine(el, { data: t.curve.map((c) => [c.observed_at, (c.complete ? 1 : c.progress) * 100]), from, to: t.now, yMin: 0, yMax: 100, fmtY: (v) => nf(v, 0) + "%", label: "Curve progress" });
    if (tokState.metric === "buyers") return Charts.timeLine(el, { data: t.observations.filter((o) => isNum(o.buyers_h1)).map((o) => [o.observed_at, o.buyers_h1]), from, to: t.now, fmtY: (v) => compact(v, 0), label: "Unique buyers per hour" });
    Charts.timeLine(el, { data: t.observations.filter((o) => isNum(o.mcap_usd)).map((o) => [o.observed_at, o.mcap_usd]), from, to: t.now, fmtY: (v) => usd(v), label: "Market cap" });
  };
  draw();
  $$("[data-m]", root).forEach((b) => b.addEventListener("click", () => { tokState.metric = b.dataset.m; $$("[data-m]", root).forEach((x) => x.setAttribute("aria-pressed", x === b)); draw(); }));
  $$("[data-h]", root).forEach((b) => b.addEventListener("click", () => { tokState.hours = +b.dataset.h; openToken(mint); }));
}

function aboutHtml(k, same) {
  const xUrl = k.x_post ? `https://x.com/${k.x_post}` : k.x_account ? `https://x.com/${k.x_account}` : null;
  const safe = (u) => (/^https:\/\//i.test(u || "") ? u : null);
  const links = [[xUrl, k.x_post ? "Linked X post" : "Linked X account"], [safe(k.website), "Website"], [safe(k.telegram), "Telegram"]].filter((l) => l[0]);
  if (!k.description && !links.length) return k.meta_status === "failed" ? `<div class="dsec"><h3>About</h3><p class="notes" style="margin:0">Its metadata file couldn’t be fetched.</p></div>` : "";
  return `<div class="dsec"><h3>About<span class="note">from the creator; unverified</span></h3>
    ${k.description ? `<p style="margin:0 0 10px">${esc(k.description)}</p>` : ""}
    ${links.length ? `<div class="links">${links.map(([u, l]) => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer nofollow">${esc(l)}</a>`).join("")}</div>` : ""}
    ${same && same.n > 1 ? `<p class="notes">${same.n} launches by ${same.c} creator${same.c === 1 ? "" : "s"} linked this same X post in the last 24 hours.</p>` : ""}</div>`;
}

// ---------------------------------------------------------------- TOKENS
const TCOLS = [
  ["sym", "Token", "", (t) => (t.symbol || "").toLowerCase()], ["age", "Age", "r", (t) => -(t.created_at || 0)], ["mcap_usd", "Market cap", "r", (t) => t.mcap_usd],
  ["liquidity_usd", "Liquidity", "r hide-s", (t) => t.liquidity_usd], ["vol_h1", "Volume 1h", "r", (t) => t.vol_h1], ["vol_h24", "Volume 24h", "r hide-s", (t) => t.vol_h24],
  ["buyers_h1", "Buyers / sellers 1h", "hide-s", (t) => t.buyers_h1], ["chg_h1", "Change 1h", "r hide-s", (t) => t.chg_h1],
  ["progress", "Curve", "hide-s", (t) => (t.graduated ? 2 : t.progress)], ["flags", "Risk flags", "hide-s", (t) => tokenFlags(t).length],
];
function renderTokens() {
  const el = $(".screen[data-screen=tokens]"), all = S.tokens?.tokens || [], T = S.tok, now = nowS();
  setHead("Tokens", `${all.length} tokens with trading stats from the last two hours. Click a row for its dossier.`);
  const q = T.q.trim().toLowerCase();
  const filt = { all: () => true, curve: (t) => !t.graduated, grad: (t) => !!t.graduated, flagged: (t) => tokenFlags(t, now).length > 0 };
  const counts = Object.fromEntries(Object.keys(filt).map((k) => [k, all.filter(filt[k]).length]));
  const col = TCOLS.find((c) => c[0] === T.key) || TCOLS[4];
  const list = all.filter(filt[T.filter]).filter((t) => !q || `${t.symbol} ${t.name} ${t.mint}`.toLowerCase().includes(q))
    .sort((a, b) => { const va = col[3](a), vb = col[3](b); if (va == null) return 1; if (vb == null) return -1; return (va > vb ? 1 : va < vb ? -1 : 0) * T.dir; });
  const focused = document.activeElement?.id === "tq";
  el.innerHTML = `
    <div class="toolbar"><label class="sr" for="tq">Search tokens</label><input id="tq" type="search" placeholder="Search by ticker, name or address" value="${esc(T.q)}" autocomplete="off" spellcheck="false">
      <div class="chips" role="group" aria-label="Filter">${[["all", "All"], ["curve", "On the curve"], ["grad", "Graduated"], ["flagged", "Flagged"]]
        .map(([v, l]) => `<button class="chip" data-tf="${v}" aria-pressed="${T.filter === v}">${l}<span class="ct">${counts[v]}</span></button>`).join("")}</div>
      <span class="end">${list.length} shown</span></div>
    <table class="tbl tokentbl"><thead><tr>${TCOLS.map(([k, l, c]) => `<th class="${c}" ${T.key === k ? `aria-sort="${T.dir < 0 ? "descending" : "ascending"}"` : ""}><button data-sort="${k}">${l}</button></th>`).join("")}</tr></thead>
      <tbody id="trows">${list.map((t, i) => {
        const ageH = t.created_at ? (now - t.created_at) / 3600 : null;
        const fl = tokenFlags(t, now);
        return `<tr data-i="${i}"><td><span class="tk"><b>${esc(t.symbol || short(t.mint))}</b><span>${esc(t.name || "")}</span>${fl.length ? `<span class="show-s ${fl.some((x) => x[0] === "neg") ? "down" : "warn"}">▲ ${esc(fl.map((x) => x[1].toLowerCase()).join(", "))}</span>` : ""}</span></td>
          <td class="r">${t.graduated && !isNum(ageH) ? "—" : esc(age(ageH))}</td><td class="r">${usd(t.mcap_usd)}</td><td class="r hide-s">${usd(t.liquidity_usd)}</td>
          <td class="r">${usd(t.vol_h1)}</td><td class="r hide-s">${usd(t.vol_h24)}</td><td class="hide-s">${bsr(t.buyers_h1, t.sellers_h1)}</td>
          <td class="r hide-s ${t.chg_h1 > 0 ? "up" : t.chg_h1 < 0 ? "down" : ""}">${isNum(t.chg_h1) ? signed(t.chg_h1, 0, "%") : "—"}</td>
          <td class="hide-s">${curveCell(t)}</td><td class="hide-s">${flagsHtml(fl)}</td></tr>`;
      }).join("") || `<tr><td colspan="10"><div class="empty">${all.length ? `<h3>No match</h3>No token matches these filters.` : `<h3>No active tokens yet</h3>Tokens appear once their trading stats are refreshed, every five minutes.`}</div></td></tr>`}</tbody></table>`;
  const inp = $("#tq");
  if (focused) { inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }
  inp.addEventListener("input", () => { T.q = inp.value; renderTokens(); });
  $$("[data-tf]", el).forEach((b) => b.addEventListener("click", () => { T.filter = b.dataset.tf; renderTokens(); }));
  $$("[data-sort]", el).forEach((b) => b.addEventListener("click", () => { const k = b.dataset.sort; T.dir = T.key === k ? -T.dir : (k === "sym" ? 1 : -1); T.key = k; renderTokens(); }));
  $$("#trows tr[data-i]", el).forEach((r) => r.addEventListener("click", () => openToken(list[+r.dataset.i].mint)));
}

// ---------------------------------------------------------------- ANALYST
function md(text) {
  const lines = esc(text.replace(/^# .*\n+/, "")).split("\n");
  let out = "", inList = false;
  const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|\s)_(.+?)_(?=\s|$|[.,])/g, "$1<em>$2</em>");
  for (const ln of lines) {
    const li = ln.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
    if (li) { if (!inList) { out += "<ul>"; inList = true; } out += `<li>${inline(li[1])}</li>`; continue; }
    if (inList) { out += "</ul>"; inList = false; }
    const hd = ln.match(/^\*\*(.+?)\*\*\s*$/) || ln.match(/^#{2,3} (.*)/);
    if (hd) out += `<h3>${inline(hd[1])}</h3>`;
    else if (ln.trim()) out += `<p>${inline(ln)}</p>`;
  }
  return out + (inList ? "</ul>" : "");
}
async function renderAnalyst() {
  const el = $(".screen[data-screen=analyst]"), ai = S.ov.config.anthropic_analyst;
  setHead("Analyst", ai ? `Claude (${esc(S.ov.config.analyst_model)}) writes from the evidence pack and may only cite its numbers.` : "The rules analyst writes from the same evidence pack. Add a Claude key in settings for written analysis.",
    `<button class="btn solid" id="write">Write a new report</button>`);
  $("#write").addEventListener("click", writeReport);
  if (!S.reports) {
    el.innerHTML = `<div class="ws"><div class="sk" style="height:420px"></div><div class="sk" style="height:300px"></div></div>`;
    try {
      S.reports = await api("/api/reports?limit=20");
      if (S.reports.length) S.report = await api(`/api/reports/${S.reports[0].id}`);
    } catch (e) { S.reports = []; S.report = { error: e.message }; }
    if (S.tab !== "analyst") return;
  }
  const metas = S.ov.metas;
  if (!S.cmp) S.cmp = metas.slice(0, 3).map((m) => m.meta_key);
  S.cmp = S.cmp.filter((k) => metas.some((m) => m.meta_key === k));
  const chosen = S.cmp.map((k) => metas.find((m) => m.meta_key === k));
  const R = S.report;
  const rowsDef = [
    ["Verdict", (m) => { const v = vinfo(m.verdict); return st(v.tone, v.g, v.label.replace(" evidence", "")); }], ["Readiness score", (m) => `<span class="${isProv(m) ? "i3" : ""}">${isNum(m.score) ? Math.round(m.score) : "—"}</span>`],
    ["Confidence", (m) => `<span class="${m.confidence < CONF_BAR ? "warn" : ""}">${nf(m.confidence, 2)}</span>`],
    ["Launches 1h / 6h", (m) => `${m.evidence.launch.launches_1h} / ${m.evidence.launch.launches_6h}`], ["Buyers per hour", (m) => compact(m.evidence.demand.unique_buyers_h1_sum)],
    ["Buyer share", (m) => pct(m.evidence.demand.buyer_share_h1)], ["Net SOL into curves 1h", (m) => (isNum(m.evidence.demand.curve_net_sol_1h) ? signed(m.evidence.demand.curve_net_sol_1h, 1) : "—")],
    ["Graduated 24h", (m) => m.evidence.demand.graduations_24h], ["Top token share of volume", (m) => pct(m.evidence.demand.top_token_share_vol24)],
    ["Crowding", (m) => (isNum(m.evidence.saturation.index) ? nf(m.evidence.saturation.index, 2) : "—")], ["Reused tickers", (m) => pct(m.evidence.launch.duplicate_symbol_share_6h)],
    ["Hype check", (m) => `<span class="i2">${esc(cap(m.hype_check))}</span>`],
  ];
  el.innerHTML = `<div class="ws">
    <article>
      <div class="repmeta">${S.reports.length ? `<label class="sr" for="rep">Report</label><select id="rep">${S.reports.map((r) => `<option value="${r.id}" ${R?.id === r.id ? "selected" : ""}>${esc(dayhm(r.created_at))}, ${esc(r.kind.replace("_", " "))}</option>`).join("")}</select>
        <span>Written by ${esc(R?.analyst || "—")}</span>` : "<span>No reports yet</span>"}</div>
      ${R?.error ? `<div class="empty"><h3>Couldn’t load the report</h3>${esc(cap(R.error))}.</div>` : R?.body ? `<div class="report">${md(R.body)}</div>`
        : `<div class="empty"><h3>No report yet</h3>Reports are written at the scheduled times, or now with “Write a new report”.</div>`}
    </article>
    <aside>
      <div class="sec-h"><h2>Compare narratives</h2><span class="note">pick up to three</span></div>
      <div class="chips" style="margin-bottom:12px">${metas.slice(0, 12).map((m) => `<button class="chip" data-c="${esc(m.meta_key)}" aria-pressed="${S.cmp.includes(m.meta_key)}">${esc(m.meta_key)}</button>`).join("")}</div>
      ${chosen.length ? `<table class="tbl cmp"><thead><tr><th></th>${chosen.map((m) => `<th class="nm">${esc(m.meta_key)}</th>`).join("")}</tr></thead>
        <tbody>${rowsDef.map(([k, f]) => `<tr><td class="k">${k}</td>${chosen.map((m) => `<td>${f(m)}</td>`).join("")}</tr>`).join("")}</tbody></table>
        <p class="notes">Figures from the analysis of ${esc(hhmm(S.ov.as_of))}, the same evidence the analyst reads. Buyer counts are per-token sums.</p>`
        : `<p class="notes">Choose narratives above to compare their evidence side by side.</p>`}
    </aside></div>`;
  const sel = $("#rep");
  if (sel) sel.addEventListener("change", async () => { try { S.report = await api(`/api/reports/${sel.value}`); } catch (e) { S.report = { error: e.message }; } renderAnalyst(); });
  $$("[data-c]", el).forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.c;
    S.cmp = S.cmp.includes(k) ? S.cmp.filter((x) => x !== k) : [...S.cmp, k].slice(-3);
    renderAnalyst();
  }));
}
async function writeReport(e) {
  const b = e.currentTarget; b.disabled = true; b.textContent = S.ov.config.anthropic_analyst ? "Writing, up to a minute" : "Writing";
  try { const r = await api("/api/reports", { method: "POST" }); S.reports = null; toast("Report written"); S.report = { id: r.id }; }
  catch (err) { toast(`Report failed: ${err.message}`); }
  if (S.tab === "analyst") renderAnalyst();
}

// ---------------------------------------------------------------- SYSTEM
const SRC_NAMES = { "chain/pump_stream": "Live chain stream", "chain/snapshot": "Token stats from the stream",
  "chain/pumpswap_pools": "PumpSwap pools after graduation", "defillama/sol_price": "SOL price", "dexscreener/boosts_profiles": "Paid promotion",
  "defillama/launchpad_volume": "Launchpad volume", "x_api/recent_search": "X posts", "reddit/new_posts": "Reddit posts",
  "pumpfun/latest_coins": "pump.fun API", "bitquery/net_flow": "Net flow (Bitquery)", "outcomes/label": "Outcome labelling" };
const SRC_STATE = { fresh: ["pos", "●", "Fresh"], degraded: ["warn", "▲", "Degraded"], stale: ["warn", "▲", "Stale"], expired: ["neg", "✕", "Expired"],
  unavailable: ["neg", "✕", "Unavailable"], error: ["neg", "✕", "Error"], skipped: ["mute", "○", "Not configured"] };
async function renderSystem() {
  const el = $(".screen[data-screen=system]"), ov = S.ov, L = liveState(), b = baseline();
  setHead("System", "Collection health, data freshness and display settings.");
  // problems first: failing, then degraded or stale, then not configured, then fresh
  const SEV = { error: 0, unavailable: 0, expired: 1, stale: 2, degraded: 2, skipped: 3, fresh: 4 };
  const f = Object.values(ov.freshness).sort((a, c) => (SEV[a.state] ?? 2) - (SEV[c.state] ?? 2)
    || (SRC_NAMES[`${a.source}/${a.job}`] || "").localeCompare(SRC_NAMES[`${c.source}/${c.job}`] || ""));
  let up = S.charts[S.range]?.uptime_1h || {};
  const hourNow = Math.floor(nowS() / 3600) * 3600;
  const freshN = f.filter((x) => x.state === "fresh").length;
  const rows = f.map((x) => {
    const k = `${x.source}/${x.job}`, cells = new Map((up[k] || []).map((c) => [c[0], c])), s = SRC_STATE[x.state] || ["mute", "○", x.state];
    const strip = Array.from({ length: 24 }, (_, i) => {
      const hb = hourNow - (23 - i) * 3600, c = cells.get(hb);
      if (!c) return `<i title="${esc(hhmm(hb))}: no runs"></i>`;
      const cls = c[3] && !c[1] && !c[2] ? "skip" : c[2] && !c[1] ? "bad" : c[2] ? "mix" : "ok";
      return `<i class="${cls}" title="${esc(hhmm(hb))}: ${c[1]} ok, ${c[2]} failed"></i>`;
    }).join("");
    return `<tr><td><div style="font-weight:500">${esc(SRC_NAMES[k] || k)}</div><div class="i3 mono" style="font-size:11px">${esc(k)}</div></td><td>${st(s[0], s[1], s[2])}</td>
      <td class="r">${esc(x.last_ok ? ago(nowS() - x.last_ok) : "never")}</td><td class="r hide-s">every ${esc(Math.round(x.expected_every_s / 60))} min</td>
      <td class="hide-s"><div class="strip" aria-label="runs in the last 24 hours">${strip}</div></td>
      <td class="hide-s"><span class="errtxt">${x.last_error && x.state !== "fresh" ? esc(x.last_error) : ""}</span></td></tr>`;
  }).join("");
  const h = ov.context.history || {}, cfg = ov.config, bt = ov.backtest, db = ov.db;
  const yes = (v) => (v ? st("pos", "●", "On") : st("mute", "○", "Off"));
  const pref = Perf.pref(), sig = Perf.signals();
  el.innerHTML = `
    <div class="sys-sum">
      <div><div class="k">Collection</div><div class="v">${st(L.cls === "ok" ? "pos" : L.cls === "stale" ? "warn" : "neg", L.cls === "ok" ? "●" : "▲", L.text)}</div><div class="c">last analysis ${esc(ago(L.lag))}</div></div>
      <div><div class="k">Sources fresh</div><div class="v">${freshN} <span class="i3" style="font-size:16px">of ${f.length}</span></div><div class="c">${f.filter((x) => x.state === "skipped").length} not configured</div></div>
      <div><div class="k">Baseline history</div><div class="v">${esc(b.label)} <span class="i3" style="font-size:16px">of ~${b.need}h</span></div><div class="c">${b.ready ? "acceleration is being scored" : "calls are held until this completes"}</div></div>
      <div><div class="k">Launch coverage, 6h</div><div class="v">${pct(h.launch_coverage_6h)}</div><div class="c">share of launches the collector saw</div></div>
    </div>
    <div class="sec"><div class="sec-h"><h2>Data sources</h2><span class="note">runs per hour over the last 24 hours</span></div>
      <table class="tbl systbl"><thead><tr><th>Source</th><th>Status</th><th class="r">Last success</th><th class="r hide-s">Cadence</th><th class="hide-s">Last 24 hours</th><th class="hide-s">Last error</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="6" class="i3">No collection runs yet.</td></tr>`}</tbody></table></div>
    <div class="sec three">
      <div><div class="sec-h"><h2>Stored history</h2></div><div class="ledger">
        <div class="li"><span class="k">Tokens tracked</span><span class="v">${compact(db.tokens)}</span></div><div class="li"><span class="k">Trading observations</span><span class="v">${compact(db.token_obs)}</span></div>
        <div class="li"><span class="k">Bonding-curve reads</span><span class="v">${compact(db.curve_obs)}</span></div><div class="li"><span class="k">Graduations seen</span><span class="v">${compact(db.graduations)}</span></div>
        <div class="li"><span class="k">Outcomes labelled</span><span class="v">${compact(db.token_outcomes)}</span></div><div class="li"><span class="k">Social posts</span><span class="v">${compact(db.social_posts)}</span></div>
        <div class="li"><span class="k">Baseline coverage, the 6h before the last hour</span><span class="v">${pct(h.launch_coverage_baseline)}</span></div></div></div>
      <div><div class="sec-h"><h2>Backtest</h2>${bt ? st(bt.validated ? "pos" : "warn", bt.validated ? "●" : "▲", bt.validated ? "Validated" : "Not validated") : ""}</div>
        ${bt ? `<p class="notes" style="margin:0 0 10px">${esc(cap(bt.verdict))}. ${bt.signals} signals over ${bt.steps} steps${bt.steps_excluded ? ` (${bt.steps_excluded} skipped for collection gaps)` : ""}${bt.dataset ? `, on ${esc(bt.dataset)} ${isNum(bt.range?.[0]) ? `${esc(new Date(bt.range[0] * 1000).toLocaleDateString([], { month: "short", day: "numeric" }))}–${esc(new Date(bt.range[1] * 1000).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }))}` : ""}` : ""}, run ${esc(ago(nowS() - bt.created_at))}.</p>
          <table class="tbl bt"><thead><tr><th>Verdict</th><th class="r">Signals</th><th class="r">Graduation lift</th><th class="r hide-s">Net-positive lift</th><th class="r">False positives</th></tr></thead><tbody>
          ${Object.entries(bt.by_verdict).map(([v, r]) => `<tr><td>${esc(vinfo(v).label)}</td><td class="r">${r.signals}</td><td class="r">${isNum(r.mean_grad_lift) ? signed(r.mean_grad_lift * 100, 2, " pts") : "—"}</td><td class="r hide-s">${isNum(r.mean_net_positive_lift) ? signed(r.mean_net_positive_lift * 100, 1, " pts") : "—"}</td><td class="r">${isNum(r.false_positive_rate) ? pct(r.false_positive_rate) : "—"}</td></tr>`).join("")}</tbody></table>
          <p class="notes">Lift compares later launches in a narrative with all launches in the same window. Validation needs at least 30 favorable signals.</p>`
          : `<p class="notes" style="margin:0">No backtest yet. It needs labelled outcomes, which start about 13 hours after collection begins (7h of baseline, then 6h for the first outcomes to mature).</p>`}
        <button class="btn" id="runbt" style="margin-top:12px">Run a 3-day backtest</button></div>
      <div><div class="sec-h"><h2>Display</h2></div><div class="modes">
        ${seg("Display mode", [["auto", "Auto"], ["premium", "Premium"], ["low", "Low visual"]], pref, "data-perf")}
        <p>${pref === "auto" ? `Auto is using <b>${Perf.resolved() === "low" ? "Low visual" : "Premium"}</b>${sig.length ? ` because this device reports ${esc(sig.join(", "))}` : " because this device reports no constraints"}.` : `${pref === "low" ? "Low visual" : "Premium"} is set manually.`}</p>
        <p>Low visual drops transitions, blur and continuous chart tracking (tooltips follow taps), refreshes every five minutes instead of two, and skips redraws when nothing changed. Every number and chart stays.</p></div>
        <div class="sec-h" style="margin-top:24px"><h2>Integrations</h2></div><div class="ledger">
          <div class="li"><span class="k">X API</span><span class="v">${yes(cfg.x_api)}</span></div><div class="li"><span class="k">Reddit OAuth</span><span class="v">${yes(cfg.reddit_oauth)}</span></div>
          <div class="li"><span class="k">Bitquery</span><span class="v">${yes(cfg.bitquery)}</span></div><div class="li"><span class="k">Claude analyst</span><span class="v">${yes(cfg.anthropic_analyst)}</span></div>
          <div class="li"><span class="k">Telegram</span><span class="v">${yes(cfg.telegram)}</span></div><div class="li"><span class="k">Solana RPC</span><span class="v i2">${esc(cfg.solana_rpc)}</span></div></div>
        <p class="notes">Keys live in your settings file and never reach this page.</p></div>
    </div>
    <div class="sec"><div class="sec-h"><h2>Recent alerts</h2><span class="note">verdict changes, large score moves, regime changes and outages</span></div><div id="alerts" class="posts"><div class="sk" style="height:60px"></div></div></div>`;
  $$("[data-perf]", el).forEach((b) => b.addEventListener("click", () => Perf.set(b.dataset.perf)));
  $("#runbt").addEventListener("click", async (e) => {
    const btn = e.currentTarget; btn.disabled = true; btn.textContent = "Running";
    try { await api("/api/backtests?days=3", { method: "POST" }); toast("Backtest finished"); await load(); }
    catch (err) { toast(`Backtest failed: ${err.message}`); btn.disabled = false; btn.textContent = "Run a 3-day backtest"; }
  });
  try {
    const al = await api("/api/alerts?limit=8"), box = $("#alerts");
    if (box) box.innerHTML = al.length ? al.map((a) => `<div class="post"><div class="by">${esc(dayhm(a.created_at))}, ${esc(a.kind.replace("_", " "))}, ${a.delivered ? "sent to Telegram" : "logged only"}</div>
      ${esc(a.message.replace("TRENCH//RADAR alert\n", "").split("\n\nResearch")[0])}</div>`).join("") : `<p class="notes" style="margin:0">No alerts yet.</p>`;
  } catch (_) { const box = $("#alerts"); if (box) box.innerHTML = `<p class="notes">Alerts are unavailable.</p>`; }
}

// ---------------------------------------------------------------- boot
$("#mrefresh").addEventListener("click", () => load());
let resizeT;
window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => { if (S.ov && !$("#sheet").classList.contains("on")) render(); }, Perf.low() ? 400 : 150); });
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && Date.now() - S.lastOk > 60000) load({ quiet: true }); });
matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", () => { if (Perf.pref() === "auto") { Perf.apply(); render(); } });
if ("serviceWorker" in navigator && (location.protocol === "https:" || ["127.0.0.1", "localhost"].includes(location.hostname))) navigator.serviceWorker.register("/sw.js").catch(() => {});
let start = (location.hash.match(/^#\/(\w+)/) || [])[1];
try { start = start || localStorage.getItem("radar-tab"); } catch (_) { /* ignore */ }
go(start || "overview");
renderStatus();
schedule();
load();
