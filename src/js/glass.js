/**
 * Liquid glass: real edge refraction for the site's glass UI (buttons, header,
 * dropdown, sticky bar, photo captions).
 *
 * Technique (after cocolayuan/liquid-glass): a canvas draws a displacement map from
 * the signed distance field of the element's rounded rectangle, so pixels near the
 * rim are pushed along the surface normal; an SVG feDisplacementMap applies it, with
 * red shifted slightly more than green/blue for a hint of chromatic aberration.
 *
 * Applied through backdrop-filter, which can take an SVG filter in Chromium only:
 * the backdrops here are live WebGL canvases, so the reference's clone-the-scene path
 * cannot work. Safari and Firefox keep the CSS glass (blur, tint, specular rim)
 * defined in main.css, without the bending. Skipped entirely under
 * prefers-reduced-transparency.
 */
const ROLES = {
  // [selector, refraction depth px, rim width px, blur px, saturate]
  light: ['.btn--primary, .btn--filled, .header__cta, .nav__link--cta', 14, 10, 8, 1.5],
  clear: ['.btn--ghost', 18, 12, 4, 1.6],
  bar: ['.site-header', 22, 16, 14, 1.6],
  panel: ['.dd', 22, 16, 18, 1.5],
  chip: ['.photo figcaption', 16, 10, 10, 1.4],
};

const SVGNS = 'http://www.w3.org/2000/svg';
let defs = null;
let uid = 0;
const maps = new Map();

// Chromium on desktop and Android (iOS Chrome is WebKit and reports CriOS, not Chrome/)
const chromium = () => /Chrome\/|Edg\//.test(navigator.userAgent) && !/Firefox\//.test(navigator.userAgent);

/** Displacement map for a w×h rounded rect of radius r: rim px wide, strongest at the edge. */
function lensMap(w, h, r, rim) {
  const key = `${w}x${h}r${r}m${rim}`;
  if (maps.has(key)) return maps.get(key);
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const ctx = c.getContext('2d');
  const img = ctx.createImageData(w, h);
  const px = img.data;
  const hx = w / 2, hy = h / 2;
  const sdf = (x, y) => {
    const qx = Math.abs(x - hx) - (hx - r);
    const qy = Math.abs(y - hy) - (hy - r);
    return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - r;
  };
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const cx = x + 0.5, cy = y + 0.5;
      const s = sdf(cx, cy); // negative inside
      const gx = sdf(cx + 1, cy) - sdf(cx - 1, cy);
      const gy = sdf(cx, cy + 1) - sdf(cx, cy - 1);
      const len = Math.hypot(gx, gy) || 1;
      let a = Math.max(0, 1 - Math.abs(s) / rim);
      a = a * a * a * (a * (a * 6 - 15) + 10); // smootherstep: a lens-like falloff into the body
      const i = (y * w + x) * 4;
      // push inward along the normal: the rim magnifies what lies just outside the edge
      px[i] = Math.round(127.5 - (gx / len) * a * 127);
      px[i + 1] = Math.round(127.5 - (gy / len) * a * 127);
      px[i + 2] = 128;
      px[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  const url = c.toDataURL('image/png');
  maps.set(key, url);
  return url;
}

function filterFor(w, h, r, depth, rim) {
  const id = `lg-${++uid}`;
  const map = lensMap(w, h, r, rim);
  const f = document.createElementNS(SVGNS, 'filter');
  f.setAttribute('id', id);
  f.setAttribute('x', '0'); f.setAttribute('y', '0');
  f.setAttribute('width', String(w)); f.setAttribute('height', String(h));
  f.setAttribute('filterUnits', 'userSpaceOnUse');
  f.setAttribute('color-interpolation-filters', 'sRGB');
  const sR = depth * 1.06, sGB = depth * 0.94; // chromatic aberration: red bends a touch further
  f.innerHTML = `
    <feImage href="${map}" x="0" y="0" width="${w}" height="${h}" preserveAspectRatio="none" result="map"/>
    <feDisplacementMap in="SourceGraphic" in2="map" scale="${sR}" xChannelSelector="R" yChannelSelector="G" result="dR"/>
    <feDisplacementMap in="SourceGraphic" in2="map" scale="${sGB}" xChannelSelector="R" yChannelSelector="G" result="dGB"/>
    <feColorMatrix in="dR" type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="cR"/>
    <feColorMatrix in="dGB" type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0" result="cGB"/>
    <feComposite in="cR" in2="cGB" operator="arithmetic" k1="0" k2="1" k3="1" k4="0"/>`;
  defs.appendChild(f);
  return f;
}

function mount(el, [, depth, rim, blur, sat]) {
  let current = null;
  const apply = () => {
    const rect = el.getBoundingClientRect();
    const w = Math.round(rect.width), h = Math.round(rect.height);
    if (w < 8 || h < 8) return;
    const r = Math.min(parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0, h / 2, w / 2);
    if (current?.dataset.size === `${w}x${h}`) return;
    current?.remove();
    current = filterFor(w, h, Math.round(r), depth, Math.min(rim, h / 2, w / 2));
    current.dataset.size = `${w}x${h}`;
    const v = `url(#${current.id}) blur(${blur}px) saturate(${sat})`;
    el.style.backdropFilter = v;
    el.style.setProperty('-webkit-backdrop-filter', v);
  };
  apply();
  new ResizeObserver(apply).observe(el);
}

export function initGlass() {
  if (!chromium()) return; // Safari / Firefox: CSS glass without refraction
  // phones and tablets: CSS glass only, to spare the GPU and battery
  if (window.matchMedia('(pointer: coarse)').matches) return;
  if (window.matchMedia('(prefers-reduced-transparency: reduce)').matches) return;
  if (document.documentElement.classList.contains('capture')) return;
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('width', '0'); svg.setAttribute('height', '0');
  svg.setAttribute('aria-hidden', 'true');
  svg.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden';
  defs = document.createElementNS(SVGNS, 'defs');
  svg.appendChild(defs);
  document.body.appendChild(svg);
  for (const role of Object.values(ROLES)) {
    document.querySelectorAll(role[0]).forEach((el) => mount(el, role));
  }
  document.documentElement.classList.add('glass-refract');
}
