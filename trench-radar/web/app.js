// TRENCH//RADAR client. Token names, posts and URLs come from strangers:
// every data-derived string goes through esc() before reaching innerHTML.
"use strict";

const { esc, hhmm, dayhm } = Charts;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const wide = () => matchMedia("(min-width: 720px)").matches;
const desk = () => matchMedia("(min-width: 1280px)").matches;

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
const plural = (n, w, ws = w + "s") => `${nf(n)} ${n === 1 ? w : ws}`;

const VERDICT = {
  favorable: { tone: "accelerating", label: "Favorable" }, mixed: { tone: "heating", label: "Mixed" },
  unfavorable: { tone: "fading", label: "Unfavorable" }, "insufficient data": { tone: "steady", label: "Insufficient evidence" },
};
const vinfo = (v) => VERDICT[v] || VERDICT["insufficient data"];
const vst = (v) => { const x = vinfo(v); return `<span class="stamp ${x.tone}">${Viz.GLYPH[x.tone]}${esc(x.label)}</span>`; };
const meter = (v, cls = "", thr) => `<span class="meter ${cls}" role="img" aria-label="${isNum(v) ? nf(v, 2) : "no data"}"><i style="width:${isNum(v) ? Math.max(0, Math.min(1, v)) * 100 : 0}%"></i>${isNum(thr) ? `<span class="thr" style="left:${thr * 100}%"></span>` : ""}</span>`;
const CONF_BAR = 0.35;   // scoring.py: confidence below this is always "insufficient data"

// ---------------------------------------------------------------- display: motion mode and edition
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
const Edition = {
  get() { return document.documentElement.dataset.edition === "night" ? "night" : "day"; },
  set(e) {
    document.documentElement.dataset.edition = e;
    try { localStorage.setItem("radar-edition", e); } catch (_) { /* ignore */ }
    const tc = $('meta[name="theme-color"]'); if (tc) tc.content = e === "night" ? "#121926" : "#eee8da";
    $("#edition").setAttribute("aria-label", e === "night" ? "Switch to the day edition" : "Switch to the night edition");
    $("#edition").innerHTML = e === "night" ? `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></svg>`
      : `<svg viewBox="0 0 24 24"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/></svg>`;
    if (S.ov) render();
  },
};

// ---------------------------------------------------------------- api + state
const S = { nar: null, narAsOf: null, metaView: "narratives", narSel: null, narState: "all", narCat: "all", ov: null, charts: {}, tokens: null, reports: null, report: null, range: 24, tab: "overview", sel: null,
  metaFilter: "all", metaSort: "edge", tok: { key: "vol_h1", dir: -1, filter: "all", q: "" }, cmp: null, error: null, lastOk: 0, sig: null };
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

// ---------------------------------------------------------------- collection status (masthead, banner)
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
  const d = S.ov ? new Date(S.ov.as_of * 1000) : new Date();
  $("#dateline").innerHTML = S.ov ? `Edition <b>${esc(hhmm(S.ov.as_of))}</b> · ${esc(d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" }))}<br>${fr.filter((x) => x.state === "fresh").length} of ${fr.length} sources fresh`
    : "Edition pending";
  $("#mstat").innerHTML = `<span class="livedot ${L.cls}"></span>${S.ov && !b.ready && L.cls === "ok" ? `Baseline ${esc(b.label.replace(" min", "m"))}/${b.need}h` : esc(L.text)}`;
  let html = "";
  if (S.ov && S.error) html = `<div class="alert neg" role="status"><b>Couldn’t refresh</b><span>Showing the edition from ${esc(hhmm(S.ov.as_of))}. ${esc(cap(S.error))}.</span></div>`;
  else if (L.cls === "stale") html = `<div class="alert" role="status"><b>Stale data</b><span>${L.bad.length ? esc(L.bad.map((x) => `${x.source}/${x.job} is ${x.state}`).join("; ")) + "." : `The last analysis ran ${esc(ago(L.lag))}.`} Figures may lag the market.</span></div>`;
  $("#banner").innerHTML = html;
}

// ---------------------------------------------------------------- loading
let refreshTimer;
function schedule() { clearInterval(refreshTimer); refreshTimer = setInterval(() => { if (document.visibilityState === "visible") load({ quiet: true }); }, Perf.low() ? 60000 : 30000); liveSchedule(); }

