/**
 * Atmospheric backdrops (Gradient Backdrops, src/lib/backdrop, MIT) on a few chosen
 * sections only: the hero after the film, the closing call to action, and the
 * inner-page heads. Each section keeps a static CSS background in the same colours
 * (main.css), which is also what shows without WebGL. The runtime pauses off-screen
 * and freezes on one frame under prefers-reduced-motion.
 */
const LOOKS = {
  // lit satin folds in navy and steel: sheets of electrical steel, slowly turning
  hero: {
    style: 'silk',
    colors: ['#06080d', '#08101e', '#0e1a33', '#18294f', '#2b4373'],
    params: { folds: 2.2, angle: 24, warp: 0.5, sheen: 0.28, scale: 1.15 },
    speed: 0.35, grain: 0.07, quality: 0.28,
  },
  // the close: a slow, low-contrast current of the brand blue under deep navy
  cta: {
    style: 'flow',
    colors: ['#0a1223', '#0c1730', '#10203f', '#172d5a', '#0c1730'],
    params: { scale: 0.55, warp: 0.6, contrast: 0.68 },
    speed: 0.2, grain: 0.07,
  },
  // inner-page heads: a barely-there haze
  phero: {
    style: 'mesh',
    colors: ['#06080d', '#0a1325', '#122244', '#06080d'],
    params: { points: [[0.08, 0.2], [0.55, 0.15], [0.9, 0.35], [0.3, 0.9]], blend: 2.2, drift: 0.6, warp: 0.8 },
    speed: 0.4, grain: 0.06,
  },
};

function webgl() {
  try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; }
}

export function initBackdrops() {
  const els = [...document.querySelectorAll('[data-atmos]')];
  if (!els.length || !webgl() || document.documentElement.classList.contains('capture')) return;
  const phone = window.matchMedia('(max-width: 760px), (pointer: coarse)').matches;
  let lib = null;
  const mount = async (el) => {
    lib ||= import('../lib/backdrop/backdrop.mjs');
    const { createBackdrop } = await lib;
    const look = LOOKS[el.dataset.atmos];
    if (!look) return;
    createBackdrop(el, {
      ...look,
      // phones: fewer pixels and a slower drift; soft styles look the same at low resolution
      ...(phone ? { maxPixels: 2.5e5, speed: look.speed * 0.8 } : { maxPixels: 9e5 }),
      seed: 3,
    });
    // fade the canvas in once it has drawn, over the static CSS fallback
    requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('atmos-live')));
  };
  // only build a backdrop when its section comes near the viewport
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { io.unobserve(e.target); mount(e.target); }
  }, { rootMargin: '50% 0px' });
  els.forEach((el) => io.observe(el));
}
