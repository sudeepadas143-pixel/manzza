// TRENCH//RADAR client. Token names, posts and URLs come from strangers: every
// data-derived string goes through esc() before innerHTML.
"use strict";

const { esc, hhmm, dayhm } = Charts;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

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
const signed = (v, d = 1, suffix = "") => (isNum(v) ? (v > 0 ? "+" : v < 0 ? "−" : "") + nf(Math.abs(v), d) + suffix : "—");
const ago = (s) => (!isNum(s) ? "never" : s < 60 ? "just now" : s < 3600 ? `${Math.round(s / 60)}m ago` : s < 172800 ? `${nf(s / 3600, s < 36000 ? 1 : 0)}h ago` : `${Math.round(s / 86400)}d ago`);
const age = (h) => (!isNum(h) ? "—" : h < 1 ? `${Math.max(1, Math.round(h * 60))}m` : h < 48 ? `${nf(h, h < 10 ? 1 : 0)}h` : `${Math.round(h / 24)}d`);
const nowS = () => Math.floor(Date.now() / 1000);
const short = (a) => (a && a.length > 12 ? `${a.slice(0, 4)}…${a.slice(-4)}` : a || "—");

const VERDICT = {
  favorable: { tone: "pos", g: "●", label: "Favorable" },
  mixed: { tone: "warn", g: "▲", label: "Mixed" },
  unfavorable: { tone: "neg", g: "✕", label: "Unfavorable" },
  "insufficient data": { tone: "mute", g: "○", label: "Insufficient" },
};
const chip = (tone, g, label) => `<span class="chip ${tone}"><span class="g" aria-hidden="true">${g}</span>${esc(label)}</span>`;
const vchip = (v) => { const x = VERDICT[v] || VERDICT["insufficient data"]; return chip(x.tone, x.g, x.label); };
const meter = (v) => `<span class="meter"><i style="--v:${isNum(v) ? Math.max(0, Math.min(1, v)) : 0}"></i></span>`;

// ---------------------------------------------------------------- api + state
const S = { ov: null, charts: {}, tokens: null, report: undefined, alerts: null, range: 24, tab: "overview",
  metaFilter: "all", metaSort: "score", tokSort: "vol", tokQuery: "", error: null, loading: false, lastOk: 0 };
let token = null;
try { token = localStorage.getItem("radar-token"); } catch (_) { /* storage may be blocked */ }

async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: token ? { "x-radar-token": token } : {} });
  if (r.status === 401) { const e = new Error("unauthorized"); e.auth = true; throw e; }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText || ""}`.trim());
  return r.json();
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(toast.h);
  toast.h = setTimeout(() => t.classList.remove("on"), 2400);
}

// ---------------------------------------------------------------- status: live pill + banner
function freshnessSummary() {
  const f = S.ov ? Object.values(S.ov.freshness) : [];
  const core = f.filter((x) => ["geckoterminal/new_pools", "geckoterminal/refresh", "solana_rpc/bonding_curves"].includes(`${x.source}/${x.job}`));
  return { all: f, coreBad: core.filter((x) => x.state !== "fresh"), fresh: f.filter((x) => x.state === "fresh").length };
}

function renderStatus() {
  const live = $("#live"), b = $("#banner");
  let cls = "", text = "Loading", html = "";
  if (S.error && !S.ov) { cls = "err"; text = "Offline"; }
  else if (S.ov) {
    const lag = nowS() - S.ov.as_of;
    const { coreBad } = freshnessSummary();
    if (S.error) { cls = "err"; text = "Offline"; html = banner("neg", "!", `<b>Couldn’t refresh.</b> Showing data from ${esc(hhmm(S.ov.as_of))} (${esc(ago(lag))}). ${esc(S.error)}`); }
    else if (lag > 1200 || coreBad.length) {
      cls = "stale"; text = "Stale";
      html = banner("warn", "▲", `<b>Data is stale.</b> ${coreBad.length ? esc(coreBad.map((x) => `${x.source}/${x.job}: ${x.state}`).join(", ")) + "." : `Last analysis ${esc(ago(lag))}.`} Scores below may lag the market.`);
    } else { cls = "ok"; text = `Live · ${hhmm(S.ov.as_of)}`; }
    const h = S.ov.context.history || {};
    if (!html && isNum(h.launch_coverage_baseline) && h.launch_coverage_baseline < 0.5) {
      const got = Math.max(h.launch_coverage_baseline * 24, (h.launch_coverage_6h || 0) * 6);
      const have = got < 1 ? `${Math.max(1, Math.round(got * 60))} min` : `${nf(got, 1)}h`;
      html = banner("", "○", `<b>Building baseline · ${esc(have)} of ~30h.</b> Verdicts stay <i>insufficient</i> until there is a full day of history to compare against. Live counts below are real.`);
    }
  }
  live.className = `live ${cls}`;
  live.lastElementChild.textContent = text;
  b.innerHTML = html;
}
const banner = (tone, g, body) => `<div class="banner ${tone}" role="status"><span class="ic" aria-hidden="true">${g}</span><div>${body}</div></div>`;

// ---------------------------------------------------------------- loading
async function load({ quiet = false } = {}) {
  const btn = $("#refresh");
  btn.classList.add("spin");
  S.loading = true;
  try {
    const [ov, ch, tk] = await Promise.all([api("/api/overview"), api(`/api/charts?hours=${S.range}`), api("/api/tokens?limit=80")]);
    S.ov = ov; S.charts[S.range] = ch; S.tokens = tk; S.error = null; S.lastOk = Date.now();
  } catch (e) {
    if (e.auth) return askToken();
    S.error = e.message || "network error";
    if (!quiet) toast("Refresh failed");
  } finally {
    btn.classList.remove("spin");
    S.loading = false;
  }
  renderStatus();
  render();
}

function askToken() {
  $$(".screen").forEach((s) => (s.hidden = s.dataset.screen !== "overview"));
  $(".screen[data-screen=overview]").innerHTML = `<div class="card" style="margin-top:16px">
    <div class="empty"><div class="t">This dashboard is locked</div>Enter the dashboard token set in <span class="mono">DASHBOARD_TOKEN</span>.
    <form id="tokform" style="display:grid;gap:10px;max-width:320px;margin:16px auto 0">
      <label class="sr" for="tokin">Dashboard token</label><input id="tokin" type="password" autocomplete="current-password" required>
      <button class="btn primary">Unlock</button></form></div></div>`;
  $("#tokform").addEventListener("submit", (e) => {
    e.preventDefault();
    token = $("#tokin").value;
    try { localStorage.setItem("radar-token", token); } catch (_) { /* ignore */ }
    load();
  });
  $("#live").className = "live err";
  $("#live").lastElementChild.textContent = "Locked";
}

// ---------------------------------------------------------------- router
const TITLES = { overview: "Overview", metas: "Metas", tokens: "Tokens", analyst: "Analyst", system: "System" };
function go(tab, { push = true } = {}) {
  if (!TITLES[tab]) tab = "overview";
  S.tab = tab;
  $$(".tab").forEach((t) => t.setAttribute("aria-current", t.dataset.go === tab ? "page" : "false"));
  $$(".screen").forEach((s) => (s.hidden = s.dataset.screen !== tab));
  $("#title").textContent = TITLES[tab];
  if (push) history.replaceState(null, "", `#/${tab}`);
  try { localStorage.setItem("radar-tab", tab); } catch (_) { /* ignore */ }
  window.scrollTo({ top: 0 });
  render();
}
$$(".tab").forEach((t) => t.addEventListener("click", () => go(t.dataset.go)));

