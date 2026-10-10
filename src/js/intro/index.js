/**
 * Home-page scroll intro: mode selection, scroll scrubbing, captions.
 *
 *  - WebGL:          Three.js scene (./scene.js), loaded lazily.
 *  - No WebGL:       SVG frames that crossfade on scroll.
 *  - Reduced motion: no pinning, no animation: final frame + all captions.
 */
import { smooth, seg } from '../lamination/geometry.js';
import { fallbackFrames } from '../lamination/svg.js';

// Beat windows in scroll progress (keep in sync with ./scene.js)
const BEATS = [
  [0.1, 0.22], // coil
  [0.22, 0.38], // cut
  [0.38, 0.52], // mitre
  [0.52, 0.7], // step-lap
  [0.7, 0.86], // core
];
const OPENING = [0.0, 0.095];
const FINAL = 0.915;

const prefersReduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function webglAvailable() {
  try {
    const c = document.createElement('canvas');
    return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
  } catch { return false; }
}

const fade = (p, a, b, edge = 0.018) => smooth(seg(p, a - edge, a + edge)) * (1 - smooth(seg(p, b - edge, b + edge)));

export async function initIntro(section) {
  if (!section) return;
  const stage = section.querySelector('.intro__stage');
  const opening = section.querySelector('.intro__opening');
  const beats = [...section.querySelectorAll('.beat')];
  const ticks = [...section.querySelectorAll('.intro__rail li')];
  const final = section.querySelector('.intro__final');
  const cue = section.querySelector('.intro__cue');
  const skip = section.querySelector('.intro__skip');
  const framesEl = section.querySelector('.intro__frames');
  const labelEls = Object.fromEntries([...section.querySelectorAll('[data-label]')].map((el) => [el.dataset.label, el]));

  if (prefersReduced()) {
    section.classList.add('intro--static');
    return;
  }

  const mobile = window.matchMedia('(max-width: 760px), (pointer: coarse)').matches;
  // ?capture: deterministic scrubbing for recording a video of the intro
  const capture = new URLSearchParams(location.search).has('capture');
  const useGL = webglAvailable() && !new URLSearchParams(location.search).has('nogl');
  section.classList.add('intro--live', useGL ? 'intro--gl' : 'intro--frames');

  /* ------------------------------------------------------- fallback frames */
  let frameEls = [];
  if (!useGL) {
    framesEl.innerHTML = fallbackFrames().map((svg) => `<div class="intro__frame">${svg}</div>`).join('');
    frameEls = [...framesEl.children];
  }
  // frame windows: opening, five beats, logo
  const frameWindows = [[0.0, 0.1], ...BEATS, [0.86, 1.01]];

  /* ------------------------------------------------------- scroll + smooth */
  const [{ gsap }, { ScrollTrigger }] = await Promise.all([import('gsap'), import('gsap/ScrollTrigger')]);
  gsap.registerPlugin(ScrollTrigger);

  let lenis = null;
  if (!mobile && !capture) {
    const { default: Lenis } = await import('lenis');
    lenis = new Lenis({ lerp: 0.12, wheelMultiplier: 0.9, anchors: { offset: -72 } });
    lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add((t) => lenis.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
  }

  const state = { p: 0 };
  let scene = null;
  let canvas = section.querySelector('.intro__canvas');
  let pending = false;
  let size = { w: stage.clientWidth, h: stage.clientHeight };

  const request = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; apply(state.p); });
  };

  function apply(p) {
    window.__introP = p;
    window.__introReady = !!scene || frameEls.length > 0;
    // opening line
    opening.style.opacity = 1 - smooth(seg(p, OPENING[1] - 0.035, OPENING[1]));
    // captions
    let active = -1;
    beats.forEach((el, i) => {
      const [a, b] = BEATS[i];
      // sequential hand-over: the outgoing caption is gone before the next arrives
      const o = smooth(seg(p, a + 0.004, a + 0.022)) * (1 - smooth(seg(p, b - 0.022, b - 0.004)));
      el.style.opacity = o;
      el.style.transform = `translateY(${(1 - o) * 10}px)`;
      el.setAttribute('aria-hidden', o < 0.5 ? 'true' : 'false');
      if (p >= a && p < b) active = i;
    });
    ticks.forEach((t, i) => t.classList.toggle('is-active', i === active));
    section.querySelector('.intro__rail').style.opacity = fade(p, 0.1, FINAL - 0.02);
    // final logo moment
    const fo = smooth(seg(p, FINAL, FINAL + 0.06));
    final.style.opacity = fo;
    final.style.transform = `translateY(${(1 - fo) * 16}px)`;
    final.classList.toggle('is-on', fo > 0.6);
    final.setAttribute('aria-hidden', 'false');
    cue.style.opacity = Math.max(1 - smooth(seg(p, 0.0, 0.05)), smooth(seg(p, 0.97, 1.0)));
    skip.classList.toggle('is-hidden', p > FINAL);

    if (scene) {
      canvas.style.opacity = 1 - smooth(seg(p, 0.875, 0.93)) * (document.documentElement.dataset.theme === 'light' ? 0.6 : 0.88);
      const labels = scene.update(p);
      for (const [id, el] of Object.entries(labelEls)) {
        const l = labels[id];
        if (!l) continue;
        el.style.opacity = l.o;
        el.style.transform = `translate(${l.x.toFixed(1)}px, ${l.y.toFixed(1)}px) translate(-50%, -50%)`;
      }
    } else if (frameEls.length) {
      frameEls.forEach((el, i) => {
        const [a, b] = frameWindows[i];
        el.style.opacity = i === frameEls.length - 1 ? smooth(seg(p, a, a + 0.04)) * 0.5 : fade(p, a, b, 0.025);
      });
    }
  }

  /* ------------------------------------------------------------- 3D scene */
  let createScene = null;
  async function startScene() {
    if (scene || !useGL) return;
    try {
      if (!createScene) ({ createIntroScene: createScene } = await import('./scene.js'));
      if (scene) return;
      if (canvas.dataset.used) {
        // a disposed context cannot be revived: swap in a fresh canvas
        const fresh = canvas.cloneNode(false);
        canvas.replaceWith(fresh);
        canvas = fresh;
      }
      canvas.dataset.used = '1';
      scene = createScene(canvas, { mobile, light: document.documentElement.dataset.theme === 'light' });
      scene.resize(size.w, size.h);
      section.classList.add('is-ready');
      apply(state.p);
    } catch (err) {
      console.warn('[intro] WebGL scene failed, using fallback frames', err);
      section.classList.remove('intro--gl');
      section.classList.add('intro--frames');
      framesEl.innerHTML = fallbackFrames().map((svg) => `<div class="intro__frame">${svg}</div>`).join('');
      frameEls = [...framesEl.children];
      apply(state.p);
    }
  }
  function stopScene() {
    if (!scene) return;
    scene.dispose();
    scene = null;
    section.classList.remove('is-ready');
  }

  // Lazy start; dispose when the section is well out of view, rebuild on return.
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) startScene(); else stopScene();
    }
  }, { rootMargin: '25% 0px 25% 0px' });
  io.observe(section);

  /* --------------------------------------------------------------- resize */
  const ro = new ResizeObserver(() => {
    const w = stage.clientWidth, h = stage.clientHeight;
    // mobile browser chrome changes height while scrolling: ignore small jumps
    if (mobile && w === size.w && Math.abs(h - size.h) < 140) return;
    size = { w, h };
    if (scene) scene.resize(w, h);
    request();
  });
  ro.observe(stage);

  /* ------------------------------------------------------------- scrubbing */
  gsap.to(state, {
    p: 1,
    ease: 'none',
    scrollTrigger: {
      trigger: section,
      start: 'top top',
      end: 'bottom bottom',
      scrub: lenis || capture ? true : 0.35,
      invalidateOnRefresh: true,
    },
    onUpdate: request,
  });

  skip.addEventListener('click', (e) => {
    const target = document.querySelector(skip.getAttribute('href'));
    if (!target) return;
    e.preventDefault();
    if (lenis) lenis.scrollTo(target, { offset: -72, duration: 1.2 });
    else target.scrollIntoView({ behavior: 'smooth' });
    target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
  });

  apply(0);
  window.addEventListener('pagehide', () => { stopScene(); io.disconnect(); ro.disconnect(); });
}

