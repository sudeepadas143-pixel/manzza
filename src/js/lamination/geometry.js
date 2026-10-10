/**
 * Lamination geometry – pure 2D maths, no rendering dependencies.
 *
 * Shared by the Three.js intro, the small product visuals, the SVG step-lap
 * diagram (rendered at build time) and the no-WebGL fallback frames, so every
 * picture of a lamination on the site is drawn from the same numbers.
 *
 * Units are arbitrary "core units". Points are [x, y] arrays.
 */

export const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));

/** Keep only the part of a polygon where a*x + b*y <= c (Sutherland–Hodgman, one plane). */
export function clipHalfPlane(poly, a, b, c) {
  const out = [];
  const inside = (p) => a * p[0] + b * p[1] <= c + 1e-9;
  for (let i = 0; i < poly.length; i++) {
    const cur = poly[i];
    const prev = poly[(i + poly.length - 1) % poly.length];
    const cin = inside(cur);
    const pin = inside(prev);
    if (cin !== pin) {
      const dp = a * prev[0] + b * prev[1] - c;
      const dc = a * cur[0] + b * cur[1] - c;
      const t = dp / (dp - dc);
      out.push([prev[0] + (cur[0] - prev[0]) * t, prev[1] + (cur[1] - prev[1]) * t]);
    }
    if (cin) out.push(cur);
  }
  return out;
}

export function rect(x0, y0, x1, y1) {
  return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
}

/** Drop consecutive duplicate points (and a closing duplicate). */
export function dedupe(poly, eps = 1e-7) {
  const out = [];
  for (const p of poly) {
    const q = out[out.length - 1];
    if (!q || Math.abs(q[0] - p[0]) > eps || Math.abs(q[1] - p[1]) > eps) out.push(p);
  }
  while (out.length > 2) {
    const a = out[0], z = out[out.length - 1];
    if (Math.abs(a[0] - z[0]) < eps && Math.abs(a[1] - z[1]) < eps) out.pop();
    else break;
  }
  return out;
}

export function signedArea(poly) {
  let s = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x0, y0] = poly[i];
    const [x1, y1] = poly[(i + 1) % poly.length];
    s += x0 * y1 - x1 * y0;
  }
  return s / 2;
}

export const ccw = (poly) => (signedArea(poly) < 0 ? poly.slice().reverse() : poly);

/**
 * Inset a simple polygon by distance d (positive = shrink). Used to open a
 * hairline joint gap between neighbouring laminations so joints read clearly.
 */
export function inset(poly, d) {
  const P = dedupe(ccw(poly));
  const n = P.length;
  const lines = [];
  for (let i = 0; i < n; i++) {
    const a = P[i], b = P[(i + 1) % n];
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len, ny = dx / len; // inward normal for CCW
    lines.push({ p: [a[0] + nx * d, a[1] + ny * d], v: [dx, dy] });
  }
  const out = [];
  for (let i = 0; i < n; i++) {
    const L0 = lines[(i + n - 1) % n], L1 = lines[i];
    const den = L0.v[0] * L1.v[1] - L0.v[1] * L1.v[0];
    if (Math.abs(den) < 1e-12) { out.push(L1.p); continue; }
    const t = ((L1.p[0] - L0.p[0]) * L1.v[1] - (L1.p[1] - L0.p[1]) * L1.v[0]) / den;
    out.push([L0.p[0] + L0.v[0] * t, L0.p[1] + L0.v[1] * t]);
  }
  return out;
}

export function translate(poly, dx, dy) {
  return poly.map(([x, y]) => [x + dx, y + dy]);
}

export function bounds(polys) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const poly of polys) for (const [x, y] of poly) {
    if (x < x0) x0 = x; if (y < y0) y0 = y; if (x > x1) x1 = x; if (y > y1) y1 = y;
  }
  return { x0, y0, x1, y1, w: x1 - x0, h: y1 - y0 };
}

/* ------------------------------------------------------------------------ */
/* Three-limb mitre core                                                     */
/* ------------------------------------------------------------------------ */

/**
 * Default core proportions. Limb and yoke centrelines are fixed; narrower
 * packets (for the stepped, near-circular limb section) share them.
 */