function render() {
  if (!S.ov) return renderLoadingOrError();
  ({ overview: renderOverview, metas: renderMetas, tokens: renderTokens, analyst: renderAnalyst, system: renderSystem })[S.tab]();
}

function renderLoadingOrError() {
  const el = $(`.screen[data-screen=${S.tab}]`);
  if (S.error) {
    el.innerHTML = `<div class="card" style="margin-top:16px"><div class="empty"><div class="t">Can’t reach the radar server</div>
      ${esc(S.error)}. Is <span class="mono">python -m radar serve</span> (or TrenchRadar.exe) running?
      <div><button class="btn" id="retry">Try again</button></div></div></div>`;
    $("#retry").addEventListener("click", () => load());
    return;
  }
  const sk = (h, w = "100%") => `<div class="sk" style="height:${h}px;width:${w}"></div>`;
  el.innerHTML = `<div class="section">${sk(132)}</div><div class="section grid g4">${sk(84)}${sk(84)}${sk(84)}${sk(84)}</div>
    <div class="section">${sk(220)}</div><div class="section">${sk(56)}${"<div style='height:8px'></div>" + sk(56)}</div>`;
}

// ---------------------------------------------------------------- shared pieces
function metaRow(m, i) {
  const e = m.evidence, d = e.demand, l = e.launch, sat = e.saturation.index;
  return `<button class="row" data-meta="${i}">
    <div style="min-width:0"><div class="t"><span class="name">${esc(m.meta_key)}</span>${vchip(m.verdict)}</div>
      <div class="terms">${esc(m.terms.length > 1 ? m.terms.slice(1, 6).join(" · ") : m.hype_check)}</div></div>
    <div class="right"><span class="score${m.verdict === "insufficient data" ? " dim" : ""}" title="${m.verdict === "insufficient data" ? "provisional: not enough evidence" : "readiness score"}">${isNum(m.score) ? Math.round(m.score) : "—"}<small>/100</small></span>
      <span class="conf" title="confidence">${meter(m.confidence)}${nf(m.confidence, 2)}</span></div>
    <div class="stats"><span>launches <b>${l.launches_1h}</b> 1h · <b>${l.launches_6h}</b> 6h</span>
      <span>buyers <b>${compact(d.unique_buyers_h1_sum)}</b>/h</span><span>buyer share <b>${pct(d.buyer_share_h1)}</b></span>
      <span>saturation <b>${isNum(sat) ? nf(sat, 2) : "—"}</b></span>
      <span style="margin-left:auto">${Charts.spark(l.launch_hourly_12h)}</span></div></button>`;
}
function bindMetaRows(root, list) {
  $$("[data-meta]", root).forEach((b) => b.addEventListener("click", () => openMeta(list[+b.dataset.meta])));
}
function tokenRow(t, i) {
  const ageH = t.created_at ? (nowS() - t.created_at) / 3600 : null;
  const b = t.buyers_h1 || 0, s = t.sellers_h1 || 0, tot = b + s || 1;
  return `<button class="row trow" data-tok="${i}">
    ${Charts.ring(t.progress, !!t.graduated)}
    <div style="min-width:0"><div class="t"><span class="name">${esc(t.symbol || short(t.mint))}</span>
      ${t.graduated ? `<span class="muted" style="font-weight:400;font-size:12px">graduated</span>` : isNum(ageH) ? `<span class="muted" style="font-weight:400;font-size:12px">${esc(age(ageH))}</span>` : ""}</div>
      <div class="terms">${esc(t.name || "")}</div></div>
    <div class="right"><span class="num" style="font-size:14px;font-weight:600">${usd(t.vol_h1)}<small class="muted" style="font-size:11px"> /1h</small></span>
      <span class="conf"><span class="bs" title="buyers vs sellers, last hour"><i style="width:${(b / tot) * 100}%"></i><u style="width:${(s / tot) * 100}%"></u></span><span class="n">${compact(b)}/${compact(s)}</span></span></div></button>`;
}
function bindTokRows(root, list) {
  $$("[data-tok]", root).forEach((b) => b.addEventListener("click", () => openToken(list[+b.dataset.tok].mint)));
}
const segHtml = (name, opts, cur) => `<div class="seg" role="group" aria-label="${esc(name)}">${opts.map(([v, l]) => `<button data-v="${v}" aria-pressed="${String(v) === String(cur)}">${esc(l)}</button>`).join("")}</div>`;
function bindSeg(root, fn) { $$(".seg button", root).forEach((b) => b.addEventListener("click", () => fn(b.dataset.v))); }

// ---------------------------------------------------------------- OVERVIEW
const DRIVERS = [["launchpad_volume_trend", "Launchpad volume trend"], ["new_token_performance", "New tokens with traction"],
  ["graduation_rate", "Graduation rate"], ["fresh_rotation", "Rotation into new launches"], ["sol_trend", "SOL trend"]];

