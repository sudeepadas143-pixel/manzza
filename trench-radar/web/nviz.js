// TRENCH//RADAR narrative visuals: category encoding, the narrative field, momentum lines,
// token clusters, lifecycle tracker and number tickers. ECharts (Apache-2.0, vendored) is loaded
// on first use. Motion is only ever a change in the data: marks move when a narrative moves,
// numbers count when they change, a badge shines once when a state flips.
"use strict";

const NViz = (() => {
  const { esc } = Charts;
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  // ------------------------------------------------------------ category encoding
  // Eight pigment families in a fixed order (validated for the dark plane: every adjacent pair
  // separates under protan/deutan simulation, ΔE ≥ 11; normal vision ≥ 20; all ≥ 3:1 contrast).
  // Eleven categories share them; the second member of a family is drawn as a diamond.
  // Colour follows the category, never its rank.
  const FAMILY = [
    ["art", "#cb5589"], ["crypto", "#5193f4"], ["absurd", "#7b7c29"], ["play", "#8570dd"],
    ["tech", "#27a7a8"], ["culture", "#9f52b1"], ["creature", "#bf6d2c"], ["news", "#3ca1c4"],
  ];
  const CAT = {
    "Art & visual memes": ["art", "circle"], "Lifestyle & nostalgia": ["art", "diamond"],
    "Crypto-native": ["crypto", "circle"], "Absurdist & surreal": ["absurd", "circle"],
    "Gaming, anime & entertainment": ["play", "circle"], "Technology & AI": ["tech", "circle"],
    "Internet culture & slang": ["culture", "circle"], "Communities & fandoms": ["culture", "diamond"],
    "Characters & creatures": ["creature", "circle"], "Current events & news": ["news", "circle"],
    "Politics & geopolitics": ["news", "diamond"],
  };
  const HEX = Object.fromEntries(FAMILY);
  const NOVEL = "#edebe4", EMERGENT = "#b3b0a7";
  const catName = (c) => c?.primary || "New kind of meta";
  // a category the app created from earlier narratives is drawn in bone with a dashed outline
  const enc = (c) => {
    const e = CAT[c?.primary];
    if (e) return { color: HEX[e[0]], shape: e[1], family: e[0], kind: "seed" };
    return c?.primary ? { color: EMERGENT, shape: "roundRect", family: "emergent", kind: "emergent" }
      : { color: NOVEL, shape: "circle", family: "novel", kind: "novel" };
  };
  const ORDER = Object.keys(CAT);
  // categories the app created are folded into one group in the band and filters (8 hues is the cap)
  const CREATED = "Created by the app";
  const bandKey = (c) => (enc(c).kind === "emergent" ? CREATED : catName(c));
  const swatch = (c, size = 9) => {
    const e = enc(c);
    const r = e.shape === "diamond" ? "transform:rotate(45deg) scale(.85);border-radius:1px" : e.shape === "roundRect" ? "border-radius:2px;background:none;border:1.5px dashed " + e.color : "border-radius:50%";
    return `<i class="sw" aria-hidden="true" style="width:${size}px;height:${size}px;background:${e.color};${r}"></i>`;
  };

  // ------------------------------------------------------------ lifecycle
  // brightness encodes life: emerging narratives are lit, established ones dim, saturated ones hollow
  const LIFE = { new: "emerging", heating: "emerging", accelerating: "emerging", bought: "emerging", steady: "established", saturating: "saturated", fading: "saturated" };
  const life = (s) => LIFE[s] || "established";

  // ------------------------------------------------------------ motion helpers
  const motion = () => document.documentElement.dataset.perf !== "low" && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const prevVals = new Map();
  // remember a value; returns the previous one (undefined the first time)
  const remember = (key, v) => { const p = prevVals.get(key); prevVals.set(key, v); return p; };
  // count from the previous value to the new one; only when the data changed
  function tick(root = document) {
    if (!motion()) return;
    root.querySelectorAll("[data-tick]").forEach((el) => {
      const to = +el.dataset.tick, from = +el.dataset.from;
      if (!Number.isFinite(from) || from === to) return;
      const fmt = el.dataset.fmt === "signed" ? (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1) : (v) => Math.round(v).toLocaleString();
      const t0 = performance.now(), D = 700;
      const step = (t) => {
        const k = Math.min(1, (t - t0) / D), e = 1 - Math.pow(1 - k, 4);
        el.textContent = fmt(from + (to - from) * e);
        if (k < 1 && el.isConnected) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }
  // a number that ticks when it changed since the last render under the same key
  const num = (key, v, text, fmt = "int") => {
    const p = remember(key, v);
    return `<span ${Number.isFinite(p) && p !== v && Number.isFinite(v) ? `data-tick="${v}" data-from="${p}" data-fmt="${fmt}"` : ""}>${text}</span>`;
  };
  // up/down flash class for a ledger cell whose value moved since the last read
  const moved = (key, v) => { const p = remember(key, v); return Number.isFinite(p) && Number.isFinite(v) && p !== v ? (v > p ? "chg-up" : "chg-down") : ""; };

  // ------------------------------------------------------------ ECharts loading and theme
  let loading = null;
  const ready = () => loading || (loading = new Promise((ok, bad) => {
    if (window.echarts) return ok(window.echarts);
    const s = document.createElement("script");
    s.src = "/static/vendor/echarts-5.6.0.min.js";
    s.onload = () => { theme(); ok(window.echarts); };
    s.onerror = () => { loading = null; bad(new Error("chart library failed to load")); };
    document.head.appendChild(s);
  }));
  function theme() {
    const ink3 = css("--ink-3"), rule = css("--rule");
    echarts.registerTheme("radar", {
      color: FAMILY.map((f) => f[1]), backgroundColor: "transparent",
      textStyle: { fontFamily: css("--sans"), color: ink3, fontSize: 11.5 },
      categoryAxis: { axisLine: { lineStyle: { color: rule } }, axisTick: { show: false }, splitLine: { lineStyle: { color: rule } } },
      valueAxis: { axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: rule, type: [2, 4] } }, axisLabel: { color: ink3 } },
      logAxis: { axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: rule, type: [2, 4] } }, axisLabel: { color: ink3 } },
      timeAxis: { axisLine: { lineStyle: { color: rule } }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { color: ink3 } },
    });
  }
  const TIP = () => ({
    backgroundColor: css("--plane-2"), borderColor: css("--rule-2"), borderWidth: 1, padding: [8, 10],
    textStyle: { color: css("--ink"), fontFamily: css("--sans"), fontSize: 12.5 }, extraCssText: "border-radius:4px;box-shadow:none;max-width:280px;white-space:normal",
  });

  // One live chart per slot that survives re-renders: the page HTML is rebuilt on every refresh,
  // so the existing chart element is moved into the new placeholder and only told about changed
  // data. ECharts then animates marks from where they were to where the new read puts them, and an
  // unchanged read moves nothing (a force layout is never re-run for the same data).
  const slots = new Map();
  const fingerprint = (o) => JSON.stringify((o.series || []).map((x) => [x.id || x.name || "", (x.data || []).map((d) => (d && typeof d === "object" && !Array.isArray(d) ? { ...d, _n: 0, _t: 0 } : d)), (x.links || []).length]));
  async function mount(slot, el, build) {
    if (!el) return null;
    let ec;
    try { ec = await ready(); } catch (_) { el.innerHTML = `<p class="notes">The chart library did not load; the table has the same data.</p>`; return null; }
    if (!el.isConnected) return null;
    const option = build();
    const anim = motion();
    Object.assign(option, { animation: anim, animationDuration: 650, animationDurationUpdate: 650, animationEasing: "cubicOut", animationEasingUpdate: "cubicInOut" });
    const fp = fingerprint(option), old = slots.get(slot);
    if (old && old.sig === option._sig && !old.chart.isDisposed()) {
      const dom = old.chart.getDom();
      if (dom !== el) {
        for (const a of ["id", "class", "role", "aria-label"]) { const v = el.getAttribute(a); if (v === null) dom.removeAttribute(a); else dom.setAttribute(a, v); }
        el.replaceWith(dom);
      }
      if (old.fp !== fp) old.chart.setOption(option, { replaceMerge: ["series"] });
      old.fp = fp; old.chart.off("click"); old.chart.resize();
      return old.chart;
    }
    if (old) { try { old.chart.dispose(); } catch (_) { /* detached */ } }
    const chart = ec.init(el, "radar", { renderer: "canvas" });
    chart.setOption(option);
    slots.set(slot, { chart, sig: option._sig, fp });
    new ResizeObserver(() => { if (!chart.isDisposed() && chart.getDom().isConnected) chart.resize(); }).observe(el);
    return chart;
  }
  const drop = (slot) => { const s = slots.get(slot); if (s) { try { s.chart.dispose(); } catch (_) { /* gone */ } slots.delete(slot); } };

  // ------------------------------------------------------------ lifecycle tally + category band (HTML)
  function tally(all) {
    const n = { emerging: 0, established: 0, saturated: 0 };
    all.forEach((x) => n[life(x.state)]++);
    const tot = all.length || 1;
    const seg = (k, label) => `<div class="lf ${k}"><div class="lf-n">${num("life:" + k, n[k], n[k])}</div><div class="lf-k">${label}</div></div>`;
    return `<div class="tally">${seg("emerging", "Emerging")}${seg("established", "Established")}${seg("saturated", "Saturating or fading")}
      <div class="lifebar" role="img" aria-label="${n.emerging} emerging, ${n.established} established, ${n.saturated} saturating or fading">
        ${["emerging", "established", "saturated"].map((k) => n[k] ? `<i class="${k}" style="flex:${n[k] / tot}"></i>` : "").join("")}</div></div>`;
  }
  function band(all, selected) {
    const by = new Map();
    all.forEach((x) => { const k = bandKey(x.category); const b = by.get(k) || { c: x.category, launches: 0, n: 0, emerging: 0, names: new Set() }; b.launches += x.popularity.launches_6h; b.n++; b.names.add(catName(x.category)); if (life(x.state) === "emerging") b.emerging++; by.set(k, b); });
    const rank = (k) => (k === CREATED ? 98 : k === "New kind of meta" ? 99 : ORDER.indexOf(k));
    const cats = [...by.entries()].sort((a, b) => rank(a[0]) - rank(b[0]) || b[1].launches - a[1].launches);
    const tot = cats.reduce((s, [, b]) => s + b.launches, 0) || 1;
    return `<div class="band" role="group" aria-label="Launches by category, last 6 hours">
      <div class="band-bar">${cats.map(([k, b]) => `<button class="bseg" data-cat="${esc(k)}" aria-pressed="${selected === k}" title="${esc(k === CREATED ? `${k}: ${[...b.names].slice(0, 6).join(", ")}` : k)}: ${b.launches} launches"
        style="flex:${Math.max(b.launches / tot, 0.012)};--c:${enc(b.c).color}"><span class="sr">${esc(k)}</span></button>`).join("")}</div>
      <div class="band-keys">${cats.map(([k, b]) => `<button class="bk" data-cat="${esc(k)}" aria-pressed="${selected === k}">${swatch(b.c)}<span class="bn">${esc(k)}</span>
        <span class="ct">${k === CREATED ? `${b.names.size} · ` : ""}${Math.round(100 * b.launches / tot)}%<span class="em">${b.emerging ? ` · ${b.emerging} emerging` : ""}</span></span></button>`).join("")}</div></div>`;
  }

  // ------------------------------------------------------------ the narrative field
  function field(el, all, { selected, compact, onPick, highlight }) {
    const pts = all.map((n) => ({ n, x: Math.max(-3, Math.min(8, n.popularity.velocity_z || 0)), y: Math.max(0.5, n.traction.buyers_per_launch_1h || 0) }));
    const ys = pts.map((p) => p.y).sort((a, b) => a - b);
    const midY = ys.length ? ys[Math.floor(ys.length / 2)] : 2;
    const maxL = Math.max(1, ...all.map((n) => n.popularity.launches_6h));
    const labelled = new Set([...all].sort((a, b) => (b.traction.buyers_h1 || 0) - (a.traction.buyers_h1 || 0)).slice(0, compact ? 4 : 9).map((n) => n.label));
    labelled.add(selected);
    const glow = motion();
    const ink = css("--ink"), ink3 = css("--ink-3"), ink4 = css("--ink-4");
    const data = pts.map(({ n, x, y }) => {
      const e = enc(n.category), L = life(n.state), sel = n.label === selected, dim = highlight && bandKey(n.category) !== highlight;
      const size = 9 + 34 * Math.sqrt(n.popularity.launches_6h / maxL);
      return {
        name: n.label, value: [x, y], symbol: e.shape, symbolSize: sel ? size + 6 : size,
        itemStyle: {
          color: L === "saturated" ? "rgba(0,0,0,0)" : e.color,
          opacity: dim ? 0.12 : L === "emerging" ? 0.95 : L === "established" ? 0.55 : 0.9,
          borderColor: sel ? ink : L === "saturated" ? e.color : css("--plane"), borderWidth: sel ? 2 : L === "saturated" ? 1.5 : 1.5,
          borderType: L === "saturated" ? [3, 3] : "solid",
          shadowBlur: glow && L === "emerging" && !dim ? 16 : 0, shadowColor: e.color,
        },
        label: { show: labelled.has(n.label) && !dim, formatter: n.title.length > 18 ? n.title.slice(0, 17) + "…" : n.title, position: x > 5 ? "left" : "right", distance: 6,
          color: sel ? ink : css("--ink-2"), fontFamily: css("--serif"), fontSize: sel ? 14 : 12.5 },
        _n: n,
      };
    });
    const zone = (x0, x1, y0, y1, label, pos) => [{ xAxis: x0, yAxis: y0, name: label, label: { show: true, position: pos, color: ink4, fontSize: 11, fontFamily: css("--sans") } }, { xAxis: x1, yAxis: y1 }];
    return mount("field", el, () => ({
      _sig: "field",
      grid: { left: 52, right: compact ? 26 : 40, top: 30, bottom: 44 },
      tooltip: { ...TIP(), trigger: "item", triggerOn: glow ? "mousemove|click" : "click", formatter: (p) => {
        const n = p.data._n; if (!n) return "";
        return `<b style="font:500 15px ${css("--serif")}">${esc(n.title)}</b><br><span style="color:${ink3}">${esc(catName(n.category))} · ${esc(n.state)}</span><br>`
          + `${n.popularity.launches_6h} launches / ${n.popularity.creators_6h} creators in 6h<br>launch momentum z ${(n.popularity.velocity_z || 0).toFixed(1)}<br>`
          + `${(n.traction.buyers_h1 || 0).toLocaleString()} buyers/h · ${(n.traction.buyers_per_launch_1h || 0).toFixed(1)} per launch`;
      } },
      xAxis: { type: "value", min: -3, max: 8, interval: 1, axisLabel: { formatter: (v) => (v === 0 ? "0" : v > 0 ? "+" + v : "−" + -v) }, name: "Launch momentum (z, creators this hour vs before)", nameLocation: "middle", nameGap: 26, nameTextStyle: { color: ink3, fontSize: 11.5 },
        splitLine: { show: false } },
      yAxis: { type: "log", min: 0.4, name: "Buyers per launch, last hour", nameLocation: "end", nameGap: 8, nameTextStyle: { color: ink3, fontSize: 11.5, align: "left" },
        axisLabel: { formatter: (v) => (v < 1 ? "0" : v >= 1000 ? Math.round(v / 1000) + "k" : String(v)) } },
      series: [{
        type: "scatter", data, cursor: "pointer", clip: false,
        emphasis: { scale: 1.15, label: { show: true }, itemStyle: { opacity: 1 } },
        labelLayout: { hideOverlap: true },
        markLine: { silent: true, symbol: "none", lineStyle: { color: css("--rule-2"), type: [4, 4] }, label: { show: false },
          data: [{ xAxis: 2 }, { yAxis: midY }] },
        markArea: { silent: true, itemStyle: { color: "rgba(0,0,0,0)" }, data: [
          zone(2, 8, midY, "max", "Emerging with buyers", "insideTopRight"),
          zone(2, 8, 0.5, midY, "Launch rush, thin buying", "insideBottomRight"),
          zone(-3, 2, midY, "max", "Bought without a rush", "insideTopLeft"),
          zone(-3, 2, 0.5, midY, "Quiet or saturated", "insideBottomLeft")] },
      }],
    })).then((c) => { if (c) c.on("click", (p) => p.data?._n && onPick(p.data._n)); return c; });
  }

  // ------------------------------------------------------------ momentum lines (buyers/h over the last 3h)
  function momentum(el, all, { onPick, compact }) {
    const withH = all.filter((n) => (n.history || []).length >= 2).sort((a, b) => (b.traction.buyers_h1 || 0) - (a.traction.buyers_h1 || 0)).slice(0, compact ? 4 : 6);
    if (!withH.length) { drop("momentum"); el.innerHTML = `<p class="notes" style="margin:0">Momentum lines appear after two reads of the same narrative (about 10 minutes).</p>`; return Promise.resolve(null); }
    const fams = new Map();
    return mount("momentum", el, () => ({
      _sig: "momentum",
      grid: { left: 44, right: compact ? 96 : 132, top: 14, bottom: 26 },
      tooltip: { ...TIP(), trigger: "axis", axisPointer: { type: "line", lineStyle: { color: css("--rule-2") } },
        valueFormatter: (v) => (v ?? 0).toLocaleString() + " buyers/h" },
      xAxis: { type: "time", axisLabel: { formatter: (v) => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), hideOverlap: true } },
      yAxis: { type: "value", min: 0, splitNumber: 3 },
      series: withH.map((n) => {
        const e = enc(n.category), k = fams.get(e.family) || 0; fams.set(e.family, k + 1);
        return {
          type: "line", name: n.title, id: n.label, showSymbol: false, smooth: 0.25, cursor: "pointer",
          data: n.history.map((h) => [h[0] * 1000, h[2] || 0]),
          // two narratives of one family: the second is dashed, so lines never rely on colour alone
          lineStyle: { width: 2, color: e.color, type: k ? [6, 3] : "solid" }, itemStyle: { color: e.color },
          endLabel: { show: true, formatter: () => (n.title.length > 14 ? n.title.slice(0, 13) + "…" : n.title), color: css("--ink-2"), fontFamily: css("--serif"), fontSize: 12.5, distance: 6 },
          labelLayout: { moveOverlap: "shiftY" }, emphasis: { focus: "series" },
          _label: n.label,
        };
      }),
    })).then((c) => { if (c) c.on("click", (p) => { const n = withH[p.seriesIndex]; if (n) onPick(n); }); return c; });
  }

  // ------------------------------------------------------------ one narrative: buyers and launches (two aligned panels, one axis each)
  function trend(el, n) {
    const h = n.history || [];
    const t = h.map((x) => x[0] * 1000);
    const dem = css("--demand"), att = css("--attention");
    return mount("trend", el, () => ({
      _sig: "trend:" + n.label,
      tooltip: { ...TIP(), trigger: "axis", axisPointer: { link: [{ xAxisIndex: "all" }], lineStyle: { color: css("--rule-2") } } },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: [{ left: 40, right: 12, top: 18, height: "34%" }, { left: 40, right: 12, top: "60%", bottom: 24 }],
      xAxis: [{ type: "time", gridIndex: 0, axisLabel: { show: false } }, { type: "time", gridIndex: 1, axisLabel: { formatter: (v) => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), hideOverlap: true } }],
      yAxis: [{ type: "value", gridIndex: 0, min: 0, splitNumber: 2, name: "Buyers per hour", nameLocation: "end", nameTextStyle: { align: "left", color: dem, fontSize: 11.5 } },
        { type: "value", gridIndex: 1, min: 0, splitNumber: 2, name: "Launches, last 6h", nameLocation: "end", nameTextStyle: { align: "left", color: att, fontSize: 11.5 } }],
      series: [
        { type: "line", name: "Buyers/h", xAxisIndex: 0, yAxisIndex: 0, showSymbol: false, data: h.map((x, i) => [t[i], x[2] || 0]),
          lineStyle: { width: 2, color: dem }, itemStyle: { color: dem },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(79,191,134,.28)" }, { offset: 1, color: "rgba(79,191,134,0)" }]) } },
        { type: "line", name: "Launches 6h", xAxisIndex: 1, yAxisIndex: 1, step: "end", showSymbol: false, data: h.map((x, i) => [t[i], x[1] || 0]),
          lineStyle: { width: 2, color: att }, itemStyle: { color: att } },
      ],
    }));
  }

  // ------------------------------------------------------------ token cluster (force graph)
  const LINK = { "same X post": () => css("--attention"), "same picture": () => "#c9a0e8", "same name": () => css("--caution"), meaning: () => css("--rule-2") };
  function cluster(el, n, cl, { onToken, compact }) {
    const e = enc(n.category);
    const maxB = Math.max(1, ...cl.nodes.map((x) => x.buyers));
    return mount("cluster", el, () => ({
      _sig: "cluster:" + n.label,
      tooltip: { ...TIP(), trigger: "item", formatter: (p) => {
        if (p.dataType === "edge") return esc(p.data._kind === "meaning" ? "nearest by meaning" : p.data._kind);
        const t = p.data._t;
        return `<b>${esc(t.symbol || "")}</b> ${esc(t.name || "")}<br>${t.buyers.toLocaleString()} buyers/h · similarity ${t.similarity.toFixed(2)}<br><span style="color:${css("--ink-3")}">linked by ${esc(t.via.join(", "))} · click to open</span>`;
      } },
      series: [{
        type: "graph", layout: "force", roam: false, draggable: !compact, cursor: "pointer",
        // spacing scales with the number of tokens so small clusters don't collapse into a knot
        force: { repulsion: (compact ? 180 : 230) / Math.sqrt(cl.nodes.length), edgeLength: [10, 34].map((v) => v * Math.sqrt(40 / Math.max(4, cl.nodes.length))),
          gravity: 0.35, friction: 0.2, layoutAnimation: motion() },
        data: cl.nodes.map((t, i) => {
          const hard = t.via.some((v) => v !== "meaning");
          return {
            id: String(i), name: t.symbol || t.name || "?", value: t.buyers, _t: t,
            symbolSize: 7 + 26 * Math.sqrt(t.buyers / maxB),
            itemStyle: { color: e.color, opacity: 0.35 + 0.65 * Math.max(0, Math.min(1, (t.similarity - 0.4) / 0.5)),
              borderColor: hard ? LINK[t.via.find((v) => v !== "meaning")]() : css("--plane"), borderWidth: hard ? 2 : 1 },
            label: { show: i < (compact ? 6 : 10), position: "right", color: css("--ink-2"), fontSize: 11.5, fontFamily: css("--mono") },
          };
        }),
        links: cl.edges.map(([a, b, kind]) => ({ source: String(a), target: String(b), _kind: kind,
          lineStyle: { color: LINK[kind](), width: kind === "meaning" ? 1 : 1.6, opacity: kind === "meaning" ? 0.6 : 0.9, curveness: 0.08 } })),
        emphasis: { focus: "adjacency", lineStyle: { width: 2 } },
        labelLayout: { hideOverlap: true },
      }],
    })).then((c) => { if (c) c.on("click", (p) => p.dataType === "node" && onToken(p.data._t.mint)); return c; });
  }
  const clusterLegend = () => `<span class="legend">${[["same X post", "--attention"], ["same picture", null], ["same name", "--caution"], ["meaning", "--rule-2"]]
    .map(([k, v]) => `<span><i style="height:2px;width:14px;vertical-align:3px;background:${v ? `var(${v})` : "#c9a0e8"}"></i>${k === "meaning" ? "nearest by meaning" : k}</span>`).join("")}</span>`;

  // ------------------------------------------------------------ state tracker (one block per read)
  const TRACK = { accelerating: "pos", bought: "pos", heating: "warn", new: "mute", steady: "mute", saturating: "warn2", fading: "neg" };
  function tracker(n) {
    const h = (n.history || []).filter((x) => x[3]);
    if (h.length < 2) return "";
    const hm = (s) => new Date(s * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return `<div class="tracker" role="img" aria-label="State at each of the last ${h.length} reads, oldest first: ${esc(h.map((x) => x[3]).join(", "))}">
      ${h.map((x) => `<i class="${TRACK[x[3]] || "mute"}" title="${hm(x[0])}: ${esc(x[3])}"></i>`).join("")}</div>
      <div class="tracker-k"><span>${hm(h[0][0])}</span><span>now</span></div>`;
  }

  return { enc, catName, bandKey, swatch, life, tally, band, field, momentum, trend, cluster, clusterLegend, tracker, num, moved, tick, remember, motion, drop, ready };
})();