export const CORE = {
  D: 1, // circumscribing diameter of the limb section
  // Proportions follow MANZZA's own core photographs: windows about 0.8 x the
  // lamination width wide and 2.2 x tall, so the core reads nearly square.
  limbX: [-1.71, 0, 1.71], // limb centrelines
  yokeY: [0.475, 3.515], // yoke centrelines (bottom yoke sits on y = 0 for the widest packet)
  holeR: 0.055, // yoke bolt holes, on fixed centrelines so they line up through every layer
};

/** Polygon approximating a circle (clockwise, for use as a hole). */
export function circle(cx, cy, r, seg = 20) {
  const pts = [];
  for (let k = 0; k < seg; k++) {
    const t = -(k / seg) * Math.PI * 2;
    pts.push([cx + Math.cos(t) * r, cy + Math.sin(t) * r]);
  }
  return pts;
}

/**
 * Pieces of one lamination layer of a three-phase, three-limb mitre core.
 *
 *  - Outer corners: 45° mitre joints.
 *  - Centre limb: pointed 90° ends sitting in a V-notch in each yoke.
 *  - Step-lap: `o` moves every joint of this layer along the limb axis.
 *    Successive layers use successive offsets, so joints never line up.
 *
 * Returns [{ id, dir, poly }] where dir is the rolling (grain) direction.
 */
export function corePieces({ w, o = 0, gap = 0, limbX = CORE.limbX, yokeY = CORE.yokeY, holes = true, holeSeg = 20 }) {
  const [x1, x2, x3] = limbX;
  const [y1, y2] = yokeY;
  const ox = x1 - w / 2;
  const oy = y1 - w / 2;
  const L = x3 - x1 + w;
  const H = y2 - y1 + w;
  const cx = x2 - ox;
  const W = w;
  const h = W / 2;

  // Limbs: band rectangles clipped by the joint lines.
  let left = rect(0, 0, W, H);
  left = clipHalfPlane(left, 1, -1, -o); //   y >= x + o
  left = clipHalfPlane(left, 1, 1, H - o); // y <= H - x - o

  let right = rect(L - W, 0, L, H);
  right = clipHalfPlane(right, -1, -1, -L - o); // y >= (L - x) + o
  right = clipHalfPlane(right, -1, 1, H - L - o); // y <= H - (L - x) - o

  let centre = rect(cx - h, 0, cx + h, H);
  centre = clipHalfPlane(centre, 1, -1, cx - h - o); //   y >= h + o + (x - cx)
  centre = clipHalfPlane(centre, -1, -1, -cx - h - o); // y >= h + o - (x - cx)
  centre = clipHalfPlane(centre, -1, 1, H - h - o - cx); // y <= H - h - o + (x - cx)
  centre = clipHalfPlane(centre, 1, 1, H - h - o + cx); //  y <= H - h - o - (x - cx)

  // Bottom yoke, traced explicitly so the V-notch and step offsets are exact.
  const yoke = [];
  if (o >= 0) yoke.push([0, 0], [0, o]); else yoke.push([-o, 0]);
  yoke.push([W, W + o], [W, W]);
  yoke.push([cx - h, W], [cx - h, W + o], [cx, h + o], [cx + h, W + o], [cx + h, W]);
  yoke.push([L - W, W], [L - W, W + o]);
  if (o >= 0) yoke.push([L, o], [L, 0]); else yoke.push([L + o, 0]);
  const bottom = dedupe(yoke);
  const top = dedupe(bottom.map(([x, y]) => [x, H - y]).reverse());

  const pieces = [
    { id: 'limb-l', dir: 'y', poly: left },
    { id: 'limb-c', dir: 'y', poly: centre },
    { id: 'limb-r', dir: 'y', poly: right },
    { id: 'yoke-b', dir: 'x', poly: bottom },
    { id: 'yoke-t', dir: 'x', poly: top },
  ];
  // bolt holes in each yoke, centred between neighbouring limbs
  const holeXs = [(x1 + x2) / 2, (x2 + x3) / 2];
  const holeFor = (id) => {
    if (!holes || !id.startsWith('yoke')) return [];
    const y = id === 'yoke-b' ? y1 : y2;
    return holeXs.map((x) => circle(x, y, CORE.holeR, holeSeg));
  };
  return pieces.map((p) => {
    let poly = dedupe(p.poly);
    if (gap > 0) poly = inset(poly, gap / 2);
    return { ...p, poly: translate(poly, ox, oy), holes: holeFor(p.id) };
  });
}

