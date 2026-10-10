/**
 * SVG drawings built from the shared lamination geometry.
 * Runs in Node (at build time, for the labelled step-lap diagram) and in the
 * browser (for the no-WebGL fallback frames). No DOM access here: every
 * function returns an SVG string.
 */
import {
  CORE, corePieces, coreOutline, stepOffsets, eShape, iShape, stripShape, bounds, holesLeftOf,
} from './geometry.js';

const f = (n) => Math.round(n * 100) / 100;

/** Path data for a polygon under a mapping fn([x,y]) -> [px,py]. */
export function pathD(poly, map) {
  return poly.map((p, i) => {
    const [x, y] = map(p);
    return `${i ? 'L' : 'M'}${f(x)} ${f(y)}`;
  }).join('') + 'Z';
}

/** Path data for a lamination with its punched holes (use with fill-rule="evenodd"). */
export function piecePathD(poly, holes = [], map) {
  return pathD(poly, map) + holes.map((h) => pathD(h, map)).join('');
}

/** Map core units into an SVG box (y flipped so +y is up). */
function mapper(b, box, pad = 0) {
  const k = Math.min((box.w - pad * 2) / b.w, (box.h - pad * 2) / b.h);
  const ox = box.x + (box.w - b.w * k) / 2;
  const oy = box.y + (box.h + b.h * k) / 2;
  return { k, map: ([x, y]) => [ox + (x - b.x0) * k, oy - (y - b.y0) * k] };
}

const STEPS = 5;
const STEP = 0.07;

/* ------------------------------------------------------------------------ */
/* Labelled step-lap diagram (mitre-core page)                               */
/* ------------------------------------------------------------------------ */

