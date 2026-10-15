/**
 * Atmospheric backdrops (Gradient Backdrops, src/lib/backdrop, MIT) on a few chosen
 * sections only: the hero after the film, the closing call to action, and the
 * inner-page heads. Each section keeps a static CSS background in the same colours
 * (main.css), which is also what shows without WebGL. The runtime pauses off-screen
 * and freezes on one frame under prefers-reduced-motion.
 */
import { whenEngaged } from './intent.js';
export const LOOKS = {
  // lit satin folds in navy and steel: sheets of electrical steel, slowly turning
  hero: {
    style: 'silk',
    colors: ['#06080d', '#0a1428', '#15274d', '#264380', '#4d72b8'],
    params: { folds: 2.4, angle: 24, warp: 0.55, sheen: 0.45, scale: 1.1 },
    speed: 0.35, grain: 0.07, quality: 0.3,
  },
  // the products intro: navy and electric-blue light pooling, fading into the first band
  products: {
    style: 'mesh',
    colors: ['#06080d', '#0e1c3a', '#1c3a7c', '#06080d', '#0a1530'],
    params: { points: [[0.05, 0.1], [0.4, 0.55], [0.82, 0.5], [0.2, 0.98], [0.7, 0.98]], blend: 2.2, drift: 0.8, warp: 1 },
    speed: 0.35, grain: 0.07,
  },
  // materials: a calm navy field behind the spec table (slow, low contrast, readable)
  materials: {
    style: 'mesh',
    colors: ['#06080d', '#0c1832', '#132a5c', '#06080d', '#0a1530'],
    params: { points: [[0.05, 0.05], [0.25, 0.45], [0.8, 0.35], [0.95, 0.95], [0.55, 0.85]], blend: 2.4, drift: 0.5, warp: 0.8 },
    speed: 0.25, grain: 0.06,
  },
  // about: a dark current behind the statement, brightest on the open right side
  about: {
    style: 'flow',
    colors: ['#06080d', '#0a1427', '#142a57', '#1f3d7c', '#06080d'],
    params: { scale: 0.5, warp: 0.7, contrast: 0.85 },
    speed: 0.22, grain: 0.07,
  },
  // the close: a slow current of the brand blue under deep navy
  cta: {
    style: 'flow',
    colors: ['#081022', '#0b1834', '#132a5a', '#21418a', '#0b1834'],
    params: { scale: 0.6, warp: 0.7, contrast: 0.82 },
    speed: 0.22, grain: 0.07,
  },
  // inner-page heads: a navy haze with a blue lift top-right
  phero: {
    style: 'mesh',
    colors: ['#06080d', '#0c1a36', '#1d3a78', '#06080d'],
    params: { points: [[0.08, 0.2], [0.55, 0.15], [0.9, 0.35], [0.3, 0.9]], blend: 2.2, drift: 0.7, warp: 0.9 },
    speed: 0.4, grain: 0.06,
  },
};

function webgl() {
  try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; }
}

export function initBackdrops() {
  // the About globe owns the GPU while it plays; start the backdrops once it is done
  if (document.documentElement.classList.contains('globe-intro')) {
    addEventListener('globe:done', initBackdrops, { once: true });
    return;
  }
  const els = [...document.querySelectorAll('[data-atmos]')];
  if (!els.length || !webgl() || document.documentElement.classList.contains('capture')) return;
  const phone = window.matchMedia('(max-width: 760px), (pointer: coarse)').matches;
  let lib = null;
  // The satin drifts slowly, so the backdrops run on one shared clock at 24 fps
  // (the library's own loop draws every display frame) and stop while off screen:
  // less GPU work competing with scrolling.
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const live = [];
  const seen = new IntersectionObserver((entries) => {
    for (const e of entries) { const b = live.find((x) => x.el === e.target); if (b) b.visible = e.isIntersecting; }
  });
  let last = 0;
  const tick = (now) => {
    requestAnimationFrame(tick);
    if (document.hidden || now - last < 1000 / 24) return;
    const dt = Math.min(0.1, (now - (last || now)) / 1000);
    last = now;
    for (const b of live) if (b.visible) { b.t += dt * b.speed; b.bd.set({ time: b.t }); }
  };
  const mount = async (el) => {
    // the static CSS gradient stands in until the visitor engages (intent.js)
    await whenEngaged();
    lib ||= import('../lib/backdrop/backdrop.mjs');
    const { createBackdrop } = await lib;
    const look = LOOKS[el.dataset.atmos];
    if (!look) return;
    const speed = phone ? look.speed * 0.8 : look.speed;
    const bd = createBackdrop(el, {
      ...look,
      animate: false, // driven by the shared clock above
      // phones: fewer pixels and a slower drift; soft styles look the same at low resolution
      ...(phone ? { maxPixels: 1.8e5 } : { maxPixels: 7e5 }),
      seed: 3,
    });
    if (!reduced) {
      live.push({ el, bd, speed, t: bd.time, visible: true });
      seen.observe(el);
      if (live.length === 1) requestAnimationFrame(tick);
    }
    // fade the canvas in once it has drawn, over the static CSS fallback
    requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('atmos-live')));
  };
  // only build a backdrop when its section comes near the viewport
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { io.unobserve(e.target); mount(e.target); }
  }, { rootMargin: '50% 0px' });
  els.forEach((el) => io.observe(el));
}
