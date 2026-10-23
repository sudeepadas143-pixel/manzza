// TRENCH//RADAR narrative visuals: category inks, the Atlas (a semantic radar), pulse ridges,
// token constellations, lifecycle glyphs and number tickers. All marks come from the narrative read;
// nothing here invents activity. Motion only reports a change in the data.
"use strict";

const Viz = (() => {
  const { esc, showTip, hideTip, hhmm } = Charts;
  const motion = () => document.documentElement.dataset.perf !== "low" && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const NS = "http://www.w3.org/2000/svg";

  // ------------------------------------------------------------ category inks
  // Eight pigments in a fixed, validated order (docs/DESIGN.md); eleven categories share them,
  // the second member of a family drawn as a diamond. Colour follows the category, never its rank.
  const CAT = {
    "Characters & creatures": [1, "circle"], "Technology & AI": [2, "circle"], "Gaming, anime & entertainment": [3, "circle"],
    "Art & visual memes": [4, "circle"], "Lifestyle & nostalgia": [4, "diamond"], "Current events & news": [5, "circle"],
    "Politics & geopolitics": [5, "diamond"], "Internet culture & slang": [6, "circle"], "Communities & fandoms": [6, "diamond"],
    "Absurdist & surreal": [7, "circle"], "Crypto-native": [8, "circle"],
  };
  // bearing order around the atlas: neighbours are related, so ambiguous metas fall between them
  const RING = ["Characters & creatures", "Absurdist & surreal", "Art & visual memes", "Lifestyle & nostalgia", "Communities & fandoms",
    "Internet culture & slang", "Gaming, anime & entertainment", "Technology & AI", "Crypto-native", "Current events & news", "Politics & geopolitics"];
  const CREATED = "Created by the app", NOVEL = "New kind of meta";
  const SHORT = { "Characters & creatures": "Creatures", "Absurdist & surreal": "Absurd", "Art & visual memes": "Art", "Lifestyle & nostalgia": "Nostalgia",
    "Communities & fandoms": "Fandoms", "Internet culture & slang": "Net culture", "Gaming, anime & entertainment": "Gaming", "Technology & AI": "Tech & AI",
    "Crypto-native": "Crypto", "Current events & news": "News", "Politics & geopolitics": "Politics" };
  const catName = (c) => c?.primary || NOVEL;
  const enc = (c) => {
    const e = CAT[c?.primary];
    if (e) return { ink: `var(--c${e[0]})`, slot: e[0], shape: e[1], kind: "seed" };
    return c?.primary ? { ink: "var(--ink-3)", slot: 0, shape: "square", kind: "created" } : { ink: "var(--novel-ink)", slot: 9, shape: "circle", kind: "novel" };
  };
  const bandKey = (c) => (enc(c).kind === "created" ? CREATED : catName(c));
  const swatch = (c) => { const e = enc(c); return `<i class="sw ${e.shape} ${e.kind === "novel" ? "novel" : e.kind === "created" ? "created" : ""}" style="background:${e.ink}" aria-hidden="true"></i>`; };

  // ------------------------------------------------------------ lifecycle
  const STAGES = ["new", "heating", "accelerating", "bought", "steady", "saturating", "fading"];
  const STAGE_LABEL = { new: "New", heating: "Heating", accelerating: "Accelerating", bought: "Being bought", steady: "Steady", saturating: "Saturating", fading: "Fading" };
  const STAGE_NOTE = { new: "first seen within two hours", heating: "launches rising, buying not yet", accelerating: "launches and buyers rising together",
    bought: "buyers rising without a launch rush", steady: "near its own recent rate", saturating: "copies or buyers per launch falling", fading: "launches and buyers falling" };
  const LIFE = { new: "emerging", heating: "emerging", accelerating: "emerging", bought: "emerging", steady: "established", saturating: "saturated", fading: "saturated" };
  const life = (s) => LIFE[s] || "established";
  const GLYPH = {
    new: `<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 0.5 L7.2 4.8 L11.5 6 L7.2 7.2 L6 11.5 L4.8 7.2 L0.5 6 L4.8 4.8Z" fill="currentColor"/></svg>`,
    heating: `<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1.5 L11 10.5 H1Z" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>`,
    accelerating: `<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M1.5 6.5 L6 2 L10.5 6.5 M1.5 10.5 L6 6 L10.5 10.5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>`,
    bought: `<svg viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="4.6" fill="currentColor"/><path d="M6 3.6v4.8M3.6 6h4.8" stroke="var(--paper)" stroke-width="1.4"/></svg>`,
    steady: `<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M1 6h10" stroke="currentColor" stroke-width="2"/></svg>`,
    saturating: `<svg viewBox="0 0 12 12" aria-hidden="true"><rect x="1" y="1" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M1 7 L7 1 M3 11 L11 3 M7 11 L11 7" stroke="currentColor" stroke-width="1.2"/></svg>`,
    fading: `<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M1.5 3.5 L6 8 L10.5 3.5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>`,
  };
  const stamp = (s, big = false) => `<span class="stamp ${esc(s)}${big ? " big" : ""}">${GLYPH[s] || GLYPH.steady}${esc(STAGE_LABEL[s] || s)}</span>`;

  // ------------------------------------------------------------ change helpers
  const prev = new Map();
  const remember = (key, v) => { const p = prev.get(key); prev.set(key, v); return p; };
  const moved = (key, v) => { const p = remember(key, v); return Number.isFinite(p) && Number.isFinite(v) && p !== v ? (v > p ? "chg-up" : "chg-down") : ""; };
  const num = (key, v, text, fmt = "int") => {
    const p = remember(key, v);
    return `<span ${Number.isFinite(p) && p !== v && Number.isFinite(v) ? `data-tick="${v}" data-from="${p}" data-fmt="${fmt}"` : ""}>${text}</span>`;
  };
  function tick(root = document) {
    if (!motion()) return;
    root.querySelectorAll("[data-tick]").forEach((el) => {
      const to = +el.dataset.tick, from = +el.dataset.from, final = el.textContent;
      const fmt = el.dataset.fmt === "signed" ? (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1) : (v) => Math.round(v).toLocaleString();
      const t0 = performance.now(), D = 700;
      const step = (t) => {
        const k = Math.min(1, (t - t0) / D), e = 1 - Math.pow(1 - k, 4);
        el.textContent = k < 1 ? fmt(from + (to - from) * e) : final;
        if (k < 1 && el.isConnected) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  // a stable pseudo-random number per label, so layouts don't shuffle between reads
  const hash = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 10000) / 10000; };
  const el = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

  // ------------------------------------------------------------ the ATLAS
  // Bearing = which categories a narrative resembles (similarity scores from the read, as a radial
  // projection onto the category ring); distance from the centre = how clearly it belongs to any.
  // Narratives that fit no category drift to the middle: "uncharted", where new kinds of meta appear.
  const A = { svg: null, asOf: null, compact: null };
  function place(all, R) {
    const n = RING.length;
    const angle = (i) => -Math.PI / 2 + (i / n) * Math.PI * 2;
    const pts = all.map((x) => {
      const sc = x.category?.scores || {};
      let vx = 0, vy = 0, ws = 0;
      RING.forEach((c, i) => { const s = sc[c]; if (s > 0.16) { const w = (s - 0.16) ** 2; vx += w * Math.cos(angle(i)); vy += w * Math.sin(angle(i)); ws += w; } });
      const top = Math.max(0, ...Object.entries(sc).filter(([k]) => CAT[k]).map(([, v]) => v));
      const conf = Math.max(0, Math.min(1, (top - 0.2) / 0.24));
      let px = 0, py = 0;
      if (ws > 0) { px = vx / ws; py = vy / ws; }
      const m = Math.hypot(px, py) || 1;
      // direction from the projection, distance from how clearly it belongs (never past 0.88 R)
      const r = R * (0.12 + 0.76 * conf) * Math.min(1, 0.55 + 0.45 * m);
      const jitter = (hash(x.label) - 0.5) * 0.28;
      const a = ws > 0 ? Math.atan2(py, px) + jitter : hash(x.label) * Math.PI * 2;
      const rr = ws > 0 ? r : R * 0.08 * (0.4 + hash(x.label + "r"));
      return { n: x, x: rr * Math.cos(a), y: rr * Math.sin(a), r: 0 };
    });
    return pts;
  }
  function relax(pts, R, iters = 60) {
    for (let k = 0; k < iters; k++) {
      let movedAny = false;
      for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
        const a = pts[i], b = pts[j], dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 0.01, min = a.r + b.r + 2.5;
        if (d < min) {
          const push = (min - d) / 2, ux = dx / d, uy = dy / d;
          a.x -= ux * push; a.y -= uy * push; b.x += ux * push; b.y += uy * push; movedAny = true;
        }
      }
      for (const p of pts) { const d = Math.hypot(p.x, p.y), lim = R - p.r - 4; if (d > lim) { p.x *= lim / d; p.y *= lim / d; } }
      if (!movedAny) break;
    }
  }

  function atlas(host, all, { selected, highlight, asOf, onPick, onOpen, compact }) {
    // phones get a smaller plate so type stays legible when it is scaled to the screen
    const W = compact ? 560 : 760, H = W, cx = W / 2, cy = H / 2, R = compact ? 196 : 292;
    if (A.compact !== compact) { A.svg = null; A.compact = compact; }
    const maxL = Math.max(1, ...all.map((x) => x.popularity.launches_6h));
    const pts = place(all, R);
    pts.forEach((p) => { p.r = 3.5 + (compact ? 13 : 19) * Math.sqrt(p.n.popularity.launches_6h / maxL); });
    relax(pts, R);
    const byLabel = new Map(pts.map((p) => [p.n.label, p]));

    // build or reuse the plate; reuse lets marks glide to their new bearing
    let svg = A.svg;
    const fresh = !svg;
    if (fresh) {
      svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", class: compact ? "compact" : "" });
      const defs = el("defs");
      for (let i = 1; i <= 8; i++) {
        defs.insertAdjacentHTML("beforeend", `<pattern id="ht-${i}" width="4.5" height="4.5" patternUnits="userSpaceOnUse"><circle cx="2.25" cy="2.25" r="1.25" style="fill:var(--c${i})"/></pattern>
          <pattern id="hx-${i}" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" style="stroke:var(--c${i})" stroke-width="1.6"/></pattern>`);
      }
      defs.insertAdjacentHTML("beforeend", `<pattern id="ht-0" width="4.5" height="4.5" patternUnits="userSpaceOnUse"><circle cx="2.25" cy="2.25" r="1.25" style="fill:var(--ink-3)"/></pattern>
        <pattern id="hx-0" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" style="stroke:var(--ink-3)" stroke-width="1.6"/></pattern>
        <pattern id="ht-9" width="4.5" height="4.5" patternUnits="userSpaceOnUse"><circle cx="2.25" cy="2.25" r="1.25" style="fill:var(--novel-ink)"/></pattern>
        <pattern id="hx-9" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" style="stroke:var(--novel-ink)" stroke-width="1.6"/></pattern>
        <linearGradient id="sweepg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" style="stop-color:var(--ink)" stop-opacity="0"/><stop offset="1" style="stop-color:var(--ink)" stop-opacity=".16"/></linearGradient>`);
      svg.appendChild(defs);
      // scope: rings, bearing ticks, spokes and territories
      const scope = el("g", { class: "scope" });
      let s = "";
      [0.25, 0.5, 0.75, 1].forEach((k, i) => { s += `<circle class="ring${i < 3 ? " dash" : ""}" cx="${cx}" cy="${cy}" r="${R * k}"/>`; });
      s += `<circle class="ring" cx="${cx}" cy="${cy}" r="${R + 10}" style="stroke:var(--ink)"/>`;
      for (let d = 0; d < 360; d += 5) {
        const a = (d - 90) * Math.PI / 180, big = d % 30 === 0, r0 = R + 10, r1 = R + (big ? 20 : 15);
        s += `<line x1="${cx + r0 * Math.cos(a)}" y1="${cy + r0 * Math.sin(a)}" x2="${cx + r1 * Math.cos(a)}" y2="${cy + r1 * Math.sin(a)}" stroke="var(--ink)" stroke-width="${big ? 1.4 : 0.7}"/>`;
      }
      const n = RING.length;
      RING.forEach((c, i) => {
        const a = -Math.PI / 2 + ((i + 0.5) / n) * Math.PI * 2, a0 = -Math.PI / 2 + (i / n) * Math.PI * 2;
        s += `<line class="spoke" x1="${cx + R * 0.25 * Math.cos(a0)}" y1="${cy + R * 0.25 * Math.sin(a0)}" x2="${cx + (R + 10) * Math.cos(a0)}" y2="${cy + (R + 10) * Math.sin(a0)}"/>`;
        void a;
      });
      s += `<text class="unch" x="${cx}" y="${cy + R * 0.25 + 16}" text-anchor="middle">uncharted</text>`;
      scope.innerHTML = s;
      svg.appendChild(scope);
      svg.appendChild(el("g", { class: "terrs" }));
      svg.appendChild(el("g", { class: "rels" }));
      const sw = el("path", { class: "sweep", d: `M${cx},${cy} L${cx + R + 10},${cy} A${R + 10},${R + 10} 0 0 0 ${cx + (R + 10) * Math.cos(-0.7)},${cy + (R + 10) * Math.sin(-0.7)} Z`, fill: "url(#sweepg)" });
      sw.style.setProperty("--cx", `${cx}px`); sw.style.setProperty("--cy", `${cy}px`);
      svg.appendChild(sw);
      svg.appendChild(el("g", { class: "marks" }));
      A.svg = svg;
    }
    svg.setAttribute("aria-label", `Atlas of ${all.length} narratives by meaning: the ring holds the categories, the centre holds narratives no category fits. The lifecycle list and the table give the same data.`);
    host.innerHTML = "";
    host.appendChild(svg);

    // territories: category names on the rim, inked and counted
    const counts = new Map();
    all.forEach((x) => { const k = catName(x.category); counts.set(k, (counts.get(k) || 0) + 1); });
    const n = RING.length;
    svg.querySelector(".terrs").innerHTML = RING.map((c, i) => {
      const a = -Math.PI / 2 + ((i + 0.5) / n) * Math.PI * 2, rr = R + (compact ? 44 : 38), x = cx + rr * Math.cos(a), y = cy + rr * Math.sin(a);
      const deg = (a * 180) / Math.PI + 90, flip = deg > 90 && deg < 270, rot = flip ? deg + 180 : deg;
      const k = counts.get(c) || 0, e = enc({ primary: c }), dim = highlight && highlight !== c;
      const short = compact ? SHORT[c] : c.replace(" & entertainment", "").replace("Gaming, anime", "Gaming & anime").replace("Current events & news", "News").replace("Politics & geopolitics", "Politics");
      return `<g transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${rot.toFixed(1)})" opacity="${dim ? 0.3 : 1}">
        <text class="terr" text-anchor="middle" y="${flip ? 10 : 0}" style="fill:${e.ink}">${esc(short)}</text>
        <text class="terr-n" text-anchor="middle" y="${flip ? 22 : 12}">${k ? `${k} narrative${k > 1 ? "s" : ""}` : "—"}</text></g>`;
    }).join("");

    // relations: sub-metas joined to their parent's largest member, plus close pairs
    const rel = [];
    const groups = new Map();
    all.forEach((x) => { if (x.parent?.label) { const g = groups.get(x.parent.label) || []; g.push(x); groups.set(x.parent.label, g); } });
    groups.forEach((g) => {
      if (g.length < 2) return;
      const head = g.reduce((a, b) => (b.popularity.launches_6h > a.popularity.launches_6h ? b : a));
      g.forEach((x) => { if (x !== head) rel.push([head.label, x.label, "parent"]); });
    });
    all.forEach((x) => { if (x.closest && x.closest.similarity >= 0.62 && byLabel.has(x.closest.label)) rel.push([x.label, x.closest.label, "close"]); });
    const seen = new Set();
    svg.querySelector(".rels").innerHTML = rel.filter(([a, b]) => { const k = [a, b].sort().join("|"); if (seen.has(k)) return false; seen.add(k); return true; }).map(([a, b, kind]) => {
      const p = byLabel.get(a), q = byLabel.get(b);
      if (!p || !q) return "";
      const mx = (p.x + q.x) / 2 * 0.82, my = (p.y + q.y) / 2 * 0.82;   // bow toward the centre
      return `<path class="rel" data-a="${esc(a)}" data-b="${esc(b)}" d="M${cx + p.x},${cy + p.y} Q${cx + mx},${cy + my} ${cx + q.x},${cy + q.y}" ${kind === "close" ? 'stroke-dasharray="2 3"' : ""}/>`;
    }).join("");

    // marks: keyed by label so a narrative glides when the read moves it
    const marks = svg.querySelector(".marks");
    const have = new Map([...marks.children].map((g) => [g.dataset.k, g]));
    const labelled = new Set([...all].sort((a, b) => (b.traction.buyers_h1 || 0) - (a.traction.buyers_h1 || 0)).slice(0, compact ? 6 : 12).map((x) => x.label));
    if (selected) labelled.add(selected);
    const boxes = [];
    const order = [...pts].sort((a, b) => (a.n.label === selected) - (b.n.label === selected) || b.r - a.r);
    const keep = new Set();
    for (const p of order) {
      const x = p.n, e = enc(x.category), L = life(x.state), sel = x.label === selected, dim = highlight && bandKey(x.category) !== highlight;
      keep.add(x.label);
      let g = have.get(x.label);
      const born = !g;
      if (!g) { g = el("g", { class: "mk" }); g.dataset.k = x.label; marks.appendChild(g); }
      else marks.appendChild(g);                       // re-append: draw order follows size, selected last
      const slot = e.slot;
      const fill = L === "emerging" ? (e.kind === "created" ? "var(--ink-4)" : e.ink) : L === "established" ? `url(#ht-${slot})` : x.state === "saturating" ? `url(#hx-${slot})` : "var(--plane)";
      const r = p.r, shape = e.shape === "diamond"
        ? `<rect x="${-r * 0.82}" y="${-r * 0.82}" width="${r * 1.64}" height="${r * 1.64}" transform="rotate(45)"`
        : e.shape === "square" ? `<rect x="${-r * 0.86}" y="${-r * 0.86}" width="${r * 1.72}" height="${r * 1.72}"` : `<circle r="${r}"`;
      // label: right of the mark unless it would leave the plate
      let lab = "";
      if (labelled.has(x.label) && !dim) {
        const t = x.title.length > 20 ? x.title.slice(0, 19) + "…" : x.title, w = t.length * (compact ? 8.6 : 7.2) + 6, right = p.x < R * 0.45;
        const lx = right ? p.x + r + 6 : p.x - r - 6 - w, box = [lx, p.y - 9, lx + w, p.y + 7];
        if (sel || !boxes.some((o) => box[0] < o[2] && box[2] > o[0] && box[1] < o[3] && box[3] > o[1])) {
          boxes.push(box);
          lab = `<text class="lab" x="${right ? r + 6 : -r - 6}" y="5" text-anchor="${right ? "start" : "end"}">${esc(t)}</text>`;
        }
      }
      g.innerHTML = `<circle class="hit" r="${r + 8}"/>
        ${x.state === "new" ? `<circle r="${r + 4.5}" fill="none" style="stroke:var(--novel-ink)" stroke-width="1.6" stroke-dasharray="1.5 2.5"/>` : ""}
        ${sel ? `<circle class="ring-sel" r="${r + 8}" fill="none" style="stroke:var(--ink)" stroke-width="1.6"/>` : ""}
        ${shape} style="fill:${fill};stroke:${e.ink}" stroke-width="${L === "saturated" ? 1.6 : 1.2}" ${x.state === "fading" ? 'stroke-dasharray="3 2"' : ""}/>${lab}`;
      g.setAttribute("class", `mk${sel ? " sel" : ""}${dim ? " dim" : ""}${born && !fresh && motion() ? " born" : ""}`);
      g.style.transform = `translate(${(cx + p.x).toFixed(1)}px, ${(cy + p.y).toFixed(1)}px)`;
      g.onclick = () => { hideTip(); onPick(x); };
      g.ondblclick = () => onOpen && onOpen(x);
      g.onpointerenter = (ev) => {
        if (document.documentElement.dataset.perf === "low") return;
        svg.querySelectorAll(".rel").forEach((r) => r.classList.toggle("hot", r.dataset.a === x.label || r.dataset.b === x.label));
        showTip(`<div class="k">${esc(catName(x.category))}</div><b>${esc(x.title)}</b><div>${esc(STAGE_LABEL[x.state] || x.state)} · <span class="n">${x.popularity.launches_6h}</span> launches · <span class="n">${(x.traction.buyers_h1 || 0).toLocaleString()}</span> buyers/h</div><div class="k" style="margin-top:4px">${esc(x.label)}</div>`, ev.clientX, ev.clientY - 6);
      };
      g.onpointerleave = () => { hideTip(); svg.querySelectorAll(".rel.hot").forEach((r) => r.classList.remove("hot")); };
    }
    for (const [k, g] of have) if (!keep.has(k)) g.remove();
    // one sweep of the scope when a new read arrives
    if (asOf && A.asOf && asOf !== A.asOf && motion()) {
      const sw = svg.querySelector(".sweep");
      sw.classList.remove("go"); void sw.getBoundingClientRect(); sw.classList.add("go");
    }
    A.asOf = asOf;
  }

  // ------------------------------------------------------------ PULSE RIDGES (buyers per hour over time)
  function ridges(host, all, { selected, onPick, compact }) {
    const withH = all.filter((x) => (x.history || []).length >= 3).sort((a, b) => (b.traction.buyers_h1 || 0) - (a.traction.buyers_h1 || 0)).slice(0, compact ? 8 : 14);
    if (!withH.length) { host.innerHTML = `<div class="chart-empty">The pulse needs three reads of the same narrative (about 15 minutes of collection).</div>`; return; }
    const W = Math.max(320, host.clientWidth), left = compact ? 112 : 200, right = compact ? 70 : 128, gap = compact ? 24 : 28, amp = gap * 2.1;
    const H = withH.length * gap + amp + 30;
    const t0 = Math.min(...withH.map((x) => x.history[0][0])), t1 = Math.max(...withH.map((x) => x.history[x.history.length - 1][0]));
    const xOf = (t) => left + ((t - t0) / (t1 - t0 || 1)) * (W - left - right);
    let out = "";
    withH.forEach((x, i) => {
      const base = amp + 6 + i * gap, h = x.history, peak = Math.max(1, ...h.map((p) => p[2] || 0));
      const yOf = (v) => base - amp * ((v || 0) / peak);
      const d = h.map((p, j) => `${j ? "L" : "M"}${xOf(p[0]).toFixed(1)},${yOf(p[2]).toFixed(1)}`).join("");
      const area = `${d}L${xOf(h[h.length - 1][0]).toFixed(1)},${base}L${xOf(h[0][0]).toFixed(1)},${base}Z`;
      // change against the read closest to an hour before the latest; small bases say nothing
      const tl = h[h.length - 1][0], ref = h.reduce((a, p) => (Math.abs(p[0] - (tl - 3600)) < Math.abs(a[0] - (tl - 3600)) ? p : a), h[0]);
      const now = x.traction.buyers_h1 || 0, then = ref[2] || 0, ch = then >= 20 && ref !== h[h.length - 1] ? (now - then) / then : null;
      const e = enc(x.category), len = Math.round(W * 1.6);
      const name = x.title.length > (compact ? 12 : 22) ? x.title.slice(0, compact ? 11 : 21) + "…" : x.title;
      out += `<g class="rg${x.label === selected ? " sel" : ""}" data-k="${esc(x.label)}" style="--len:${len};--d:${i * 45}ms">
        <path class="fill" d="${area}"/><path class="ht" d="${area}" fill="url(#ht-r${e.slot})"/><path class="ink" d="${d}"/>
        <line x1="${left}" x2="${W - right}" y1="${base}" y2="${base}" stroke="var(--rule-2)" stroke-width="0.6"/>
        <rect x="${left - 8}" y="${base - 9}" width="3" height="9" style="fill:${e.ink}"/>
        <text class="nm" x="${left - 14}" y="${base - 1}" text-anchor="end">${esc(name)}</text>
        <text class="v ${ch > 0.1 ? "up" : ch < -0.1 ? "down" : ""}" x="${W - right + 12}" y="${base - 1}">${now.toLocaleString()}${ch !== null ? `  ${ch >= 0 ? "+" : "−"}${Math.abs(Math.round(ch * 100))}%` : ""}</text>
        <rect x="0" y="${base - gap}" width="${W}" height="${gap}" fill="transparent"/></g>`;
    });
    const span = t1 - t0, step = span <= 3600 ? 900 : span <= 4 * 3600 ? 3600 : span <= 14 * 3600 ? 3 * 3600 : 6 * 3600;
    const ticks = [];
    for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) ticks.push(`<text class="ax" x="${xOf(t)}" y="${H - 4}" text-anchor="middle">${hhmm(t)}</text>`);
    const defs = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((k) => `<pattern id="ht-r${k}" width="4" height="4" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r=".9" style="fill:${k === 0 ? "var(--ink-3)" : k === 9 ? "var(--novel-ink)" : `var(--c${k})`}"/></pattern>`).join("");
    const draw = motion() && !host.dataset.drawn;
    host.innerHTML = `<div class="ridges${draw ? " draw" : ""}"><svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Buyers per hour over time for the ${withH.length} most-bought narratives, each scaled to its own peak">
      <defs>${defs}</defs><g class="chart">${ticks.join("")}<text class="ax" x="${W - right + 12}" y="12">BUYERS/H · VS 1H</text></g>
      <line class="now" x1="${xOf(t1)}" x2="${xOf(t1)}" y1="14" y2="${H - 16}"/>${out}</svg></div>`;
    host.dataset.drawn = "1";
    host.querySelectorAll(".rg").forEach((g) => g.addEventListener("click", () => { const x = withH.find((y) => y.label === g.dataset.k); if (x) onPick(x); }));
  }

  // ------------------------------------------------------------ TOKEN CONSTELLATION (deterministic force layout)
  function constellation(host, n, cl, { onToken, compact }) {
    const nodes = cl.nodes.map((t, i) => ({ t, i, x: 0, y: 0, vx: 0, vy: 0 }));
    const N = nodes.length, W = compact ? 340 : 640, H = compact ? 300 : 360;
    nodes.forEach((p, i) => { const a = (i / N) * Math.PI * 2, r = 30 + 80 * hash(p.t.mint); p.x = Math.cos(a) * r; p.y = Math.sin(a) * r; });
    const edges = cl.edges.map(([a, b, k]) => ({ a: nodes[a], b: nodes[b], k }));
    const maxB = Math.max(1, ...cl.nodes.map((t) => t.buyers));
    const rad = (t) => 4 + 13 * Math.sqrt(t.buyers / maxB);
    const L = Math.max(26, 70 * Math.sqrt(12 / Math.max(4, N)));
    for (let it = 0; it < 320; it++) {
      const cool = 1 - it / 320;
      for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
        const p = nodes[i], q = nodes[j], dx = q.x - p.x, dy = q.y - p.y, d2 = dx * dx + dy * dy + 0.01, d = Math.sqrt(d2);
        const f = (900 / d2) * cool, min = rad(p.t) + rad(q.t) + 6;
        const push = d < min ? (min - d) * 0.5 : 0;
        const fx = (dx / d) * (f + push), fy = (dy / d) * (f + push);
        p.vx -= fx; p.vy -= fy; q.vx += fx; q.vy += fy;
      }
      for (const e of edges) {
        const dx = e.b.x - e.a.x, dy = e.b.y - e.a.y, d = Math.hypot(dx, dy) || 0.01, want = e.k === "meaning" ? L : L * 0.6, f = (d - want) * 0.04 * cool;
        e.a.vx += (dx / d) * f; e.a.vy += (dy / d) * f; e.b.vx -= (dx / d) * f; e.b.vy -= (dy / d) * f;
      }
      for (const p of nodes) { p.vx -= p.x * 0.012; p.vy -= p.y * 0.012; p.x += p.vx; p.y += p.vy; p.vx *= 0.55; p.vy *= 0.55; }
    }
    // fit to the plate
    const xs = nodes.map((p) => p.x), ys = nodes.map((p) => p.y), pad = 34;
    const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
    const k = Math.min((W - pad * 2) / (maxx - minx || 1), (H - pad * 2) / (maxy - miny || 1), 3.4);
    const X = (v) => W / 2 + (v - (minx + maxx) / 2) * k, Y = (v) => H / 2 + (v - (miny + maxy) / 2) * k;
    const e = enc(n.category);
    const cls = { meaning: "meaning", "same X post": "post", "same picture": "picture", "same name": "name" };
    const top = new Set([...cl.nodes].sort((a, b) => b.buyers - a.buyers).slice(0, compact ? 6 : 12).map((t) => t.mint));
    host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${N} tokens in this narrative and how they are linked">
      ${edges.map((ed) => `<line class="edge ${cls[ed.k] || "meaning"}" x1="${X(ed.a.x).toFixed(1)}" y1="${Y(ed.a.y).toFixed(1)}" x2="${X(ed.b.x).toFixed(1)}" y2="${Y(ed.b.y).toFixed(1)}"/>`).join("")}
      ${nodes.map((p) => {
        const t = p.t, r = rad(t), op = 0.35 + 0.65 * Math.max(0, Math.min(1, (t.similarity - 0.4) / 0.5));
        return `<g class="node" tabindex="0" role="button" aria-label="${esc(t.symbol || t.name || "token")}, ${t.buyers} buyers per hour" data-m="${esc(t.mint)}" transform="translate(${X(p.x).toFixed(1)} ${Y(p.y).toFixed(1)})">
          <circle r="${r.toFixed(1)}" style="fill:${e.ink}" fill-opacity="${op.toFixed(2)}" stroke="var(--paper)" stroke-width="1"/>
          ${top.has(t.mint) ? `<text x="${(r + 4).toFixed(1)}" y="4">${esc((t.symbol || t.name || "").slice(0, 12))}</text>` : ""}</g>`;
      }).join("")}</svg>`;
    host.querySelectorAll(".node").forEach((g) => {
      const t = cl.nodes.find((x) => x.mint === g.dataset.m);
      g.addEventListener("click", () => { hideTip(); onToken(t.mint); });
      g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); onToken(t.mint); } });
      g.addEventListener("pointerenter", (ev) => showTip(`<div class="k">${esc(t.via.join(", "))}</div><b>${esc(t.symbol || "")}</b><div>${esc(t.name || "")}</div><div class="n">${t.buyers.toLocaleString()} buyers/h · similarity ${t.similarity.toFixed(2)}</div>`, ev.clientX, ev.clientY - 6));
      g.addEventListener("pointerleave", hideTip);
    });
  }

  // ------------------------------------------------------------ state tracker (one block per read)
  function tracker(n) {
    const h = (n.history || []).filter((x) => x[3]);
    if (h.length < 2) return "";
    return `<div class="tracker" role="img" aria-label="State at each of the last ${h.length} reads, oldest first: ${esc(h.map((x) => x[3]).join(", "))}">
      ${h.map((x) => `<i class="${esc(x[3])}" title="${hhmm(x[0])}: ${esc(STAGE_LABEL[x[3]] || x[3])}"></i>`).join("")}</div>
      <div class="tracker-k"><span>${hhmm(h[0][0])}</span><span>now</span></div>`;
  }

  return { CAT, RING, CREATED, NOVEL, STAGES, STAGE_LABEL, STAGE_NOTE, GLYPH, enc, catName, bandKey, swatch, life, stamp,
    remember, moved, num, tick, motion, atlas, ridges, constellation, tracker };
})();