function renderOverview() {
  const el = $(".screen[data-screen=overview]");
  const m = S.ov.market, x = m.metrics;
  const tone = { hot: "pos", neutral: "warn", cold: "neg" }[m.regime] || "mute";
  const word = m.regime ? m.regime[0].toUpperCase() + m.regime.slice(1) : "Unknown";
  const dot = { pos: "var(--pos)", warn: "var(--warn)", neg: "var(--neg)", mute: "var(--muted)" }[tone];
  const drivers = DRIVERS.map(([k, label]) => {
    const v = m.components[k];
    return `<div class="driver"><span>${esc(label)}</span>${isNum(v) ? `${meter(v)}<span class="num" style="text-align:right">${nf(v, 2)}</span>`
      : `<span class="na">${k === "graduation_rate" ? "needs 24h history" : "no data yet"}</span>`}</div>`;
  }).join("");
  const metas = S.ov.metas;
  const lead = metas.slice(0, 4);
  const toks = (S.tokens?.tokens || []).slice(0, 4);
  const ch = S.charts[S.range];
  el.innerHTML = `<div class="stag">
    <div class="section card regime">
      <div><div class="eyebrow">Market regime</div>
        <div class="word" style="margin-top:6px"><i style="background:${dot}" aria-hidden="true"></i>${esc(word)}</div>
        <div class="sub">${isNum(m.score) ? `Score <span class="num">${nf(m.score, 2)}</span> from ${pct(m.coverage)} of inputs` : "Not enough market data yet"}</div></div>
      <div class="drivers">${drivers}</div>
    </div>
    <div class="section grid g4">
      ${kpi("Launches / hour", isNum(x.launches_est_per_h) ? compact(x.launches_est_per_h) : compact(x.launches_observed_1h),
        isNum(x.launches_est_per_h) ? `observed coverage ${pct(x.launch_coverage_1h)}` : `seen in last hour · coverage ${pct(x.launch_coverage_1h)}`)}
      ${kpi("Graduation rate", isNum(x.graduation_rate_24_48h_cohort) ? pct(x.graduation_rate_24_48h_cohort, 2) : "—",
        x.graduation_cohort_n ? `24–48h cohort · n=${compact(x.graduation_cohort_n)}` : "needs 24h of launches")}
      ${kpi("Launchpad volume", usd(x.pumpfun_launchpad_vol_7d_avg_usd), isNum(x.pumpfun_launchpad_vol_7d_vs_30d)
        ? `<span class="${x.pumpfun_launchpad_vol_7d_vs_30d >= 1 ? "delta-pos" : "delta-neg"}">${signed((x.pumpfun_launchpad_vol_7d_vs_30d - 1) * 100, 0, "%")}</span> 7d avg vs 30d` : "daily, 7-day average")}
      ${kpi("SOL", isNum(x.sol_price_usd) ? "$" + nf(x.sol_price_usd, 2) : "—", isNum(x.sol_chg_24h)
        ? `<span class="${x.sol_chg_24h >= 0 ? "delta-pos" : "delta-neg"}">${signed(x.sol_chg_24h * 100, 1, "%")}</span> 24h` : "24h change after a day")}
    </div>
    <div class="section card">
      <div class="chart-title"><div><h3>Launch flow</h3><p>pump.fun launches observed per ${S.range === 6 ? "5 min" : S.range === 24 ? "15 min" : "hour"} · hatched = collector offline</p></div>
        ${segHtml("Time range", [[6, "6H"], [24, "24H"], [72, "3D"]], S.range)}</div>
      <div class="chart" id="flow"></div>
      <div class="chart-title" style="margin:14px 0 6px"><div><p>Graduations to PumpSwap per hour</p></div></div>
      <div class="chart" id="grads"></div>
    </div>
    <div class="section"><div class="sh"><h2>Leading metas</h2><button class="link" data-goto="metas">All ${metas.length} →</button></div>
      <div class="card flush list" id="lead">${lead.length ? lead.map(metaRow).join("") : emptyMetas()}</div></div>
    <div class="section"><div class="sh"><h2>Most active tokens</h2><button class="link" data-goto="tokens">All →</button></div>
      <div class="card flush list" id="otoks">${toks.length ? toks.map(tokenRow).join("") : `<div class="empty">No token has fresh trading stats yet.</div>`}</div></div>
    <p class="attrib">Sources: GeckoTerminal (launches, trades, buyers), Solana RPC (bonding curves), DefiLlama (launchpad volume), DexScreener (paid promotion).
      Model ${esc(S.ov.model_version)} · scores are hand-weighted priors${S.ov.backtest?.validated ? ", validated by the latest backtest" : " and not yet validated against outcomes"}.</p>
  </div>`;
  bindSeg(el, async (v) => { S.range = +v; if (!S.charts[S.range]) { try { S.charts[S.range] = await api(`/api/charts?hours=${S.range}`); } catch (e) { toast("Couldn’t load range"); } } renderOverview(); });
  bindMetaRows($("#lead"), lead);
  bindTokRows($("#otoks"), toks);
  $$("[data-goto]", el).forEach((b) => b.addEventListener("click", () => go(b.dataset.goto)));
  if (ch) drawFlow(ch);
}
const kpi = (k, v, s) => `<div class="card kpi"><div class="k"><span>${esc(k)}</span></div><div class="v">${v}</div><div class="s">${s}</div></div>`;
const emptyMetas = () => `<div class="empty"><div class="t">No metas detected yet</div>A meta appears once several launches or posts share a theme. The first ones show up after a few collection cycles.</div>`;

function drawFlow(ch) {
  const to = ch.now, from = to - ch.hours * 3600;
  Charts.timeBars($("#flow"), { data: ch.launches, from, to, step: ch.step_s, observed: ch.observed_buckets, height: 168,
    fmtY: (v) => compact(v, 0), label: "Launches over time", unit: "launches" });
  Charts.timeBars($("#grads"), { data: ch.graduations, from, to, step: ch.graduation_step_s, height: 74,
    fmtY: (v) => compact(v, 0), label: "Graduations over time", unit: "graduations" });
}

// ---------------------------------------------------------------- METAS
const SORTS = { score: (m) => m.score ?? -1, buyers: (m) => m.evidence.demand.unique_buyers_h1_sum, launches: (m) => m.evidence.launch.launches_1h,
  saturation: (m) => -(m.evidence.saturation.index ?? 1) };
function renderMetas() {
  const el = $(".screen[data-screen=metas]");
  const all = S.ov.metas;
  const count = (v) => all.filter((m) => m.verdict === v).length;
  const filters = [["all", "All", all.length], ["favorable", "Favorable", count("favorable")], ["mixed", "Mixed", count("mixed")],
    ["unfavorable", "Unfavorable", count("unfavorable")], ["insufficient data", "Insufficient", count("insufficient data")]];
  const list = all.filter((m) => S.metaFilter === "all" || m.verdict === S.metaFilter).sort((a, b) => SORTS[S.metaSort](b) - SORTS[S.metaSort](a));
  const pts = all.filter((m) => isNum(m.components.attention) && isNum(m.components.demand)).map((m) => ({
    x: m.components.attention, y: m.components.demand, label: m.meta_key, buyers: m.evidence.demand.unique_buyers_h1_sum,
    tone: (VERDICT[m.verdict] || VERDICT["insufficient data"]).tone, verdict: (VERDICT[m.verdict] || {}).label || m.verdict,
    conf: m.confidence, confident: m.verdict !== "insufficient data", score: m.score, meta: m }));
  el.innerHTML = `<div class="stag">
    <div class="section card">
      <div class="chart-title"><div><h3>Hype vs buying</h3><p>Attention (launch names${S.ov.social_measured ? " + social" : ""}) against measured buying. Size = buyers/h · hollow = not enough evidence.</p></div></div>
      <div class="chart" id="quad">${pts.length ? "" : `<div class="chart-empty">No metas to plot yet.</div>`}</div>
    </div>
    <div class="section">
      <div class="filters" role="group" aria-label="Filter by verdict">${filters.map(([v, l, n]) => `<button class="fchip" data-f="${esc(v)}" aria-pressed="${S.metaFilter === v}">${l}<span class="n">${n}</span></button>`).join("")}</div>
      <div class="toolbar" style="margin:6px 0 10px"><span class="aside muted" style="font-size:12px">${list.length} shown · buyers are per-token sums</span>
        <label class="sr" for="msort">Sort</label><select id="msort">${[["score", "Score"], ["buyers", "Buyers"], ["launches", "Launches"], ["saturation", "Least saturated"]]
          .map(([v, l]) => `<option value="${v}" ${S.metaSort === v ? "selected" : ""}>Sort: ${l}</option>`).join("")}</select></div>
      <div class="card flush list" id="mlist">${list.length ? list.map(metaRow).join("") : S.metaFilter === "all" ? emptyMetas() : `<div class="empty">No metas with this verdict right now.</div>`}</div>
    </div></div>`;
  if (pts.length) Charts.quadrant($("#quad"), { points: pts, onPick: (p) => openMeta(p.meta) });
  $$("[data-f]", el).forEach((b) => b.addEventListener("click", () => { S.metaFilter = b.dataset.f; renderMetas(); }));
  $("#msort").addEventListener("change", (e) => { S.metaSort = e.target.value; renderMetas(); });
  bindMetaRows($("#mlist"), list);
}

