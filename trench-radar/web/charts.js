// SVG chart kit for TRENCH//RADAR, drawn as print: ink lines, halftone areas, hatched gaps
// where the collector was not running. Axes are labelled; every data string goes through esc().
// In Low visual mode tooltips follow taps/clicks only (no per-frame pointer tracking).
"use strict";

const Charts = (() => {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const low = () => document.documentElement.dataset.perf === "low";
  const tip = () => document.getElementById("tip");

  function niceMax(v) {
    if (!(v > 0)) return 1;
    const p = 10 ** Math.floor(Math.log10(v)), m = v / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
  }
  const hhmm = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const dayhm = (t) => new Date(t * 1000).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false });

  function showTip(html, x, y) {
    const el = tip();
    el.innerHTML = html;
    const w = el.offsetWidth || 180;
    el.style.left = `${Math.max(w / 2 + 10, Math.min(window.innerWidth - w / 2 - 10, x))}px`;
    el.style.top = `${Math.max(80, y)}px`;
    el.classList.add("on");
  }
  function hideTip() { tip().classList.remove("on"); }

  function track(svg, W, H, pick) {
    const move = (e) => {
      const r = svg.getBoundingClientRect();
      const hit = pick(((e.clientX - r.left) / r.width) * W);
      if (!hit) { svg.classList.remove("tracking"); return hideTip(); }
      svg.classList.add("tracking");
      showTip(hit.html, r.left + (hit.x / W) * r.width, r.top + (hit.y / H) * r.height);
    };
    const off = () => { svg.classList.remove("tracking"); hideTip(); };
    if (!low()) svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerdown", move);
    svg.addEventListener("pointerleave", off);
    svg.addEventListener("pointercancel", off);
  }

  function timeTicks(from, to, W, padL, padR, xOf, y) {
    const span = to - from;
    const step = span <= 1800 ? 300 : span <= 3 * 3600 ? 900 : span <= 6 * 3600 ? 3600 : span <= 26 * 3600 ? 4 * 3600 : 12 * 3600;
    let out = "";
    for (let t = Math.ceil(from / step) * step; t <= to; t += step) {
      const x = xOf(t);
      if (x < padL + 16 || x > W - padR - 16) continue;
      out += `<line class="grid-x" x1="${x}" x2="${x}" y1="${y - 13}" y2="${y - 10}" stroke="currentColor"/><text class="ax" x="${x}" y="${y}" text-anchor="middle">${esc(span > 30 * 3600 ? dayhm(t).replace(/:00$/, "") : hhmm(t))}</text>`;
    }
    return out;
  }
  const yAxis = (ticks, yOf, x, fmt) => ticks.map((v) => `<text class="ax" x="${x}" y="${yOf(v) + 3.5}" text-anchor="end">${esc(fmt(v))}</text>`).join("");
  const grid = (ticks, yOf, x1, x2) => `<g class="grid">${ticks.slice(1).map((v) => `<line x1="${x1}" x2="${x2}" y1="${yOf(v)}" y2="${yOf(v)}"/>`).join("")}</g>`;

  /** Bars on a time axis. Buckets the collector never observed are hatched, not drawn as zero. */
  function timeBars(el, { data, from, to, step, observed, height = 168, fmtY = (v) => v, label = "", unit = "", cls = "" }) {
    const W = Math.max(280, el.clientWidth), H = height, pad = { l: 40, r: 4, t: 8, b: 22 };
    const max = niceMax(Math.max(1, ...data.map((d) => d[1])));
    const n = Math.max(1, Math.round((to - from) / step)), bw = (W - pad.l - pad.r) / n;
    const xOf = (t) => pad.l + ((t - from) / (to - from)) * (W - pad.l - pad.r);
    const yOf = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
    const map = new Map(data.map((d) => [d[0], d[1]])), obs = observed ? new Set(observed) : null;
    let bars = "", gaps = "";
    for (let i = 0; i < n; i++) {
      const b = Math.floor((from + i * step) / step) * step, x = xOf(b) + 0.5, w = Math.max(1, bw - (bw > 5 ? 2 : 0.6)), v = map.get(b);
      if (v) bars += `<rect class="bar ${cls}" x="${x}" y="${yOf(v)}" width="${w}" height="${H - pad.b - yOf(v)}"/>`;
      else if (obs && !obs.has(b)) gaps += `<rect class="gap" x="${x}" y="${pad.t}" width="${w}" height="${H - pad.t - pad.b}"/>`;
    }
    const ticks = [0, max / 2, max];
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${esc(label)}">${grid(ticks, yOf, pad.l, W - pad.r)}
      ${gaps}${bars}<line class="base" x1="${pad.l}" x2="${W - pad.r}" y1="${H - pad.b + 0.5}" y2="${H - pad.b + 0.5}"/>${yAxis(ticks, yOf, pad.l - 8, fmtY)}${timeTicks(from, to, W, pad.l, pad.r, xOf, H - 5)}
      <line class="xh" y1="${pad.t}" y2="${H - pad.b}" x1="-9" x2="-9"/></svg>`;
    const svg = el.querySelector("svg"), xh = svg.querySelector(".xh");
    track(svg, W, H, (mx) => {
      const i = Math.floor((mx - pad.l) / bw);
      if (i < 0 || i >= n) return null;
      const b = Math.floor((from + i * step) / step) * step, v = map.get(b), cx = xOf(b) + bw / 2;
      xh.setAttribute("x1", cx); xh.setAttribute("x2", cx);
      const missing = obs && !obs.has(b) && !v;
      return { x: cx, y: v ? yOf(v) : pad.t + 20, html: `<div class="k">${esc(hhmm(b))} – ${esc(hhmm(b + step))}</div>` +
        (missing ? `<b>Not observed</b><div class="k">the collector was not running</div>` : `<b>${esc(fmtY(v || 0))}</b><div class="k">${esc(unit)}</div>`) };
    });
  }

  /** Seismograph: launches as one continuous trace (halftone below), graduations as a rug of ticks
   *  underneath. Unobserved spans are hatched and break the trace instead of reading as zero. */
  function seismo(el, { data, from, to, step, observed, grads = [], gstep, height = 230, fmtY = (v) => v, label = "" }) {
    const rug = grads.length ? 30 : 0, W = Math.max(300, el.clientWidth), H = height, pad = { l: 40, r: 6, t: 10, b: 22 + rug };
    const max = niceMax(Math.max(1, ...data.map((d) => d[1])));
    const xOf = (t) => pad.l + ((t - from) / (to - from)) * (W - pad.l - pad.r);
    const yOf = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
    const map = new Map(data.map((d) => [d[0], d[1]])), obs = observed ? new Set(observed) : null;
    const n = Math.max(1, Math.round((to - from) / step)), bw = (W - pad.l - pad.r) / n;
    let segs = [], cur = [], gaps = "";
    for (let i = 0; i < n; i++) {
      const b = Math.floor((from + i * step) / step) * step, v = map.get(b), seen = !obs || obs.has(b) || v;
      if (!seen) { if (cur.length) segs.push(cur); cur = []; gaps += `<rect class="gap" x="${xOf(b)}" y="${pad.t}" width="${bw}" height="${H - pad.t - pad.b}"/>`; continue; }
      cur.push([xOf(b) + bw / 2, yOf(v || 0), b, v || 0]);
    }
    if (cur.length) segs.push(cur);
    const base = H - pad.b;
    const lines = segs.map((s) => {
      const d = s.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
      return `${low() ? "" : `<path class="area" d="${d}L${s[s.length - 1][0].toFixed(1)},${base}L${s[0][0].toFixed(1)},${base}Z"/>`}<path class="line" d="${d}"/>`;
    }).join("");
    const gmax = Math.max(1, ...grads.map((g) => g[1]));
    const ticks = grads.filter((g) => g[1] > 0 && g[0] >= from && g[0] <= to).map((g) => {
      const x = xOf(g[0] + (gstep || step) / 2), h = 6 + (rug - 12) * (g[1] / gmax);
      return `<line class="rugt" x1="${x}" x2="${x}" y1="${base + rug - 2}" y2="${base + rug - 2 - h}"/>`;
    }).join("");
    const yt = [0, max / 2, max];
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${esc(label)}">${grid(yt, yOf, pad.l, W - pad.r)}${gaps}${lines}
      <line class="base" x1="${pad.l}" x2="${W - pad.r}" y1="${base + 0.5}" y2="${base + 0.5}"/>
      ${rug ? `<text class="axt" x="${pad.l}" y="${base + 14}">graduations</text>${ticks}
      <line class="base" x1="${pad.l}" x2="${W - pad.r}" y1="${base + rug - 1.5}" y2="${base + rug - 1.5}" style="opacity:.4"/>` : ""}
      ${yAxis(yt, yOf, pad.l - 8, fmtY)}${timeTicks(from, to, W, pad.l, pad.r, xOf, H - 5)}
      <line class="xh" y1="${pad.t}" y2="${base + rug}" x1="-9" x2="-9"/><circle class="dot" r="4" cx="-9" cy="-9"/></svg>`;
    const svg = el.querySelector("svg"), xh = svg.querySelector(".xh"), dot = svg.querySelector(".dot");
    const gmap = new Map(grads.map((g) => [g[0], g[1]]));
    track(svg, W, H, (mx) => {
      const i = Math.floor((mx - pad.l) / bw);
      if (i < 0 || i >= n) return null;
      const b = Math.floor((from + i * step) / step) * step, v = map.get(b), cx = xOf(b) + bw / 2;
      xh.setAttribute("x1", cx); xh.setAttribute("x2", cx); dot.setAttribute("cx", cx); dot.setAttribute("cy", yOf(v || 0));
      const gb = gstep ? Math.floor(b / gstep) * gstep : b, g = gmap.get(gb);
      const missing = obs && !obs.has(b) && !v;
      return { x: cx, y: yOf(v || 0), html: `<div class="k">${esc(hhmm(b))} – ${esc(hhmm(b + step))}</div>` +
        (missing ? `<b>Not observed</b><div class="k">collector offline</div>` : `<b>${esc(fmtY(v || 0))} launches</b>${g ? `<div class="k">${g} graduation${g > 1 ? "s" : ""} that ${gstep && gstep !== step ? "hour" : "slot"}</div>` : ""}`) };
    });
  }

  /** Line on a time axis with crosshair; optional dashed reference lines. */
  function timeLine(el, { data, from, to, height = 150, fmtY = (v) => v, yMin, yMax, label = "", refs = [], cls = "" }) {
    if (data.length < 2) { el.innerHTML = `<div class="chart-empty">Not enough observations in this range yet.</div>`; return; }
    const W = Math.max(280, el.clientWidth), H = height, pad = { l: 46, r: 8, t: 10, b: 22 };
    const vals = data.map((d) => d[1]);
    let lo = yMin ?? Math.min(...vals), hi = yMax ?? Math.max(...vals);
    if (hi === lo) { hi += Math.abs(hi) * 0.05 || 1; lo -= Math.abs(lo) * 0.05 || 1; }
    if (yMin === undefined) { const m = (hi - lo) * 0.12; lo -= m; hi += m; }
    from = from ?? data[0][0]; to = to ?? data[data.length - 1][0];
    const xOf = (t) => pad.l + ((t - from) / (to - from || 1)) * (W - pad.l - pad.r);
    const yOf = (v) => pad.t + (H - pad.t - pad.b) * (1 - (v - lo) / (hi - lo));
    const d = data.map((p, i) => `${i ? "L" : "M"}${xOf(p[0]).toFixed(1)},${yOf(p[1]).toFixed(1)}`).join("");
    const area = `${d}L${xOf(data[data.length - 1][0]).toFixed(1)},${H - pad.b}L${xOf(data[0][0]).toFixed(1)},${H - pad.b}Z`;
    const ticks = [lo, (lo + hi) / 2, hi];
    const rl = refs.filter((r) => r.v > lo && r.v < hi).map((r) => `<line class="ref" x1="${pad.l}" x2="${W - pad.r}" y1="${yOf(r.v)}" y2="${yOf(r.v)}"/>
      <text class="reflabel" x="${W - pad.r}" y="${yOf(r.v) - 5}" text-anchor="end">${esc(r.label)}</text>`).join("");
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${esc(label)}">${grid(ticks, yOf, pad.l, W - pad.r)}${rl}
      ${low() ? "" : `<path class="area ${cls}" d="${area}"/>`}<path class="line ${cls}" d="${d}"/>
      <line class="base" x1="${pad.l}" x2="${W - pad.r}" y1="${H - pad.b + 0.5}" y2="${H - pad.b + 0.5}"/>${yAxis(ticks, yOf, pad.l - 8, fmtY)}
      ${timeTicks(from, to, W, pad.l, pad.r, xOf, H - 5)}
      <line class="xh" y1="${pad.t}" y2="${H - pad.b}" x1="-9" x2="-9"/><circle class="dot" r="4" cx="-9" cy="-9"/></svg>`;
    const svg = el.querySelector("svg"), xh = svg.querySelector(".xh"), dot = svg.querySelector(".dot");
    track(svg, W, H, (mx) => {
      let best = 0;
      for (let i = 1; i < data.length; i++) if (Math.abs(xOf(data[i][0]) - mx) < Math.abs(xOf(data[best][0]) - mx)) best = i;
      const p = data[best], cx = xOf(p[0]), cy = yOf(p[1]);
      xh.setAttribute("x1", cx); xh.setAttribute("x2", cx); dot.setAttribute("cx", cx); dot.setAttribute("cy", cy);
      return { x: cx, y: cy, html: `<div class="k">${esc(dayhm(p[0]))}</div><b>${esc(fmtY(p[1]))}</b>` };
    });
  }

  /** Daily bars (launchpad volume); the partial current day is drawn as an outline. */
  function catBars(el, { data, height = 130, fmtY, fmtX, label = "" }) {
    if (!data.length) { el.innerHTML = `<div class="chart-empty">No data yet.</div>`; return; }
    const W = Math.max(240, el.clientWidth), H = height, pad = { l: 46, r: 4, t: 8, b: 22 };
    const max = niceMax(Math.max(...data.map((d) => d[1]))), bw = (W - pad.l - pad.r) / data.length;
    const yOf = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max), ticks = [0, max / 2, max];
    const bars = data.map((d, i) => i === data.length - 1
      ? `<rect x="${pad.l + i * bw + 1.5}" y="${yOf(d[1]) + 0.5}" width="${Math.max(1, bw - 3)}" height="${Math.max(0, H - pad.b - yOf(d[1]) - 0.5)}" fill="url(#hatch)" stroke="var(--ink)" stroke-width="1"/>`
      : `<rect class="bar" x="${pad.l + i * bw + 1}" y="${yOf(d[1])}" width="${Math.max(1, bw - 2)}" height="${H - pad.b - yOf(d[1])}"/>`).join("");
    const every = Math.ceil(data.length / 5);
    const xl = data.map((d, i) => (i % every === 0 ? `<text class="ax" x="${pad.l + i * bw + bw / 2}" y="${H - 5}" text-anchor="middle">${esc(fmtX(d[0]))}</text>` : "")).join("");
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${esc(label)}">${grid(ticks, yOf, pad.l, W - pad.r)}${bars}
      <line class="base" x1="${pad.l}" x2="${W - pad.r}" y1="${H - pad.b + 0.5}" y2="${H - pad.b + 0.5}"/>${yAxis(ticks, yOf, pad.l - 8, fmtY)}${xl}
      <line class="xh" y1="${pad.t}" y2="${H - pad.b}" x1="-9" x2="-9"/></svg>`;
    const svg = el.querySelector("svg"), xh = svg.querySelector(".xh");
    track(svg, W, H, (mx) => {
      const i = Math.floor((mx - pad.l) / bw);
      if (i < 0 || i >= data.length) return null;
      const cx = pad.l + i * bw + bw / 2;
      xh.setAttribute("x1", cx); xh.setAttribute("x2", cx);
      return { x: cx, y: yOf(data[i][1]), html: `<div class="k">${esc(fmtX(data[i][0]))}${i === data.length - 1 ? ", partial day" : ""}</div><b>${esc(fmtY(data[i][1]))}</b>` };
    });
  }

  /** Barometer: a half dial from cold to hot with the needle at the regime score. */
  function dial(el, { score, label = "Market regime" }) {
    const W = 300, H = 168, cx = W / 2, cy = 150, R = 128;
    const pt = (a, r) => [cx + r * Math.cos(Math.PI - a * Math.PI), cy - r * Math.sin(Math.PI - a * Math.PI)];
    const arc = (a0, a1, r) => { const [x0, y0] = pt(a0, r), [x1, y1] = pt(a1, r); return `M${x0},${y0} A${r},${r} 0 0 1 ${x1},${y1}`; };
    let ticks = "";
    for (let i = 0; i <= 40; i++) {
      const a = i / 40, big = i % 10 === 0, [x0, y0] = pt(a, R), [x1, y1] = pt(a, R - (big ? 14 : i % 5 === 0 ? 9 : 5));
      ticks += `<line x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" stroke="var(--ink)" stroke-width="${big ? 1.6 : 0.8}"/>`;
    }
    const zone = (a0, a1, cls) => `<path d="${arc(a0, a1, R + 8)}" fill="none" stroke-width="5" class="${cls}"/>`;
    const lab = (a, t) => { const [x, y] = pt(a, R + 24); return `<text x="${x}" y="${y + 4}" text-anchor="middle" class="ax">${t}</text>`; };
    const s = typeof score === "number" ? Math.max(0, Math.min(1, score)) : null;
    const [nx, ny] = s === null ? [cx, cy] : pt(s, R - 22);
    el.innerHTML = `<svg viewBox="0 -18 ${W} ${H + 26}" role="img" aria-label="${esc(label)}: ${s === null ? "not enough data" : s.toFixed(2)}">
      ${zone(0, 0.38, "z-cold")}${zone(0.38, 0.62, "z-mid")}${zone(0.62, 1, "z-hot")}${ticks}
      ${lab(0.02, "COLD")}${lab(0.5, "NEUTRAL")}${lab(0.98, "HOT")}
      ${s === null ? "" : `<line class="needle" x1="${cx}" y1="${cy}" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" stroke="var(--novel-ink)" stroke-width="3" stroke-linecap="round"/>`}
      <circle cx="${cx}" cy="${cy}" r="7" fill="var(--ink)"/><circle cx="${cx}" cy="${cy}" r="2.5" fill="var(--paper)"/></svg>`;
  }

  /** The keyword-score map: attention (x) against measured buying (y). */
  function narrativeMap(el, { points, height = 360, selected, onPick }) {
    const W = Math.max(300, el.clientWidth), H = height, pad = { l: 44, r: 14, t: 14, b: 40 };
    const xOf = (v) => pad.l + v * (W - pad.l - pad.r), yOf = (v) => pad.t + (1 - v) * (H - pad.t - pad.b);
    const q = 0.55, col = { pos: "var(--buy)", warn: "var(--caution)", neg: "var(--sell)", mute: "var(--ink-3)" };
    const names = [["Organic, ahead of the talk", pad.l + 10, pad.t + 20, "start"], ["Confirmed", W - pad.r - 10, pad.t + 20, "end"],
      ["Cold", pad.l + 10, H - pad.b - 10, "start"], ["Talk without buyers", W - pad.r - 10, H - pad.b - 10, "end"]]
      .map(([t, x, y, a]) => `<text class="axt" x="${x}" y="${y}" text-anchor="${a}">${t}</text>`).join("");
    const frame = `<line class="base" x1="${pad.l}" x2="${W - pad.r}" y1="${H - pad.b}" y2="${H - pad.b}"/><line class="base" x1="${pad.l}" x2="${pad.l}" y1="${pad.t}" y2="${H - pad.b}"/>
      <line class="ref" x1="${xOf(q)}" x2="${xOf(q)}" y1="${pad.t}" y2="${H - pad.b}"/><line class="ref" x1="${pad.l}" x2="${W - pad.r}" y1="${yOf(q)}" y2="${yOf(q)}"/>
      ${[0, 0.25, 0.5, 0.75, 1].map((v) => `<text class="ax" x="${xOf(v)}" y="${H - pad.b + 15}" text-anchor="middle">${v}</text>`).join("")}
      ${[0, 0.5, 1].map((v) => `<text class="ax" x="${pad.l - 8}" y="${yOf(v) + 3.5}" text-anchor="end">${v}</text>`).join("")}
      <text class="axt" x="${(W + pad.l - pad.r) / 2}" y="${H - 6}" text-anchor="middle">Attention: launches named for it${points.some((p) => p.social) ? " and posts about it" : ""}</text>
      <text class="axt" transform="translate(12 ${(H - pad.b + pad.t) / 2}) rotate(-90)" text-anchor="middle">Buying demand</text>`;
    const rad = (p) => Math.max(4, Math.min(12, 3.5 + Math.sqrt(p.buyers || 0) / 3.5));
    const selIdx = points.findIndex((p) => p.key === selected);
    const byScore = points.map((p, i) => i).sort((a, b) => (points[b].score ?? 0) - (points[a].score ?? 0));
    const labelled = new Set(byScore.slice(0, 10)); if (selIdx >= 0) labelled.add(selIdx);
    // labels that would collide with an earlier one are dropped (the selected mark is placed first)
    const boxes = [], shown = new Set();
    for (const i of [selIdx, ...byScore].filter((i) => i >= 0 && labelled.has(i))) {
      if (shown.has(i)) continue;
      const p = points[i], r = rad(p), cx = xOf(p.x), cy = yOf(p.y), w = p.label.length * 7 + 4, left = cx > W * 0.66;
      const lx = left ? cx - r - 6 - w : cx + r + 6, box = [lx, cy - 9, lx + w, cy + 6];
      if (i === selIdx || !boxes.some((o) => box[0] < o[2] && box[2] > o[0] && box[1] < o[3] && box[3] > o[1])) { boxes.push(box); shown.add(i); }
    }
    const marks = points.map((p, i) => {
      const r = rad(p), cx = xOf(p.x), cy = yOf(p.y), c = col[p.tone], sel = i === selIdx, left = cx > W * 0.66;
      return `<g data-i="${i}" style="cursor:pointer"><circle cx="${cx}" cy="${cy}" r="${r + 9}" fill="transparent"/>
        ${p.crowded ? `<circle cx="${cx}" cy="${cy}" r="${r + 4}" fill="none" stroke="var(--caution)" stroke-width="1.2" stroke-dasharray="2 2.5"/>` : ""}
        ${sel ? `<circle cx="${cx}" cy="${cy}" r="${r + 7.5}" fill="none" stroke="var(--ink)" stroke-width="1.4"/>` : ""}
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="${p.confident ? c : "var(--paper)"}" stroke="${c}" stroke-width="1.6"/>
        ${shown.has(i) ? `<text class="plabel" x="${left ? cx - r - 6 : cx + r + 6}" y="${cy + 4}" text-anchor="${left ? "end" : "start"}">${esc(p.label)}</text>` : ""}</g>`;
    }).join("");
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Keyword map: attention against buying demand">${frame}${names}${marks}</svg>`;
    el.querySelectorAll("g[data-i]").forEach((g) => {
      const p = points[+g.dataset.i];
      const html = `<b>${esc(p.label)}</b><div class="k">${esc(p.verdict)}, confidence ${p.conf.toFixed(2)}</div>
        <div class="n">attention ${p.x.toFixed(2)} · demand ${p.y.toFixed(2)}</div><div class="n">${esc(p.buyers)} buyers/h${p.crowded ? " · crowded" : ""}</div>`;
      if (!low()) g.addEventListener("pointerenter", (e) => showTip(html, e.clientX, e.clientY - 8));
      g.addEventListener("pointerleave", hideTip);
      g.addEventListener("click", () => { hideTip(); onPick && onPick(p); });
    });
  }

  function spark(values, w = 72, h = 22) {
    if (!values || values.length < 2 || Math.max(...values) === 0) return `<svg class="spark" width="${w}" height="${h}" aria-hidden="true"><path class="l" d="M0,${h - 1}H${w}" opacity=".3"/></svg>`;
    const max = Math.max(...values), xs = (i) => (i / (values.length - 1)) * w, ys = (v) => h - 1 - (v / max) * (h - 3);
    const d = values.map((v, i) => `${i ? "L" : "M"}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join("");
    return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path class="a" d="${d}L${w},${h}L0,${h}Z"/><path class="l" d="${d}"/></svg>`;
  }

  return { timeBars, seismo, timeLine, catBars, dial, narrativeMap, spark, showTip, hideTip, esc, hhmm, dayhm, niceMax };
})();
