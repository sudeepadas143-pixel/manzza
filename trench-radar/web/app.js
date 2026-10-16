// TRENCH//RADAR dashboard. Token names and posts are attacker-controlled: everything
// user-derived goes through esc() before it touches innerHTML.
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
const usd = (v) => (v === null || v === undefined ? "—" : "$" + (Math.abs(v) >= 1e6 ? fmt(v / 1e6, 1) + "M" : Math.abs(v) >= 1e3 ? fmt(v / 1e3, 1) + "k" : fmt(v, 0)));
const pct = (v, d = 0) => (v === null || v === undefined ? "—" : fmt(v * 100, d) + "%");
const ago = (s) => (s === null || s === undefined ? "never" : s < 90 ? `${s}s` : s < 5400 ? `${Math.round(s / 60)}m` : `${fmt(s / 3600, 1)}h`);
const utc = (t) => new Date(t * 1000).toISOString().slice(0, 16).replace("T", " ");

let token = null;
try { token = sessionStorage.getItem("radar-token"); } catch (_) { /* storage blocked */ }
let state = null;
let selected = null;

async function api(path, opts = {}) {
  const headers = token ? { "x-radar-token": token } : {};
  const r = await fetch(path, { ...opts, headers });
  if (r.status === 401) {
    token = prompt("Dashboard token");
    try { sessionStorage.setItem("radar-token", token || ""); } catch (_) { /* ignore */ }
    return api(path, opts);
  }
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

// status = good | warning | serious | critical | muted; always icon + label, never colour alone
const STATUS_ICON = { good: "●", warning: "▲", serious: "◆", critical: "✕", muted: "○" };
const status = (kind, label) => `<span class="st st-${kind}">${STATUS_ICON[kind]} ${esc(label)}</span>`;
const VERDICT = { favorable: "good", mixed: "warning", unfavorable: "critical", "insufficient data": "muted" };
const FRESH = { fresh: "good", degraded: "warning", stale: "serious", expired: "critical", unavailable: "critical", error: "critical", skipped: "muted" };

function renderSources(fresh, cfg) {
  const items = Object.values(fresh).sort((a, b) => a.source.localeCompare(b.source));
  $("#sources").innerHTML = items.map((f) => {
    const why = f.state === "skipped" ? "not configured" : f.state;
    return `<span class="chip" title="${esc(f.last_error || "")}">${status(FRESH[f.state] || "muted", `${f.source}/${f.job}`)}
      <span class="age">${esc(why)} · ${f.last_ok ? ago(f.age_s) + " ago" : "no data"}</span></span>`;
  }).join("") + `<span class="chip">${status(cfg.anthropic_analyst ? "good" : "muted", "AI analyst")}<span class="age">${cfg.anthropic_analyst ? esc(cfg.analyst_model) : "rules fallback"}</span></span>`
    + `<span class="chip">${status(cfg.telegram ? "good" : "muted", "Telegram")}<span class="age">${cfg.telegram ? "on" : "not configured"}</span></span>`;
}

function tile(k, v, s = "") {
  return `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${v}</div><div class="s">${esc(s)}</div></div>`;
}

function renderMarket(m) {
  const x = m.metrics;
  const regime = m.regime ? status({ hot: "good", neutral: "warning", cold: "critical" }[m.regime], m.regime) : status("muted", "unknown");
  $("#market-tiles").innerHTML = [
    tile("Regime", regime, m.score !== null ? `score ${fmt(m.score, 2)} · coverage ${pct(m.coverage)}` : "not enough data"),
    tile("Launchpad vol 7d vs 30d", x.pumpfun_launchpad_vol_7d_vs_30d ? fmt(x.pumpfun_launchpad_vol_7d_vs_30d, 2) + "×" : "—", x.pumpfun_launchpad_vol_7d_avg_usd ? usd(x.pumpfun_launchpad_vol_7d_avg_usd) + "/day avg" : ""),
    tile("Launches / hour", x.launches_est_per_h ?? "—", `observed ${x.launches_observed_1h ?? 0} · coverage ${pct(x.launch_coverage_1h)}`),
    tile("Graduation rate", x.graduation_rate_24_48h_cohort !== undefined ? pct(x.graduation_rate_24_48h_cohort, 2) : "—", x.graduation_cohort_n ? `cohort n=${x.graduation_cohort_n}` : "needs 24h+ history"),
    tile("Top traded: median 24h", x.active_median_chg_h24_pct !== undefined ? fmt(x.active_median_chg_h24_pct, 0) + "%" : "—", "bonding-curve tokens with most trades"),
    tile("Top traded: < 24h old", pct(x.active_share_under_24h), "rotation into new launches"),
    tile("SOL", x.sol_price_usd ? "$" + fmt(x.sol_price_usd, 2) : "—", x.sol_chg_24h !== undefined ? `${pct(x.sol_chg_24h, 1)} 24h` : ""),
    tile("PumpSwap vol 7d vs 30d", x.pumpswap_vol_7d_vs_30d ? fmt(x.pumpswap_vol_7d_vs_30d, 2) + "×" : "—", "post-graduation trading"),
  ].join("");
  $("#market-notes").innerHTML = (m.notes || []).map((n) => `<li>${esc(n)}</li>`).join("");
  let series = [];
  try { series = JSON.parse((x.pumpfun_launchpad_daily_series || "[]").replace(/'/g, '"')); } catch (_) { series = []; }
  barChart($("#vol-chart"), series.map(([t, v]) => ({ x: t, y: v, label: utc(t).slice(5, 10) })), usd);
}

// single-series bar chart, one hue, hover tooltip, recessive grid
function barChart(el, pts, yfmt) {
  if (!pts.length) { el.innerHTML = `<p class="muted">No data yet.</p>`; return; }
  const W = el.clientWidth || 600, Hh = el.clientHeight || 180, pad = { l: 44, r: 4, t: 8, b: 18 };
  const max = Math.max(...pts.map((p) => p.y)) * 1.08 || 1;
  const bw = (W - pad.l - pad.r) / pts.length;
  const y = (v) => pad.t + (Hh - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, max / 2, max].map((v) => `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${pad.l - 4}" y="${y(v) + 3}" text-anchor="end">${esc(yfmt(v))}</text>`).join("");
  const bars = pts.map((p, i) => {
    const x0 = pad.l + i * bw + 1, h = Math.max(1, Hh - pad.b - y(p.y));
    return `<rect class="bar" data-i="${i}" x="${x0}" y="${y(p.y)}" width="${Math.max(1, bw - 2)}" height="${h}" rx="2"/>`;
  }).join("");
  const lbl = pts.map((p, i) => (i % Math.ceil(pts.length / 6) === 0 ? `<text class="axis" x="${pad.l + i * bw + bw / 2}" y="${Hh - 4}" text-anchor="middle">${esc(p.label)}</text>` : "")).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none">${ticks}${bars}${lbl}
    <rect x="${pad.l}" y="0" width="${W - pad.l}" height="${Hh}" fill="transparent" class="hit"/></svg><div class="tip" hidden></div>`;
  const tip = el.querySelector(".tip"), svg = el.querySelector("svg");
  svg.addEventListener("mousemove", (e) => {
    const r = svg.getBoundingClientRect();
    const i = Math.min(pts.length - 1, Math.max(0, Math.floor(((e.clientX - r.left) * (W / r.width) - pad.l) / bw)));
    svg.querySelectorAll(".bar").forEach((b) => b.classList.toggle("on", +b.dataset.i === i));
    tip.hidden = false;
    tip.textContent = `${pts[i].label}  ${yfmt(pts[i].y)}`;
    tip.style.left = `${((pad.l + i * bw + bw / 2) / W) * r.width}px`;
    tip.style.top = `${(y(pts[i].y) / Hh) * r.height}px`;
  });
  svg.addEventListener("mouseleave", () => { tip.hidden = true; svg.querySelectorAll(".bar.on").forEach((b) => b.classList.remove("on")); });
}

function lineChart(el, pts, yfmt) {
  if (pts.length < 2) { el.innerHTML = `<p class="muted">Score history appears after a few analysis runs.</p>`; return; }
  const W = el.clientWidth || 500, Hh = el.clientHeight || 140, pad = { l: 30, r: 6, t: 8, b: 16 };
  const xs = pts.map((p) => p.x), x0 = Math.min(...xs), x1 = Math.max(...xs) || x0 + 1;
  const X = (v) => pad.l + (W - pad.l - pad.r) * ((v - x0) / (x1 - x0 || 1));
  const Y = (v) => pad.t + (Hh - pad.t - pad.b) * (1 - v / 100);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p.x)},${Y(p.y)}`).join("");
  const grid = [0, 50, 100].map((v) => `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${pad.l - 4}" y="${Y(v) + 3}" text-anchor="end">${v}</text>`).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none">${grid}<path class="line" d="${d}"/>
    <circle r="4" fill="var(--accent)" stroke="var(--bg)" stroke-width="2" hidden/></svg><div class="tip" hidden></div>`;
  const svg = el.querySelector("svg"), tip = el.querySelector(".tip"), dot = svg.querySelector("circle");
  svg.addEventListener("mousemove", (e) => {
    const r = svg.getBoundingClientRect(), mx = (e.clientX - r.left) * (W / r.width);
    let best = 0;
    pts.forEach((p, i) => { if (Math.abs(X(p.x) - mx) < Math.abs(X(pts[best].x) - mx)) best = i; });
    const p = pts[best];
    dot.setAttribute("cx", X(p.x)); dot.setAttribute("cy", Y(p.y)); dot.hidden = false;
    tip.hidden = false; tip.textContent = `${utc(p.x).slice(5)}  ${yfmt(p.y)}`;
    tip.style.left = `${(X(p.x) / W) * r.width}px`; tip.style.top = `${(Y(p.y) / Hh) * r.height}px`;
  });
  svg.addEventListener("mouseleave", () => { tip.hidden = true; dot.hidden = true; });
}

function scorebar(s) {
  if (s === null || s === undefined) return "—";
  return `<span class="scorebar"><b><i style="width:${Math.max(2, Math.min(100, s))}%"></i></b>${fmt(s, 0)}</span>`;
}

function renderMetas(metas) {
  const tb = $("#metas tbody");
  if (!metas.length) {
    tb.innerHTML = `<tr><td colspan="10" class="muted">No metas detected yet. Collection needs a few cycles (launches every 3 min).</td></tr>`;
    return;
  }
  tb.innerHTML = metas.map((m, i) => {
    const e = m.evidence, d = e.demand, l = e.launch, sat = e.saturation.index;
    return `<tr data-i="${i}" class="${selected === m.meta_key ? "sel" : ""}">
      <td><strong>${esc(m.meta_key)}</strong><div class="terms">${esc(m.terms.slice(1, 5).join(" · "))}</div></td>
      <td>${scorebar(m.score)}</td><td class="num">${fmt(m.confidence, 2)}</td>
      <td>${status(VERDICT[m.verdict] || "muted", m.verdict)}</td>
      <td style="white-space:normal;min-width:180px">${esc(m.hype_check)}</td>
      <td class="num">${l.launches_1h} / ${l.launches_6h}</td>
      <td class="num">${fmt(d.unique_buyers_h1_sum)}</td><td class="num">${pct(d.buyer_share_h1)}</td>
      <td class="num">${d.curve_net_sol_1h === null ? "—" : fmt(d.curve_net_sol_1h, 1) + " SOL"}</td>
      <td class="num">${sat === null ? "—" : fmt(sat, 2)}</td></tr>`;
  }).join("");
  tb.querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => showDetail(metas[+tr.dataset.i])));
}

function compRow(name, v, w) {
  const val = v === null || v === undefined;
  return `<div class="comp"><span>${esc(name)} <span class="muted">×${w}</span></span>
    ${val ? `<span class="na">no data — excluded, weight renormalised</span>` : `<div class="track"><i style="width:${v * 100}%"></i></div>`}
    <span class="mono">${val ? "" : fmt(v, 2)}</span></div>`;
}

async function showDetail(m) {
  selected = m.meta_key;
  document.querySelectorAll("#metas tbody tr").forEach((tr) => tr.classList.toggle("sel", state.metas[+tr.dataset.i]?.meta_key === selected));
  const e = m.evidence, d = e.demand, s = e.social, l = e.launch, cf = m.confidence_factors;
  const parts = (o) => Object.entries(o || {}).map(([k, v]) => `${esc(k)} ${fmt(v, 2)}`).join(" · ");
  const sig = Object.entries(e.saturation.signals).map(([k, v]) => `<li><strong>${esc(k)}</strong> ${fmt(v.s, 2)} — ${esc(v.why)}</li>`).join("") || "<li class='muted'>no saturation signal has enough data</li>";
  const tokens = d.top_tokens.map((t) => `<tr>
      <td><a href="https://pump.fun/coin/${encodeURIComponent(t.mint)}" target="_blank" rel="noopener noreferrer">${esc(t.symbol || t.mint.slice(0, 6))}</a> <span class="terms">${esc((t.name || "").slice(0, 28))}</span></td>
      <td class="num">${t.age_h ?? "—"}h</td><td class="num">${fmt(t.buyers_h1)}/${fmt(t.sellers_h1)}</td>
      <td class="num">${usd(t.vol_h1)}</td><td class="num">${usd(t.vol_h24)}</td><td class="num">${usd(t.mcap_usd)}</td>
      <td class="num">${t.graduated ? "graduated" : t.progress === null || t.progress === undefined ? "—" : pct(t.progress)}</td>
      <td><a href="https://dexscreener.com/solana/${encodeURIComponent(t.mint)}" target="_blank" rel="noopener noreferrer">chart</a></td></tr>`).join("");
  const posts = (s.influential_posts || []).map((p) => `<div class="post"><div class="meta">@${esc(p.author)} · ${fmt(p.followers)} followers · engagement ${fmt(p.engagement)} · <a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">open</a></div>${esc(p.text)}</div>`).join("");
  const el = $("#detail");
  el.hidden = false;
  el.innerHTML = `<h3>${esc(m.meta_key)} <span class="terms">${esc(m.terms.join(", "))}</span></h3>
    <div>${status(VERDICT[m.verdict] || "muted", m.verdict)} · score <strong class="mono">${fmt(m.score, 1)}</strong>
      · confidence <span class="mono">${fmt(m.confidence, 2)}</span>
      <span class="muted">(weights with data ${pct(cf.weight_coverage)}, sample ${fmt(cf.sample, 2)}, freshness ${fmt(cf.freshness, 2)}, history ${fmt(cf.history, 2)}${cf.social_measured ? "" : ", social not measured"})</span>
      ${m.validated ? "" : `<span class="muted"> · unvalidated</span>`}</div>
    <div class="grid2">
      <div><h4>Score components</h4>
        ${compRow("attention", m.components.attention, m.weights.attention)}
        <div class="terms" style="margin-left:4px">${parts(m.component_parts.attention)}</div>
        ${compRow("demand", m.components.demand, m.weights.demand)}
        <div class="terms" style="margin-left:4px">${parts(m.component_parts.demand)}</div>
        ${compRow("market", m.components.market, m.weights.market)}
        ${compRow("freshness", m.components.freshness, m.weights.freshness)}
        <h4>Score history</h4><div id="hist" class="chart" style="height:130px"></div></div>
      <div><h4>Why it scores</h4><ul class="list reasons">${m.reasons.map((r) => `<li>${esc(r)}</li>`).join("") || "<li class='muted'>no strong positive evidence</li>"}</ul>
        <h4>Risks</h4><ul class="list risks">${m.risks.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>
    </div>
    <div class="grid2">
      <div><h4>Launch activity</h4><ul class="list">
        <li>${l.launches_1h} launches last hour, ${l.launches_6h} in 6h, ${l.launches_base_24h} in the prior 24h (baseline ${fmt(l.launch_base_rate_h, 1)}/h)</li>
        <li>acceleration z ${l.launch_accel_z ?? "— (baseline not established)"}; ${pct(l.launch_share_6h, 1)} of all launches in 6h</li>
        <li>${pct(l.duplicate_symbol_share_6h)} reuse a ticker; serial deployers: ${e.creators.serial_share === null ? "unknown" : pct(e.creators.serial_share)} (${e.creators.known} known)</li>
        <li>paid attention 24h: ${e.attention_purchased.boosts_24h} boosted, ${e.attention_purchased.profiles_24h} profiled (DexScreener)</li></ul></div>
      <div><h4>Buying demand</h4><ul class="list">
        <li>${d.tokens_tracked} tokens with fresh stats · ${fmt(d.unique_buyers_h1_sum)} buyers / ${fmt(d.unique_sellers_h1_sum)} sellers last hour (summed)</li>
        <li>volume ${usd(d.vol_h1_usd)} 1h · ${usd(d.vol_h24_usd)} 24h · top token ${pct(d.top_token_share_vol24)} of 24h volume</li>
        <li>net SOL into curves 1h: ${d.curve_net_sol_1h === null ? "—" : fmt(d.curve_net_sol_1h, 2)} (${d.curve_tokens_compared} curves compared) · net USD flow ${d.net_flow_usd_h1 === null ? "— (needs Bitquery)" : usd(d.net_flow_usd_h1)}</li>
        <li>${d.tokens_over_50pct} curves past 50% · ${d.graduations_24h} graduated in 24h</li></ul></div>
    </div>
    <h4>Top related tokens</h4>
    <div class="table-wrap"><table><thead><tr><th>Token</th><th class="num">Age</th><th class="num">Buyers/sellers 1h</th><th class="num">Vol 1h</th><th class="num">Vol 24h</th><th class="num">Mcap</th><th class="num">Curve</th><th></th></tr></thead><tbody>${tokens || "<tr><td colspan='8' class='muted'>no fresh token stats</td></tr>"}</tbody></table></div>
    <div class="grid2">
      <div><h4>Social</h4>${cf.social_measured ? `<ul class="list"><li>${s.mentions_1h} mentions last hour, ${s.mentions_6h} in 6h · ${s.independent_authors_6h} independent accounts · ${s.copy_paste_posts_6h} copy-paste posts</li>
        <li>sentiment ${fmt(s.sentiment_6h, 2)} (−1..1) · ${esc(Object.entries(s.sentiment_labels || {}).map(([k, v]) => k + " " + v).join(", "))}</li></ul>${posts}` : `<p class="muted">Social sources are not connected. Add X_BEARER_TOKEN or Reddit OAuth (see SETUP.md).</p>`}</div>
      <div><h4>Saturation signals</h4><ul class="list">${sig}</ul></div>
    </div>`;
  try {
    const hist = await api(`/api/metas/${encodeURIComponent(m.meta_key)}/history?hours=48`);
    lineChart($("#hist"), hist.filter((h) => h.score !== null).map((h) => ({ x: h.computed_at, y: h.score })), (v) => fmt(v, 0));
  } catch (_) { $("#hist").textContent = "history unavailable"; }
}

function renderBacktest(bt) {
  const el = $("#backtest");
  $("#validation").textContent = bt && bt.validated ? "(validated by the latest backtest)" : "(not yet validated against outcomes)";
  if (!bt) { el.innerHTML = `<p class="muted">No backtest yet. Run <code>python -m radar backtest</code> once outcomes exist (24h+ of collection).</p>`; return; }
  const rows = Object.entries(bt.by_verdict).map(([v, r]) => `<tr><td>${status(VERDICT[v] || "muted", v)}</td><td class="num">${r.signals}</td>
    <td class="num">${r.mean_grad_lift === null ? "—" : fmt(r.mean_grad_lift * 100, 2) + " pp"}</td>
    <td class="num">${r.mean_net_positive_lift === null ? "—" : fmt(r.mean_net_positive_lift * 100, 1) + " pp"}</td>
    <td class="num">${r.false_positive_rate === null ? "—" : pct(r.false_positive_rate)}</td></tr>`).join("");
  el.innerHTML = `<p>${status(bt.validated ? "good" : "warning", bt.validated ? "validated" : "not validated")} <span class="muted">${esc(bt.verdict)} · ${bt.signals} signals over ${bt.steps} steps · run ${utc(bt.created_at)}</span></p>
    <div class="table-wrap"><table><thead><tr><th>Verdict</th><th class="num">Signals</th><th class="num">Graduation lift</th><th class="num">Net-positive lift</th><th class="num">False positives</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="hint">Lift = later launches in the meta vs all launches in the same window. Graduation and profitability are measured separately.</p>`;
}

async function renderSide() {
  try {
    const rep = await api("/api/reports/latest");
    if (rep) $("#report").textContent = rep.body;
  } catch (_) { /* keep placeholder */ }
  try {
    const al = await api("/api/alerts?limit=15");
    $("#alerts").innerHTML = al.length ? al.map((a) => `<li><span class="mono muted">${utc(a.created_at)}</span> ${status(a.delivered ? "good" : "muted", a.delivered ? "sent" : "logged")} ${esc(a.message.replace("TRENCH//RADAR alert\n", ""))}</li>`).join("") : `<li class="muted">No alerts yet.</li>`;
  } catch (_) { /* ignore */ }
}

async function load() {
  $("#btn-refresh").disabled = true;
  try {
    state = await api("/api/overview");
    $("#asof").textContent = `as of ${utc(state.as_of)} UTC · model ${state.model_version} · ${fmt(state.db.tokens)} tokens · ${fmt(state.db.token_obs)} observations`;
    renderSources(state.freshness, state.config);
    renderMarket(state.market);
    renderMetas(state.metas);
    renderBacktest(state.backtest);
    if (selected) { const m = state.metas.find((x) => x.meta_key === selected); if (m) showDetail(m); }
    renderSide();
  } catch (e) {
    $("#asof").textContent = "failed to load: " + e.message;
  } finally { $("#btn-refresh").disabled = false; }
}

$("#btn-refresh").addEventListener("click", load);
$("#btn-report").addEventListener("click", async () => {
  const b = $("#btn-report"); b.disabled = true; b.textContent = "Writing…";
  try { const r = await api("/api/reports", { method: "POST" }); $("#report").textContent = r.body; }
  catch (e) { $("#report").textContent = "Report failed: " + e.message; }
  finally { b.disabled = false; b.textContent = "Write report"; }
});
load();
setInterval(load, 120000);