// ---------------------------------------------------------------- sheet
let lastFocus = null, sheetCloser = null;
function openSheet(title, sub, body, onReady) {
  lastFocus = document.activeElement;
  $("#sheet-title").textContent = title;
  $("#sheet-sub").innerHTML = sub;
  $("#sheet-body").innerHTML = body;
  $("#sheet-body").scrollTop = 0;
  const sh = $("#sheet");
  sh.style.transform = "";
  $("#backdrop").classList.add("on");
  sh.classList.add("on");
  document.body.style.overflow = "hidden";
  $(".app").inert = true;
  setTimeout(() => sh.focus({ preventScroll: true }), 30);
  onReady && onReady($("#sheet-body"));
}
function closeSheet() {
  const sh = $("#sheet");
  if (!sh.classList.contains("on")) return;
  sh.classList.remove("on");
  sh.style.transform = "";
  $("#backdrop").classList.remove("on");
  document.body.style.overflow = "";
  $(".app").inert = false;
  Charts.hideTip();
  sheetCloser && sheetCloser();
  if (lastFocus) lastFocus.focus({ preventScroll: true });
}
$("#sheet-close").addEventListener("click", closeSheet);
$("#backdrop").addEventListener("click", closeSheet);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });
// drag the grabber down to dismiss (velocity- or distance-based), springs back otherwise
(() => {
  const g = $("#grab"), sh = $("#sheet");
  let y0 = 0, t0 = 0, dy = 0, on = false;
  g.addEventListener("pointerdown", (e) => { on = true; y0 = e.clientY; t0 = performance.now(); dy = 0; sh.classList.add("dragging"); g.setPointerCapture(e.pointerId); });
  g.addEventListener("pointermove", (e) => { if (!on) return; dy = Math.max(0, e.clientY - y0); sh.style.transform = `translateY(${dy}px)`; });
  const end = () => {
    if (!on) return;
    on = false;
    sh.classList.remove("dragging");
    const v = dy / Math.max(1, performance.now() - t0);
    if (dy > 110 || v > 0.6) closeSheet(); else sh.style.transform = "";
  };
  g.addEventListener("pointerup", end);
  g.addEventListener("pointercancel", end);
})();

