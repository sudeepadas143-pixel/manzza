/**
 * About infographics (render.js aboutInfo): each figure draws in once, when it is
 * well into the viewport. Reduced motion: drawn immediately, no transitions (CSS).
 */
export function initAboutInfo() {
  const figs = [...document.querySelectorAll('.ainfo [data-draw]')];
  if (!figs.length) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced || !('IntersectionObserver' in window)) { figs.forEach((f) => f.classList.add('is-drawn')); return; }
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { e.target.classList.add('is-drawn'); io.unobserve(e.target); }
  }, { rootMargin: '0px 0px -18% 0px', threshold: 0.25 });
  figs.forEach((f) => io.observe(f));
}
