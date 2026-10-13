/**
 * Factory photo carousel. Scrolling is native (scroll-snap), so swipe, trackpad
 * and keyboard work without help; this adds arrow buttons, mouse drag, the
 * counter, segment progress and a slow autoplay that stops for good once the
 * visitor takes over, pauses off-screen and on hover, and never runs under
 * prefers-reduced-motion.
 */
const DWELL = 6000;

export function initReels() {
  document.querySelectorAll('[data-reel]').forEach(reel);
}

function reel(root) {
  const track = root.querySelector('.reel__track');
  const slides = [...track.children];
  const ticks = [...root.querySelectorAll('.reel__tick')];
  const now = root.querySelector('[data-reel-now]');
  const prev = root.querySelector('[data-reel-prev]');
  const next = root.querySelector('[data-reel-next]');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let index = -1;
  let auto = !reduced;
  let visible = false;
  let hovered = false;
  let t0 = 0;
  let raf = 0;

  // the last frames clamp to the end of the track instead of leaving a gap
  const left = (i) => Math.min(slides[i].offsetLeft - slides[0].offsetLeft, track.scrollWidth - track.clientWidth);
  // where the track is heading: repeated clicks step from here, not from a mid-glide position
  let target = 0;
  const go = (i, smooth = true) => {
    i = (i + slides.length) % slides.length;
    target = i;
    track.scrollTo({ left: left(i), behavior: smooth && !reduced ? 'smooth' : 'auto' });
  };
  const setActive = (i) => {
    if (i === index) return;
    index = i;
    slides.forEach((s, k) => {
      s.classList.toggle('is-active', k === i);
      s.setAttribute('aria-hidden', k === i ? 'false' : 'true');
    });
    ticks.forEach((t, k) => { t.classList.toggle('is-done', k < i); t.firstElementChild.style.setProperty('--p', k === i && !auto ? 1 : 0); });
    now.textContent = String(i + 1).padStart(2, '0');
    t0 = performance.now();
  };
  const nearest = () => {
    const x = track.scrollLeft;
    const max = track.scrollWidth - track.clientWidth;
    if (x >= max - 2) return slides.length - 1;
    let best = 0;
    slides.forEach((_, k) => { if (Math.abs(left(k) - x) < Math.abs(left(best) - x)) best = k; });
    return best;
  };
  const stopAuto = () => {
    if (!auto) return;
    auto = false;
    ticks[index]?.firstElementChild.style.setProperty('--p', 1);
  };

  let settle = 0;
  track.addEventListener('scroll', () => {
    setActive(nearest());
    clearTimeout(settle);
    settle = setTimeout(() => { target = nearest(); }, 160);
  }, { passive: true });
  prev.addEventListener('click', () => { stopAuto(); go(target - 1); });
  next.addEventListener('click', () => { stopAuto(); go(target + 1); });
  ticks.forEach((t, k) => t.addEventListener('click', () => { stopAuto(); go(k); }));
  track.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight') { e.preventDefault(); stopAuto(); go(target + 1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); stopAuto(); go(target - 1); }
  });
  ['touchstart', 'wheel'].forEach((ev) => track.addEventListener(ev, stopAuto, { passive: true }));
  root.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse') hovered = true; });
  root.addEventListener('pointerleave', () => { hovered = false; t0 = performance.now() - progress() * DWELL; });

  // mouse drag (touch already scrolls natively)
  let drag = null;
  track.addEventListener('pointerdown', (e) => {
    if (e.pointerType !== 'mouse' || e.button !== 0) return;
    drag = { x: e.clientX, left: track.scrollLeft, moved: false };
    track.setPointerCapture(e.pointerId);
  });
  track.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x;
    if (!drag.moved && Math.abs(dx) > 4) { drag.moved = true; track.classList.add('is-drag'); stopAuto(); }
    if (drag.moved) track.scrollLeft = drag.left - dx;
  });
  const endDrag = (e) => {
    if (!drag) return;
    const { moved, x } = drag;
    drag = null;
    track.classList.remove('is-drag');
    if (!moved) return;
    // flick direction decides, then snap
    const dx = e.clientX - x;
    const target = Math.abs(dx) > 60 ? index + (dx < 0 ? 1 : -1) : nearest();
    go(Math.max(0, Math.min(slides.length - 1, target)));
  };
  track.addEventListener('pointerup', endDrag);
  track.addEventListener('pointercancel', endDrag);

  // autoplay: fill the active segment, then advance
  let paused = 0;
  const progress = () => Math.min(1, (performance.now() - t0) / DWELL);
  const tick = () => {
    raf = requestAnimationFrame(tick);
    if (!auto) return;
    if (!seen) return;
    if (!visible || hovered || document.hidden) { if (!paused) paused = performance.now(); return; }
    if (paused) { t0 += performance.now() - paused; paused = 0; }
    const p = progress();
    ticks[index].firstElementChild.style.setProperty('--p', p.toFixed(4));
    if (p >= 1) go(index + 1);
  };
  let seen = false;
  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    // the clock starts the first time the reel is actually on screen
    if (visible && !seen) { seen = true; t0 = performance.now(); paused = 0; }
  }, { threshold: 0.35 }).observe(root);

  setActive(0);
  if (auto) raf = requestAnimationFrame(tick);
}
