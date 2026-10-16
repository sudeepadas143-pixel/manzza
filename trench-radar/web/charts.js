// Small SVG chart kit: one data hue, labelled axes, crosshair tooltips that work with touch.
// Every label that comes from data goes through esc().
"use strict";

const Charts = (() => {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const tip = () => document.getElementById("tip");
  const DEFS = `<defs>
    <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="6" stroke="#1d2126" stroke-width="2"/></pattern>
    <linearGradient id="areaFill" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#79a6f2" stop-opacity=".22"/><stop offset="1" stop-color="#79a6f2" stop-opacity="0"/></linearGradient></defs>`;

  function niceMax(v) {
    if (!(v > 0)) return 1;
    const p = 10 ** Math.floor(Math.log10(v));
    const m = v / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
  }
  const hhmm = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const dayhm = (t) => new Date(t * 1000).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false });

  function showTip(html, x, y) {
    const el = tip();
    el.innerHTML = html;
    const w = el.offsetWidth || 160;
    el.style.left = `${Math.max(w / 2 + 8, Math.min(window.innerWidth - w / 2 - 8, x))}px`;
    el.style.top = `${Math.max(64, y)}px`;
    el.classList.add("on");
  }
  function hideTip() { tip().classList.remove("on"); }

  // Pointer tracking for crosshair charts: mouse hover and touch drag both work; scrolling still works on touch.
  function track(svg, W, pick) {
    const move = (e) => {
      const r = svg.getBoundingClientRect();
      const mx = ((e.clientX - r.left) / r.width) * W;
      const hit = pick(mx);
      if (!hit) return hideTip();
      showTip(hit.html, r.left + (hit.x / W) * r.width, r.top + (hit.y / (svg.viewBox.baseVal.height || 1)) * r.height);
    };
    const off = () => { svg.classList.remove("tracking"); hideTip(); };
    svg.addEventListener("pointermove", (e) => { svg.classList.add("tracking"); move(e); });
    svg.addEventListener("pointerdown", (e) => { svg.classList.add("tracking"); move(e); });
    svg.addEventListener("pointerleave", off);
    svg.addEventListener("pointercancel", off);
  }

  function timeTicks(from, to, W, padL, padR, xOf) {
    const span = to - from;
    const step = span <= 1800 ? 300 : span <= 3 * 3600 ? 900 : span <= 6 * 3600 ? 3600 : span <= 24 * 3600 ? 4 * 3600 : 12 * 3600;
    let t = Math.ceil(from / step) * step;
    let out = "";
    for (; t <= to; t += step) {
      const x = xOf(t);
      if (x < padL + 12 || x > W - padR - 12) continue;
      out += `<text class="ax" x="${x}" y="__H__" text-anchor="middle">${span > 30 * 3600 ? esc(dayhm(t).replace(/:00$/, "")) : hhmm(t)}</text>`;
    }
    return out;
  }

  /** Bars on a time axis. gaps = bucket starts with no observation (drawn hatched, not as zero). */
  function timeBars(el, { data, from, to, step, observed, height = 168, fmtY = (v) => v, label = "", unit = "" }) {
    const W = Math.max(280, el.clientWidth), H = height, pad = { l: 34, r: 6, t: 8, b: 20 };
    const max = niceMax(Math.max(1, ...data.map((d) => d[1])));
    const n = Math.max(1, Math.round((to - from) / step));
    const bw = (W - pad.l - pad.r) / n;
    const xOf = (t) => pad.l + ((t - from) / (to - from)) * (W - pad.l - pad.r);
    const yOf = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
    const map = new Map(data.map((d) => [d[0], d[1]]));
    const obs = observed ? new Set(observed) : null;
    let bars = "", gaps = "";
    for (let i = 0; i < n; i++) {
      const b = Math.floor((from + i * step) / step) * step;
      const x = xOf(b) + 0.5, w = Math.max(1, bw - (bw > 5 ? 1.5 : 0.5));
      const v = map.get(b);
      if (v) bars += `<rect class="bar" x="${x}" y="${yOf(v)}" width="${w}" height="${H - pad.b - yOf(v)}" rx="${bw > 6 ? 1.5 : 0}"/>`;
      else if (obs && !obs.has(b)) gaps += `<rect class="gap" x="${x}" y="${pad.t}" width="${w}" height="${H - pad.t - pad.b}"/>`;
    }
    const grid = [0, max / 2, max].map((v) => `<line x1="${pad.l}" x2="${W - pad.r}" y1="${yOf(v)}" y2="${yOf(v)}"/>`).join("");
    const yl = [0, max / 2, max].map((v) => `<text class="ax" x="${pad.l - 6}" y="${yOf(v) + 3.5}" text-anchor="end">${esc(fmtY(v))}</text>`).join("");
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${esc(label)}">${DEFS}
      <g class="grid">${grid}</g>${gaps}${bars}${yl}${timeTicks(from, to, W, pad.l, pad.r, xOf).replaceAll("__H__", H - 5)}
      <line class="xh" y1="${pad.t}" y2="${H - pad.b}" x1="-9" x2="-9"/></svg>`;
    const svg = el.querySelector("svg"), xh = svg.querySelector(".xh");
    track(svg, W, (mx) => {
      const i = Math.floor((mx - pad.l) / bw);
      if (i < 0 || i >= n) { xh.setAttribute("x1", -9); xh.setAttribute("x2", -9); return null; }
      const b = Math.floor((from + i * step) / step) * step, v = map.get(b), cx = xOf(b) + bw / 2;
      xh.setAttribute("x1", cx); xh.setAttribute("x2", cx);
      const missing = obs && !obs.has(b) && !v;
      return { x: cx, y: v ? yOf(v) : pad.t + 20,
        html: `<div class="muted">${esc(hhmm(b))}–${esc(hhmm(b + step))}</div>` +
          (missing ? `<b>Not observed</b><div class="muted">collector was not running</div>` : `<b class="num">${esc(fmtY(v || 0))}</b> ${esc(unit)}`) };
    });
    svg.addEventListener("pointerleave", () => { xh.setAttribute("x1", -9); xh.setAttribute("x2", -9); });
  }

  /** Line (+area) on a time axis with crosshair. */
  function timeLine(el, { data, from, to, height = 150, fmtY = (v) => v, yMin, yMax, label = "", refs = [] }) {
    if (data.length < 2) { el.innerHTML = `<div class="chart-empty">Not enough points yet in this range.</div>`; return; }
    const W = Math.max(280, el.clientWidth), H = height, pad = { l: 40, r: 8, t: 10, b: 20 };
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
    const grid = ticks.map((v) => `<line x1="${pad.l}" x2="${W - pad.r}" y1="${yOf(v)}" y2="${yOf(v)}"/>`).join("");
    const yl = ticks.map((v) => `<text class="ax" x="${pad.l - 6}" y="${yOf(v) + 3.5}" text-anchor="end">${esc(fmtY(v))}</text>`).join("");
    const rl = refs.filter((r) => r.v > lo && r.v < hi).map((r) => `<line class="ref" x1="${pad.l}" x2="${W - pad.r}" y1="${yOf(r.v)}" y2="${yOf(r.v)}"/>
      <text class="ax" x="${W - pad.r}" y="${yOf(r.v) - 4}" text-anchor="end">${esc(r.label)}</text>`).join("");
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${esc(label)}">${DEFS}
      <g class="grid">${grid}</g>${rl}<path class="area" d="${area}"/><path class="line" d="${d}"/>${yl}
      ${timeTicks(from, to, W, pad.l, pad.r, xOf).replaceAll("__H__", H - 5)}
      <line class="xh" y1="${pad.t}" y2="${H - pad.b}" x1="-9" x2="-9"/><circle class="dot" r="4" cx="-9" cy="-9"/></svg>`;
    const svg = el.querySelector("svg"), xh = svg.querySelector(".xh"), dot = svg.querySelector(".dot");
    track(svg, W, (mx) => {
      let best = 0;
      for (let i = 1; i < data.length; i++) if (Math.abs(xOf(data[i][0]) - mx) < Math.abs(xOf(data[best][0]) - mx)) best = i;
      const p = data[best], cx = xOf(p[0]), cy = yOf(p[1]);
      xh.setAttribute("x1", cx); xh.setAttribute("x2", cx); dot.setAttribute("cx", cx); dot.setAttribute("cy", cy);
      return { x: cx, y: cy, html: `<div class="muted">${esc(dayhm(p[0]))}</div><b class="num">${esc(fmtY(p[1]))}</b>` };
    });
    svg.addEventListener("pointerleave", () => { xh.setAttribute("x1", -9); xh.setAttribute("x2", -9); dot.setAttribute("cx", -9); });
  }

  /** Category bars (daily volume). */
  function catBars(el, { data, height = 150, fmtY, fmtX, label = "" }) {
    if (!data.length) { el.innerHTML = `<div class="chart-empty">No data yet.</div>`; return; }
    const W = Math.max(280, el.clientWidth), H = height, pad = { l: 44, r: 4, t: 8, b: 20 };
    const max = niceMax(Math.max(...data.map((d) => d[1])));
    const bw = (W - pad.l - pad.r) / data.length;
    const yOf = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
    const bars = data.map((d, i) => `<rect class="bar${i === data.length - 1 ? " dim" : ""}" x="${pad.l + i * bw + 1}" y="${yOf(d[1])}" width="${Math.max(1, bw - 2)}" height="${H - pad.b - yOf(d[1])}" rx="1.5"/>`).join("");
    const grid = [0, max / 2, max].map((v) => `<line x1="${pad.l}" x2="${W - pad.r}" y1="${yOf(v)}" y2="${yOf(v)}"/>`).join("");
    const yl = [0, max / 2, max].map((v) => `<text class="ax" x="${pad.l - 6}" y="${yOf(v) + 3.5}" text-anchor="end">${esc(fmtY(v))}</text>`).join("");
    const every = Math.ceil(data.length / 5);
    const xl = data.map((d, i) => (i % every === 0 ? `<text class="ax" x="${pad.l + i * bw + bw / 2}" y="${H - 5}" text-anchor="middle">${esc(fmtX(d[0]))}</text>` : "")).join("");
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${esc(label)}">${DEFS}<g class="grid">${grid}</g>${bars}${yl}${xl}
      <line class="xh" y1="${pad.t}" y2="${H - pad.b}" x1="-9" x2="-9"/></svg>`;
    const svg = el.querySelector("svg"), xh = svg.querySelector(".xh");
    track(svg, W, (mx) => {
      const i = Math.floor((mx - pad.l) / bw);
      if (i < 0 || i >= data.length) return null;
      const cx = pad.l + i * bw + bw / 2;
      xh.setAttribute("x1", cx); xh.setAttribute("x2", cx);
      return { x: cx, y: yOf(data[i][1]), html: `<div class="muted">${esc(fmtX(data[i][0]))}${i === data.length - 1 ? " (partial day)" : ""}</div><b class="num">${esc(fmtY(data[i][1]))}</b>` };
    });
  }

  /** Attention (x) vs buying demand (y), quadrants at 0.55 like the hype check. */
  function quadrant(el, { points, height = 280, onPick }) {
    const W = Math.max(280, el.clientWidth), H = height, pad = { l: 30, r: 10, t: 10, b: 28 };
    const xOf = (v) => pad.l + v * (W - pad.l - pad.r), yOf = (v) => pad.t + (1 - v) * (H - pad.t - pad.b);
    const q = 0.55;
    const ql = [["ORGANIC", pad.l + 6, pad.t + 14, "start"], ["CONFIRMED", W - pad.r - 6, pad.t + 14, "end"],
      ["COLD", pad.l + 6, H - pad.b - 8, "start"], ["HYPE, NO BUYERS", W - pad.r - 6, H - pad.b - 8, "end"]]
      .map(([t, x, y, a]) => `<text class="ql" x="${x}" y="${y}" text-anchor="${a}">${t}</text>`).join("");
    const axes = `<line class="ref" x1="${xOf(q)}" x2="${xOf(q)}" y1="${pad.t}" y2="${H - pad.b}"/><line class="ref" x1="${pad.l}" x2="${W - pad.r}" y1="${yOf(q)}" y2="${yOf(q)}"/>
      <rect x="${pad.l}" y="${pad.t}" width="${W - pad.l - pad.r}" height="${H - pad.t - pad.b}" fill="none" stroke="#23272d"/>
      <text class="ax" x="${(W + pad.l) / 2}" y="${H - 6}" text-anchor="middle">attention →</text>
      <text class="ax" transform="translate(11 ${(H - pad.b + pad.t) / 2}) rotate(-90)" text-anchor="middle">buying demand →</text>
      ${[0, 0.5, 1].map((v) => `<text class="ax" x="${xOf(v)}" y="${H - pad.b + 12}" text-anchor="middle">${v}</text>`).join("")}`;
    const color = { pos: "#3fb950", warn: "#d29922", neg: "#f85149", mute: "#868d97" };
    // draw the strongest last so they sit on top; label greedily, skipping any label that would collide
    const order = points.map((p, i) => i).sort((a, b) => (points[a].score ?? 0) - (points[b].score ?? 0));
    const rad = (p) => Math.max(3.5, Math.min(9, 3 + Math.sqrt(p.buyers || 0) / 4));
    const dots = points.map((p) => [xOf(p.x) - rad(p), yOf(p.y) - rad(p), xOf(p.x) + rad(p), yOf(p.y) + rad(p)]);
    const boxes = [];
    const hits = (box, self) => boxes.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])
      || dots.some((b, j) => j !== self && box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]);
    const labelled = new Set(points.map((p, i) => i).sort((a, b) => (points[b].score ?? 0) - (points[a].score ?? 0)).slice(0, 10));
    const pts = order.map((i) => {
      const p = points[i];
      const r = rad(p);
      const cx = xOf(p.x), cy = yOf(p.y), c = color[p.tone];
      let lab = "";
      if (labelled.has(i)) {
        const w = p.label.length * 6.2 + 4, left = cx > W * 0.62;
        const lx = left ? cx - r - 4 - w : cx + r + 4, box = [lx, cy - 8, lx + w, cy + 6];
        if (lx > pad.l && lx + w < W - pad.r && !hits(box, i)) {
          boxes.push(box);
          lab = `<text class="plabel" x="${left ? cx - r - 4 : cx + r + 4}" y="${cy + 4}" text-anchor="${left ? "end" : "start"}">${esc(p.label)}</text>`;
        }
      }
      const fill = p.confident ? `fill="${c}" fill-opacity=".85"` : `fill="#111316"`;
      return `<g data-i="${i}" style="cursor:pointer"><circle cx="${cx}" cy="${cy}" r="${r + 8}" fill="transparent"/>
        <circle cx="${cx}" cy="${cy}" r="${r}" ${fill} stroke="${c}" stroke-width="1.5"/>${lab}</g>`;
    }).join("");
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Attention versus buying demand by meta">${axes}${ql}${pts}</svg>`;
    const svg = el.querySelector("svg");
    svg.querySelectorAll("g[data-i]").forEach((g) => {
      const p = points[+g.dataset.i];
      const html = `<b>${esc(p.label)}</b><div class="muted">${esc(p.verdict)} · conf ${p.conf.toFixed(2)}</div>
        <div>attention <span class="num">${p.x.toFixed(2)}</span> · demand <span class="num">${p.y.toFixed(2)}</span></div>
        <div>${esc(p.buyers)} buyers/h</div>`;
      g.addEventListener("pointerenter", (e) => showTip(html, e.clientX, e.clientY - 6));
      g.addEventListener("pointerleave", hideTip);
      g.addEventListener("click", () => { hideTip(); onPick && onPick(p); });
    });
  }

  function spark(values, w = 72, h = 22) {
    if (!values || values.length < 2 || Math.max(...values) === 0) return `<svg class="spark" width="${w}" height="${h}" aria-hidden="true"><path class="l" d="M0,${h - 1}H${w}" opacity=".3"/></svg>`;
    const max = Math.max(...values);
    const xs = (i) => (i / (values.length - 1)) * w, ys = (v) => h - 1 - (v / max) * (h - 3);
    const d = values.map((v, i) => `${i ? "L" : "M"}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join("");
    return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path class="a" d="${d}L${w},${h}L0,${h}Z"/><path class="l" d="${d}"/></svg>`;
  }

  function ring(progress, done, size = 36) {
    const r = 15, c = 2 * Math.PI * r, p = Math.max(0, Math.min(1, progress ?? 0));
    const label = done ? "✓" : progress === null || progress === undefined ? "–" : Math.round(p * 100);
    return `<svg class="ring${done ? " done" : ""}" viewBox="0 0 36 36" width="${size}" height="${size}" role="img" aria-label="${done ? "graduated" : "curve " + label + "%"}">
      <circle class="bg" cx="18" cy="18" r="${r}"/><circle class="fg" cx="18" cy="18" r="${r}" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - (done ? 1 : p))}" transform="rotate(-90 18 18)"/>
      <text x="18" y="18.5">${label}</text></svg>`;
  }

  return { timeBars, timeLine, catBars, quadrant, spark, ring, hideTip, esc, hhmm, dayhm };
})();
