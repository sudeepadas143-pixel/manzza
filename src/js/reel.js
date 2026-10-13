/**
 * Factory photo carousel. Frames are stacked in one stage; changing frame wipes
 * the new one in from the direction of travel. Thumbnails act as pagination and
 * show autoplay progress. Swipe/drag on the stage, arrow buttons and arrow keys
 * all navigate. Autoplay starts the first time the reel is on screen, pauses on
 * hover, off-screen or in a background tab, and stops for good once the visitor
 * takes over. No autoplay and no transitions under prefers-reduced-motion.
 */
const DWELL = 6000;
const WIPE = 1100;

export function initReels() {
  document.querySelectorAll('[data-reel]').forEach(reel);
}

function reel(root) {
  const stage = root.querySelector('.reel__stage');
  const slides = [...stage.querySelectorAll('.reel__slide')];
  const thumbs = [...root.querySelectorAll('.reel__thumb')];
  const now = root.querySelector('[data-reel-now]');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const n = slides.length;
  let index = 0;
  let auto = !reduced;
  let seen = false, visible = false, hovered = false;
  let t0 = 0, paused = 0;
  const timers = new WeakMap();

  root.classList.toggle('is-auto', auto);

  const show = (i, dir) => {
    i = (i + n) % n;
    if (i === index) return;
    const from = slides[index], to = slides[i];
    dir = dir || (i > index ? 1 : -1);
    clearTimeout(timers.get(from)); clearTimeout(timers.get(to));
    slides.forEach((s) => s.classList.remove('is-leaving', 'is-in', 'from-left'));
    from.classList.remove('is-active');
    from.setAttribute('aria-hidden', 'true');
    to.setAttribute('aria-hidden', 'false');
    to.classList.add('is-active');
    if (!reduced) {
      from.classList.add('is-leaving');
      to.classList.add('is-in');
      if (dir < 0) to.classList.add('from-left');
      timers.set(from, setTimeout(() => from.classList.remove('is-leaving'), WIPE));
      timers.set(to, setTimeout(() => to.classList.remove('is-in', 'from-left'), WIPE));
    }
    thumbs.forEach((t, k) => (k === i ? t.setAttribute('aria-current', 'true') : t.removeAttribute('aria-current')));
    now.textContent = String(i + 1).padStart(2, '0');
    index = i;
    t0 = performance.now();
    root.style.setProperty('--auto', 0);
  };

  const play = root.querySelector('[data-reel-play]');
  const syncPlay = () => {
    if (!play) return;
    play.hidden = reduced;
    play.setAttribute('aria-label', auto ? 'Pause slideshow' : 'Play slideshow');
    play.setAttribute('aria-pressed', auto ? 'false' : 'true');
    play.classList.toggle('is-paused', !auto);
    stage.setAttribute('aria-live', auto ? 'off' : 'polite');
  };
  const takeOver = () => {
    if (!auto) return;
    auto = false;
    root.classList.remove('is-auto');
    syncPlay();
  };
  play?.addEventListener('click', () => {
    if (auto) { takeOver(); return; }
    auto = true; paused = 0; t0 = performance.now();
    root.classList.add('is-auto');
    syncPlay();
    requestAnimationFrame(tick);
  });

  root.querySelector('[data-reel-prev]').addEventListener('click', () => { takeOver(); show(index - 1, -1); });
  root.querySelector('[data-reel-next]').addEventListener('click', () => { takeOver(); show(index + 1, 1); });
  thumbs.forEach((t, k) => t.addEventListener('click', () => { takeOver(); show(k); }));
  stage.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight') { e.preventDefault(); takeOver(); show(index + 1, 1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); takeOver(); show(index - 1, -1); }
  });
  root.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse') hovered = true; });
  root.addEventListener('pointerleave', () => { hovered = false; });
  root.addEventListener('focusin', (e) => { if (e.target !== play) takeOver(); });

  // swipe (touch) and drag (mouse) on the stage
  let drag = null;
  stage.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    drag = { x: e.clientX, y: e.clientY, id: e.pointerId };
  });
  stage.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (Math.abs(e.clientX - drag.x) > 8 && Math.abs(e.clientX - drag.x) > Math.abs(e.clientY - drag.y)) {
      stage.classList.add('is-drag');
      try { stage.setPointerCapture(e.pointerId); } catch {}
    }
  });
  const end = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    drag = null;
    stage.classList.remove('is-drag');
    if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy)) { takeOver(); show(index + (dx < 0 ? 1 : -1), dx < 0 ? 1 : -1); }
  };
  stage.addEventListener('pointerup', end);
  stage.addEventListener('pointercancel', () => { drag = null; stage.classList.remove('is-drag'); });

  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    if (visible && !seen) { seen = true; t0 = performance.now(); }
  }, { threshold: 0.35 }).observe(root);

  function tick() {
    if (!auto) return;
    requestAnimationFrame(tick);
    if (!seen) return;
    if (!visible || hovered || document.hidden) { if (!paused) paused = performance.now(); return; }
    if (paused) { t0 += performance.now() - paused; paused = 0; }
    const p = Math.min(1, (performance.now() - t0) / DWELL);
    root.style.setProperty('--auto', p.toFixed(4));
    if (p >= 1) show(index + 1, 1);
  }
  syncPlay();
  if (auto) requestAnimationFrame(tick);
}
