/**
 * Builds the dot data for the About transition globe (src/js/globe.js).
 * Run once with `node scripts/build-globe.mjs`; the output is committed.
 *
 *   public/globe/world.bin  – land dots on a ~1.5° equal-area grid
 *   public/globe/india.bin  – India dots on a ~0.3° grid (the close-up)
 *
 * Format: Int16 pairs (lat * 100, lon * 100), little-endian.
 * Source: Natural Earth via world-atlas (public domain).
 */
import fs from 'node:fs';
import path from 'node:path';
import { feature } from 'topojson-client';
import { geoContains } from 'd3-geo';

const root = path.resolve(import.meta.dirname, '..');
const read = (f) => JSON.parse(fs.readFileSync(path.join(root, 'node_modules/world-atlas', f), 'utf8'));

const land = feature(read('land-50m.json'), read('land-50m.json').objects.land);
const countries = feature(read('countries-50m.json'), read('countries-50m.json').objects.countries);
const india = countries.features.find((f) => f.id === '356');
if (!india) throw new Error('India not found in world-atlas');

/** Dots on rows of constant latitude; row spacing `step`, columns widened toward the poles so density stays even. */
function grid(step, latMin, latMax, lonMin, lonMax, inside) {
  const out = [];
  for (let lat = latMin; lat <= latMax; lat += step) {
    const lonStep = step / Math.max(Math.cos((lat * Math.PI) / 180), 0.15);
    // stagger alternate rows for a calmer pattern
    const off = (Math.round((lat - latMin) / step) % 2) * lonStep * 0.5;
    for (let lon = lonMin + off; lon <= lonMax; lon += lonStep) {
      if (inside([lon, lat])) out.push(lat, lon);
    }
  }
  return out;
}

function write(file, pts) {
  const buf = Buffer.alloc(pts.length * 2);
  pts.forEach((v, i) => buf.writeInt16LE(Math.round(v * 100), i * 2));
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, buf);
  console.log(path.relative(root, file), pts.length / 2, 'dots', (buf.length / 1024).toFixed(1), 'KB');
}

const inIndia = (p) => geoContains(india, p);
// world: everything except India, which comes from the dense set
write(path.join(root, 'public/globe/world.bin'), grid(1.5, -58, 80, -180, 180, (p) => geoContains(land, p) && !inIndia(p)));
write(path.join(root, 'public/globe/india.bin'), grid(0.3, 6, 37.5, 68, 98, inIndia));
