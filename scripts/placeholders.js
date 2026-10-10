/**
 * Lists everything MANZZA still has to supply:
 *   npm run placeholders
 * Reads site.config.js (TODO values) and checks which photo slots are still empty.
 */
import fs from 'node:fs';
import path from 'node:path';
import { loadData, listPlaceholders } from '../src/build/render.js';

const root = path.resolve(import.meta.dirname, '..');
const data = await loadData(root);

const open = listPlaceholders(data.config);
console.log('\nsite.config.js');
if (!open.length) console.log('  All filled in.');
for (const [key, note] of open) console.log(`  [ ] ${key.padEnd(22)} ${note}`);

const slots = [['factory-cnc-line', 'Home page, "How we work": CNC cutting line'], ...data.products.map((p) => [`product-${p.slug}`, `${p.name} page, "Customisation"`])];
const dir = path.join(root, 'public', 'images');
console.log('\nPhoto slots (drop a file into public/images/)');
for (const [id, where] of slots) {
  const found = ['webp', 'jpg', 'jpeg', 'png'].map((e) => `${id}.${e}`).find((f) => fs.existsSync(path.join(dir, f)));
  console.log(`  [${found ? 'x' : ' '}] ${(id + '.jpg').padEnd(32)} ${where}${found ? `  (using ${found})` : ''}`);
}
console.log('');