// ---------------------------------------------------------------- meta detail
function openMeta(m) {
  const e = m.evidence, d = e.demand, l = e.launch, s = e.social, cf = m.confidence_factors, sat = e.saturation;
  const fresh = S.ov.freshness;
  const why = [];
  if (cf.history < 0.6) why.push("collection history is still short");
  if (cf.sample < 0.5) why.push("few tokens have fresh trading stats");
  if (!cf.social_measured) why.push("social sources are not connected");
  if (cf.freshness < 0.8) why.push("some sources are stale");
  const comp = (k, label) => {
    const v = m.components[k];
    return `<div class="comp"><span>${esc(label)} <span class="w">×${m.weights[k]}</span></span>${isNum(v) ? meter(v) : `<span class="na">no data, excluded</span>`}
      <span class="num" style="text-align:right">${isNum(v) ? nf(v, 2) : ""}</span></div>`;
  };
  const parts = (o) => Object.entries(o || {}).map(([k, v]) => `${esc(k.replaceAll("_", " "))} ${nf(v, 2)}`).join(" · ");
  const satRows = Object.entries(sat.signals).map(([k, v]) => `<div class="comp"><span>${esc(k.replaceAll("_", " "))}</span>${meter(v.s)}<span class="num" style="text-align:right">${nf(v.s, 2)}</span></div>
    <div class="parts" style="margin-left:0">${esc(v.why)}</div>`).join("");
  const posts = (s.influential_posts || []).map((p) => `<div class="post"><div class="by">@${esc(p.author || "?")} · ${compact(p.followers)} followers · ${compact(p.engagement)} engagement ·
      <a href="${esc(/^https:\/\//.test(p.url) ? p.url : "#")}" target="_blank" rel="noopener noreferrer">open</a></div>${esc(p.text)}</div>`).join("");
  const toks = d.top_tokens || [];
  const used = ["geckoterminal/refresh", "geckoterminal/new_pools", "solana_rpc/bonding_curves", "dexscreener/boosts_profiles", "x_api/recent_search", "reddit/new_posts"]
    .filter((k) => fresh[k]).map((k) => `${k.split("/")[0]} (${fresh[k].state}${isNum(fresh[k].age_s) ? ", " + ago(fresh[k].age_s) : ""})`);
  const body = `
    <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:12px">
      <div>${vchip(m.verdict)}<div class="score${m.verdict === "insufficient data" ? " dim" : ""}" style="font-size:34px;margin-top:8px">${isNum(m.score) ? Math.round(m.score) : "—"}<small style="font-size:14px">/100</small></div></div>
      <div style="text-align:right"><div class="eyebrow">Confidence</div><div class="num" style="font-size:20px;font-weight:600;margin:2px 0 4px">${nf(m.confidence, 2)}</div>
        <div style="width:110px;margin-left:auto">${meter(m.confidence)}</div></div></div>
    <p class="sec" style="font-size:13.5px;margin:12px 0 0">${esc(m.hype_check[0].toUpperCase() + m.hype_check.slice(1))}.${m.validated ? "" : " Score not yet validated against outcomes."}</p>
    ${m.verdict === "insufficient data" ? `<div class="callout" style="margin-top:12px"><b>Not enough evidence for a call.</b> ${esc(((s) => s[0].toUpperCase() + s.slice(1))(why.join(", ") || "confidence is below the 0.35 bar"))}.
      The score is shown for reference only.</div>` : ""}
    ${m.reasons.length ? `<div class="sh" style="margin-top:18px"><h2>Evidence for</h2></div><ul class="bul pos">${m.reasons.map((r) => `<li><span class="g">●</span><span>${esc(r)}</span></li>`).join("")}</ul>` : ""}
    <div class="sh" style="margin-top:18px"><h2>Risks</h2></div><ul class="bul neg">${m.risks.map((r) => `<li><span class="g">▲</span><span>${esc(r)}</span></li>`).join("")}</ul>
    <details class="ev" open><summary>Score breakdown<span class="aside">${pct(cf.weight_coverage)} of weight has data</span></summary><div class="in">
      ${comp("attention", "Attention")}<div class="parts">${parts(m.component_parts.attention)}</div>
      ${comp("demand", "Demand")}<div class="parts">${parts(m.component_parts.demand)}</div>
      ${comp("market", "Market")}${comp("freshness", "Freshness")}
      <dl class="kv" style="margin-top:10px"><dt>Confidence factors</dt><dd>sample ${nf(cf.sample, 2)} · history ${nf(cf.history, 2)} · freshness ${nf(cf.freshness, 2)}</dd></dl></div></details>
    <details class="ev" open><summary>Launches<span class="aside">${l.launches_1h} in 1h</span></summary><div class="in">
      <div class="chart" id="mlaunch"></div>
      <dl class="kv" style="margin-top:10px"><dt>Last hour / 6h</dt><dd>${l.launches_1h} / ${l.launches_6h}</dd>
        <dt>Prior 24h baseline</dt><dd>${nf(l.launch_base_rate_h, 1)}/h</dd>
        <dt>Acceleration (z)</dt><dd>${isNum(l.launch_accel_z) ? nf(l.launch_accel_z, 1) : "baseline not ready"}</dd>
        <dt>Share of all launches, 6h</dt><dd>${pct(l.launch_share_6h, 1)}</dd>
        <dt>Reused tickers</dt><dd>${pct(l.duplicate_symbol_share_6h)}</dd>
        <dt>Serial deployers</dt><dd>${isNum(e.creators?.serial_share) ? pct(e.creators.serial_share) : "unknown"} <span class="muted">(${e.creators?.known ?? 0} known)</span></dd>
        <dt>Paid promotion, 24h</dt><dd>${e.attention_purchased?.boosts_24h ?? 0} boosted · ${e.attention_purchased?.profiles_24h ?? 0} profiled</dd></dl></div></details>
    <details class="ev" open><summary>Buying demand<span class="aside">${compact(d.unique_buyers_h1_sum)} buyers/h</span></summary><div class="in">
      <div class="statgrid c3">
        <div><div class="k">Buyers / sellers 1h</div><div class="v">${compact(d.unique_buyers_h1_sum)}/${compact(d.unique_sellers_h1_sum)}</div></div>
        <div><div class="k">Buyer share</div><div class="v">${pct(d.buyer_share_h1)}</div></div>
        <div><div class="k">Volume 1h</div><div class="v">${usd(d.vol_h1_usd)}</div></div>
        <div><div class="k">Volume 24h</div><div class="v">${usd(d.vol_h24_usd)}</div></div>
        <div><div class="k">Net SOL into curves 1h</div><div class="v">${isNum(d.curve_net_sol_1h) ? signed(d.curve_net_sol_1h, 1) + '<small class="muted" style="font-size:12px"> SOL</small>' : "—"}</div></div>
        <div><div class="k">Graduated 24h</div><div class="v">${d.graduations_24h}</div></div></div>
      <p class="attrib" style="margin-top:8px">${d.tokens_tracked} tokens with fresh stats. Buyer counts are per-token sums: one wallet in three tokens counts three times.
        Net USD flow ${isNum(d.net_flow_usd_h1) ? usd(d.net_flow_usd_h1) : "needs Bitquery"}. Top token holds ${pct(d.top_token_share_vol24)} of 24h volume.</p></div></details>
    <details class="ev"><summary>Saturation<span class="aside">${isNum(sat.index) ? "index " + nf(sat.index, 2) : "no signals yet"}</span></summary><div class="in">
      ${satRows || `<p class="muted" style="font-size:13px;margin:0">No saturation signal has enough data yet.</p>`}</div></details>
    <details class="ev"><summary>Social<span class="aside">${cf.social_measured ? `${s.mentions_6h} posts 6h` : "not connected"}</span></summary><div class="in">
      ${cf.social_measured ? `<dl class="kv"><dt>Mentions 1h / 6h</dt><dd>${s.mentions_1h} / ${s.mentions_6h}</dd><dt>Independent accounts</dt><dd>${s.independent_authors_6h}</dd>
        <dt>Copy-paste posts</dt><dd>${s.copy_paste_posts_6h}</dd><dt>Sentiment (−1…1)</dt><dd>${isNum(s.sentiment_6h) ? nf(s.sentiment_6h, 2) : "—"}</dd></dl>${posts}`
        : `<p class="muted" style="font-size:13px;margin:0">No social source is connected, so attention comes from launch names only. Add an X token or Reddit OAuth in settings.</p>`}</div></details>
    <details class="ev"><summary>Score history<span class="aside">last 48h</span></summary><div class="in"><div class="chart" id="mhist"><div class="chart-empty">Loading…</div></div></div></details>
    <div class="sh" style="margin-top:20px"><h2>Top tokens in this meta</h2></div>
    <div class="card flush list" id="mtoks">${toks.length ? toks.map((t, i) => tokenRow({ ...t, created_at: isNum(t.age_h) ? nowS() - t.age_h * 3600 : null }, i)).join("") : `<div class="empty">No token in this meta has fresh stats.</div>`}</div>
    <p class="attrib">Computed ${esc(dayhm(S.ov.as_of))} by model ${esc(S.ov.model_version)}. Sources: ${esc(used.join(", "))}.</p>`;
  openSheet(m.meta_key, esc(m.terms.length > 1 ? m.terms.join(" · ") : `${l.launches_6h} launches in 6h · ${d.tokens_tracked} tokens trading`), body, async (root) => {
    bindTokRows($("#mtoks", root), toks);
    const to = S.ov.as_of;
    Charts.timeBars($("#mlaunch", root), { data: l.launch_hourly_12h.map((v, i) => [Math.floor((to - (11 - i) * 3600) / 3600) * 3600, v]),
      from: Math.floor(to / 3600) * 3600 - 11 * 3600, to: Math.floor(to / 3600) * 3600 + 3600, step: 3600, height: 110, fmtY: (v) => compact(v, 0), unit: "launches", label: "Launches per hour" });
    try {
      const h = await api(`/api/metas/${encodeURIComponent(m.meta_key)}/history?hours=48`);
      Charts.timeLine($("#mhist", root), { data: h.filter((r) => isNum(r.score)).map((r) => [r.computed_at, r.score]), yMin: 0, yMax: 100, height: 140,
        fmtY: (v) => nf(v, 0), refs: [{ v: 65, label: "favorable" }, { v: 45, label: "mixed" }], label: "Score history" });
    } catch (_) { $("#mhist", root).innerHTML = `<div class="chart-empty">History unavailable.</div>`; }
  });
}