/** Face view of one outer mitre corner: top layer drawn, joints below dashed. */
export function stepLapFaceSVG({ id = 'face', compact = false } = {}) {
  const w = 0.95;
  const offsets = stepOffsets(STEPS, STEP);
  const top = offsets[STEPS - 1];
  const pieces = corePieces({ w, o: top, gap: 0.012 });
  const ox = CORE.limbX[0] - w / 2;
  const oy = CORE.yokeY[0] - w / 2;
  // Window onto the bottom-left corner
  const view = { x0: ox - 0.12, y0: oy - 0.12, x1: ox + 1.58, y1: oy + 2.05 }; // stop short of the V-notch
  view.w = view.x1 - view.x0; view.h = view.y1 - view.y0;
  const W = 780, H = 560;
  const { map } = mapper(view, { x: 80, y: 20, w: 420, h: 520 }, 0);
  const clipId = `${id}-clip`;
  const [cx0, cy0] = map([view.x0, view.y1]);
  const [cx1, cy1] = map([view.x1, view.y0]);

  const limb = pieces.find((p) => p.id === 'limb-l');
  const yoke = pieces.find((p) => p.id === 'yoke-b');

  // Joint line of a layer with offset o (outer corner -> inner corner)
  const joint = (o) => {
    const a = [ox + Math.max(0, -o), oy + Math.max(0, -o) + o];
    const b = [ox + w, oy + w + o];
    return [map(a), map(b)];
  };
  const dashed = offsets.slice(0, -1).map((o) => {
    const [[x1, y1], [x2, y2]] = joint(o);
    return `<line x1="${f(x1)}" y1="${f(y1)}" x2="${f(x2)}" y2="${f(y2)}" class="d-hidden"/>`;
  }).join('');
  const [[jx1, jy1], [jx2, jy2]] = joint(top);

  // Step dimension along the outer edge (x = ox), between two joints
  const oA = offsets[STEPS - 2], oB = offsets[STEPS - 1];
  const dimX = map([ox, 0])[0] - 18;
  const yA = map([0, oy + oA])[1];
  const yB = map([0, oy + oB])[1];

  // 45° arc at the outer end of the top joint: between the outer edge and the cut
  const outer = map([ox, oy + top]);
  const r = 56;
  const arc = `M${f(outer[0])} ${f(outer[1] - r)} A${r} ${r} 0 0 1 ${f(outer[0] + r * Math.SQRT1_2)} ${f(outer[1] - r * Math.SQRT1_2)}`;

  const limbC = map([ox + w / 2, oy + 1.45]);
  const yokeC = map([ox + 0.98, oy + w / 2]); // clear of the bolt hole

  let n = 0;
  const vb = compact ? '-14 0 530 560' : `0 0 ${W} ${H}`;
  return `<svg viewBox="${vb}" role="img" aria-labelledby="${id}-t ${id}-d" class="diagram${compact ? ' diagram--compact' : ' diagram--full'}">
  <title id="${id}-t">Face view of a step-lap mitre corner</title>
  <desc id="${id}-d">The limb lamination meets the yoke lamination on a 45 degree mitre. The joint of the top layer is highlighted; the joints of the layers beneath are shown dashed, each moved one step along from the last.</desc>
  <defs><clipPath id="${clipId}"><rect x="${f(cx0)}" y="${f(cy0)}" width="${f(cx1 - cx0)}" height="${f(cy1 - cy0)}"/></clipPath>
  <marker id="${id}-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="d-arrowhead"/></marker></defs>
  <g clip-path="url(#${clipId})">
    <path d="${pathD(limb.poly, map)}" class="d-steel"/>
    <path d="${piecePathD(yoke.poly, yoke.holes, map)}" class="d-steel" fill-rule="evenodd"/>
    ${dashed}
    <line x1="${f(jx1)}" y1="${f(jy1)}" x2="${f(jx2)}" y2="${f(jy2)}" class="d-accent"/>
  </g>
  <line x1="${f(limbC[0])}" y1="${f(limbC[1] + 40)}" x2="${f(limbC[0])}" y2="${f(limbC[1] - 40)}" class="d-grain" marker-end="url(#${id}-ar)"/>
  <line x1="${f(yokeC[0] - 40)}" y1="${f(yokeC[1])}" x2="${f(yokeC[0] + 40)}" y2="${f(yokeC[1])}" class="d-grain" marker-end="url(#${id}-ar)"/>
  <path d="${arc}" class="d-dim"/>
  <text x="${f(outer[0] + r * 0.42)}" y="${f(outer[1] - r - 8)}" class="d-label d-strong">45°</text>
  <line x1="${f(dimX)}" y1="${f(yA)}" x2="${f(dimX)}" y2="${f(yB)}" class="d-dim" marker-start="url(#${id}-ar)" marker-end="url(#${id}-ar)"/>
  <line x1="${f(dimX - 6)}" y1="${f(yA)}" x2="${f(map([ox, 0])[0])}" y2="${f(yA)}" class="d-dim d-thin"/>
  <line x1="${f(dimX - 6)}" y1="${f(yB)}" x2="${f(map([ox, 0])[0])}" y2="${f(yB)}" class="d-dim d-thin"/>
  ${callout(limbC[0] + 26, limbC[1] - 60, 540, 70, 'Limb lamination', 'Grain runs along the limb')}
  ${callout(yokeC[0] + 50, yokeC[1] - 4, 540, 470, 'Yoke lamination', 'Grain runs along the yoke')}
  ${callout((jx1 + jx2) / 2 + 4, (jy1 + jy2) / 2 - 2, 540, 200, 'Joint, top layer', '45° mitre cut')}
  ${callout(f(map([ox + w * 0.55, oy + w * 0.55 + offsets[1]])[0]), f(map([ox + w * 0.55, oy + w * 0.55 + offsets[1]])[1]), 540, 330, 'Joints of the layers below', 'Each moved one step along')}
  <text x="${f(dimX - 10)}" y="${f((yA + yB) / 2 + 5)}" class="d-label" text-anchor="end">Step</text>
</svg>`;
  function callout(x, y, tx, ty, title, sub) {
    n++;
    if (compact) {
      return `<g class="d-marker"><circle cx="${f(x)}" cy="${f(y)}" r="17" class="d-mark"/><text x="${f(x)}" y="${f(y + 8)}" class="d-mark-n" text-anchor="middle">${n}</text></g>`;
    }
    return `<g class="d-callout"><polyline points="${f(x)},${f(y)} ${f(tx - 14)},${f(ty)} ${f(tx - 4)},${f(ty)}" class="d-leader"/><circle cx="${f(x)}" cy="${f(y)}" r="3" class="d-dot"/>
    <text x="${f(tx)}" y="${f(ty - 3)}" class="d-label d-strong">${title}</text><text x="${f(tx)}" y="${f(ty + 19)}" class="d-label">${sub}</text></g>`;
  }
}

