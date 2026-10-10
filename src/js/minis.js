/**
 * Small live product visuals (product cards, product page heroes).
 * Lazy: Three.js is only fetched once a visual is close to the viewport.
 * Each <canvas data-mini="core|mitre-corner|ei|strip"> sits inside a figure
 * that also contains a static SVG, shown when WebGL is unavailable.
 */
export function initMinis() {
  const canvases = [...document.querySelectorAll('canvas[data-mini]')];
  if (!canvases.length) return;

  let gl = false;
  try {
    const c = document.createElement('canvas');
    gl = !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch { gl = false; }
  if (!gl) return;

  let started = false;
  const io = new IntersectionObserver((entries) => {
    if (started || !entries.some((e) => e.isIntersecting)) return;
    started = true;
    io.disconnect();
    import('./mini-scenes.js').then(({ startMinis }) => startMinis(canvases)).catch((err) => {
      console.warn('[minis] could not start', err);
    });
  }, { rootMargin: '200px 0px' });
  canvases.forEach((c) => io.observe(c));
}