// ---------------------------------------------------------------- token detail
let tokState = { mint: null, metric: "mcap", hours: 24 };
async function openToken(mint) {
  tokState = { ...tokState, mint };
  openSheet("Loading…", "", `<div class="sk" style="height:96px"></div><div style="height:10px"></div><div class="sk" style="height:170px"></div>`);
  let t;
  try { t = await api(`/api/tokens/${encodeURIComponent(mint)}?hours=${tokState.hours}`); }
  catch (e) { $("#sheet-title").textContent = "Token"; $("#sheet-body").innerHTML = `<div class="empty"><div class="t">Couldn’t load this token</div>${esc(e.message)}</div>`; return; }
  if (tokState.mint !== mint) return;
  const k = t.token, last = t.observations[t.observations.length - 1] || {}, curve = t.curve[t.curve.length - 1];
  const ageH = k.created_at ? (t.now - k.created_at) / 3600 : null;
  const graduated = !!t.graduation || !!curve?.complete;
  const risks = [];
  if (isNum(ageH) && ageH < 1) risks.push(["warn", `Launched ${age(ageH)} ago: most launches are dead within 30 minutes.`]);
  if ((last.sellers_h1 || 0) > (last.buyers_h1 || 0)) risks.push(["neg", `More sellers than buyers in the last hour (${last.sellers_h1} vs ${last.buyers_h1}).`]);
  if (isNum(last.liquidity_usd) && last.liquidity_usd < 5000) risks.push(["warn", `Thin liquidity: ${usd(last.liquidity_usd)}.`]);
  if (t.deployer?.launches_seen_24h >= 3) risks.push(["neg", `Deployer launched ${t.deployer.launches_seen_24h} tokens we saw in 24h (serial deployer).`]);
  if (last.observed_at && t.now - last.observed_at > 1800) risks.push(["warn", `Trading stats are ${ago(t.now - last.observed_at)} old.`]);
  if (!t.observations.length) risks.push(["warn", "No trading observations in this range."]);
  const outcomes = t.outcomes.map((o) => `<tr><td>${o.horizon_h}h</td><td>${o.graduated ? "graduated" : esc(o.bucket || "—")}</td><td class="r">${isNum(o.ret_end) ? signed(o.ret_end * 100, 0, "%") : "—"}</td><td class="r">${isNum(o.ret_max) ? signed(o.ret_max * 100, 0, "%") : "—"}</td></tr>`).join("");
  const body = `
    <div class="addr"><span>${esc(short(k.mint))}</span><button id="copy">Copy address</button></div>
    <div class="links" style="margin-top:10px">
      <a href="https://pump.fun/coin/${encodeURIComponent(k.mint)}" target="_blank" rel="noopener noreferrer">pump.fun ↗</a>
      <a href="https://dexscreener.com/solana/${encodeURIComponent(k.mint)}" target="_blank" rel="noopener noreferrer">DexScreener ↗</a>
      <a href="https://solscan.io/token/${encodeURIComponent(k.mint)}" target="_blank" rel="noopener noreferrer">Solscan ↗</a></div>
    <div class="statgrid c3" style="margin-top:14px">
      <div><div class="k">Market cap</div><div class="v">${usd(last.mcap_usd)}</div></div>
      <div><div class="k">Liquidity</div><div class="v">${usd(last.liquidity_usd)}</div></div>
      <div><div class="k">Curve</div><div class="v">${graduated ? "Graduated" : curve ? pct(curve.progress) : "—"}</div></div>
      <div><div class="k">Volume 1h</div><div class="v">${usd(last.vol_h1)}</div></div>
      <div><div class="k">Volume 24h</div><div class="v">${usd(last.vol_h24)}</div></div>
      <div><div class="k">Buyers / sellers 1h</div><div class="v">${last.buyers_h1 ?? "—"}/${last.sellers_h1 ?? "—"}</div></div></div>
    <div class="section card">
      <div class="chart-title"><div class="seg" id="tmetric" role="group" aria-label="Metric">${[["mcap", "Market cap"], ["buyers", "Buyers/h"], ["curve", "Curve"]]
        .map(([v, l]) => `<button data-v="${v}" aria-pressed="${tokState.metric === v}">${l}</button>`).join("")}</div>
        <div class="seg" id="trange" role="group" aria-label="Range">${[[6, "6H"], [24, "24H"], [72, "3D"]].map(([v, l]) => `<button data-v="${v}" aria-pressed="${tokState.hours === v}">${l}</button>`).join("")}</div></div>
      <div class="chart" id="tchart"></div></div>
    <div class="sh" style="margin-top:18px"><h2>Risk indicators</h2></div>
    ${risks.length ? `<ul class="bul">${risks.map(([tone, r]) => `<li class="${tone}"><span class="g" style="color:var(--${tone})">▲</span><span>${esc(r)}</span></li>`).join("")}</ul>`
      : `<p class="sec" style="font-size:13.5px;margin:0">No automatic flags. That is not a safety check: rugs, bundles and insider wallets are not detected here.</p>`}
    <details class="ev"><summary>Deployer<span class="aside">${t.deployer ? esc(short(t.deployer.wallet)) : "unknown"}</span></summary><div class="in">
      ${t.deployer ? `<dl class="kv"><dt>Wallet</dt><dd>${esc(short(t.deployer.wallet))}</dd><dt>Launches we saw, 24h</dt><dd>${t.deployer.launches_seen_24h}</dd>
        <dt>SOL balance</dt><dd>${isNum(t.deployer.activity?.sol_balance) ? nf(t.deployer.activity.sol_balance, 2) : "—"}</dd>
        <dt>Recent transactions</dt><dd>${t.deployer.activity?.recent_tx ?? "—"}${t.deployer.activity?.recent_tx >= 100 ? "+" : ""}</dd></dl>
        <p class="attrib" style="margin-top:8px">Deployer = fee payer of the create transaction (Solana RPC).</p>`
        : `<p class="muted" style="font-size:13px;margin:0">Not looked up. Deployer lookups cost 2 RPC calls, so only the most active tokens get one.</p>`}</div></details>
    ${outcomes ? `<details class="ev"><summary>Outcomes<span class="aside">measured after launch</span></summary><div class="in">
      <table class="tbl"><thead><tr><th>Horizon</th><th>Result</th><th class="r">Return</th><th class="r">Max</th></tr></thead><tbody>${outcomes}</tbody></table>
      <p class="attrib">Return is from the first observed candle and ignores fees. Graduation and profit are separate outcomes.</p></div></details>` : ""}
    <p class="attrib">Trading stats: GeckoTerminal pool ${esc(short(k.pool))}, ${t.observations.length} observations in range${last.observed_at ? `, latest ${esc(ago(t.now - last.observed_at))}` : ""}.
      Curve: Solana RPC account state${curve ? `, ${esc(ago(t.now - curve.observed_at))}` : ", not read"}.${t.attention.length ? ` Paid DexScreener ${esc(t.attention[0].kind)} seen.` : ""}</p>`;
  $("#sheet-title").textContent = k.symbol ? `$${k.symbol}` : short(k.mint);
  $("#sheet-sub").textContent = `${k.name || ""}${isNum(ageH) ? " · launched " + age(ageH) + " ago" : ""}${graduated ? " · graduated" : ""}`;
  const root = $("#sheet-body");
  root.innerHTML = body;
  $("#copy", root).addEventListener("click", async () => { try { await navigator.clipboard.writeText(k.mint); toast("Address copied"); } catch (_) { toast("Copy not allowed here"); } });
  const draw = () => {
    // start at launch when the token is younger than the range, so its whole life fills the chart
    const firstSeen = Math.min(...[k.created_at, t.observations[0]?.observed_at, t.curve[0]?.observed_at].filter(isNum));
    const el = $("#tchart", root), from = Math.max(t.now - tokState.hours * 3600, isFinite(firstSeen) ? firstSeen - 120 : 0);
    if (tokState.metric === "curve") return Charts.timeLine(el, { data: t.curve.map((c) => [c.observed_at, (c.complete ? 1 : c.progress) * 100]), from, to: t.now, yMin: 0, yMax: 100, fmtY: (v) => nf(v, 0) + "%", label: "Curve progress" });
    if (tokState.metric === "buyers") return Charts.timeLine(el, { data: t.observations.filter((o) => isNum(o.buyers_h1)).map((o) => [o.observed_at, o.buyers_h1]), from, to: t.now, fmtY: (v) => compact(v, 0), label: "Unique buyers per hour" });
    Charts.timeLine(el, { data: t.observations.filter((o) => isNum(o.mcap_usd)).map((o) => [o.observed_at, o.mcap_usd]), from, to: t.now, fmtY: (v) => usd(v), label: "Market cap" });
  };
  draw();
  $$("#tmetric button", root).forEach((b) => b.addEventListener("click", () => { tokState.metric = b.dataset.v; $$("#tmetric button", root).forEach((x) => x.setAttribute("aria-pressed", x === b)); draw(); }));
  $$("#trange button", root).forEach((b) => b.addEventListener("click", () => { tokState.hours = +b.dataset.v; openToken(mint); }));
}