/** Section through the joint region: layers as bars, the gap moving one step per layer. */
export function stepLapSectionSVG({ id = 'section', layers = 10, compact = false } = {}) {
  const W = compact ? 700 : 640, H = compact ? 470 : 440;
  const offsets = stepOffsets(STEPS, 1);
  const x0 = 60, x1 = 540, barH = 16, gapY = 8, top = 70;
  const mid = (x0 + x1) / 2, step = 34, gap = 8;
  let bars = '';
  for (let i = 0; i < layers; i++) {
    const y = top + i * (barH + gapY);
    const o = offsets[i % STEPS] * step;
    const gx = mid + o;
        bars += `<rect x="${x0}" y="${y}" width="${f(gx - gap / 2 - x0)}" height="${barH}" class="d-bar"/>`;
    bars += `<rect x="${f(gx + gap / 2)}" y="${y}" width="${f(x1 - gx - gap / 2)}" height="${barH}" class="d-bar"/>`;
  }
  const yBottom = top + layers * (barH + gapY) - gapY;
  // bracket for one step-lap cycle (first STEPS layers)
  const by0 = top, by1 = top + STEPS * (barH + gapY) - gapY;
  // step dimension between first two gaps
  const g0 = mid + offsets[(layers - 2) % STEPS] * step, g1 = mid + offsets[(layers - 1) % STEPS] * step;
  const rowPrev = top + (layers - 2) * (barH + gapY);
  // flux path around a gap: through layer 2, around the gap via neighbours
  const ly = top + 2 * (barH + gapY) + barH / 2;
  const gx2 = mid + offsets[2] * step;
  const flux = `M${x0 + 30} ${ly} L${f(gx2 - 34)} ${ly} C${f(gx2 - 14)} ${ly} ${f(gx2 - 14)} ${f(ly + barH + gapY)} ${f(gx2)} ${f(ly + barH + gapY)} C${f(gx2 + 14)} ${f(ly + barH + gapY)} ${f(gx2 + 14)} ${ly} ${f(gx2 + 34)} ${ly} L${x1 - 30} ${ly}`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="${id}-t ${id}-d" class="diagram${compact ? ' diagram--compact' : ' diagram--full'}">
  <title id="${id}-t">Section through a step-lap joint</title>
  <desc id="${id}-d">Laminations shown edge-on, thickness exaggerated. The joint gap in each layer sits one step along from the gap in the layer below, and the pattern repeats every cycle, so magnetic flux can pass around a gap through the neighbouring layers.</desc>
  <defs><marker id="${id}-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="d-arrowhead"/></marker>
  <marker id="${id}-af" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" class="d-arrowhead-accent"/></marker></defs>
  <text x="${x0}" y="${top - 30}" class="d-label d-strong">Yoke side</text>
  <text x="${x1}" y="${top - 30}" class="d-label d-strong" text-anchor="end">Limb side</text>
  ${bars}
  <path d="${flux}" class="d-flux" marker-end="url(#${id}-af)"/>
  <line x1="${f(g0)}" y1="${yBottom + 22}" x2="${f(g1)}" y2="${yBottom + 22}" class="d-dim" marker-start="url(#${id}-ar)" marker-end="url(#${id}-ar)"/>
  <line x1="${f(g0)}" y1="${rowPrev + barH}" x2="${f(g0)}" y2="${yBottom + 30}" class="d-dim d-thin"/>
  <line x1="${f(g1)}" y1="${yBottom}" x2="${f(g1)}" y2="${yBottom + 30}" class="d-dim d-thin"/>
  <text x="${f((g0 + g1) / 2)}" y="${yBottom + 50}" class="d-label" text-anchor="middle">Step offset</text>
  <path d="M${x1 + 14} ${by0} h10 V${by1} h-10" class="d-dim"/>
  <text x="${x1 + 30}" y="${(by0 + by1) / 2 - 6}" class="d-label d-strong">One</text>
  <text x="${x1 + 30}" y="${(by0 + by1) / 2 + 14}" class="d-label d-strong">cycle</text>
  <line x1="${x0}" y1="${yBottom + 86}" x2="${x0 + 34}" y2="${yBottom + 86}" class="d-flux"/>
  <text x="${x0 + 46}" y="${yBottom + 91}" class="d-label">Flux path around a joint gap</text>
  <text x="${x0}" y="${yBottom + 50}" class="d-label">Joint gaps</text>
  <line x1="${x0 + 92}" y1="${yBottom + 45}" x2="${f(mid + offsets[0] * step)}" y2="${f(top + (layers - STEPS) * (barH + gapY) + barH / 2)}" class="d-leader"/>
</svg>`;
}

/* ------------------------------------------------------------------------ */
/* Core face drawing (fallback frames, reduced-motion still)                 */
/* ------------------------------------------------------------------------ */

export function coreFace({ box = { x: 0, y: 0, w: 800, h: 520 }, layer = 2, cls = 'f-steel', outlineOnly = false } = {}) {
  const w = 0.95;
  const pieces = corePieces({ w, o: stepOffsets(STEPS, STEP)[layer], gap: 0.02 });
  const b = bounds(pieces.map((p) => p.poly));
  const { map } = mapper(b, box, 30);
  if (outlineOnly) {
    const o = coreOutline({ w });
    return [o.outer, ...o.windows].map((p) => `<path d="${pathD(p, map)}" class="${cls}"/>`).join('');
  }
  return pieces.map((p) => `<path d="${piecePathD(p.poly, p.holes, map)}" class="${cls}" fill-rule="evenodd"/>`).join('');
}

/* ------------------------------------------------------------------------ */
/* Fallback frame set (no WebGL)                                             */
/* ------------------------------------------------------------------------ */

export function fallbackFrames() {
  const V = 'viewBox="0 0 800 520" aria-hidden="true" focusable="false"';
  const frames = [];
  // 1 – empty stage: the opening line is HTML
  frames.push(`<svg ${V}></svg>`);
  // 2 – coil, end view with wraps
  let rings = '';
  for (let r = 70; r <= 170; r += 6) rings += `<circle cx="400" cy="260" r="${r}" class="f-ring"/>`;
  frames.push(`<svg ${V}>${rings}<circle cx="400" cy="260" r="170" class="f-edge"/><circle cx="400" cy="260" r="70" class="f-edge"/></svg>`);
  // 3 – sheet with cut lines, splitting into strips
  let strips = '';
  const sw = 64;
  for (let i = 0; i < 4; i++) {
    const y = 150 + i * (sw + 16);
    strips += `<rect x="150" y="${y}" width="520" height="${sw}" class="f-steel"/>`;
  }
  let cuts = '';
  for (let i = 0; i < 3; i++) {
    const y = 150 + sw + 8 + i * (sw + 16);
    cuts += `<line x1="130" y1="${y}" x2="690" y2="${y}" class="f-cut"/>`;
  }
  frames.push(`<svg ${V}>${strips}${cuts}</svg>`);
  // 4 – mitre lamination with 45° dimension, plus E, I and strip profiles
  const trap = 'M120 170 L520 170 L460 230 L180 230 Z';
  const eMap = (p) => [540 + p[0] * 36, 380 - p[1] * 36];
  const ePath = pathD(eShape(1), eMap);
  const iPath = pathD(iShape(1), (p) => [540 + p[0] * 36, 420 - p[1] * 36]);
  const s = stripShape({ length: 4, width: 0.5, holes: 3, holeR: 0.07 });
  const sMap = (p) => [120 + p[0] * 70, 420 - p[1] * 70];
  const sPath = pathD(s.outer, sMap) + s.holes.map((h) => pathD(h, sMap)).join('');
  frames.push(`<svg ${V}><path d="${trap}" class="f-steel"/><line x1="530" y1="160" x2="450" y2="240" class="f-cut"/>
    <path d="M520 170 L520 120" class="f-dim"/><path d="M520 130 A40 40 0 0 0 491.7 141.7" class="f-dim"/>
    <path d="${ePath}" class="f-steel"/><path d="${iPath}" class="f-steel"/><path d="${sPath}" class="f-steel" fill-rule="evenodd"/></svg>`);
  // 5 – step-lap: corner face with stepped joints
  const offs = stepOffsets(STEPS, STEP);
  const w = 0.95;
  const cx0 = CORE.limbX[0] - 0.95 / 2;
  const view = { x0: cx0 - 0.12, y0: -0.12, x1: cx0 + 1.58, y1: 1.58 }; // stop short of the V-notch
  view.w = view.x1 - view.x0; view.h = view.y1 - view.y0;
  const { map } = mapper(view, { x: 160, y: 20, w: 480, h: 480 }, 0);
  const top = corePieces({ w, o: offs[STEPS - 1], gap: 0.012 }).filter((p) => p.id === 'limb-l' || p.id === 'yoke-b');
  const ox = CORE.limbX[0] - w / 2, oy = CORE.yokeY[0] - w / 2;
  let joints = '';
  offs.forEach((o, i) => {
    const a = map([ox + Math.max(0, -o), oy + Math.max(0, -o) + o]);
    const b2 = map([ox + w, oy + w + o]);
    joints += `<line x1="${f(a[0])}" y1="${f(a[1])}" x2="${f(b2[0])}" y2="${f(b2[1])}" class="${i === STEPS - 1 ? 'f-cut' : 'f-hidden'}"/>`;
  });
  frames.push(`<svg ${V}><defs><clipPath id="fb-c"><rect x="160" y="20" width="480" height="480"/></clipPath></defs><g clip-path="url(#fb-c)">${top.map((p) => `<path d="${piecePathD(p.poly, p.holes, map)}" class="f-steel" fill-rule="evenodd"/>`).join('')}${joints}</g></svg>`);
  // 6 – full core
  frames.push(`<svg ${V}>${coreFace({ box: { x: 80, y: 20, w: 640, h: 480 } })}</svg>`);
  // 7 – outline only (logo resolves over it)
  frames.push(`<svg ${V}>${coreFace({ box: { x: 80, y: 20, w: 640, h: 480 }, outlineOnly: true, cls: 'f-outline' })}</svg>`);
  return frames;
}

/* ------------------------------------------------------------------------ */
/* Core anatomy (mitre-core page): the client's own terms                    */
/* ------------------------------------------------------------------------ */

/** Labelled face view of a three-limb core: yokes, limbs, mitre, diamond tip, V-notch, bolt holes. */
export function coreAnatomySVG({ id = 'anatomy', compact = false } = {}) {
  const w = 0.95;
  const pieces = corePieces({ w, o: 0, gap: 0.03 });
  const b = bounds(pieces.map((p) => p.poly));
  const W = compact ? 560 : 960, H = compact ? 520 : 600;
  const box = compact ? { x: 20, y: 20, w: 520, h: 480 } : { x: 260, y: 40, w: 440, h: 520 };
  const { map } = mapper(b, box, 0);
  const P = (x, y) => map([x, y]).map(f);
  const [x1, x2, x3] = CORE.limbX;
  const [y1, y2] = CORE.yokeY;
  const hx = (x2 + x3) / 2;

  const steel = pieces.map((p) => `<path d="${piecePathD(p.poly, p.holes, map)}" class="d-steel" fill-rule="evenodd"/>`).join('');
  const pts = {
    yokeT: P(x1 + w * 0.55, y2 + w * 0.22), yokeB: P(x1 + w * 0.55, y1 - w * 0.22),
    limbs: [P(x1, (y1 + y2) / 2), P(x2, (y1 + y2) / 2), P(x3, (y1 + y2) / 2)],
    mitre: P(x1, y2), diamond: P(x2, y2 - w * 0.28), vnotch: P(x2 + w * 0.25, y1 + w * 0.25), hole: P(hx, y1),
  };
  const dot = ([x, y]) => `<circle cx="${x}" cy="${y}" r="4" class="d-dot"/>`;
  let n = 0;
  const marker = ([x, y]) => { n++; return `<g class="d-marker"><circle cx="${x}" cy="${y}" r="17" class="d-mark"/><text x="${x}" y="${y + 8}" class="d-mark-n" text-anchor="middle">${n}</text></g>`; };

  let notes = '';
  if (compact) {
    notes = [P(x3 - w * 1.45, y2 + w * 0.12), pts.limbs[2], pts.mitre, pts.diamond, pts.vnotch, pts.hole].map(marker).join('');
  } else {
    const label = (x, y, title, sub, anchor = 'start') => `<text x="${x}" y="${y}" class="d-label d-strong" text-anchor="${anchor}">${title}</text><text x="${x}" y="${y + 22}" class="d-label" text-anchor="${anchor}">${sub}</text>`;
    const L = 225, R = 735;
    // Yoke: bracket to top and bottom yokes
    notes += `<polyline points="${L - 10},${(pts.yokeT[1] + pts.yokeB[1]) / 2} ${L},${(pts.yokeT[1] + pts.yokeB[1]) / 2}" class="d-leader"/>`;
    notes += `<polyline points="${pts.yokeT[0]},${pts.yokeT[1]} ${L},${pts.yokeT[1]} ${L},${pts.yokeB[1]} ${pts.yokeB[0]},${pts.yokeB[1]}" class="d-leader"/>${dot(pts.yokeT)}${dot(pts.yokeB)}`;
    notes += label(L - 18, (pts.yokeT[1] + pts.yokeB[1]) / 2 - 4, 'Yokes', 'Top and bottom', 'end');
    // Mitre corner
    notes += `<polyline points="${pts.mitre[0]},${pts.mitre[1]} ${L - 30},${pts.mitre[1] - 40} ${L - 40},${pts.mitre[1] - 40}" class="d-leader"/>${dot(pts.mitre)}`;
    notes += label(L - 50, pts.mitre[1] - 44, 'Mitre corner', '45° joint', 'end');
    // Limbs: one line through all three, like a drawing callout
    notes += `<polyline points="${pts.limbs[0][0]},${pts.limbs[0][1]} ${R},${pts.limbs[0][1]}" class="d-leader"/>${pts.limbs.map(dot).join('')}`;
    notes += label(R + 14, pts.limbs[0][1] - 4, 'Limbs', 'Two outer, one centre');
    // Diamond tip
    notes += `<polyline points="${pts.diamond[0]},${pts.diamond[1]} ${R - 20},${pts.diamond[1] - 70} ${R},${pts.diamond[1] - 70}" class="d-leader"/>${dot(pts.diamond)}`;
    notes += label(R + 14, pts.diamond[1] - 74, 'Diamond tip', 'Pointed centre limb');
    // V-notch
    notes += `<polyline points="${pts.vnotch[0]},${pts.vnotch[1]} ${R - 20},${pts.vnotch[1] - 60} ${R},${pts.vnotch[1] - 60}" class="d-leader"/>${dot(pts.vnotch)}`;
    notes += label(R + 14, pts.vnotch[1] - 64, 'V-notch', 'Seats the diamond tip');
    // Bolt holes
    notes += `<polyline points="${pts.hole[0]},${pts.hole[1]} ${R - 20},${pts.hole[1] + 50} ${R},${pts.hole[1] + 50}" class="d-leader"/>${dot(pts.hole)}`;
    notes += label(R + 14, pts.hole[1] + 46, 'Bolt holes', 'Punched to drawing');
  }
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="${id}-t ${id}-d" class="diagram${compact ? ' diagram--compact' : ' diagram--full'}">
  <title id="${id}-t">Parts of a three-limb mitre core</title>
  <desc id="${id}-d">Face view of one lamination layer: top and bottom yokes, two outer limbs and a centre limb, 45 degree mitre corners, a diamond-pointed centre limb seated in a V-notch in each yoke, and bolt holes punched in the yokes.</desc>
  ${steel}${notes}
</svg>`;
}