async function load({ quiet = false } = {}) {
  setBusy(true);
  try {
    const [ov, ch, tk, nar] = await Promise.all([api("/api/overview"), api(`/api/charts?hours=${S.range}`), api("/api/tokens?limit=120"),
      api("/api/narratives").catch(() => null)]);
    S.nar = nar;
    const sig = JSON.stringify([nar?.as_of, ov.as_of, ov.db, ov.metas.length, ch.launches.at(-1), ch.launches.length, tk.tokens.map((t) => t.observed_at).join()]);
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
  setHead("Locked edition", "This radar is protected. Enter the dashboard token from your settings file to read it.", "", "Access");
  $$(".screen").forEach((s) => (s.hidden = s.dataset.screen !== "overview"));
  $(".screen[data-screen=overview]").innerHTML = `<div class="empty" style="max-width:440px">
    <h3>Dashboard token</h3><p>The value of <span class="mono">DASHBOARD_TOKEN</span> in your settings file.</p>
    <form id="tokform" style="display:grid;gap:14px;margin-top:14px"><label class="sr" for="tokin">Dashboard token</label>
      <input id="tokin" type="password" autocomplete="current-password" required><button class="btn solid" style="justify-self:start">Unlock</button></form></div>`;
  $("#tokform").addEventListener("submit", (e) => {
    e.preventDefault(); token = $("#tokin").value;
    try { localStorage.setItem("radar-token", token); } catch (_) { /* ignore */ }
    load();
  });
}

// ---------------------------------------------------------------- router + folio
const TITLES = { overview: "Briefing", live: "Live wire", metas: "Metas", tokens: "Tokens", analyst: "Analyst", system: "System" };
const NUMS = { overview: "01", live: "02", metas: "03", tokens: "04", analyst: "05", system: "06" };
function go(tab, { keepScroll = false } = {}) {
  if (!TITLES[tab]) tab = "overview";
  const changed = S.tab !== tab;
  S.tab = tab;
  $$(".tab").forEach((t) => t.setAttribute("aria-current", t.dataset.go === tab ? "page" : "false"));
  $$(".screen").forEach((s) => { s.hidden = s.dataset.screen !== tab; if (!s.hidden && changed) { s.classList.remove("enter"); void s.offsetWidth; s.classList.add("enter"); } });
  history.replaceState(null, "", `#/${tab}`);
  try { localStorage.setItem("radar-tab", tab); } catch (_) { /* ignore */ }
  if (!keepScroll) window.scrollTo({ top: 0 });
  render();
  liveSchedule();
  if (tab === "live") pollLive();
}
$$(".tab").forEach((t) => t.addEventListener("click", () => go(t.dataset.go)));
window.addEventListener("hashchange", () => { const t = (location.hash.match(/^#\/(\w+)/) || [])[1]; if (t && t !== S.tab) go(t); });
function setHead(title, ctx, tools = "", kicker = "") {
  $("#kicker").innerHTML = `<span>§${NUMS[S.tab] || "00"}</span><b>${esc(TITLES[S.tab] || "")}</b>${kicker ? `<span>${kicker}</span>` : ""}`;
  $("#title").innerHTML = title;
  $("#ctx").innerHTML = ctx;
  $("#ctx").hidden = !ctx;
  $("#tools").innerHTML = tools;
  $$("[data-refresh]", $("#tools")).forEach((b) => b.addEventListener("click", () => load()));
  document.title = `${TITLES[S.tab] || ""} · TRENCH//RADAR`;
}

function render() {
  if (S.tab === "live") return renderLive();
  if (!S.ov) return renderLoadingOrError();
  ({ overview: renderOverview, metas: renderMetas, tokens: renderTokens, analyst: renderAnalyst, system: renderSystem })[S.tab]();
}
function renderLoadingOrError() {
  const el = $(`.screen[data-screen=${S.tab}]`);
  if (S.error) {
    setHead("The press is offline", `${esc(cap(S.error))}. Check that <span class="mono">python -m radar serve</span> or TrenchRadar.exe is running.`);
    el.innerHTML = `<div class="empty"><h3>Can’t reach the radar server</h3><p>Nothing on this page is being updated until the server answers again.</p><button class="btn" id="retry">Try again</button></div>`;
    $("#retry").addEventListener("click", () => load());
    return;
  }
  setHead("Printing the edition", "Reading the latest analysis from the collector.");
  el.innerHTML = `<div class="front"><div><div class="sk line" style="width:90%"></div><div class="sk line" style="width:82%"></div><div class="sk line" style="width:70%"></div>
    <div class="sk" style="height:220px;margin-top:32px"></div></div><div class="sk" style="height:360px"></div></div>`;
}

// ---------------------------------------------------------------- shared builders
const isProv = (m) => m.verdict === "insufficient data";
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
// danger first (boxed, red), then the quiet notes
const flagsHtml = (fl) => (fl.length ? `<span class="flags">${[...fl].sort((a, b) => (b[0] === "neg") - (a[0] === "neg")).map(([c, l]) => `<span class="flag ${c}">${esc(l)}</span>`).join("")}</span>` : `<span class="i4">—</span>`);
const bsr = (b = 0, s = 0) => { const t = b + s || 1; return `<span class="bsr"><span class="bsb" aria-hidden="true"><i style="width:${(b / t) * 100}%"></i><u style="width:${(s / t) * 100}%"></u></span><span>${compact(b)}/${compact(s)}</span></span>`; };
const ruler = (p, grad) => `<span class="curve"><span class="ruler${grad ? " grad" : ""}" role="img" aria-label="${grad ? "graduated" : `curve ${pct(p)}`}"><i style="width:${grad ? 100 : Math.max(0, Math.min(1, p || 0)) * 100}%"></i></span><span>${grad ? "GRAD" : pct(p)}</span></span>`;
const curveCell = (t) => (t.graduated ? ruler(1, true) : isNum(t.progress) ? ruler(t.progress) : `<span class="i4">—</span>`);
const seg = (name, opts, cur, attr = "data-v") => `<div class="seg" role="group" aria-label="${esc(name)}">${opts.map(([v, l]) => `<button ${attr}="${v}" aria-pressed="${String(v) === String(cur)}">${esc(l)}</button>`).join("")}</div>`;
const slug = (h, note = "", end = "", cls = "") => `<div class="slug ${cls}"><h2 class="h2">${h}</h2>${note ? `<span class="note">${note}</span>` : ""}${end ? `<span class="end">${end}</span>` : ""}</div>`;
const tk = (sym, name, extra = "") => `<span class="tk"><b>${esc(String(sym ?? "").trim() || "unnamed")}</b><span>${esc(name || "")}</span>${extra}</span>`;

// ---------------------------------------------------------------- narrative helpers (used on several pages)
const STATES = Viz.STAGES;
const catLabel = (c) => Viz.catName(c);
const narByBuyers = () => [...(S.nar?.narratives || [])].sort((a, b) => (b.traction.buyers_h1 || 0) - (a.traction.buyers_h1 || 0));
const NFLIP = new Map();        // narrative label -> {from, to, at}: a state change seen between two reads
function trackFlips(N) {
  if (S.narAsOf === N.as_of) return;
  S.narAsOf = N.as_of;
  N.narratives.forEach((n) => {
    const p = Viz.remember("state:" + n.label, n.state);
    if (p && p !== n.state) NFLIP.set(n.label, { from: p, to: n.state, at: N.as_of });
    else if (NFLIP.has(n.label) && N.as_of - NFLIP.get(n.label).at > 900) NFLIP.delete(n.label);
  });
}
const flipBadge = (n) => { const f = NFLIP.get(n.label); return f ? `<span class="flip" title="Was ${esc(Viz.STAGE_LABEL[f.from] || f.from)} at the previous read">just turned</span>` : ""; };

// ================================================================ BRIEFING (front page)
const DRIVERS = [["launchpad_volume_trend", "Launchpad volume trend"], ["new_token_performance", "New tokens with traction"],
  ["graduation_rate", "Graduation rate"], ["fresh_rotation", "Rotation into new launches"], ["sol_trend", "SOL trend"]];
function briefing() {
  const ov = S.ov, m = ov.market, metas = ov.metas, N = S.nar?.narratives || [];
  const fav = metas.filter((x) => x.verdict === "favorable");
  const regime = { hot: "The trenches are running hot", neutral: "A steady market", cold: "A cold market" }[m.regime] || "Conditions still being measured";
  const emerging = N.filter((n) => Viz.life(n.state) === "emerging"), sat = N.filter((n) => Viz.life(n.state) === "saturated");
  const lead = narByBuyers().find((n) => Viz.life(n.state) === "emerging") || narByBuyers()[0];
  const tail = fav.length ? `${fav.length === 1 ? "one narrative" : `${fav.length} narratives`} with attention and buying together`
    : lead ? `${lead.title} leads the pulse` : "no narrative has formed";
  const b = baseline(), x = m.metrics;
  const bits = [];
  if (N.length) bits.push(`${plural(N.length, "narrative")} are in play by meaning: <b>${emerging.length} emerging</b>, ${sat.length} saturating or fading.`);
  if (lead) bits.push(`The strongest pulse is <b>${esc(lead.title)}</b> (${esc(catLabel(lead.category).toLowerCase())}) with ${compact(lead.traction.buyers_h1)} buyers an hour across ${plural(lead.popularity.launches_6h, "launch", "launches")}.`);
  if (isNum(x.pumpfun_launchpad_vol_7d_vs_30d)) bits.push(`Launchpad volume is ${x.pumpfun_launchpad_vol_7d_vs_30d >= 1 ? "up" : "down"} ${nf(Math.abs(x.pumpfun_launchpad_vol_7d_vs_30d - 1) * 100, 0)}% on its 30-day average.`);
  if (!b.ready) bits.push(`Calls wait for about ${b.need} hours of history; ${esc(b.label)} is collected.`);
  return { head: `${regime}. <em>${esc(cap(tail))}.</em>`, lede: bits.length ? `<span class="runin">The read</span>${bits.join(" ")}` : "" };
}
function storyHtml(n, i) {
  const P = n.popularity, T = n.traction;
  return `<article class="story" tabindex="0" role="button" data-story="${esc(n.label)}" aria-label="${esc(n.title)}: open the profile">
    <div class="label">${Viz.swatch(n.category)}<span>${esc(catLabel(n.category))}</span><span class="i4">/</span>${Viz.stamp(n.state)}</div>
    <h3>${esc(n.title)}</h3>
    <p>${esc(n.explanation?.[1] && i === 0 ? n.explanation[1] : n.explanation?.[0] || n.label)}</p>
    <div class="nums"><div>Buyers/h<b>${compact(T.buyers_h1)}</b></div><div>Launches 6h<b>${P.launches_6h}</b></div><div>Creators 1h<b>${P.creators_1h}</b></div>${i === 0 ? `<div>Net SOL<b class="${T.net_sol_h1 > 0 ? "up" : T.net_sol_h1 < 0 ? "down" : ""}">${signed(T.net_sol_h1, 1)}</b></div>` : ""}</div>
  </article>`;
}
function renderOverview() {
  const el = $(".screen[data-screen=overview]"), ov = S.ov, m = ov.market, x = m.metrics, ch = S.charts[S.range];
  const ins = briefing();
  const valid = ov.backtest?.validated ? "validated by the latest backtest" : ov.backtest ? `the latest backtest${ov.backtest.dataset ? ` (${esc(ov.backtest.dataset)})` : ""} found no edge` : "not yet validated against outcomes";
  setHead(ins.head, ov.metas.some((x) => x.edge) ? `Metas are ranked by launch edge, which picked better metas than the readiness score in back-tests and in two later months; a ranking, not a forecast. Readiness scores are hand-weighted priors, ${valid}.` : `Scores are hand-weighted priors, ${valid}: read them as structure, not prediction.`, `<button class="btn ghost" data-goto="metas">Open the atlas</button>`, `Edition ${esc(hhmm(ov.as_of))}`);
  $$("[data-goto]", $("#tools")).forEach((b) => b.addEventListener("click", () => go(b.dataset.goto)));
  const drivers = DRIVERS.map(([k, label]) => {
    const v = m.components[k];
    return `<div class="readout"><span>${esc(label)}</span>${isNum(v) ? `${meter(v)}<span class="v">${nf(v, 2)}</span>` : `<span class="na">${k === "graduation_rate" ? "needs 24h of launches" : "no data yet"}</span>`}</div>`;
  }).join("");
  const stories = (() => {
    const all = narByBuyers();
    const em = all.filter((n) => Viz.life(n.state) === "emerging");
    return [...em, ...all.filter((n) => !em.includes(n))].slice(0, 3);
  })();
  const metas = ov.metas.slice(0, 7);
  const toks = (S.tokens?.tokens || []).slice(0, 7);
  let daily = [];
  try { daily = JSON.parse((x.pumpfun_launchpad_daily_series || "[]").replace(/'/g, '"')); } catch (_) { daily = []; }
  el.innerHTML = `
    <div class="front">
      <div class="lead-copy">
        <p class="lede">${ins.lede || "The first narrative read arrives a few minutes after the collector starts."}</p>
        <div class="sect">
          ${slug("Launch activity", `pump.fun launches per ${S.range === 6 ? "5 minutes" : S.range === 24 ? "15 minutes" : "hour"}, graduations below`, seg("Time range", [[6, "6H"], [24, "24H"], [72, "3D"]], S.range))}
          <div class="figs" style="margin-bottom:20px">
            <div class="fig"><div class="k">Launches per hour</div><div class="v">${isNum(x.launches_est_per_h) ? compact(x.launches_est_per_h) : compact(x.launches_observed_1h)}</div>
              <div class="c">${isNum(x.launches_est_per_h) ? `estimated from ${pct(x.launch_coverage_1h)} coverage` : `seen in the last hour, ${pct(x.launch_coverage_1h)} coverage`}</div></div>
            <div class="fig"><div class="k">Graduation rate</div><div class="v">${isNum(x.graduation_rate_24_48h_cohort) ? pct(x.graduation_rate_24_48h_cohort, 2) : "—"}</div>
              <div class="c">${x.graduation_cohort_n ? `launches 24 to 48h old, n=${compact(x.graduation_cohort_n)}` : "needs a day of launches"}</div></div>
            <div class="fig"><div class="k">Launchpad volume, 7d avg</div><div class="v">${usd(x.pumpfun_launchpad_vol_7d_avg_usd)}</div>
              <div class="c">${isNum(x.pumpfun_launchpad_vol_7d_vs_30d) ? `<span class="${x.pumpfun_launchpad_vol_7d_vs_30d >= 1 ? "up" : "down"}">${signed((x.pumpfun_launchpad_vol_7d_vs_30d - 1) * 100, 0, "%")}</span> against the 30-day average` : ""}</div></div>
          </div>
          <div class="chart" id="flow"></div>
          <div class="legend" style="margin-top:8px"><span><i style="background:var(--ink);height:2px"></i>launches</span><span><i style="background:url(#)" class="hk"></i>collector not running</span><span><i style="background:var(--ink);width:2px;height:10px"></i>graduations</span></div>
        </div>
      </div>
      <aside class="plate reg barometer" aria-label="Market regime">
        <div class="label">Barometer · market regime</div>
        <div class="regime" style="margin-top:10px">${esc(m.regime ? cap(m.regime) : "Unknown")}<small style="display:inline;margin-left:10px">${isNum(m.score) ? `score ${nf(m.score, 2)} · ${pct(m.coverage)} of inputs` : "not enough data"}</small></div>
        <div class="chart" id="dial" style="margin-top:6px"></div>
        <div class="readouts">${drivers}</div>
      </aside>
    </div>
    <div class="sect">
      ${slug("Emerging now", "narratives read by meaning, ranked by buyers", `<button class="linkbtn" data-goto="metas">The atlas →</button>`)}
      ${stories.length ? `<div class="fold">${stories.map(storyHtml).join("")}</div>` : `<div class="empty"><h3>No narrative yet</h3><p>A narrative forms once three or more tokens from two or more creators share an idea. The first read runs a few minutes after start.</p></div>`}
    </div>
    <div class="sect g12">
      <div class="span-7">
        ${slug("Meta ledger", "ranked by launch edge; readiness is the baseline score; buyers are per-token sums", `<button class="linkbtn" data-goto="metas" data-kw="1">All ${ov.metas.length} →</button>`)}
        <div class="ranks" id="lead-n">${metas.length ? metas.map((mm, i) => {
          const d = mm.evidence.demand, l = mm.evidence.launch;
          return `<button class="rank" data-meta="${esc(mm.meta_key)}"><span class="n">${String(i + 1).padStart(2, "0")}</span>
            <span class="t">${esc(mm.meta_key)}<small>${mm.edge ? `<b class="${edgeCls(mm)}">${esc(cap(mm.edge.tier))} edge</b> · ` : ""}${esc(mm.terms.length > 1 ? `with ${mm.terms.slice(1, 5).join(", ")}` : `${l.launches_6h} launches in 6h, ${pct(d.buyer_share_h1)} of traders buying`)}</small></span>
            <span class="s ${isProv(mm) ? "prov" : ""}">${isNum(mm.score) ? Math.round(mm.score) : "—"}<small>${isProv(mm) ? "provisional" : esc(vinfo(mm.verdict).label)}</small></span>
            <span class="b">${compact(d.unique_buyers_h1_sum)}<small>buyers/h</small></span></button>`;
        }).join("") : `<div class="chart-empty">No keyword cluster yet.</div>`}</div>
        <div class="sect" style="margin-top:36px">${slug("Launchpad volume by day", "pump.fun, DefiLlama, 30 days; today is partial", "", "thin")}<div class="chart" id="daily"></div></div>
      </div>
      <div class="span-5 colrule">
        ${slug("Where the buying is", "last hour", `<button class="linkbtn" data-goto="tokens">All tokens →</button>`)}
        <table class="tbl" id="buying"><thead><tr><th>Token</th><th class="r">Vol 1h</th><th>Buy/sell</th><th class="hide-s">Curve</th></tr></thead>
          <tbody>${toks.map((t, i) => `<tr data-tok="${i}"><td>${tk(t.symbol || short(t.mint), t.name)}</td>
            <td class="r">${usd(t.vol_h1)}</td><td>${bsr(t.buyers_h1, t.sellers_h1)}</td><td class="hide-s">${curveCell(t)}</td></tr>`).join("")
            || `<tr><td colspan="4" class="i3">No token has fresh stats yet.</td></tr>`}</tbody></table>
        <div class="sect" style="margin-top:36px">${slug("Market data", "", "", "thin")}
          <div class="ledger">
            <div class="li"><span class="k">SOL</span><span class="v">${isNum(x.sol_price_usd) ? "$" + nf(x.sol_price_usd, 2) : "—"}</span>
              <span class="c">${isNum(x.sol_chg_24h) ? `${signed(x.sol_chg_24h * 100, 1, "%")} over 24 hours` : "24-hour change appears after a day"}</span></div>
            <div class="li"><span class="k">Median 24h move, most-traded curve tokens</span><span class="v ${x.active_median_chg_h24_pct >= 0 ? "up" : "down"}">${isNum(x.active_median_chg_h24_pct) ? signed(x.active_median_chg_h24_pct, 0, "%") : "—"}</span></div>
            <div class="li"><span class="k">Most-traded tokens under a day old</span><span class="v">${pct(x.active_share_under_24h)}</span><span class="c">a high share means money is rotating into new launches</span></div>
            <div class="li"><span class="k">PumpSwap volume, 7d against 30d</span><span class="v">${isNum(x.pumpswap_vol_7d_vs_30d) ? signed((x.pumpswap_vol_7d_vs_30d - 1) * 100, 0, "%") : "—"}</span></div>
          </div></div>
      </div>
    </div>`;
  $$(".seg button", el).forEach((b) => b.addEventListener("click", async () => {
    S.range = +b.dataset.v;
    if (!S.charts[S.range]) { try { S.charts[S.range] = await api(`/api/charts?hours=${S.range}`); } catch (_) { toast("Couldn’t load that range"); } }
    renderOverview();
  }));
  $$("[data-goto]", el).forEach((b) => b.addEventListener("click", () => { if (b.dataset.kw) S.metaView = "keywords"; go(b.dataset.goto); }));
  $$("[data-meta]", el).forEach((b) => b.addEventListener("click", () => pickMeta(b.dataset.meta)));
  $$("[data-story]", el).forEach((s) => {
    const open = () => { const n = (S.nar?.narratives || []).find((x) => x.label === s.dataset.story); if (n) openNarrative(n); };
    s.addEventListener("click", open); s.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  });
  $$("#buying tr[data-tok]", el).forEach((r) => r.addEventListener("click", () => openToken(toks[+r.dataset.tok].mint)));
  const hk = $(".hk", el); if (hk) hk.style.background = "repeating-linear-gradient(45deg,var(--rule-2) 0 1.4px,transparent 1.4px 4px)";
  Charts.dial($("#dial"), { score: m.score });
  if (ch) {
    const to = ch.now, from = to - ch.hours * 3600;
    Charts.seismo($("#flow"), { data: ch.launches, from, to, step: ch.step_s, observed: ch.observed_buckets, grads: ch.graduations, gstep: ch.graduation_step_s,
      height: wide() ? 250 : 200, fmtY: (v) => compact(v, 0), label: "Launches over time, with graduations" });
  }
  Charts.catBars($("#daily"), { data: daily, height: 130, fmtY: (v) => usd(v, 0), fmtX: (t) => new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric" }), label: "Daily launchpad volume" });
}

// ================================================================ LIVE WIRE
const LV = { data: null, err: null, timer: null, seen: null };
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
    setHead(LV.err ? "Off air" : "Tuning in", LV.err ? esc(cap(LV.err)) : "Connecting to the chain feed.", "", "Solana · pump.fun program");
    el.innerHTML = LV.err ? `<div class="empty"><h3>Can’t reach the radar server</h3><p>${esc(cap(LV.err))}.</p></div>` : `<div class="sk" style="height:240px"></div>`;
    return;
  }
  const s = d.stream, now = d.now;
  const status = !s.enabled ? "The live stream runs with the collector; start the app normally (not with --no-scheduler)."
    : s.connected ? `Read straight from the Solana chain, about ${nf(s.lag_s ?? 0, 1)}s behind. The wire refreshes every ${Perf.low() ? 6 : 3} seconds.`
    : `Reconnecting to the chain${s.error ? `: ${esc(s.error)}` : ""}.`;
  const per = d.launches_per_min, last60 = per.reduce((a, b) => a + b[1], 0), last5 = per.slice(-6, -1).reduce((a, b) => a + b[1], 0);
  setHead(`${compact(last60)} launches <em>this hour</em>`, status, `<span class="onair ${s.connected ? "" : "off"}">${s.connected ? "● On air" : "○ Off air"}</span>`, "Solana · pump.fun program");
  const hot = d.hot, flag = (c, t) => `<span class="flag ${c}">${esc(t)}</span>`;
  const first = !LV.seen;
  const seen = LV.seen || new Set();
  const launches = d.launches.slice(0, 26);
  el.innerHTML = `
    <div class="wire-top">
      <div class="figs" style="grid-auto-flow:row;grid-template-columns:1fr 1fr;row-gap:18px">
        <div class="fig"><div class="k">Per minute, last 5</div><div class="v">${nf(last5 / 5, 1)}</div><div class="c">launches a minute</div></div>
        <div class="fig"><div class="k">Being bought now</div><div class="v">${hot.length}${hot.length >= 20 ? "+" : ""}</div><div class="c">3+ buyers in 5 minutes</div></div>
        <div class="fig" style="border-left:0;padding-left:0"><div class="k">Proven wallets</div><div class="v">${compact(s.smart_wallets + s.labelled_wallets)}</div><div class="c">${compact(s.smart_wallets)} learned here, ${compact(s.labelled_wallets)} from a public dataset</div></div>
        <div class="fig"><div class="k">Graduated</div><div class="v">${d.graduations.length}</div><div class="c">since the app started</div></div>
      </div>
      <div>${slug("Launches per minute", "last hour; the current minute is partial", "", "thin")}<div class="chart" id="lpm"></div></div>
    </div>
    <div class="wire-cols">
      <section>${slug("The tape", "newest first")}
        <div class="tape">${launches.map((l, i) => {
          const fl = [l.clones >= 2 ? flag("", `${l.clones} wallets, same name`) : "", l.creator_launches_24h >= 3 ? flag("neg", `creator's ${ordinal(l.creator_launches_24h)} today`) : "",
            l.launch_block_buyers >= 3 ? flag("neg", `${l.launch_block_buyers} bought in launch block`) : ""].filter(Boolean);
          return `<button class="tape-row${!first && !seen.has(l.mint) ? " fresh" : ""}" data-l="${i}"><span class="t">${esc(secs(now - l.ts))}</span>
            <span class="s">${esc(l.symbol || short(l.mint))}<span>${esc(l.name || "")}</span></span>${fl.length ? `<span class="flags">${fl.join("")}</span>` : ""}</button>`;
        }).join("") || `<div class="chart-empty">Waiting for the first launch.</div>`}</div></section>
      <section>${slug("Being bought now", "last 5 minutes · proven wallets first")}
        <table class="tbl" id="hot"><thead><tr><th>Token</th><th class="r hide-m">Age</th><th>Buy/sell</th><th class="r">Net SOL</th><th class="r" title="Buyers with a proven early-entry record or labelled smart money">Proven</th><th class="hide-m">Curve</th></tr></thead>
          <tbody>${hot.map((h, i) => {
            const fl = [];
            if (h.dev_sold_sol >= 0.5) fl.push(flag("neg", `creator sold ${nf(h.dev_sold_sol, 1)} SOL`));
            if (h.launch_block_buyers >= 3) fl.push(flag("neg", `bundled: ${h.launch_block_buyers}`));
            if (h.insider_5m) fl.push(flag("neg", `${h.insider_5m} insider${h.insider_5m > 1 ? "s" : ""}`));
            if (isNum(h.top10_pct) && h.top10_pct >= 0.3) fl.push(flag("", `top 10 hold ${pct(h.top10_pct)}`));
            if (h.sellers_5m > h.buyers_5m) fl.push(flag("neg", "more sellers"));
            return `<tr data-h="${i}"><td>${tk(h.symbol || short(h.mint), h.name, fl.length ? `<span class="flags" style="margin-top:3px">${fl.join("")}</span>` : "")}</td>
              <td class="r hide-m">${secs(h.age_s)}</td><td>${bsr(h.buyers_5m, h.sellers_5m)}</td>
              <td class="r ${h.net_sol_5m > 0 ? "up" : h.net_sol_5m < 0 ? "down" : ""}">${signed(h.net_sol_5m, 1)}</td>
              <td class="r ${h.smart_5m + h.labelled_5m ? "up" : "i4"}" title="learned ${h.smart_5m}, dataset-labelled ${h.labelled_5m}">${h.smart_5m + h.labelled_5m || "—"}</td>
              <td class="hide-m">${h.graduated ? ruler(1, true) : curveCell(h)}</td></tr>`;
          }).join("") || `<tr><td colspan="6"><div class="chart-empty">Tokens show up here once three or more wallets buy within five minutes.</div></td></tr>`}</tbody></table></section>
      <section>${slug("Dispatches")}
        ${(d.source_posts || []).map((p) => `<div class="dispatch"><div class="k">X post spawning coins</div><div class="h"><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer nofollow">@${esc(p.account)}</a> · ${p.launches} launches</div>
          ${p.text ? `<p>“${esc(p.text.length > 150 ? p.text.slice(0, 147) + "…" : p.text)}”</p>` : ""}
          <div class="m">${p.creators} creator${p.creators === 1 ? "" : "s"} · ${p.buyers_1h} buyers/h · ${signed(p.net_sol_1h, 1)} SOL${isNum(p.likes) ? ` · ${compact(p.likes)} likes` : ""}${isNum(p.followers) ? ` · ${compact(p.followers)} followers` : ""}</div></div>`).join("")}
        ${(d.image_groups || []).map((g) => `<div class="dispatch"><div class="k">Same picture, different names</div><div class="h">${g.tokens} tokens</div>
          <p>${esc(g.names.slice(0, 4).join(", "))}${g.names.length > 4 ? "…" : ""}</p><div class="m">first ${esc(secs(d.now - g.first_at))} ago · latest ${esc(secs(d.now - g.last_at))} ago</div></div>`).join("")}
        ${d.graduations.slice(0, 8).map((g) => `<div class="dispatch"><div class="k">Graduated · ${esc(secs(now - g.ts))} ago</div><div class="h">${esc(g.symbol ? "$" + g.symbol : short(g.mint))}</div><p>${esc(g.name || "")}</p></div>`).join("")}
        ${!(d.source_posts || []).length && !(d.image_groups || []).length && !d.graduations.length ? `<div class="chart-empty">No post has spawned two launches, no picture is shared and nothing has graduated yet.</div>` : ""}
      </section>
    </div>`;
  LV.seen = new Set(d.launches.map((l) => l.mint));
  Charts.seismo($("#lpm"), { data: per, from: per[0][0], to: per[per.length - 1][0] + 60, step: 60, height: wide() ? 210 : 160, fmtY: (v) => compact(v, 0), label: "Launches per minute" });
  $$("#hot tr[data-h]", el).forEach((r) => r.addEventListener("click", () => openToken(hot[+r.dataset.h].mint)));
  $$(".tape-row", el).forEach((r) => r.addEventListener("click", () => openToken(launches[+r.dataset.l].mint)));
}

// ================================================================ METAS: the atlas
const VIEW_SEG = () => seg("View", [["narratives", "Atlas"], ["keywords", "Keyword scores"]], S.metaView, "data-view");
function bindView() { $$("[data-view]", $("#tools")).forEach((b) => b.addEventListener("click", () => { S.metaView = b.dataset.view; renderMetas(); })); }
function renderMetas() {
  if (S.metaView === "narratives") return renderNarratives();
  return renderKeywords();
}
function atlasHeadline(all) {
  const em = all.filter((n) => Viz.life(n.state) === "emerging"), nov = all.filter((n) => !n.category?.primary);
  const lead = [...em].sort((a, b) => (b.traction.buyers_h1 || 0) - (a.traction.buyers_h1 || 0))[0];
  const cats = new Map(); all.forEach((n) => cats.set(Viz.bandKey(n.category), (cats.get(Viz.bandKey(n.category)) || 0) + n.popularity.launches_6h));
  const topCat = [...cats.entries()].sort((a, b) => b[1] - a[1])[0];
  return { head: `${plural(all.length, "narrative")} in play. ${lead ? `<em>${esc(lead.title)}</em> leads.` : "Nothing is emerging."}`,
    dek: `${topCat ? `${esc(cap(topCat[0]))} holds the most launches. ` : ""}${em.length} emerging${nov.length ? `, ${plural(nov.length, "new kind", "new kinds")} of meta no category fits` : ""}. ` };
}
function renderNarratives() {
  const el = $(".screen[data-screen=metas]"), N = S.nar;
  if (!N || N.pending || !N.narratives?.length) {
    setHead(N?.pending ? "The first read is printing" : "No narrative yet", esc(N?.note || "A narrative forms once 3+ tokens from 2+ creators share an idea."), VIEW_SEG(), "The atlas");
    bindView();
    el.innerHTML = `<div class="empty"><h3>${N?.pending ? "Reading the trenches" : N?.semantic === false ? "Narratives need the language model" : "Quiet for now"}</h3><p>${esc(N?.note || "The atlas fills in as launches share ideas. It refreshes every five minutes.")}</p></div>`;
    return;
  }
  const all = N.narratives;
  trackFlips(N);
  const hl = atlasHeadline(all);
  setHead(hl.head, `${hl.dek}Read by meaning from ${compact(N.launches_considered)} launches in the last six hours${N.factory_launches_excluded ? `, after leaving out ${compact(N.factory_launches_excluded)} by factory wallets` : ""}. Updated ${esc(hhmm(N.as_of))}.`,
    VIEW_SEG(), `The atlas · ${N.total ?? all.length} read`);
  bindView();
  if (S.narCat !== "all" && !all.some((n) => Viz.bandKey(n.category) === S.narCat)) S.narCat = "all";
  if (!S.narSel || !all.some((n) => n.label === S.narSel)) S.narSel = (narByBuyers().find((n) => Viz.life(n.state) === "emerging") || all[0]).label;
  const sel = all.find((n) => n.label === S.narSel);
  const states = STATES.filter((s) => all.some((n) => n.state === s));
  const list = all.filter((n) => (S.narState === "all" || n.state === S.narState) && (S.narCat === "all" || Viz.bandKey(n.category) === S.narCat));
  // lifecycle column
  const cycle = STATES.map((s) => {
    const xs = all.filter((n) => n.state === s).sort((a, b) => (b.traction.buyers_h1 || 0) - (a.traction.buyers_h1 || 0));
    return `<div class="cyc${xs.length ? "" : " none"}"><span class="g stamp ${s}">${Viz.GLYPH[s]}</span><span class="s">${esc(Viz.STAGE_LABEL[s])}</span><span class="n">${xs.length}</span>
      <div class="names">${xs.slice(0, 5).map((n) => `<button data-pick="${esc(n.label)}">${esc(n.title)}</button>`).join("")}${xs.length > 5 ? `<span class="more">+${xs.length - 5}</span>` : xs.length ? "" : `<span class="i4" style="font:italic 13px var(--serif)">${esc(Viz.STAGE_NOTE[s])}</span>`}</div></div>`;
  }).join("");
  // category index
  const byCat = new Map();
  all.forEach((n) => { const k = Viz.bandKey(n.category); const b = byCat.get(k) || { c: n.category, xs: [], launches: 0, em: 0 }; b.xs.push(n); b.launches += n.popularity.launches_6h; if (Viz.life(n.state) === "emerging") b.em++; byCat.set(k, b); });
  const totL = all.reduce((s, n) => s + n.popularity.launches_6h, 0) || 1;
  const order = (k) => (k === Viz.NOVEL ? 98 : k === Viz.CREATED ? 99 : Viz.RING.indexOf(k));
  const index = [...byCat.entries()].sort((a, b) => b[1].launches - a[1].launches || order(a[0]) - order(b[0])).map(([k, b]) => {
    const e = Viz.enc(b.c), share = b.launches / totL, emShare = b.xs.filter((n) => Viz.life(n.state) === "emerging").reduce((s, n) => s + n.popularity.launches_6h, 0) / totL;
    return `<div class="ix"><button class="ix-h" data-cat="${esc(k)}" aria-pressed="${S.narCat === k}">${Viz.swatch(b.c)}<span class="t">${esc(k)}</span><span class="p">${pct(share)}</span></button>
      <div class="share" role="img" aria-label="${pct(share)} of launches, ${pct(emShare)} in emerging narratives"><i style="width:${share * 100}%;background:${e.ink}"></i><u style="left:${emShare * 100}%;width:${Math.max(0, share - emShare) * 100}%"></u></div>
      <div class="subs">${b.xs.sort((p, q) => (q.traction.buyers_h1 || 0) - (p.traction.buyers_h1 || 0)).slice(0, 8).map((n) => `<button data-pick="${esc(n.label)}" class="${n.state === "new" ? "nv" : ""}">${esc(n.label.split(" · ")[0])}<b>${compact(n.traction.buyers_h1)}</b></button>`).join("")}${b.xs.length > 8 ? `<span class="i4 mono" style="font-size:10px">+${b.xs.length - 8}</span>` : ""}</div>
      <div class="em">${plural(b.xs.length, "narrative")} · ${b.em} emerging${k === Viz.CREATED ? ` · e.g. ${esc([...new Set(b.xs.map((n) => n.category.primary.split(" · ")[0]))].slice(0, 3).join(", "))}` : ""}</div></div>`;
  }).join("");
  const parents = (N.parents || []).filter((p) => p.sub_metas?.length >= 2).slice(0, 6);
  const events = (N.events || []).slice(0, 6);
  const row = (n) => {
    const T = n.traction, P = n.popularity, sp = (n.history || []).map((h) => h[2] || 0);
    return `<tr data-n="${esc(n.label)}" class="${n.label === S.narSel ? "sel" : ""}">
      <td class="nmc"><span class="nm" title="${esc(catLabel(n.category))}">${Viz.swatch(n.category)}<span>${esc(n.title)}</span><span class="sr">, ${esc(catLabel(n.category))}</span></span><small>${esc(n.label)}</small></td>
      <td class="wide-only"><span class="i2">${esc(catLabel(n.category))}</span></td>
      <td>${Viz.stamp(n.state)}${flipBadge(n)}</td>
      <td class="r hide-s ${Viz.moved("c1:" + n.label, P.creators_1h)}">${P.creators_1h}<span class="i4">/${P.creators_6h}</span></td>
      <td class="r"><span class="lc"><span class="hide-m">${sp.length >= 2 ? Charts.spark(sp, 56, 18) : ""}</span><span class="${Viz.moved("b1:" + n.label, T.buyers_h1)}">${compact(T.buyers_h1)}</span></span></td>
      <td class="r hide-s ${T.net_sol_h1 > 0 ? "up" : T.net_sol_h1 < 0 ? "down" : ""}">${signed(T.net_sol_h1, 1)}</td>
      <td class="r hide-m">${pct(P.clone_share)}</td>
      <td class="wide-only"><span class="i3">${esc(n.evidence.level)}</span></td></tr>`;
  };
  el.innerHTML = `
    <div class="atlas-wrap">
      <div class="plate reg atlas">
        <div class="atlas-h"><span class="label">Plate I · narratives by meaning</span>
          <span class="legend" style="margin-left:auto"><span><i style="background:var(--ink);border-radius:50%;width:9px;height:9px"></i>emerging</span><span><i style="background:radial-gradient(var(--ink) 1px,transparent 1.3px) 0 0/3px 3px;border-radius:50%;width:9px;height:9px"></i>established</span><span><i style="background:repeating-linear-gradient(45deg,var(--ink) 0 1px,transparent 1px 3px);border:1px solid var(--ink);width:9px;height:9px"></i>saturating</span><span><i style="border:1.5px dashed var(--novel-ink);border-radius:50%;width:10px;height:10px"></i>new</span></span></div>
        <div id="atlas" style="margin-top:8px"></div>
        <p class="notes" style="margin-top:4px">Bearing shows which categories a narrative resembles; distance from the centre shows how clearly. Size is launches in six hours. Lines join sub-metas of one broad narrative (solid) and close relatives (dotted). Click to inspect, double-click for the profile.</p>
      </div>
      <aside>
        <div class="spec" id="spec">${sel ? specimen(sel) : ""}</div>
        <div class="cycle">${slug("Lifecycle", "where every narrative stands", "", "thin")}${cycle}</div>
      </aside>
    </div>
    <div class="sect">${slug("The pulse", "buyers per hour, read by read; each line scaled to its own peak, so its shape is its momentum")}<div class="plate" style="padding:18px 22px 12px"><div id="ridges"></div></div></div>
    <div class="sect g12">
      <div class="span-8">${slug("Index of categories", "share of launches; dotted part is not emerging. Sub-metas by buyers")}<div class="index">${index}</div></div>
      <div class="span-4 colrule">
        ${slug("Broad narratives", "sub-metas that share a parent idea")}
        <div class="events">${parents.map((p) => `<div class="event"><b>${esc(p.label)}</b><br><span class="i3">${esc(p.sub_metas.slice(0, 7).join(" · "))}${p.sub_metas.length > 7 ? " …" : ""}</span><br><span class="mono i3" style="font-size:11px">${p.launches_6h} launches</span></div>`).join("") || `<div class="chart-empty">No narrative has split into sub-metas yet.</div>`}</div>
        <div style="margin-top:28px">${slug("Merges & splits", "since the last read", "", "thin")}
          <div class="events">${events.map((e) => e.kind === "merge" ? `<div class="event"><span class="k">Merge</span><b>${esc((e.from || []).join(" + "))}</b> → ${esc(e.into || "")}</div>`
            : `<div class="event"><span class="k">${esc(e.kind)}</span><b>${esc(e.from || e.label || "")}</b>${e.into ? ` → ${esc([].concat(e.into).join(", "))}` : ""}</div>`).join("") || `<div class="chart-empty">Nothing merged or split at this read.</div>`}</div></div>
      </div>
    </div>
    <div class="sect">
      ${slug("All narratives", `${list.length} shown`, S.narCat !== "all" ? `<button class="linkbtn" data-cat="all">${esc(S.narCat)} ✕</button>` : "")}
      <div class="filters" role="group" aria-label="Filter by state" style="margin-bottom:10px"><button class="fil" data-ns="all" aria-pressed="${S.narState === "all"}">All<sup>${all.length}</sup></button>${states.map((s) => `<button class="fil" data-ns="${s}" aria-pressed="${S.narState === s}">${esc(Viz.STAGE_LABEL[s])}<sup>${all.filter((n) => n.state === s).length}</sup></button>`).join("")}</div>
      <table class="tbl"><thead><tr><th>Narrative</th><th class="wide-only">Category</th><th>State</th><th class="r hide-s">Creators 1h/6h</th><th class="r">Buyers/h</th><th class="r hide-s">Net SOL 1h</th><th class="r hide-m">Copies</th><th class="wide-only">Evidence</th></tr></thead>
        <tbody id="nrows">${list.map(row).join("") || `<tr><td colspan="8" class="i3">No narrative matches these filters.</td></tr>`}</tbody></table>
      <p class="notes">Grouped by what the tokens mean (name, description, the X post they link to) and by shared pictures, not by keywords. States describe launches and buying; none of them is a tested profit signal (docs/RESEARCH_NARRATIVES.md).</p>
    </div>`;
  const pick = (label) => {
    S.narSel = label;
    const n = all.find((x) => x.label === label);
    $("#spec").innerHTML = specimen(n); bindSpec(n);
    $$("#nrows tr").forEach((r) => r.classList.toggle("sel", r.dataset.n === label));
    drawAtlas();
    $$(".ridges .rg").forEach((g) => g.classList.toggle("sel", g.dataset.k === label));
    if (!desk()) $("#spec").scrollIntoView({ behavior: Viz.motion() ? "smooth" : "auto", block: "nearest" });
  };
  const drawAtlas = () => Viz.atlas($("#atlas"), all, { selected: S.narSel, highlight: S.narCat !== "all" ? S.narCat : null, asOf: N.as_of, compact: !wide(), onPick: (x) => pick(x.label), onOpen: openNarrative });
  const bindSpec = (n) => {
    $$("[data-open]", $("#spec")).forEach((b) => b.addEventListener("click", () => openNarrative(n)));
    $$("[data-ex]", $("#spec")).forEach((b) => b.addEventListener("click", () => openToken(n.represents.examples[+b.dataset.ex].mint)));
    Viz.tick($("#spec"));
  };
  drawAtlas();
  if (sel) bindSpec(sel);
  Viz.ridges($("#ridges"), all, { selected: S.narSel, compact: !wide(), onPick: (x) => pick(x.label) });
  $$("[data-pick]", el).forEach((b) => b.addEventListener("click", () => pick(b.dataset.pick)));
  $$("[data-ns]", el).forEach((b) => b.addEventListener("click", () => { S.narState = b.dataset.ns; renderNarratives(); }));
  $$("[data-cat]", el).forEach((b) => b.addEventListener("click", () => { S.narCat = b.dataset.cat === S.narCat ? "all" : b.dataset.cat; renderNarratives(); }));
  $$("#nrows tr[data-n]", el).forEach((r) => r.addEventListener("click", () => { const n = all.find((x) => x.label === r.dataset.n); S.narSel = n.label; openNarrative(n); }));
  Viz.tick(el);
}
function specimen(n) {
  const P = n.popularity, T = n.traction, k = n.label;
  return `<div class="cat label">${Viz.swatch(n.category)}<span>${esc(catLabel(n.category))}</span><span style="margin-left:auto">${Viz.stamp(n.state)}${flipBadge(n)}</span></div>
    <h2>${esc(n.title)}</h2>
    <div class="sub">${esc(n.label)}${n.parent?.siblings?.length ? ` · part of ${esc(n.parent.label)}` : ""}</div>
    <p class="why">${esc(n.explanation?.[1] || n.explanation?.[0] || "")}</p>
    <div class="trio">
      <div><div class="k">Popularity</div><div class="v">${Viz.num("s:c1:" + k, P.creators_1h, P.creators_1h)}</div><div class="c">creators this hour, ${nf(P.creator_rate_h, 1)}/h before</div></div>
      <div><div class="k">Traction</div><div class="v">${Viz.num("s:b1:" + k, T.buyers_h1, compact(T.buyers_h1))}</div><div class="c">buyers/h${isNum(T.buyers_h1_hour_ago) ? `, ${compact(T.buyers_h1_hour_ago)} an hour ago` : ""}</div></div>
      <div><div class="k">Crowding</div><div class="v ${P.clone_share >= 0.5 ? "warn" : ""}">${pct(P.clone_share)}</div><div class="c">of launches reuse a name</div></div>
    </div>
    <div class="acts"><button class="btn solid" data-open>Read the profile</button>${n.represents.examples.slice(0, 3).map((x, i) => `<button class="specimen" data-ex="${i}">${esc(x.symbol || x.name || "token")}${x.buyers ? `<small>${compact(x.buyers)}</small>` : ""}</button>`).join("")}</div>`;
}

// ---------------------------------------------------------------- NARRATIVE PROFILE (sheet)
const CLUSTERS = new Map();      // "label@as_of" -> cluster, so re-opening doesn't refetch
// the launch-edge ranking of the keyword meta that holds this narrative's coins (explain.py joins them)
function narRecHtml(n) {
  const ms = (S.ov?.metas || []).filter((m) => m.explain?.concept.narrative?.label === n.label);
  if (!ms.length) return `<p class="notes"><b style="color:var(--ink-2)">Recommendation:</b> none of the ranked keyword metas holds enough of these coins to rank this narrative.</p>`;
  return `<div class="recbox"><div class="label">Recommendation</div>${ms.map((m) => `<p class="prose" style="margin:6px 0 0">Its coins rank as the keyword meta <b>${esc(m.meta_key)}</b>: <b class="${edgeCls(m)}">${esc(m.explain.recommendation.stance.toLowerCase())}</b>, #${m.edge.rank} of ${m.edge.of}. <button class="linkbtn" data-rec="${esc(m.meta_key)}">Why →</button></p>`).join("")}
    <p class="notes">A narrative's state says what is happening to the idea; the recommendation says how its next coins are likely to fare against other metas. They can disagree.</p></div>`;
}
function openNarrative(n) {
  openSheet("Narrative profile", `${esc(catLabel(n.category))} · ${esc(n.label)}`, profileHtml(n), (root) => bindProfile(root, n));
}
function profileHtml(n) {
  const P = n.popularity, T = n.traction, c = n.category, p = n.represents.post, k = n.label;
  const firstSeen = isNum(P.first_launch_at) ? `first launch ${esc(ago(S.nar.as_of - P.first_launch_at))}` : "";
  return `
    <header class="prof-head">
      <div class="cat label">${Viz.swatch(c)}<span>${esc(catLabel(c))}${c.secondary?.length ? ` · also ${esc(c.secondary.join(", "))}` : ""}</span><span style="margin-left:auto">${Viz.stamp(n.state, true)}</span></div>
      <h2>${esc(n.title)}</h2>
      <p class="dek">${esc(n.explanation?.[0] || "")}</p>
      <div class="by"><span>Sub-meta: ${esc(n.label)}</span>${firstSeen ? `<span>${firstSeen}</span>` : ""}<span>${n.history_hours ? `tracked ${nf(n.history_hours, 1)}h` : "first read"}</span><span>evidence ${esc(n.evidence.level)}</span></div>
      ${Viz.tracker(n)}
    </header>
    ${p ? `<blockquote class="pull">“${esc(p.text)}”<cite>@${esc(p.author || "?")}${isNum(p.followers) ? ` · ${compact(p.followers)} followers` : ""}${isNum(p.likes) ? ` · ${compact(p.likes)} likes` : ""} · cited by ${plural(p.tokens, "launch", "launches")} · <a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer nofollow">open on X</a></cite></blockquote>` : ""}
    <div class="vitals">
      <div class="vital"><h4>Popularity</h4><div class="big">${Viz.num("p:c1:" + k, P.creators_1h, P.creators_1h)}<small>creators/h</small></div>
        <div class="row"><span>Before this hour</span><b>${nf(P.creator_rate_h, 1)}/h</b></div><div class="row"><span>Launches, 6h</span><b>${P.launches_6h}</b></div><div class="row"><span>Momentum (z)</span><b class="${P.velocity_z >= 2 ? "up" : P.velocity_z <= -1 ? "down" : ""}">${signed(P.velocity_z, 1)}</b></div></div>
      <div class="vital"><h4>Traction</h4><div class="big">${Viz.num("p:b1:" + k, T.buyers_h1, compact(T.buyers_h1))}<small>buyers/h</small></div>
        <div class="row"><span>An hour ago</span><b>${isNum(T.buyers_h1_hour_ago) ? compact(T.buyers_h1_hour_ago) : "—"}</b></div><div class="row"><span>Net SOL, 1h</span><b class="${T.net_sol_h1 > 0 ? "up" : T.net_sol_h1 < 0 ? "down" : ""}">${signed(T.net_sol_h1, 1)}</b></div><div class="row"><span>Proven wallets</span><b>${T.smart_buyers_h1 || 0}</b></div></div>
      <div class="vital"><h4>Saturation</h4><div class="big ${P.clone_share >= 0.5 ? "warn" : ""}">${pct(P.clone_share)}<small>copies</small></div>
        <div class="row"><span>Buyers per launch</span><b>${nf(T.buyers_per_launch_1h, 1)}</b></div><div class="row"><span>Top token's share</span><b>${isNum(T.top_token_share) ? pct(T.top_token_share) : "—"}</b></div><div class="row"><span>Tokens trading</span><b>${T.tokens_traded}</b></div></div>
    </div>
    <p class="notes"><b style="color:var(--ink-2)">Why ${esc((Viz.STAGE_LABEL[n.state] || n.state).toLowerCase())}:</b> ${esc(n.state_reasons.join("; "))}. <b style="color:var(--ink-2)">Opportunity:</b> ${esc(n.opportunity)}</p>
    ${narRecHtml(n)}
    <section class="psec">${slug("What drives it", "", "", "thin")}<div class="two">
      <div><h4 class="label" style="margin:0 0 6px">Drivers</h4>${n.drivers.length ? `<ul class="ev pos">${n.drivers.map((d) => `<li><span class="g">●</span><span>${esc(d)}</span></li>`).join("")}</ul>` : `<p class="dek2">No single driver stands out.</p>`}</div>
      <div><h4 class="label" style="margin:0 0 6px">Saturation and risks</h4>${n.risks.length ? `<ul class="ev cau">${n.risks.map((r) => `<li><span class="g">▲</span><span>${esc(r)}</span></li>`).join("")}</ul>` : `<p class="dek2">No copycat, bundling, insider or creator-selling pattern found.</p>`}</div></div></section>
    <section class="psec">${slug("Momentum", n.history?.length >= 2 ? "buyers per hour, then launches in six hours, read by read" : "history builds up every five minutes", "", "thin")}
      ${n.merged_from ? `<p class="notes" style="margin:0 0 6px">Merged with ${esc(n.merged_from.join(", "))}.</p>` : ""}${n.split_from ? `<p class="notes" style="margin:0 0 6px">Split from ${esc(n.split_from)}.</p>` : ""}
      ${n.history?.length >= 2 ? `<div class="chart" id="pbuy"></div><div class="chart" id="plaunch" style="margin-top:6px"></div>` : ""}</section>
    <section class="psec">${slug("Token constellation", "", "", "thin")}<div class="constellation" id="pcl"><div class="sk" style="height:240px"></div></div>
      <div class="ckey"><span><i style="border-color:var(--ink)"></i>same X post</span><span><i style="border-color:var(--novel-ink)"></i>same picture</span><span><i style="border-color:var(--caution)"></i>same name</span><span><i style="border-color:var(--ink-4);border-top-style:dotted"></i>nearest by meaning</span><span>size = buyers/h · faint = loosely related</span></div></section>
    <section class="psec">${slug("Specimens", "most-bought tokens; open one for its dossier", "", "thin")}
      <div class="specimens">${n.represents.examples.map((x, i) => `<button class="specimen" data-ex="${i}">${esc(x.symbol || "?")}<small>${esc(x.name || "")}${x.buyers ? ` · ${compact(x.buyers)}/h` : ""}</small></button>`).join("")}</div></section>
    <section class="psec">${slug("Classification", "", "", "thin")}
      <div class="ledger">
        <div class="li"><span class="k">Category</span><span class="v">${esc(catLabel(c))}</span><span class="c">${c.primary ? `similarity ${nf(c.primary_score, 2)} to the category's description${c.emergent ? "; a category the app created from earlier narratives" : ""}` : `no known category fits (closest ${esc(c.nearest_seed || "—")}, ${nf(c.primary_score, 2)})`}</span></div>
        ${c.secondary?.length ? `<div class="li"><span class="k">Also resembles</span><span class="v">${esc(c.secondary.join(", "))}</span></div>` : ""}
        <div class="li"><span class="k">Sub-meta</span><span class="v">${esc(n.label)}</span></div>
        <div class="li"><span class="k">Novelty</span><span class="v">${isNum(n.novelty?.score) ? nf(n.novelty.score, 2) : "—"}</span><span class="c">${esc(n.novelty?.most_similar_before ? `resembles “${n.novelty.most_similar_before}” seen earlier` : n.novelty?.basis || "")}</span></div>
        ${n.closest ? `<div class="li"><span class="k">Closest other narrative</span><span class="v">${esc(n.closest.title)}</span><span class="c">similarity ${nf(n.closest.similarity, 2)}${n.closest.distinct_terms.length ? `; this one is about ${esc(n.closest.distinct_terms.join(", "))}` : ""}</span></div>` : ""}
      </div></section>
    <section class="psec foot">${slug("Evidence", n.evidence.level, "", "thin")}<ol>
      <li>Grouping: ${n.grouping.by_meaning} by similar meaning${Object.entries(n.grouping.links).map(([kk, v]) => `, ${v} by ${esc(kk)}`).join("")}; coherence ${nf(n.grouping.coherence, 2)}, weakest member ${nf(n.grouping.weakest_member_similarity, 2)}.</li>
      <li>${n.evidence.gaps.length ? esc(cap(n.evidence.gaps.join("; "))) + "." : "Several creators, readable descriptions or posts, and trading data."}</li>
      <li>Buyer counts are per-token sums; one wallet buying three tokens counts three times. States are descriptions, not tested profit signals.</li></ol></section>`;
}
function bindProfile(root, n) {
  $$("[data-rec]", root).forEach((b) => b.addEventListener("click", () => { const m = S.ov.metas.find((x) => x.meta_key === b.dataset.rec); if (m) openMetaSheet(m); }));
  $$("[data-ex]", root).forEach((b) => b.addEventListener("click", () => openToken(n.represents.examples[+b.dataset.ex].mint)));
  Viz.tick(root);
  if (n.history?.length >= 2) {
    const h = n.history, from = h[0][0], to = h[h.length - 1][0];
    Charts.timeLine($("#pbuy", root), { data: h.map((x) => [x[0], x[2] || 0]), from, to, height: 130, yMin: 0, cls: "dem", fmtY: (v) => compact(v, 0), label: "Buyers per hour in this narrative" });
    Charts.timeLine($("#plaunch", root), { data: h.map((x) => [x[0], x[1] || 0]), from, to, height: 100, yMin: 0, fmtY: (v) => compact(v, 0), label: "Launches in the last six hours" });
  }
  const box = $("#pcl", root), key = `${n.label}@${S.nar?.as_of}`;
  const draw = (cl) => {
    if (!box.isConnected) return;
    if (!cl.nodes?.length) { box.innerHTML = `<div class="chart-empty">No token data for this read.</div>`; return; }
    Viz.constellation(box, n, cl, { compact: !wide(), onToken: (m) => openToken(m) });
    box.insertAdjacentHTML("afterbegin", `<p class="notes" style="margin:0 0 6px">${cl.shown} most-bought of ${cl.of} tokens.</p>`);
  };
  if (CLUSTERS.has(key)) return draw(CLUSTERS.get(key));
  api(`/api/narratives/cluster?label=${encodeURIComponent(n.label)}`).then((cl) => {
    if (CLUSTERS.size > 40) CLUSTERS.clear();
    CLUSTERS.set(key, cl); draw(cl);
  }).catch(() => { if (box.isConnected) box.innerHTML = `<div class="chart-empty">The constellation is not in the latest read; refresh to load it.</div>`; });
}

// ---------------------------------------------------------------- keyword scores (the readiness model)
// launch edge (radar/analytics/meta_model.py): a ranking of metas, validated walk-forward and in two
// later months; the size of the lift did not hold up, so only rank and tier are shown
const edgeCls = (m) => ({ strongest: "up", weakest: "down" }[m.edge?.tier] || "");
const edgeTxt = (m) => (m.edge ? `#${m.edge.rank} of ${m.edge.of}` : "—");
const MSORT = { edge: (m) => (m.edge ? -m.edge.rank : -1e9), score: (m) => m.score ?? -1, confidence: (m) => m.confidence, buyers: (m) => m.evidence.demand.unique_buyers_h1_sum,
  launches: (m) => m.evidence.launch.launches_1h, saturation: (m) => -(m.evidence.saturation.index ?? 1) };
function pickMeta(key) {
  S.sel = key; S.metaView = "keywords";
  const m = S.ov.metas.find((x) => x.meta_key === key);
  if (S.tab !== "metas") go("metas"); else renderKeywords();
  if (m) openMetaSheet(m);
}
function renderKeywords() {
  const el = $(".screen[data-screen=metas]"), all = S.ov.metas;
  setHead(`${plural(all.length, "keyword cluster")} <em>ranked by launch edge</em>`, "Launch edge ranks metas by how their next launches graduated against the market in back-tests: real creators, live trading, little copycat crowding. The hand-weighted readiness score stays alongside as the baseline. Select one for its evidence.", VIEW_SEG(), "Keyword scores");
  bindView();
  if (!all.length) { el.innerHTML = `<div class="empty"><h3>No keyword cluster yet</h3><p>A cluster appears once several launches or posts share a term. The first ones show up within a few collection cycles.</p></div>`; return; }
  if (!S.sel || !all.some((m) => m.meta_key === S.sel)) S.sel = all[0].meta_key;
  const count = (v) => all.filter((m) => m.verdict === v).length;
  const filters = [["all", "All", all.length], ["favorable", "Favorable", count("favorable")], ["mixed", "Mixed", count("mixed")],
    ["unfavorable", "Unfavorable", count("unfavorable")], ["insufficient data", "Insufficient", count("insufficient data")]];
  const list = all.filter((m) => S.metaFilter === "all" || m.verdict === S.metaFilter).sort((a, b) => MSORT[S.metaSort](b) - MSORT[S.metaSort](a));
  el.innerHTML = `<div class="g12">
    <div class="span-7"><div class="plate reg" style="padding:16px 18px 10px"><div class="label">Plate II · does the buying confirm the attention?</div><div class="chart" id="map" style="margin-top:8px"></div></div></div>
    <div class="span-5 colrule">${slug("How to read it", "", "", "thin")}<p class="prose" style="margin:0">Right means launches are named for the idea${S.ov.social_measured ? " and people post about it" : ""}; up means wallets are buying it. Filled marks have enough evidence for a call; a dashed ring means the narrative is crowded. Size is buyers per hour.</p>
      <p class="notes">These scores come from the keyword model. The atlas reads the same launches by meaning and is usually the better guide to what a meta is.</p></div>
    <div class="span-12">
      <div style="display:flex;gap:16px;align-items:end;flex-wrap:wrap;margin-bottom:10px"><div class="filters" role="group" aria-label="Filter by verdict">${filters.map(([v, l, n]) => `<button class="fil" data-f="${esc(v)}" aria-pressed="${S.metaFilter === v}">${l}<sup>${n}</sup></button>`).join("")}</div>
        <span style="margin-left:auto"><label class="sr" for="msort">Sort</label><select id="msort">${[["edge", "Launch edge"], ["score", "Readiness score"], ["confidence", "Confidence"], ["buyers", "Buyers"], ["launches", "Launches"], ["saturation", "Least crowded"]]
          .map(([v, l]) => `<option value="${v}" ${S.metaSort === v ? "selected" : ""}>Sort by ${l.toLowerCase()}</option>`).join("")}</select></span></div>
      <table class="tbl"><thead><tr><th>Cluster</th><th>Edge</th><th class="r">Readiness</th><th class="hide-s">Confidence</th><th>Launches 1h/6h</th><th class="r">Buyers/h</th><th class="r hide-m">Buyer share</th><th class="r hide-m">Curve SOL 1h</th><th class="r hide-s">Crowding</th></tr></thead>
        <tbody id="mrows">${list.map((m) => {
          const d = m.evidence.demand, l = m.evidence.launch, sat = m.evidence.saturation.index;
          return `<tr data-k="${esc(m.meta_key)}" class="${m.meta_key === S.sel ? "sel" : ""}">
            <td class="nmc"><span class="nm"><span>${esc(m.meta_key)}</span></span><small>${esc(m.terms.length > 1 ? `with ${m.terms.slice(1, 4).join(", ")}` : d.top_tokens?.[0]?.symbol ? `led by ${d.top_tokens[0].symbol}` : `${d.tokens_tracked} tokens trading`)}</small></td>
            <td class="${edgeCls(m)}"><span class="mono" style="font-size:12.5px">${edgeTxt(m)}</span>${m.edge ? `<small style="display:block">${esc(m.edge.tier)}</small>` : ""}</td>
            <td class="r ${isProv(m) ? "i3" : ""}">${isNum(m.score) ? Math.round(m.score) : "—"}</td>
            <td class="hide-s">${meter(m.confidence, m.confidence < CONF_BAR ? "cau" : "", CONF_BAR)} <span class="mono" style="font-size:12px">${nf(m.confidence, 2)}</span></td>
            <td><span class="lc" style="justify-content:flex-start"><span class="hide-s">${Charts.spark(l.launch_hourly_12h, 52, 18)}</span><span class="mono" style="font-size:12.5px">${l.launches_1h}<span class="i4">/${l.launches_6h}</span></span></span></td>
            <td class="r">${compact(d.unique_buyers_h1_sum)}</td><td class="r hide-m">${pct(d.buyer_share_h1)}</td>
            <td class="r hide-m ${isNum(d.curve_net_sol_1h) ? (d.curve_net_sol_1h >= 0 ? "up" : "down") : ""}">${isNum(d.curve_net_sol_1h) ? signed(d.curve_net_sol_1h, 1) : "—"}</td>
            <td class="r hide-s ${isNum(sat) && sat >= 0.6 ? "warn" : ""}">${isNum(sat) ? nf(sat, 2) : "—"}</td></tr>`;
        }).join("") || `<tr><td colspan="9" class="i3">No cluster has this verdict right now.</td></tr>`}</tbody></table></div></div>`;
  const pts = all.filter((m) => isNum(m.components.attention) && isNum(m.components.demand)).map((m) => ({
    key: m.meta_key, label: m.meta_key, x: m.components.attention, y: m.components.demand, buyers: m.evidence.demand.unique_buyers_h1_sum,
    tone: { favorable: "pos", mixed: "warn", unfavorable: "neg" }[m.verdict] || "mute", verdict: vinfo(m.verdict).label, conf: m.confidence, confident: !isProv(m), score: m.score,
    crowded: (m.evidence.saturation.index ?? 0) >= 0.6, social: S.ov.social_measured }));
  if (pts.length) Charts.narrativeMap($("#map"), { points: pts, selected: S.sel, height: wide() ? 380 : 300, onPick: (p) => { S.sel = p.key; openMetaSheet(all.find((m) => m.meta_key === p.key)); } });
  $$("#mrows tr[data-k]").forEach((r) => r.addEventListener("click", () => { S.sel = r.dataset.k; $$("#mrows tr").forEach((x) => x.classList.toggle("sel", x === r)); openMetaSheet(all.find((m) => m.meta_key === r.dataset.k)); }));
  $$("[data-f]", el).forEach((b) => b.addEventListener("click", () => { S.metaFilter = b.dataset.f; renderKeywords(); }));
  $("#msort").addEventListener("change", (e) => { S.metaSort = e.target.value; renderKeywords(); });
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
// ---------------------------------------------------------------- plain-language explanation (analytics/explain.py)
const STATUS = { new: ["New", "novel"], growing: ["Growing", "accelerating"], steady: ["Steady", "steady"], fading: ["Fading", "fading"], crowded: ["Crowded", "saturating"] };
const effBar = (v, max) => {
  const w = Math.min(50, (Math.abs(v) / (max || 1)) * 50);
  return `<span class="eff" aria-hidden="true"><i class="${v >= 0 ? "p" : "n"}" style="${v >= 0 ? "left" : "right"}:50%;width:${w}%"></i></span>`;
};
function explainHtml(m) {
  const x = m.explain, r = x.recommendation, c = x.confidence, h = x.happening, st = STATUS[h.status] || STATUS.steady;
  const li = (arr, cls, g) => `<ul class="ev ${cls}">${arr.map((t) => `<li><span class="g">${g}</span><span>${esc(t)}</span></li>`).join("")}</ul>`;
  // each reason carries how that kind of reason held up on its own in periods the model never saw
  const reasons = (arr, cls, g) => `<ul class="ev ${cls}">${arr.map((t) => `<li><span class="g">${g}</span><span>${esc(t.text)}<small class="rel ${t.reliability.held === t.reliability.tested && t.reliability.tested ? "" : t.reliability.held ? "mid" : "weak"}">${esc(t.reliability.note)}</small></span></li>`).join("")}</ul>`;
  const maxD = Math.max(...r.drivers.map((d) => Math.abs(d.effect)), 0.01), maxE = Math.max(...x.evidence.map((d) => Math.abs(d.effect)), 0.01);
  const hist = x.history;
  return `
    <div class="dsec"><h3>What it is<span class="note">${x.concept.source === "names" ? "read from coin names" : x.concept.source === "post" ? "from the X post its coins cite" : "from its creators' descriptions"}</span></h3>
      ${x.concept.text.map((t) => `<p class="prose" style="margin:0 0 8px">${esc(t)}</p>`).join("")}
      <p class="notes">${esc(x.concept.connects)}${x.concept.narrative ? ` The atlas reads the same coins as the narrative <button class="linkbtn" data-nar="${esc(x.concept.narrative.label)}">${esc(x.concept.narrative.title)} →</button>` : ""}</p></div>
    <div class="dsec"><h3>What's happening<span class="note"><span class="stamp ${st[1]}">${st[0]}</span></span></h3>
      ${h.text.map((t) => `<p class="prose" style="margin:0 0 8px">${esc(t)}</p>`).join("")}
      <div class="chart" id="x-launch"></div></div>
    <div class="dsec"><h3>Why it's getting attention</h3>${li(x.attention, "", "●")}</div>
    <div class="dsec"><h3>Why it's ranked here<span class="note">#${r.rank} of ${r.of} · ${esc(r.tier)}</span></h3>
      <p class="prose" style="margin:0 0 10px"><b>${esc(r.stance)}.</b> ${r.tier === "strongest" || r.tier === "above average" ? "Compared with the other metas right now, this is what lifts it:" : "Compared with the other metas right now, this is what holds it back:"}</p>
      ${r.for.length ? `<div class="label" style="margin:6px 0 2px">In its favour</div>${reasons(r.for, "pos", "+")}` : ""}
      ${r.against.length ? `<div class="label" style="margin:14px 0 2px">Against it</div>${reasons(r.against, "neg", "−")}` : ""}
      ${r.conflict ? `<p class="notes"><b>The signals disagree:</b> the points against it are nearly as strong as the points for it, so the rank could flip with a little new data.</p>` : ""}
      ${x.popular_vs_promising ? `<p class="notes">${esc(x.popular_vs_promising)}</p>` : ""}</div>
    <div class="dsec"><h3>What could go wrong</h3>${li(x.risks, "cau", "▲")}</div>
    <div class="dsec"><h3>What to watch next<span class="note">what would move its rank</span></h3>${li(x.watch, "", "→")}</div>
    <div class="dsec"><h3>How sure is this?<span class="note">${esc(c.level)}</span></h3>
      <p class="prose" style="margin:0 0 8px"><b>${esc(c.summary)}</b>${c.track ? ` ${esc(c.track)}` : ""}</p>
      ${c.notes.map((t) => `<p class="notes" style="margin-top:4px">${esc(t)}</p>`).join("")}</div>
    <details class="more"><summary>Why this recommendation? <span>the numbers behind it</span></summary>
      <div class="dsec"><h3>What moved the rank<span class="note">exact share of its rank vs the average meta now</span></h3>
        <div class="drv">${r.drivers.map((d) => `<span>${esc(d.label)}</span>${effBar(d.effect, maxD)}<span class="mono ${d.effect > 0.02 ? "up" : d.effect < -0.02 ? "down" : "i3"}">${Math.abs(d.effect) < 0.005 ? "0.00" : `${d.effect > 0 ? "+" : ""}${nf(d.effect, 2)}`}</span>`).join("")}</div>
        <p class="notes">Positive lifts the rank, negative lowers it. Related measurements are grouped, because on their own they overlap; the table below has each one.</p></div>
      <div class="dsec"><h3>Every measurement</h3>
        <table class="tbl static ev-tbl"><thead><tr><th>Measurement</th><th class="r">This meta</th><th class="r">Typical now</th><th>Effect on rank</th></tr></thead><tbody>
        ${x.evidence.map((e) => `<tr><td>${esc(e.label)}${e.unusual ? ` <span class="warn">unusual</span>` : ""}<small>${esc(e.meaning)}</small></td><td class="r mono">${esc(e.value)}</td><td class="r mono i3">${esc(e.most_metas_now)}</td>
          <td>${effBar(e.effect, maxE)} <small class="${e.reads.startsWith("supports") ? "up" : e.reads.startsWith("weakens") ? "down" : "i3"}">${esc(e.reads)}</small></td></tr>`).join("")}</tbody></table>
        <p class="notes">Single measurements inside a group can point the “wrong” way (for example more buyers lowering the rank) because they overlap with others in the group; read the group total above.</p></div>
      <div class="dsec"><h3>How metas ranked “${esc(r.tier)}” did before</h3>
        <table class="tbl static wrap"><thead><tr><th>Period</th><th class="r">Next coins graduated vs all coins</th><th class="r hide-s">90% range</th><th class="r hide-s">Sample</th></tr></thead><tbody>
        ${c.periods.map((p) => `<tr><td>${esc(p.period)}</td><td class="r mono">${nf(p.ratio, 2)}×</td><td class="r mono hide-s">${nf(p.ci90[0], 2)}–${nf(p.ci90[1], 2)}</td><td class="r hide-s">${compact(p.meta_hours)} meta-hours, ${compact(p.launches)} coins</td></tr>`).join("")}</tbody></table>
        ${c.text.length ? `<p class="notes">${esc(c.text[c.text.length - 1])} For reference, “strongest” vs “weakest”: ${c.periods.map((p) => `${esc(p.period.split(" (")[0])} ${nf(p.strongest, 2)}× vs ${nf(p.weakest, 2)}×`).join("; ")}.</p>` : ""}</div>
      ${hist ? `<div class="dsec"><h3>Its own record<span class="note">while the app was running</span></h3>
        <p class="prose" style="margin:0">${hist.launches} coins using “${esc(m.terms[0])}” have a known 1-hour outcome; ${hist.graduated} graduated (${pct(hist.rate, 1)}), against ${pct(hist.all_rate_24h, 1)} of all coins in the last day.</p>
        <p class="notes">${esc(hist.note)}</p></div>` : ""}
    </details>`;
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
    <header class="prof-head"><div class="cat label">${m.edge ? `<span class="stamp ${{ strongest: "accelerating", weakest: "fading" }[m.edge.tier] || "steady"}">${esc(cap(m.edge.tier))} edge</span><span class="i3" style="margin:0 10px">·</span>` : ""}<span class="i3" style="margin-right:6px">readiness</span>${vst(m.verdict)}<span style="margin-left:auto">keyword cluster</span></div><h2>${esc(m.meta_key)}</h2>
      <p class="dek">${m.explain ? `${esc(m.explain.recommendation.stance)}: ranked #${m.explain.recommendation.rank} of ${m.explain.recommendation.of} metas right now. Interest is ${esc((STATUS[m.explain.happening.status] || STATUS.steady)[0].toLowerCase())}.` : `${esc(cap(m.hype_check))}.`}</p>
      <div class="by"><span>${esc(m.terms.length > 1 ? `matches ${m.terms.join(", ")}` : `${l.launches_6h} launches in 6h`)}</span>${e.merged_by_meaning?.length ? `<span>grouped by meaning: ${esc(e.merged_by_meaning.map(([w]) => w).join(", "))}</span>` : ""}</div></header>
    ${m.explain ? explainHtml(m) : ""}
    <details class="more" id="d-baseline" ${m.explain ? "" : "open"}><summary>The readiness score <span>the older baseline, and its raw evidence</span></summary>
    <div class="verdict">
      <div class="${isProv(m) ? "prov" : ""}"><div class="k">Readiness score <small style="text-transform:none;letter-spacing:0">(baseline)</small></div><div class="big">${isNum(m.score) ? Math.round(m.score) : "—"}<small> / 100</small></div>
        <div class="c">${isProv(m) ? "Provisional. Not a call: confidence is below the bar." : `${vinfo(m.verdict).label}.`}${m.validated ? "" : " The weights have not been validated against outcomes."}</div></div>
      <div><div class="k">Confidence</div><div class="big ${lowConf ? "warn" : ""}">${nf(m.confidence, 2)}</div>${meter(m.confidence, lowConf ? "cau" : "", CONF_BAR)}
        <div class="c" style="margin-top:8px">A call needs ${CONF_BAR}. Coverage ${pct(cf.weight_coverage)}, sample ${nf(cf.sample, 2)}, freshness ${nf(cf.freshness, 2)}, history ${nf(cf.history, 2)}.</div></div>
    </div>
    ${miss.length ? `<div class="missing"><h3>${isProv(m) ? "Not enough evidence for a call" : "Missing evidence lowers confidence"}</h3><ul class="cov">
      ${cov.map(([name, have, ht, mt]) => `<li class="${have ? "have" : "miss"}"><span class="g">${have ? "●" : "○"}</span><span>${esc(name)}</span><em>${esc(have ? ht : mt)}</em></li>`).join("")}</ul></div>` : ""}
    <div class="dsec"><h3>Evidence for</h3>${m.reasons.length ? `<ul class="ev pos">${m.reasons.map((r) => `<li><span class="g">●</span><span>${esc(r)}</span></li>`).join("")}</ul>` : `<p class="dek2">No strong positive signal.</p>`}</div>
    <div class="dsec"><h3>Buying activity<span class="note">last hour, per-token sums</span></h3>
      <div class="facts">
        <div><div class="k">Buyers</div><div class="v">${compact(d.unique_buyers_h1_sum)}</div></div><div><div class="k">Sellers</div><div class="v">${compact(d.unique_sellers_h1_sum)}</div></div>
        <div><div class="k">Buyer share</div><div class="v ${d.buyer_share_h1 >= 0.55 ? "up" : d.buyer_share_h1 < 0.45 ? "down" : ""}">${pct(d.buyer_share_h1)}</div></div>
        <div><div class="k">Volume</div><div class="v">${usd(d.vol_h1_usd)}</div></div>
        <div><div class="k">Net SOL into curves</div><div class="v ${isNum(d.curve_net_sol_1h) ? (d.curve_net_sol_1h >= 0 ? "up" : "down") : ""}">${isNum(d.curve_net_sol_1h) ? signed(d.curve_net_sol_1h, 1) : "—"}</div></div>
        <div><div class="k">Graduated, 24h</div><div class="v">${d.graduations_24h}</div></div></div>
      <div class="slug thin" style="margin-top:20px"><h3 class="h3">Launches per hour</h3><span class="note">last 12 hours</span></div><div class="chart" id="d-launch"></div>
      <p class="notes">${d.tokens_tracked} tokens with fresh stats. Top token holds ${pct(d.top_token_share_vol24)} of 24-hour volume. Net USD flow ${isNum(d.net_flow_usd_h1) ? usd(d.net_flow_usd_h1) : "needs Bitquery"}.</p></div>
    <div class="dsec"><h3>Saturation<span class="note">${isNum(sat.index) ? `index ${nf(sat.index, 2)}, 1 = crowded` : "not enough data"}</span></h3>
      ${Object.entries(sat.signals).map(([k, v]) => `<div class="sig"><span>${esc(cap(k.replaceAll("_", " ")))}</span>${meter(v.s, v.s >= 0.6 ? "cau" : "")}<span class="mono" style="text-align:right;font-size:12px">${nf(v.s, 2)}</span><span class="why">${esc(cap(v.why))}</span></div>`).join("")
        || `<p class="dek2">No saturation signal has enough data yet.</p>`}
      <p class="notes">Reused tickers ${pct(l.duplicate_symbol_share_6h)}. Serial deployers ${isNum(e.creators?.serial_share) ? pct(e.creators.serial_share) : "unknown"}. Paid DexScreener promotion: ${e.attention_purchased?.boosts_24h ?? 0} boosted, ${e.attention_purchased?.profiles_24h ?? 0} profiled.</p></div>
    <div class="dsec"><h3>Risks</h3><ul class="ev cau">${m.risks.map((r) => `<li><span class="g">▲</span><span>${esc(r)}</span></li>`).join("")}</ul></div>
    <div class="dsec"><h3>Score breakdown<span class="note">${pct(cf.weight_coverage)} of the weight has data</span></h3>
      <div class="bd">${comp("attention", "Attention")}<span class="parts">${parts(m.component_parts.attention)}</span>${comp("demand", "Demand")}<span class="parts">${parts(m.component_parts.demand)}</span>${comp("market", "Market")}${comp("freshness", "Freshness")}</div></div>
    <div class="dsec"><h3>Score history<span class="note">last 48 hours</span></h3><div class="chart" id="d-hist"><div class="chart-empty">Loading…</div></div></div>
    <div class="dsec"><h3>Social</h3>${cf.social_measured ? `<p class="notes" style="margin:0 0 8px">${s.mentions_1h} mentions in the last hour, ${s.mentions_6h} in 6 hours, from ${s.independent_authors_6h} independent accounts. ${s.copy_paste_posts_6h} copy-paste posts. Sentiment ${isNum(s.sentiment_6h) ? nf(s.sentiment_6h, 2) : "—"} on a −1 to 1 scale.</p>
      <div class="posts">${(s.influential_posts || []).map((p) => `<div class="post"><div class="by">@${esc(p.author || "?")} · ${compact(p.followers)} followers · ${compact(p.engagement)} engagement · <a href="${esc(/^https:\/\//.test(p.url) ? p.url : "#")}" target="_blank" rel="noopener noreferrer">open</a></div>${esc(p.text)}</div>`).join("")}</div>`
      : `<p class="dek2">Not measured. No X or Reddit source is connected, so attention comes from launch names alone.</p>`}</div>
    <div class="dsec"><h3>Top tokens</h3>
      <table class="tbl"><thead><tr><th>Token</th><th class="r">Vol 1h</th><th>Buy/sell</th><th>Curve</th></tr></thead><tbody>
      ${toks.map((t, i) => `<tr data-dt="${i}"><td>${tk(t.symbol || short(t.mint), `${t.name || ""}${isNum(t.age_h) ? `, ${age(t.age_h)} old` : ""}`)}</td><td class="r">${usd(t.vol_h1)}</td>
        <td>${bsr(t.buyers_h1, t.sellers_h1)}</td><td>${t.graduated ? ruler(1, true) : ruler(t.progress)}</td></tr>`).join("") || `<tr><td colspan="4" class="i3">No token in this cluster has fresh stats.</td></tr>`}</tbody></table></div>
    </details>
    <p class="attr">Computed ${esc(dayhm(S.ov.as_of))} by model ${esc(S.ov.model_version)}${S.ov.edge_model ? ` and ranked by ${esc(S.ov.edge_model)}` : ""}. Sources: ${esc(srcs.join("; "))}.</p>`;
}
async function bindDossier(root, m) {
  const l = m.evidence.launch, to = S.ov.as_of, hr = Math.floor(to / 3600) * 3600;
  $$("tr[data-dt]", root).forEach((r) => r.addEventListener("click", () => openToken(m.evidence.demand.top_tokens[+r.dataset.dt].mint)));
  const bars = (el) => el && Charts.timeBars(el, { data: l.launch_hourly_12h.map((v, i) => [hr - (11 - i) * 3600, v]), from: hr - 11 * 3600, to: hr + 3600, step: 3600,
    height: 100, fmtY: (v) => compact(v, 0), unit: "launches", label: "Launches per hour" });
  bars($("#x-launch", root));
  $$("[data-nar]", root).forEach((b) => b.addEventListener("click", () => {
    const n = (S.nar?.narratives || []).find((x) => x.label === b.dataset.nar);
    if (n) openNarrative(n); else toast("Open the atlas to see this narrative");
  }));
  const base = $("#d-baseline", root);
  if (base && !base.open) { base.addEventListener("toggle", () => { if (base.open) { bars($("#d-launch", root)); drawHist(); } }, { once: true }); }
  else bars($("#d-launch", root));
  const drawHist = async () => { try {
    const h = await api(`/api/metas/${encodeURIComponent(m.meta_key)}/history?hours=48`);
    const el = $("#d-hist", root);
    if (el) Charts.timeLine(el, { data: h.filter((r) => isNum(r.score)).map((r) => [r.computed_at, r.score]), yMin: 0, yMax: 100, height: 130,
      fmtY: (v) => nf(v, 0), refs: [{ v: 65, label: "favorable from 65" }, { v: 45, label: "mixed from 45" }], label: "Score history" });
  } catch (_) { const el = $("#d-hist", root); if (el) el.innerHTML = `<div class="chart-empty">Score history is unavailable.</div>`; } };
  if (!base || base.open) drawHist();
}
function openMetaSheet(m) { openSheet("Keyword cluster", esc(m.meta_key), dossierHtml(m), (root) => bindDossier(root, m)); }

// ---------------------------------------------------------------- sheet
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

// ---------------------------------------------------------------- launch window (radar/early.py)
// The first minutes of a token born while the app listened on chain, and the fitted model's read of them.
function launchHtml(t) {
  const rows = (t.launch_window || []).filter((r) => r.age_s !== 900), card = t.launch_model;
  if (!rows.length) return "";
  const r = rows[rows.length - 1], f = r.features || {}, cr = f.creator || {};
  const when = r.age_s >= 60 ? `${r.age_s / 60} min` : `${r.age_s} s`;
  const lift = isNum(r.p_grad) && f.base_rate > 0 ? r.p_grad / f.base_rate : null;
  const wf = card?.walk_forward?.["eligible/grad_1h"];
  const li = (k, v, c = "", cls = "") => `<div class="li"><span class="k">${esc(k)}</span><span class="v ${cls}">${v}</span>${c ? `<span class="c">${esc(c)}</span>` : ""}</div>`;
  const head = isNum(r.p_grad)
    ? `<div class="facts"><div><div class="k">Chance it graduates within 1 hour</div><div class="v">${pct(r.p_grad, r.p_grad < 0.1 ? 1 : 0)}</div></div>
       <div><div class="k">Against the current base rate</div><div class="v ${lift >= 2 ? "up" : lift < 0.5 ? "down" : ""}">${isNum(lift) ? `${nf(lift, lift < 10 ? 1 : 0)}×` : "—"}<small>base ${pct(f.base_rate, 2)}</small></div></div></div>
       <p class="notes">${r.calibrated ? "Probability on the live cohort’s base rate." : `Ranking only: the live base rate rests on ${f.base_n ?? 0} matured launches, below the ${card?.min_base_n ?? 2000} needed to read this as a probability.`}
       ${wf ? ` In walk-forward tests on ${esc(card.trained_on?.from || "")} to ${esc(card.trained_on?.to || "")} it ranked graduates above non-graduates ${pct(wf.auc_within_day, 0)} of the time within a day (cohort base rate alone: ${pct(wf.base_auc_within_day, 0)}).` : ""}
       Graduation is not profit.</p>`
    : `<p class="dek2">No fitted model is installed, so only the measurements are shown.</p>`;
  return `<div class="dsec"><h3>Launch window<span class="note">first ${esc(when)}, read ${esc(ago(t.now - r.observed_at))}</span></h3>${head}
    <div class="ledger">${li("Unique buyers", f.uniq_buyers ?? "—", `${f.n_trades ?? "—"} trades, ${f.uniq_sellers ?? "—"} sellers`)}
      ${li("Proven wallets", f.proven_buyers ?? "—", "bought early into earlier graduates", f.proven_buyers ? "up" : "")}
      ${li("Serial buyers", isNum(f.serial_share) ? pct(f.serial_share) : "—", "first-bought 10+ tokens in the past hour")}
      ${li("Snipers", f.snipers ?? "—", "bought within 3 seconds", f.snipers >= 3 ? "down" : "")}
      ${li("Price vs launch", isNum(f.mcap_ratio) ? `${nf(f.mcap_ratio, 2)}×` : "—")}
      ${li("Creator sold", f.creator_sold ? "Yes" : "No", "", f.creator_sold ? "down" : "")}
      ${li("Creator’s earlier launches", cr.prior ?? "—", isNum(cr.grads) ? `${cr.grads} graduated` : "")}
      ${f.meta_term ? li(`Meta “${f.meta_term}”`, `${f.m_launch_1h ?? 0}<small> launches 1h</small>`, f.m_hist_n ? `${f.m_hist_grad} of ${f.m_hist_n} graduated in 7 days` : "no matured history yet") : ""}</div></div>`;
}

// ---------------------------------------------------------------- token dossier
let tokState = { mint: null, metric: "mcap", hours: 24 };
async function openToken(mint) {
  tokState = { ...tokState, mint };
  if (!$("#sheet").classList.contains("on")) openSheet("Token", "", `<div class="sk title"></div><div class="sk" style="height:180px;margin-top:16px"></div>`);
  else { $("#sheet-body").scrollTop = 0; }
  let t;
  try { t = await api(`/api/tokens/${encodeURIComponent(mint)}?hours=${tokState.hours}`); }
  catch (e) { $("#sheet-title").textContent = "Token"; $("#sheet-body").innerHTML = `<div class="empty"><h3>Couldn’t load this token</h3><p>${esc(cap(e.message))}.</p></div>`; return; }
  if (tokState.mint !== mint) return;
  const k = t.token, last = t.observations[t.observations.length - 1] || {}, curve = t.curve[t.curve.length - 1];
  const ageH = k.created_at ? (t.now - k.created_at) / 3600 : null, graduated = !!t.graduation || !!curve?.complete;
  const flags = tokenFlags({ ...last, created_at: k.created_at, graduated, deployer_launches_24h: t.deployer?.launches_seen_24h }, t.now);
  if (!t.observations.length) flags.push(["", "No trading observations in this range"]);
  const out = t.outcomes.map((o) => `<tr><td class="n">${o.horizon_h}h</td><td>${o.graduated ? "Graduated" : esc(cap(o.bucket || "—"))}</td><td class="r">${isNum(o.ret_end) ? signed(o.ret_end * 100, 0, "%") : "—"}</td><td class="r">${isNum(o.ret_max) ? signed(o.ret_max * 100, 0, "%") : "—"}</td></tr>`).join("");
  $("#sheet-title").textContent = "Token dossier";
  $("#sheet-sub").textContent = `${isNum(ageH) ? `launched ${age(ageH)} ago` : "launch time unknown"}${graduated ? " · graduated" : ""}`;
  const root = $("#sheet-body");
  const fact = (kk, v, cls = "") => `<div><div class="k">${esc(kk)}</div><div class="v ${cls}">${v}</div></div>`;
  root.innerHTML = `
    <header class="prof-head"><div class="cat label"><span>${graduated ? "Graduated to PumpSwap" : curve ? `On the curve · ${pct(curve.progress)}` : "Curve not read"}</span><span style="margin-left:auto">${graduated ? ruler(1, true) : curve ? ruler(curve.progress) : ""}</span></div>
      <h2>${esc(k.symbol ? "$" + k.symbol : short(k.mint))}</h2><p class="dek">${esc(k.name || "")}</p>
      <div class="addr" style="margin-top:12px"><span>${esc(k.mint)}</span><button class="btn ghost" id="copy">Copy</button></div>
      <div class="links"><a href="https://pump.fun/coin/${encodeURIComponent(k.mint)}" target="_blank" rel="noopener noreferrer">pump.fun</a>
        <a href="https://dexscreener.com/solana/${encodeURIComponent(k.mint)}" target="_blank" rel="noopener noreferrer">DexScreener</a>
        <a href="https://solscan.io/token/${encodeURIComponent(k.mint)}" target="_blank" rel="noopener noreferrer">Solscan</a></div></header>
    ${aboutHtml(k, t.same_x_post_24h)}
    <div class="dsec"><h3>Now<span class="note">${last.observed_at ? `observed ${esc(ago(t.now - last.observed_at))}` : "no recent observation"}</span></h3>
      <div class="facts">${fact("Market cap", usd(last.mcap_usd))}${fact("Liquidity", usd(last.liquidity_usd))}${fact("Volume 1h", usd(last.vol_h1))}
        ${fact("Volume 24h", usd(last.vol_h24))}${fact("Buyers / sellers 1h", `${last.buyers_h1 ?? "—"}<small>/ ${last.sellers_h1 ?? "—"}</small>`)}
        ${isNum(last.smart_buyers_h1) ? `${fact("Proven wallets 1h", last.smart_buyers_h1, last.smart_buyers_h1 ? "up" : "")}${fact("Buyers not bots 1h", last.organic_buyers_h1 ?? "—")}
        ${fact("Net SOL 1h", signed(last.net_sol_h1, 1), last.net_sol_h1 > 0 ? "up" : last.net_sol_h1 < 0 ? "down" : "")}${fact("Creator sold", isNum(last.dev_sold_sol) ? nf(last.dev_sold_sol, 2) + "<small>SOL</small>" : "—", last.dev_sold_sol >= 0.5 ? "down" : "")}
        ${fact("Smart / insider 1h", `${last.labelled_buyers_h1 ?? "—"}<small>/ ${last.insider_buyers_h1 ?? "—"}</small>`)}${fact("Launch-block wallets", `${last.launch_block_buyers ?? "—"}${isNum(last.launch_block_pct) ? `<small>${pct(last.launch_block_pct, 1)} supply</small>` : ""}`, last.launch_block_buyers >= 3 ? "down" : "")}
        ${fact("Top 10 / creator hold", `${isNum(last.top10_pct) ? pct(last.top10_pct) : "—"}<small>/ ${isNum(last.dev_holds_pct) ? pct(last.dev_holds_pct, 1) : "—"}</small>`)}` : ""}</div>
      ${last.sol_paired === 0 ? `<p class="notes">Paired with a token other than SOL: SOL and USD figures are left out.</p>` : ""}</div>
    ${launchHtml(t)}
    <div class="dsec"><h3>Risk flags</h3>${flags.length ? `<ul class="ev cau">${flags.map(([c, f]) => `<li><span class="g" style="color:var(--${c === "neg" ? "sell" : "caution"})">▲</span><span>${esc(f)}</span></li>`).join("")}</ul>`
      : `<p class="dek2">None of the automatic checks fired. They do not detect every rug, bundle or insider wallet.</p>`}</div>
    <div class="dsec"><div style="display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin-bottom:8px">${seg("Metric", [["mcap", "Market cap"], ["buyers", "Buyers/h"], ["curve", "Curve"]], tokState.metric, "data-m")}
      <span style="margin-left:auto">${seg("Range", [[6, "6H"], [24, "24H"], [72, "3D"]], tokState.hours, "data-h")}</span></div><div class="chart" id="tchart"></div></div>
    <div class="dsec"><h3>Creator<span class="note">${t.deployer ? esc(short(t.deployer.wallet)) : "unknown"}</span></h3>
      ${t.deployer ? `<div class="ledger"><div class="li"><span class="k">Launches we saw in 24 hours</span><span class="v ${t.deployer.launches_seen_24h >= 3 ? "down" : ""}">${t.deployer.launches_seen_24h}</span></div>
        ${t.deployer.label ? `<div class="li"><span class="k">Dataset label</span><span class="v ${t.deployer.label === "insider" ? "down" : ""}">${t.deployer.label === "insider" ? "Insider" : "Smart money"}</span><span class="c">public wallet labels, June 2026</span></div>` : ""}
        ${t.deployer.activity ? `<div class="li"><span class="k">SOL balance</span><span class="v">${isNum(t.deployer.activity.sol_balance) ? nf(t.deployer.activity.sol_balance, 2) : "—"}</span></div>` : ""}</div>`
        : `<p class="dek2">This token launched before the app started listening, so its creator wasn't seen.</p>`}</div>
    ${out ? `<div class="dsec"><h3>Outcomes<span class="note">measured after launch</span></h3><table class="tbl static"><thead><tr><th>Horizon</th><th>Result</th><th class="r">Return</th><th class="r">Peak</th></tr></thead><tbody>${out}</tbody></table>
      <p class="notes">Return runs from the first observed candle and ignores fees. Graduation and profit are separate outcomes.</p></div>` : ""}
    <p class="attr">Trading stats: live chain stream, ${t.observations.length} snapshots in range${t.pool?.length ? `; ${t.pool.length} PumpSwap pool readings after graduation` : ""}. Curve: Solana RPC account state${curve ? `, read ${esc(ago(t.now - curve.observed_at))}` : ", not read"}.${t.attention.length ? ` Paid DexScreener ${esc(t.attention[0].kind)} seen.` : ""}</p>`;
  $("#copy", root).addEventListener("click", async () => { try { await navigator.clipboard.writeText(k.mint); toast("Address copied"); } catch (_) { toast("Copying isn’t allowed here"); } });
  const draw = () => {
    const first = Math.min(...[k.created_at, t.observations[0]?.observed_at, t.curve[0]?.observed_at].filter(isNum));
    const el = $("#tchart", root), from = Math.max(t.now - tokState.hours * 3600, isFinite(first) ? first - 120 : 0);
    if (tokState.metric === "curve") return Charts.timeLine(el, { data: t.curve.map((c) => [c.observed_at, (c.complete ? 1 : c.progress) * 100]), from, to: t.now, yMin: 0, yMax: 100, fmtY: (v) => nf(v, 0) + "%", label: "Curve progress" });
    if (tokState.metric === "buyers") return Charts.timeLine(el, { data: t.observations.filter((o) => isNum(o.buyers_h1)).map((o) => [o.observed_at, o.buyers_h1]), from, to: t.now, cls: "dem", fmtY: (v) => compact(v, 0), label: "Unique buyers per hour" });
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
  if (!k.description && !links.length) return k.meta_status === "failed" ? `<div class="dsec"><h3>About</h3><p class="dek2">Its metadata file couldn’t be fetched.</p></div>` : "";
  return `<div class="dsec"><h3>About<span class="note">from the creator; unverified</span></h3>
    ${k.description ? `<p class="prose" style="margin:0 0 10px">${esc(k.description)}</p>` : ""}
    ${links.length ? `<div class="links">${links.map(([u, l]) => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer nofollow">${esc(l)}</a>`).join("")}</div>` : ""}
    ${same && same.n > 1 ? `<p class="notes">${same.n} launches by ${same.c} creator${same.c === 1 ? "" : "s"} linked this same X post in the last 24 hours.</p>` : ""}</div>`;
}

// ================================================================ TOKENS
const TCOLS = [
  ["sym", "Token", "", (t) => (t.symbol || "").toLowerCase()], ["age", "Age", "r hide-s", (t) => -(t.created_at || 0)], ["mcap_usd", "Mkt cap", "r", (t) => t.mcap_usd],
  ["liquidity_usd", "Liquidity", "r hide-m", (t) => t.liquidity_usd], ["vol_h1", "Vol 1h", "r", (t) => t.vol_h1], ["vol_h24", "Vol 24h", "r hide-m", (t) => t.vol_h24],
  ["buyers_h1", "Buy/sell 1h", "hide-s", (t) => t.buyers_h1], ["chg_h1", "Chg 1h", "r hide-s", (t) => t.chg_h1],
  ["progress", "Curve", "hide-s", (t) => (t.graduated ? 2 : t.progress)], ["flags", "Flags", "hide-m", (t) => tokenFlags(t).length],
];
function renderTokens() {
  const el = $(".screen[data-screen=tokens]"), all = S.tokens?.tokens || [], T = S.tok, now = nowS();
  const grads = all.filter((t) => t.graduated).length, flagged = all.filter((t) => tokenFlags(t, now).length).length;
  setHead(`${plural(all.length, "token")} <em>trading</em>`, `Every token with trading stats from the last two hours: ${grads} graduated, ${flagged} carrying a risk flag. Select a row for its dossier.`, "", "Listings");
  const q = T.q.trim().toLowerCase();
  const filt = { all: () => true, curve: (t) => !t.graduated, grad: (t) => !!t.graduated, flagged: (t) => tokenFlags(t, now).length > 0 };
  const counts = Object.fromEntries(Object.keys(filt).map((k) => [k, all.filter(filt[k]).length]));
  const col = TCOLS.find((c) => c[0] === T.key) || TCOLS[4];
  const list = all.filter(filt[T.filter]).filter((t) => !q || `${t.symbol} ${t.name} ${t.mint}`.toLowerCase().includes(q))
    .sort((a, b) => { const va = col[3](a), vb = col[3](b); if (va == null) return 1; if (vb == null) return -1; return (va > vb ? 1 : va < vb ? -1 : 0) * T.dir; });
  const focused = document.activeElement?.id === "tq";
  el.innerHTML = `
    <div class="tok-tools"><label class="sr" for="tq">Search tokens</label><input id="tq" type="search" placeholder="Ticker, name or address" value="${esc(T.q)}" autocomplete="off" spellcheck="false">
      <div class="filters" role="group" aria-label="Filter">${[["all", "All"], ["curve", "On the curve"], ["grad", "Graduated"], ["flagged", "Flagged"]]
        .map(([v, l]) => `<button class="fil" data-tf="${v}" aria-pressed="${T.filter === v}">${l}<sup>${counts[v]}</sup></button>`).join("")}</div>
      <span class="end">${list.length} shown</span></div>
    <table class="tbl tokentbl"><thead><tr>${TCOLS.map(([k, l, c]) => `<th class="${c}" ${T.key === k ? `aria-sort="${T.dir < 0 ? "descending" : "ascending"}"` : ""}><button data-sort="${k}">${l}</button></th>`).join("")}</tr></thead>
      <tbody id="trows">${list.map((t, i) => {
        const ageH = t.created_at ? (now - t.created_at) / 3600 : null;
        const fl = tokenFlags(t, now);
        const bad = fl.filter((x) => x[0] === "neg").map((x) => x[1].toLowerCase()), quiet = fl.filter((x) => x[0] !== "neg").map((x) => x[1].toLowerCase());
        return `<tr data-i="${i}"><td>${tk(t.symbol || short(t.mint), t.name, fl.length ? `<span class="show-s">${bad.length ? `<span class="down">▲ ${esc(bad.join(", "))}</span>${quiet.length ? " · " : ""}` : ""}<span class="i3">${esc(quiet.join(", "))}</span></span>` : "")}</td>
          <td class="r hide-s">${t.graduated && !isNum(ageH) ? "—" : esc(age(ageH))}</td><td class="r">${usd(t.mcap_usd)}</td><td class="r hide-m">${usd(t.liquidity_usd)}</td>
          <td class="r">${usd(t.vol_h1)}</td><td class="r hide-m">${usd(t.vol_h24)}</td><td class="hide-s">${bsr(t.buyers_h1, t.sellers_h1)}</td>
          <td class="r hide-s ${t.chg_h1 > 0 ? "up" : t.chg_h1 < 0 ? "down" : ""}">${isNum(t.chg_h1) ? signed(t.chg_h1, 0, "%") : "—"}</td>
          <td class="hide-s">${curveCell(t)}</td><td class="hide-m">${flagsHtml(fl)}</td></tr>`;
      }).join("") || `<tr><td colspan="10"><div class="chart-empty">${all.length ? "No token matches these filters." : "Tokens appear once their trading stats are refreshed, every two minutes."}</div></td></tr>`}</tbody></table>`;
  const inp = $("#tq");
  if (focused) { inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }
  inp.addEventListener("input", () => { T.q = inp.value; renderTokens(); });
  $$("[data-tf]", el).forEach((b) => b.addEventListener("click", () => { T.filter = b.dataset.tf; renderTokens(); }));
  $$("[data-sort]", el).forEach((b) => b.addEventListener("click", () => { const k = b.dataset.sort; T.dir = T.key === k ? -T.dir : (k === "sym" ? 1 : -1); T.key = k; renderTokens(); }));
  $$("#trows tr[data-i]", el).forEach((r) => r.addEventListener("click", () => openToken(list[+r.dataset.i].mint)));
}

// ================================================================ ANALYST
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
  setHead("The analyst’s <em>desk</em>", ai ? `Claude (${esc(S.ov.config.analyst_model)}) writes from the evidence pack and may only cite its numbers.` : "The rules analyst writes from the same evidence pack as Claude would. Add a Claude key in settings for written analysis.",
    `<button class="btn solid" id="write">Write a new report</button>`, "Reports & evidence");
  $("#write").addEventListener("click", writeReport);
  if (!S.reports) {
    el.innerHTML = `<div class="desk"><div><div class="sk title"></div><div class="sk line"></div><div class="sk line" style="width:80%"></div><div class="sk line" style="width:90%"></div></div><div class="sk" style="height:300px"></div></div>`;
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
    ["Verdict", (m) => vst(m.verdict)], ["Readiness score", (m) => `<span class="mono ${isProv(m) ? "i3" : ""}">${isNum(m.score) ? Math.round(m.score) : "—"}</span>`],
    ["Confidence", (m) => `<span class="mono ${m.confidence < CONF_BAR ? "warn" : ""}">${nf(m.confidence, 2)}</span>`],
    ["Launches 1h / 6h", (m) => `<span class="mono">${m.evidence.launch.launches_1h} / ${m.evidence.launch.launches_6h}</span>`], ["Buyers per hour", (m) => `<span class="mono">${compact(m.evidence.demand.unique_buyers_h1_sum)}</span>`],
    ["Buyer share", (m) => `<span class="mono">${pct(m.evidence.demand.buyer_share_h1)}</span>`], ["Net SOL into curves 1h", (m) => `<span class="mono">${isNum(m.evidence.demand.curve_net_sol_1h) ? signed(m.evidence.demand.curve_net_sol_1h, 1) : "—"}</span>`],
    ["Graduated 24h", (m) => `<span class="mono">${m.evidence.demand.graduations_24h}</span>`], ["Top token share", (m) => `<span class="mono">${pct(m.evidence.demand.top_token_share_vol24)}</span>`],
    ["Crowding", (m) => `<span class="mono">${isNum(m.evidence.saturation.index) ? nf(m.evidence.saturation.index, 2) : "—"}</span>`], ["Reused tickers", (m) => `<span class="mono">${pct(m.evidence.launch.duplicate_symbol_share_6h)}</span>`],
    ["Hype check", (m) => `<span class="i2" style="font:italic 13px var(--serif)">${esc(cap(m.hype_check))}</span>`],
  ];
  el.innerHTML = `<div class="desk">
    <article>
      <div class="repmeta">${S.reports.length ? `<label class="sr" for="rep">Report</label><select id="rep">${S.reports.map((r) => `<option value="${r.id}" ${R?.id === r.id ? "selected" : ""}>${esc(dayhm(r.created_at))}, ${esc(r.kind.replace("_", " "))}</option>`).join("")}</select>
        <span>Written by ${esc(R?.analyst || "—")}</span>` : "<span>No reports yet</span>"}</div>
      ${R?.error ? `<div class="empty"><h3>Couldn’t load the report</h3><p>${esc(cap(R.error))}.</p></div>` : R?.body ? `<div class="report">${md(R.body)}</div>`
        : `<div class="empty"><h3>No report yet</h3><p>Reports are written at the scheduled times, or now with “Write a new report”.</p></div>`}
    </article>
    <aside>
      ${slug("Compare clusters", "up to three")}
      <div class="filters" style="margin-bottom:12px">${metas.slice(0, 12).map((m) => `<button class="fil" data-c="${esc(m.meta_key)}" aria-pressed="${S.cmp.includes(m.meta_key)}">${esc(m.meta_key)}</button>`).join("")}</div>
      ${chosen.length ? `<table class="tbl static cmp"><thead><tr><th></th>${chosen.map((m) => `<th class="nm">${esc(m.meta_key)}</th>`).join("")}</tr></thead>
        <tbody>${rowsDef.map(([k, f]) => `<tr><td class="k">${k}</td>${chosen.map((m) => `<td>${f(m)}</td>`).join("")}</tr>`).join("")}</tbody></table>
        <p class="notes">Figures from the analysis of ${esc(hhmm(S.ov.as_of))}, the same evidence the analyst reads. Buyer counts are per-token sums.</p>`
        : `<p class="dek2">Choose clusters above to compare their evidence side by side.</p>`}
      ${S.nar?.narratives?.length ? `<div class="sect">${slug("Narratives in play", "by meaning, most bought", `<button class="linkbtn" data-goto="metas">Atlas →</button>`)}
        <div class="ranks">${narByBuyers().slice(0, 6).map((n, i) => `<button class="rank" data-nar="${esc(n.label)}"><span class="n">${String(i + 1).padStart(2, "0")}</span><span class="t">${esc(n.title)}<small>${esc(catLabel(n.category))} · ${esc(Viz.STAGE_LABEL[n.state] || n.state)}</small></span><span class="s">${n.popularity.launches_6h}<small>launches</small></span><span class="b">${compact(n.traction.buyers_h1)}<small>buyers/h</small></span></button>`).join("")}</div></div>` : ""}
    </aside></div>`;
  const sel = $("#rep");
  if (sel) sel.addEventListener("change", async () => { try { S.report = await api(`/api/reports/${sel.value}`); } catch (e) { S.report = { error: e.message }; } renderAnalyst(); });
  $$("[data-c]", el).forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.c;
    S.cmp = S.cmp.includes(k) ? S.cmp.filter((x) => x !== k) : [...S.cmp, k].slice(-3);
    renderAnalyst();
  }));
  $$("[data-nar]", el).forEach((b) => b.addEventListener("click", () => { const n = S.nar.narratives.find((x) => x.label === b.dataset.nar); if (n) openNarrative(n); }));
  $$("[data-goto]", el).forEach((b) => b.addEventListener("click", () => { S.metaView = "narratives"; go(b.dataset.goto); }));
}
async function writeReport(e) {
  const b = e.currentTarget; b.disabled = true; b.textContent = S.ov.config.anthropic_analyst ? "Writing, up to a minute" : "Writing";
  try { const r = await api("/api/reports", { method: "POST" }); S.reports = null; toast("Report written"); S.report = { id: r.id }; }
  catch (err) { toast(`Report failed: ${err.message}`); }
  if (S.tab === "analyst") renderAnalyst();
}

// ================================================================ SYSTEM
const SRC_NAMES = { "chain/pump_stream": "Live chain stream", "chain/snapshot": "Token stats from the stream",
  "chain/pumpswap_pools": "PumpSwap pools after graduation", "defillama/sol_price": "SOL price", "dexscreener/boosts_profiles": "Paid promotion",
  "defillama/launchpad_volume": "Launchpad volume", "x_api/recent_search": "X posts", "reddit/new_posts": "Reddit posts",
  "pumpfun/latest_coins": "pump.fun API", "bitquery/net_flow": "Net flow (Bitquery)", "outcomes/label": "Outcome labelling" };
const SRC_STATE = { fresh: ["accelerating", "Fresh"], degraded: ["heating", "Degraded"], stale: ["heating", "Stale"], expired: ["fading", "Expired"],
  unavailable: ["fading", "Unavailable"], error: ["fading", "Error"], skipped: ["steady", "Not configured"] };
const srcStamp = (s) => { const x = SRC_STATE[s] || ["steady", s]; return `<span class="stamp ${x[0]}">${Viz.GLYPH[x[0]]}${esc(x[1])}</span>`; };
async function renderSystem() {
  const el = $(".screen[data-screen=system]"), ov = S.ov, L = liveState(), b = baseline();
  const SEV = { error: 0, unavailable: 0, expired: 1, stale: 2, degraded: 2, skipped: 3, fresh: 4 };
  const f = Object.values(ov.freshness).sort((a, c) => (SEV[a.state] ?? 2) - (SEV[c.state] ?? 2)
    || (SRC_NAMES[`${a.source}/${a.job}`] || "").localeCompare(SRC_NAMES[`${c.source}/${c.job}`] || ""));
  const failing = f.filter((x) => (SEV[x.state] ?? 2) <= 1).length;
  setHead(failing ? `${plural(failing, "source")} <em>failing</em>` : L.cls === "ok" ? "All collectors <em>running</em>" : `Collection is <em>${esc(L.text.toLowerCase())}</em>`,
    "Collection health, data freshness, history and display settings. Problems are listed first.", "", "Colophon");
  const up = S.charts[S.range]?.uptime_1h || {};
  const hourNow = Math.floor(nowS() / 3600) * 3600;
  const freshN = f.filter((x) => x.state === "fresh").length;
  const rows = f.map((x) => {
    const k = `${x.source}/${x.job}`, cells = new Map((up[k] || []).map((c) => [c[0], c]));
    const strip = Array.from({ length: 24 }, (_, i) => {
      const hb = hourNow - (23 - i) * 3600, c = cells.get(hb);
      if (!c) return `<i title="${esc(hhmm(hb))}: no runs"></i>`;
      const cls = c[3] && !c[1] && !c[2] ? "skip" : c[2] && !c[1] ? "bad" : c[2] ? "mix" : "ok";
      return `<i class="${cls}" title="${esc(hhmm(hb))}: ${c[1]} ok, ${c[2]} failed"></i>`;
    }).join("");
    return `<tr><td><div style="font:400 19px/1 var(--display);letter-spacing:.03em;text-transform:uppercase">${esc(SRC_NAMES[k] || k)}</div><div class="i3 mono" style="font-size:10.5px;margin-top:3px">${esc(k)}</div></td><td>${srcStamp(x.state)}</td>
      <td class="r">${esc(x.last_ok ? ago(nowS() - x.last_ok) : "never")}</td><td class="r hide-s">${esc(Math.round(x.expected_every_s / 60))} min</td>
      <td class="hide-s"><div class="strip" aria-label="runs in the last 24 hours">${strip}</div></td>
      <td class="hide-m"><span class="errtxt">${x.last_error && x.state !== "fresh" ? esc(x.last_error) : ""}</span></td></tr>`;
  }).join("");
  const h = ov.context.history || {}, cfg = ov.config, bt = ov.backtest, db = ov.db;
  const yes = (v) => (v ? `<span class="stamp accelerating">${Viz.GLYPH.bought}On</span>` : `<span class="stamp steady">${Viz.GLYPH.steady}Off</span>`);
  const pref = Perf.pref(), sig = Perf.signals();
  el.innerHTML = `
    <div class="sys-top">
      <div><div class="k">Collection</div><div class="v ${L.cls === "ok" ? "up" : L.cls === "stale" ? "warn" : "down"}">${esc(L.text)}</div><div class="c">last analysis ${esc(ago(L.lag))}</div></div>
      <div><div class="k">Sources fresh</div><div class="v">${freshN}<small> / ${f.length}</small></div><div class="c">${f.filter((x) => x.state === "skipped").length} not configured</div></div>
      <div><div class="k">Baseline history</div><div class="v">${esc(b.label)}<small> / ~${b.need}h</small></div><div class="c">${b.ready ? "acceleration is being scored" : "calls are held until this completes"}</div></div>
      <div><div class="k">Launch coverage, 6h</div><div class="v">${pct(h.launch_coverage_6h)}</div><div class="c">share of launches the collector saw</div></div>
    </div>
    <div class="sect">${slug("Data sources", "runs per hour, last 24 hours: ink ran, red failed, hatched mixed")}
      <table class="tbl static"><thead><tr><th>Source</th><th>Status</th><th class="r">Last success</th><th class="r hide-s">Cadence</th><th class="hide-s">Last 24 hours</th><th class="hide-m">Last error</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="6" class="i3">No collection runs yet.</td></tr>`}</tbody></table></div>
    <div class="sect three">
      <div>${slug("Stored history", "", "", "thin")}<div class="ledger">
        <div class="li"><span class="k">Tokens tracked</span><span class="v">${compact(db.tokens)}</span></div><div class="li"><span class="k">Trading observations</span><span class="v">${compact(db.token_obs)}</span></div>
        <div class="li"><span class="k">Bonding-curve reads</span><span class="v">${compact(db.curve_obs)}</span></div><div class="li"><span class="k">Graduations seen</span><span class="v">${compact(db.graduations)}</span></div>
        <div class="li"><span class="k">Outcomes labelled</span><span class="v">${compact(db.token_outcomes)}</span></div><div class="li"><span class="k">Social posts</span><span class="v">${compact(db.social_posts)}</span></div>
        <div class="li"><span class="k">Baseline coverage, the 6h before the last hour</span><span class="v">${pct(h.launch_coverage_baseline)}</span></div></div></div>
      <div>${slug("Backtest", "", bt ? (bt.validated ? `<span class="stamp accelerating">${Viz.GLYPH.bought}Validated</span>` : `<span class="stamp heating">${Viz.GLYPH.heating}Not validated</span>`) : "", "thin")}
        ${bt ? `<p class="dek2" style="margin:0 0 10px">${esc(cap(bt.verdict))}. ${bt.signals} signals over ${bt.steps} steps${bt.steps_excluded ? ` (${bt.steps_excluded} skipped for collection gaps)` : ""}${bt.dataset ? `, on ${esc(bt.dataset)}` : ""}, run ${esc(ago(nowS() - bt.created_at))}.</p>
          <table class="tbl static"><thead><tr><th>Verdict</th><th class="r">Signals</th><th class="r">Grad lift</th><th class="r hide-s">Net+ lift</th><th class="r">False pos</th></tr></thead><tbody>
          ${Object.entries(bt.by_verdict).map(([v, r]) => `<tr><td>${esc(vinfo(v).label)}</td><td class="r">${r.signals}</td><td class="r">${isNum(r.mean_grad_lift) ? signed(r.mean_grad_lift * 100, 2, " pts") : "—"}</td><td class="r hide-s">${isNum(r.mean_net_positive_lift) ? signed(r.mean_net_positive_lift * 100, 1, " pts") : "—"}</td><td class="r">${isNum(r.false_positive_rate) ? pct(r.false_positive_rate) : "—"}</td></tr>`).join("")}</tbody></table>
          ${bt.top_pick?.edge ? `<p class="notes">Top meta each step, next launches' graduation against all launches: launch edge ${nf(bt.top_pick.edge.ratio, 2)}×, readiness score ${nf(bt.top_pick.readiness.ratio, 2)}× (${bt.top_pick.edge.steps} steps).</p>` : ""}
          <p class="notes">Lift compares later launches in a narrative with all launches in the same window. Validation needs at least 30 favorable signals.</p>`
          : `<p class="dek2">No backtest yet. It needs labelled outcomes, which start about 13 hours after collection begins.</p>`}
        ${S.ov.edge_monitor?.inputs ? `<p class="notes"><b>Launch-edge inputs in this read:</b> ${pct(S.ov.edge_monitor.missing_share)} not measured yet, ${pct(S.ov.edge_monitor.unusual_share, 1)} outside what the model was trained on${Object.keys(S.ov.edge_monitor.unusual_by_input || {}).length ? ` (${esc(Object.entries(S.ov.edge_monitor.unusual_by_input).map(([k, n]) => `${k.toLowerCase()} ×${n}`).join(", "))})` : ""}. A rising share means the market has moved away from the data the ranking learned from.</p>` : ""}
        <button class="btn" id="runbt" style="margin-top:14px">Run a 3-day backtest</button></div>
      <div>${slug("Display", "", "", "thin")}
        <div class="label" style="margin-bottom:6px">Edition</div>${seg("Edition", [["day", "Day · newsprint"], ["night", "Night · blueprint"]], Edition.get(), "data-ed")}
        <div class="label" style="margin:18px 0 6px">Motion</div>${seg("Display mode", [["auto", "Auto"], ["premium", "Full"], ["low", "Low visual"]], pref, "data-perf")}
        <p class="notes">${pref === "auto" ? `Auto is using <b>${Perf.resolved() === "low" ? "Low visual" : "Full"}</b>${sig.length ? ` because this device reports ${esc(sig.join(", "))}` : " because this device reports no constraints"}.` : `${pref === "low" ? "Low visual" : "Full"} is set manually.`}
          Low visual drops transitions, textures and pointer tracking, refreshes every minute instead of every 30 seconds, and skips redraws when nothing changed. Every number and chart stays.</p>
        <div style="margin-top:22px">${slug("Integrations", "", "", "thin")}<div class="ledger">
          <div class="li"><span class="k">X API</span><span class="v">${yes(cfg.x_api)}</span></div><div class="li"><span class="k">Reddit OAuth</span><span class="v">${yes(cfg.reddit_oauth)}</span></div>
          <div class="li"><span class="k">Bitquery</span><span class="v">${yes(cfg.bitquery)}</span></div><div class="li"><span class="k">Claude analyst</span><span class="v">${yes(cfg.anthropic_analyst)}</span></div>
          <div class="li"><span class="k">Solana RPC</span><span class="v i2" style="font-weight:400;font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(cfg.solana_rpc)}</span></div></div>
        <p class="notes">Keys live in your settings file and never reach this page.</p></div></div>
    </div>
    <div class="sect">${slug("Recent alerts", "verdict changes, large score moves, regime changes and outages")}<div id="alerts" class="posts"><div class="sk line"></div><div class="sk line"></div></div></div>`;
  $$("[data-perf]", el).forEach((bb) => bb.addEventListener("click", () => Perf.set(bb.dataset.perf)));
  $$("[data-ed]", el).forEach((bb) => bb.addEventListener("click", () => Edition.set(bb.dataset.ed)));
  $("#runbt").addEventListener("click", async (e) => {
    const btn = e.currentTarget; btn.disabled = true; btn.textContent = "Running";
    try { await api("/api/backtests?days=3", { method: "POST" }); toast("Backtest finished"); await load(); }
    catch (err) { toast(`Backtest failed: ${err.message}`); btn.disabled = false; btn.textContent = "Run a 3-day backtest"; }
  });
  try {
    const al = await api("/api/alerts?limit=8"), box = $("#alerts");
    if (box) box.innerHTML = al.length ? al.map((a) => `<div class="post"><div class="by">${esc(dayhm(a.created_at))} · ${esc(a.kind.replace("_", " "))} · ${a.delivered ? "delivered" : "logged only"}</div>
      ${esc(a.message.replace("TRENCH//RADAR alert\n", "").split("\n\nResearch")[0])}</div>`).join("") : `<p class="dek2">No alerts yet.</p>`;
  } catch (_) { const box = $("#alerts"); if (box) box.innerHTML = `<p class="dek2">Alerts are unavailable.</p>`; }
}

// ---------------------------------------------------------------- boot
$("#mrefresh").addEventListener("click", () => load());
$("#edition").addEventListener("click", () => Edition.set(Edition.get() === "night" ? "day" : "night"));
Edition.set(Edition.get());
const mastObs = new ResizeObserver(() => document.documentElement.style.setProperty("--mast-h", `${$(".mast").offsetHeight}px`));
mastObs.observe($(".mast"));
let resizeT, lastW = innerWidth;
window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => { if (innerWidth === lastW) return; lastW = innerWidth; if (S.ov && !$("#sheet").classList.contains("on")) render(); }, Perf.low() ? 400 : 150); });
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && Date.now() - S.lastOk > 60000) load({ quiet: true }); });
matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", () => { if (Perf.pref() === "auto") { Perf.apply(); render(); } });
if ("serviceWorker" in navigator && (location.protocol === "https:" || ["127.0.0.1", "localhost"].includes(location.hostname))) navigator.serviceWorker.register("/sw.js").catch(() => {});
let start = (location.hash.match(/^#\/(\w+)/) || [])[1];
try { start = start || localStorage.getItem("radar-tab"); } catch (_) { /* ignore */ }
go(start || "overview");
renderStatus();
schedule();
load();