/** Holes that sit wholly on the kept side of a clip line x <= c (for cropped corner views). */
export function holesLeftOf(holes = [], c) {
  return holes.filter((h) => h.every(([x]) => x < c));
}

/** Outline of the core (outer boundary + the two windows) for the widest packet. */
export function coreOutline({ w, limbX = CORE.limbX, yokeY = CORE.yokeY }) {
  const [x1, x2, x3] = limbX;
  const [y1, y2] = yokeY;
  const h = w / 2;
  return {
    outer: rect(x1 - h, y1 - h, x3 + h, y2 + h),
    windows: [rect(x1 + h, y1 + h, x2 - h, y2 - h), rect(x2 + h, y1 + h, x3 - h, y2 - h)],
  };
}

/**
 * Stepped (cruciform) limb section: packets of decreasing width that fill a
 * circle of diameter D. Returns packets bottom-to-top with z ranges.
 */
export function cruciform(D = 1, widths = [0.95, 0.85, 0.7, 0.5]) {
  const R = D / 2;
  const edges = widths.map((w) => Math.sqrt(Math.max(0, R * R - (w / 2) ** 2)));
  // edges[i] = half stack height where width widths[i] ends
  const half = [];
  let z = 0;
  for (let i = 0; i < widths.length; i++) {
    half.push({ w: widths[i], z0: z, z1: edges[i] });
    z = edges[i];
  }
  const packets = [];
  for (let i = half.length - 1; i >= 0; i--) packets.push({ w: half[i].w, z0: -half[i].z1, z1: -half[i].z0 });
  // merge the two central packets (same width) into one
  const centre = packets.pop();
  packets.push({ w: centre.w, z0: centre.z0, z1: half[0].z1 });
  for (let i = 1; i < half.length; i++) packets.push({ w: half[i].w, z0: half[i].z0, z1: half[i].z1 });
  return packets;
}

/** Step offsets for a step-lap cycle, centred on zero. */
export function stepOffsets(steps = 5, s = 0.045) {
  return Array.from({ length: steps }, (_, k) => (k - (steps - 1) / 2) * s);
}

/* ------------------------------------------------------------------------ */
/* E, I and strip profiles                                                   */
/* ------------------------------------------------------------------------ */

/**
 * E lamination, opening upwards, in the classic "scrapless" proportions
 * (tongue a, legs and windows a/2, back a/2, windows 1.5a deep) so that two
 * I pieces come out of the windows. Illustration only: real parts follow the
 * customer's drawing.
 */
export function eShape(a = 1) {
  const W = 3 * a; // overall width
  const Hh = 2 * a; // overall height
  const back = a / 2; // back (yoke) depth
  const leg = a / 2;
  const win = a / 2;
  return [
    [0, 0], [W, 0], [W, Hh], [W - leg, Hh], [W - leg, back],
    [W - leg - win, back], [W - leg - win, Hh], [leg + win, Hh],
    [leg + win, back], [leg, back], [leg, Hh], [0, Hh],
  ];
}

export function iShape(a = 1) {
  return rect(0, 0, 3 * a, a / 2);
}

/** Strip with optional mitred ends and a row of punched holes. */
export function stripShape({ length = 4, width = 0.6, mitre = false, holes = 2, holeR = 0.07, seg = 20 }) {
  const outer = mitre
    ? [[0, 0], [length, 0], [length - width, width], [width, width]]
    : rect(0, 0, length, width);
  const holeList = [];
  for (let i = 0; i < holes; i++) {
    const cx = (length * (i + 1)) / (holes + 1);
    const cy = width / 2;
    const ring = [];
    for (let k = 0; k < seg; k++) {
      const t = (k / seg) * Math.PI * 2;
      ring.push([cx + Math.cos(t) * holeR, cy + Math.sin(t) * holeR]);
    }
    holeList.push(ring.reverse());
  }
  return { outer, holes: holeList };
}

/* ------------------------------------------------------------------------ */
/* Small helpers                                                             */
/* ------------------------------------------------------------------------ */

export const smooth = (t) => t * t * (3 - 2 * t);
export const seg = (p, a, b) => clamp((p - a) / (b - a));
export const lerp = (a, b, t) => a + (b - a) * t;
