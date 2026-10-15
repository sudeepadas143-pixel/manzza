/**
 * Builds the data for the About transition globe (src/js/globe.js).
 * Outputs are committed; re-run only to change the data:
 *
 *   NE_DIR=/path/to/natural-earth-vector/geojson node scripts/build-globe.mjs
 *
 *   public/globe/world.bin  – land dots outside India, ~1.5° equal-area grid
 *   public/globe/india.bin  – India dots, ~0.3° grid (the close-up)
 *   public/globe/lines.json – India border, state borders, Karnataka and the
 *                             Bengaluru urban area, simplified, [lat, lon] rings
 *
 * .bin format: Int16 pairs (lat * 100, lon * 100), little-endian.
 *
 * Sources (all public domain, Natural Earth):
 *   land            world-atlas land-50m (Natural Earth 1:50m)
 *   India           ne_10m_admin_0_countries_ind  – India's official boundary
 *                   (Natural Earth's India point-of-view edition)
 *   states          ne_10m_admin_1_states_provinces
 *   Bengaluru       ne_10m_urban_areas (the built-up area around 12.97 N, 77.59 E)
 */
import fs from 'node:fs';
import path from 'node:path';
import { feature } from 'topojson-client';
import { geoContains } from 'd3-geo';

const root = path.resolve(import.meta.dirname, '..');
const NE = process.env.NE_DIR;
if (!NE) throw new Error('Set NE_DIR to natural-earth-vector/geojson (see header)');
const atlas = (f) => JSON.parse(fs.readFileSync(path.join(root, 'node_modules/world-atlas', f), 'utf8'));
const ne = (f) => JSON.parse(fs.readFileSync(path.join(NE, f), 'utf8'));

const landTopo = atlas('land-50m.json');
const land = feature(landTopo, landTopo.objects.land);
const india = ne('ne_10m_admin_0_countries_ind.geojson').features.find((f) => f.properties.ADM0_A3 === 'IND');
const states = ne('ne_10m_admin_1_states_provinces.geojson').features.filter((f) => f.properties.adm0_a3 === 'IND');
const karnataka = states.find((f) => f.properties.name === 'Karnataka');
const BLR = [77.5946, 12.9716];
const blr = ne('ne_10m_urban_areas.geojson').features.find((f) => geoContains(f, BLR));
if (!india || !karnataka || !blr) throw new Error('missing source feature');

/* ---------------------------------------------------------------- dots */
function grid(step, latMin, latMax, lonMin, lonMax, inside) {
  const out = [];
  for (let lat = latMin; lat <= latMax; lat += step) {
    const lonStep = step / Math.max(Math.cos((lat * Math.PI) / 180), 0.15);
    const off = (Math.round((lat - latMin) / step) % 2) * lonStep * 0.5; // staggered rows
    for (let lon = lonMin + off; lon <= lonMax; lon += lonStep) if (inside([lon, lat])) out.push(lat, lon);
  }
  return out;
}
function writeBin(file, pts) {
  const buf = Buffer.alloc(pts.length * 2);
  pts.forEach((v, i) => buf.writeInt16LE(Math.round(v * 100), i * 2));
  fs.writeFileSync(file, buf);
  console.log(path.relative(root, file), pts.length / 2, 'dots', (buf.length / 1024).toFixed(1), 'KB');
}

/* --------------------------------------------------------------- lines */
/** Douglas-Peucker on [lon, lat] points. */
function simplify(pts, tol) {
  if (pts.length < 3) return pts;
  const keep = new Uint8Array(pts.length); keep[0] = keep[pts.length - 1] = 1;
  const stack = [[0, pts.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop();
    const [ax, ay] = pts[a], [bx, by] = pts[b];
    const dx = bx - ax, dy = by - ay, len = Math.hypot(dx, dy);
    let max = 0, idx = -1;
    for (let i = a + 1; i < b; i++) {
      // closed rings start and end on the same point: measure to that point instead
      const d = len < 1e-9 ? Math.hypot(pts[i][0] - ax, pts[i][1] - ay)
        : Math.abs(dy * pts[i][0] - dx * pts[i][1] + bx * ay - by * ax) / len;
      if (d > max) { max = d; idx = i; }
    }
    if (max > tol) { keep[idx] = 1; stack.push([a, idx], [idx, b]); }
  }
  return pts.filter((_, i) => keep[i]);
}
/** Outer rings of a (Multi)Polygon as simplified [lat, lon] rings, dropping slivers. */
function rings(f, tol, minPts = 4) {
  const polys = f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates : [f.geometry.coordinates];
  return polys
    .map((p) => simplify(p[0], tol))
    .filter((r) => r.length >= minPts)
    .map((r) => r.map(([lon, lat]) => [+lat.toFixed(3), +lon.toFixed(3)]));
}

const inIndia = (p) => geoContains(india, p);
fs.mkdirSync(path.join(root, 'public/globe'), { recursive: true });
const lines = {
  india: rings(india, 0.04, 8),
  states: states.filter((f) => f !== karnataka).flatMap((f) => rings(f, 0.06, 6)),
  karnataka: rings(karnataka, 0.02, 6),
  blr: rings(blr, 0.002, 4),
};
const json = JSON.stringify(lines);
fs.writeFileSync(path.join(root, 'public/globe/lines.json'), json);
console.log('public/globe/lines.json', Object.entries(lines).map(([k, v]) => `${k}:${v.length}r/${v.reduce((n, r) => n + r.length, 0)}p`).join(' '), (json.length / 1024).toFixed(1), 'KB');

writeBin(path.join(root, 'public/globe/india.bin'), grid(0.3, 6, 37.5, 68, 98, inIndia));
writeBin(path.join(root, 'public/globe/world.bin'), grid(1.5, -58, 80, -180, 180, (p) => geoContains(land, p) && !inIndia(p)));
