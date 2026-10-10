/**
 * Home-page scroll intro: mode selection and scroll scrubbing.
 * The intro is pure animation, with no captions or labels.
 *
 *  - WebGL:          Three.js scene (./scene.js), loaded lazily.
 *  - No WebGL:       SVG frames that crossfade on scroll.
 *  - Reduced motion: no pinning, no animation: the final logo frame.
 */
import { smooth, seg } from '../lamination/geometry.js';
import { fallbackFrames } from '../lamination/svg.js';

// frame windows for the SVG fallback: empty, coil, cut, mitre, step-lap, core, logo
const FRAME_WINDOWS = [[0.0, 0.1], [0.1, 0.22], [0.22, 0.38], [0.38, 0.52], [0.52, 0.7], [0.7, 0.86], [0.86, 1.01]];

const prefersReduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function webglAvailable() {
  try {
    const c = document.createElement('canvas');
    return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
  } catch { return false; }
}

const fade = (p, a, b, edge = 0.025) => smooth(seg(p, a - edge, a + edge)) * (1 - smooth(seg(p, b - edge, b + edge)));

export async function initIntro(section) {
  if (!section) return;
  const stage = section.querySelector('.intro__stage');
  const night = section.querySelector('.intro__night');
  const final = section.querySelector('.intro__final');
  const framesEl = section.querySelector('.intro__frames');

  if (prefersReduced()) {
    section.classList.add('intro--static');
    return;
  }

  const mobile = window.matchMedia('(max-width: 760px), (pointer: coarse)').matches;
  // ?capture: deterministic scrubbing for recording a video of the intro
  const capture = new URLSearchParams(location.search).has('capture');
  const useGL = webglAvailable() && !new URLSearchParams(location.search).has('nogl');
  section.classList.add('intro--live', useGL ? 'intro--gl' : 'intro--frames');

  let frameEls = [];
  const buildFrames = () => {
    framesEl.innerHTML = fallbackFrames().map((svg) => `<div class="intro__frame">${svg}</div>`).join('');
    frameEls = [...framesEl.children];
  };
  if (!useGL) buildFrames();

  /* ------------------------------------------------------- scroll + smooth */
  const [{ gsap }, { ScrollTrigger }] = await Promise.all([import('gsap'), import('gsap/ScrollTrigger')]);
  gsap.registerPlugin(ScrollTrigger);

  let lenis = null;
  if (!mobile && !capture) {
    const { default: Lenis } = await import('lenis');
    lenis = new Lenis({ lerp: 0.1, wheelMultiplier: 0.85, anchors: { offset: -72 } });
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
    // logo reveal: the 3D studio has already gone dark; the logo fades up on black
    const fo = smooth(seg(p, 0.925, 0.975));
    final.style.opacity = fo;
    final.style.transform = `scale(${(0.985 + fo * 0.015).toFixed(4)})`;
    if (scene) {
      canvas.style.opacity = 1 - smooth(seg(p, 0.915, 0.96));
      scene.update(p);
    } else if (frameEls.length) {
      night.style.opacity = smooth(seg(p, 0.86, 0.92));
      frameEls.forEach((el, i) => {
        const [a, b] = FRAME_WINDOWS[i];
        el.style.opacity = fade(p, a, b);
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
      scene = createScene(canvas, { mobile });
      scene.resize(size.w, size.h);
      section.classList.add('is-ready');
      apply(state.p);
    } catch (err) {
      console.warn('[intro] WebGL scene failed, using fallback frames', err);
      section.classList.remove('intro--gl');
      section.classList.add('intro--frames');
      buildFrames();
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
    for (const e of entries) { if (e.isIntersecting) startScene(); else stopScene(); }
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

  apply(0);
  window.addEventListener('pagehide', () => { stopScene(); io.disconnect(); ro.disconnect(); });
}