// ---------------------------------------------------------------- TOKENS
const TSORT = { vol: (t) => t.vol_h1 || 0, buyers: (t) => t.buyers_h1 || 0, new: (t) => t.created_at || 0, curve: (t) => (t.graduated ? 1.01 : t.progress || 0) };
function renderTokens() {
  const el = $(".screen[data-screen=tokens]");
  const q = S.tokQuery.trim().toLowerCase();
  const all = S.tokens?.tokens || [];
  const list = all.filter((t) => !q || `${t.symbol} ${t.name} ${t.mint}`.toLowerCase().includes(q)).sort((a, b) => TSORT[S.tokSort](b) - TSORT[S.tokSort](a));
  const focused = document.activeElement?.id === "tq";
  el.innerHTML = `<div class="${focused ? "" : "stag"}"><div class="section" style="display:grid;gap:10px">
      <label class="sr" for="tq">Search tokens</label><input id="tq" type="search" placeholder="Search symbol, name or address" value="${esc(S.tokQuery)}" autocomplete="off" spellcheck="false">
      <div class="toolbar">${segHtml("Sort", [["vol", "Volume"], ["buyers", "Buyers"], ["new", "Newest"], ["curve", "Curve"]], S.tokSort)}
        <span class="muted" style="font-size:12px">${list.length} active · stats ≤2h old</span></div></div>
    <div class="section card flush list" id="tlist">${list.length ? list.map(tokenRow).join("") : all.length ? `<div class="empty">No token matches “${esc(S.tokQuery)}”.</div>`
      : `<div class="empty"><div class="t">No active tokens yet</div>Tokens appear here once their trading stats have been refreshed (every 5 minutes).</div>`}</div></div>`;
  const inp = $("#tq");
  inp.addEventListener("input", () => { S.tokQuery = inp.value; renderTokens(); const n = $("#tq"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); });
  bindSeg(el, (v) => { S.tokSort = v; renderTokens(); });
  bindTokRows($("#tlist"), list);
}

// ---------------------------------------------------------------- ANALYST
function md(text) {
  const lines = esc(text).split("\n");
  let out = "", inList = false;
  const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|\s)_(.+?)_(?=\s|$|[.,])/g, "$1<em>$2</em>");
  for (const ln of lines) {
    const li = ln.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
    if (li) { if (!inList) { out += "<ul>"; inList = true; } out += `<li>${inline(li[1])}</li>`; continue; }
    if (inList) { out += "</ul>"; inList = false; }
    if (/^# /.test(ln)) out += `<h1>${inline(ln.slice(2))}</h1>`;
    else if (/^#{2,3} /.test(ln)) out += `<h3>${inline(ln.replace(/^#+ /, ""))}</h3>`;
    else if (ln.trim()) out += `<p>${inline(ln)}</p>`;
  }
  return out + (inList ? "</ul>" : "");
}
async function renderAnalyst() {
  const el = $(".screen[data-screen=analyst]");
  if (S.report === undefined) {
    el.innerHTML = `<div class="section"><div class="sk" style="height:300px"></div></div>`;
    try { S.report = await api("/api/reports/latest"); } catch (e) { S.report = { error: e.message }; }
    if (S.tab !== "analyst") return;
  }
  const r = S.report, ai = S.ov.config.anthropic_analyst;
  el.innerHTML = `<div class="stag">
    <div class="section toolbar"><div class="muted" style="font-size:12.5px">${ai ? `Claude (${esc(S.ov.config.analyst_model)}) writes from the evidence pack and may only cite its numbers.`
      : "Rules analyst (no Claude key set). Deterministic, built from the same evidence."}</div>
      <button class="btn primary" id="write">Write new report</button></div>
    <div class="section card">${r?.error ? `<div class="empty"><div class="t">Couldn’t load the report</div>${esc(r.error)}</div>`
      : r ? `<div class="eyebrow" style="margin-bottom:8px">${esc(dayhm(r.created_at))} · ${esc(r.analyst)} · ${esc(r.kind.replace("_", " "))}</div><div class="report">${md(r.body.replace(/^# .*\n+/, ""))}</div>`
      : `<div class="empty"><div class="t">No report yet</div>Reports are written at the scheduled times, or now with the button above.</div>`}</div></div>`;
  $("#write").addEventListener("click", async (e) => {
    const b = e.currentTarget;
    b.disabled = true; b.textContent = ai ? "Writing… (up to a minute)" : "Writing…";
    try { S.report = await api("/api/reports", { method: "POST" }); S.report.created_at = nowS(); S.report.kind = "on_demand"; toast("Report written"); }
    catch (err) { toast("Report failed: " + err.message); }
    if (S.tab === "analyst") renderAnalyst();
  });
}

// ---------------------------------------------------------------- SYSTEM
async function renderSystem() {
  const el = $(".screen[data-screen=system]");
  const f = Object.values(S.ov.freshness).sort((a, b) => `${a.source}/${a.job}`.localeCompare(`${b.source}/${b.job}`));
  const up = S.charts[S.range]?.uptime_1h || {};
  const hourNow = Math.floor(nowS() / 3600) * 3600;
  const NAMES = { "geckoterminal/new_pools": "New launches", "geckoterminal/active_pools": "Most-traded tokens", "geckoterminal/refresh": "Token trading stats",
    "solana_rpc/bonding_curves": "Bonding curves", "solana_rpc/deployers": "Deployer wallets", "dexscreener/boosts_profiles": "Paid promotion",
    "defillama/launchpad_volume": "Launchpad volume", "x_api/recent_search": "X posts", "reddit/new_posts": "Reddit posts",
    "pumpfun/latest_coins": "pump.fun API", "bitquery/net_flow": "Net flow (Bitquery)", "outcomes/label": "Outcome labelling" };
  const STATE = { fresh: ["pos", "●", "Fresh"], degraded: ["warn", "▲", "Degraded"], stale: ["warn", "▲", "Stale"], expired: ["neg", "✕", "Expired"],
    unavailable: ["neg", "✕", "Unavailable"], error: ["neg", "✕", "Error"], skipped: ["mute", "○", "Not configured"] };
  const srcRows = f.map((x) => {
    const k = `${x.source}/${x.job}`, cells = new Map((up[k] || []).map((c) => [c[0], c]));
    let okH = 0, seen = 0;
    const strip = Array.from({ length: 24 }, (_, i) => {
      const b = hourNow - (23 - i) * 3600, c = cells.get(b);
      if (!c) return `<i title="${esc(hhmm(b))}: no runs"></i>`;
      seen++; if (c[1] && !c[2]) okH++;
      const cls = c[3] && !c[1] && !c[2] ? "skip" : c[2] && !c[1] ? "bad" : c[2] ? "mix" : "ok";
      return `<i class="${cls}" title="${esc(hhmm(b))}: ${c[1]} ok, ${c[2]} failed"></i>`;
    }).join("");
    const st = STATE[x.state] || ["mute", "○", x.state];
    return `<div class="src"><span class="nm">${esc(NAMES[k] || k)} <span class="muted mono" style="font-size:11px;font-weight:400">${esc(k)}</span></span>${chip(st[0], st[1], st[2])}
      <span class="meta">last success ${esc(x.last_ok ? ago(nowS() - x.last_ok) : "never")} · every ${esc(Math.round(x.expected_every_s / 60))} min${seen ? ` · ${okH} of ${seen} hours error-free` : ""}</span>
      ${x.last_error && x.state !== "fresh" ? `<span class="err">${esc(x.last_error)}</span>` : ""}<div class="strip" aria-label="last 24 hours">${strip}</div></div>`;
  }).join("");
  const h = S.ov.context.history || {}, cfg = S.ov.config, bt = S.ov.backtest, db = S.ov.db;
  const btRows = bt ? Object.entries(bt.by_verdict).map(([v, r]) => `<tr><td>${vchip(v)}</td><td class="r">${r.signals}</td>
    <td class="r">${isNum(r.mean_grad_lift) ? signed(r.mean_grad_lift * 100, 2, " pp") : "—"}</td><td class="r">${isNum(r.false_positive_rate) ? pct(r.false_positive_rate) : "—"}</td></tr>`).join("") : "";
  const yes = (v) => (v ? chip("pos", "●", "On") : chip("mute", "○", "Off"));
  el.innerHTML = `<div class="stag">
    <div class="section"><div class="sh"><h2>Data sources</h2><span class="aside">last 24h, hourly</span></div>
      <div class="card flush">${srcRows || `<div class="empty">No collection runs yet.</div>`}</div></div>
    <div class="section grid split">
      <div class="card"><div class="sh"><h2>History & coverage</h2></div><dl class="kv">
        <dt>Launch coverage, last 6h</dt><dd>${pct(h.launch_coverage_6h)}</dd>
        <dt>Baseline coverage, prior 24h</dt><dd>${pct(h.launch_coverage_baseline)}</dd>
        <dt>Social history</dt><dd>${isNum(h.social_history_h) ? nf(h.social_history_h, 1) + "h" : "—"}</dd>
        <dt>Tokens tracked</dt><dd>${compact(db.tokens)}</dd><dt>Observations</dt><dd>${compact(db.token_obs)}</dd>
        <dt>Curve reads</dt><dd>${compact(db.curve_obs)}</dd><dt>Graduations seen</dt><dd>${compact(db.graduations)}</dd>
        <dt>Outcomes labelled</dt><dd>${compact(db.token_outcomes)}</dd></dl></div>
      <div class="card"><div class="sh"><h2>Backtest</h2>${bt ? chip(bt.validated ? "pos" : "warn", bt.validated ? "●" : "▲", bt.validated ? "Validated" : "Not validated") : ""}</div>
        ${bt ? `<p class="sec" style="font-size:13px;margin:0 0 10px">${esc(bt.verdict)}. ${bt.signals} signals over ${bt.steps} steps, run ${esc(ago(nowS() - bt.created_at))}.</p>
          <table class="tbl"><thead><tr><th>Verdict</th><th class="r">Signals</th><th class="r">Grad. lift</th><th class="r">False pos.</th></tr></thead><tbody>${btRows}</tbody></table>
          <p class="attrib">Lift = later launches in the meta vs all launches in the same window. Needs ≥30 favorable signals to validate.</p>`
          : `<p class="sec" style="font-size:13px;margin:0">No backtest yet. It needs outcomes, which start ~30h after collection begins.</p>`}
        <button class="btn" id="runbt" style="margin-top:12px">Run backtest (3 days)</button></div></div>
    <div class="section grid split">
      <div class="card"><div class="sh"><h2>Recent alerts</h2></div><div id="alerts"><div class="sk" style="height:60px"></div></div></div>
      <div class="card"><div class="sh"><h2>Integrations</h2></div><dl class="kv">
        <dt>X API</dt><dd>${yes(cfg.x_api)}</dd><dt>Reddit OAuth</dt><dd>${yes(cfg.reddit_oauth)}</dd><dt>Bitquery</dt><dd>${yes(cfg.bitquery)}</dd>
        <dt>Claude analyst</dt><dd>${yes(cfg.anthropic_analyst)}</dd><dt>Telegram</dt><dd>${yes(cfg.telegram)}</dd>
        <dt>Solana RPC</dt><dd class="sec">${esc(cfg.solana_rpc)}</dd></dl>
        <p class="attrib">Keys live in your settings file, never in this page. To install on iPhone: Share → Add to Home Screen.</p></div></div></div>`;
  $("#runbt").addEventListener("click", async (e) => {
    const b = e.currentTarget; b.disabled = true; b.textContent = "Running…";
    try { await api("/api/backtests?days=3", { method: "POST" }); toast("Backtest finished"); await load({ quiet: true }); }
    catch (err) { toast("Backtest failed: " + err.message); b.disabled = false; b.textContent = "Run backtest (3 days)"; }
  });
  try {
    const al = await api("/api/alerts?limit=8");
    const box = $("#alerts");
    if (box) box.innerHTML = al.length ? al.map((a) => `<div class="post"><div class="by">${esc(dayhm(a.created_at))} · ${esc(a.kind.replace("_", " "))} · ${a.delivered ? "sent to Telegram" : "logged"}</div>
      ${esc(a.message.replace("TRENCH//RADAR alert\n", "").split("\n\nResearch")[0])}</div>`).join("") : `<p class="muted" style="font-size:13px;margin:0">No alerts yet. They fire on verdict changes, large score moves and outages.</p>`;
  } catch (_) { const box = $("#alerts"); if (box) box.innerHTML = `<p class="muted">Alerts unavailable.</p>`; }
}

// ---------------------------------------------------------------- boot
window.addEventListener("scroll", () => $("#topbar").classList.toggle("scrolled", scrollY > 4), { passive: true });
$("#refresh").addEventListener("click", () => load());
let resizeT;
window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => { if (S.ov && !$("#sheet").classList.contains("on")) render(); }, 150); });
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && Date.now() - S.lastOk > 60000) load({ quiet: true }); });
setInterval(() => { if (document.visibilityState === "visible" && !S.loading) load({ quiet: true }); }, 120000);
setTimeout(() => document.body.classList.remove("intro"), 1200);   // entrance stagger plays once
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "127.0.0.1" || location.hostname === "localhost")) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
let startTab = (location.hash.match(/^#\/(\w+)/) || [])[1];
try { startTab = startTab || localStorage.getItem("radar-tab"); } catch (_) { /* ignore */ }
go(startTab || "overview", { push: false });
load();
