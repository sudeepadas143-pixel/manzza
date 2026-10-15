/**
 * Home-page scroll intro: mode selection and scroll scrubbing.
 * The intro is pure animation, with no captions or labels.
 *
 * It opens on the MANZZA logo. On scroll the wordmark leaves, the M takes the
 * centre of the screen and dissolves into the end face of a coil of steel,
 * and the 3D scene (./scene.js) takes over.
 *
 *  - WebGL:          Three.js scene, loaded lazily.
 *  - No WebGL:       SVG frames that crossfade on scroll.
 *  - Reduced motion: no pinning, no animation: the logo.
 */
import { smooth, seg, lerp } from '../lamination/geometry.js';
import { fallbackFrames } from '../lamination/svg.js';
import { STUDIO_HDRI } from '../lamination/hdri.js';

// frame windows for the SVG fallback: empty, coil, cut, mitre, step-lap (unused), core, outline (unused)
const FRAME_WINDOWS = [[0, 0.1], [0.1, 0.22], [0.22, 0.38], [0.38, 0.52], [2, 2], [0.52, 1.01], [2, 2]];

// The M in the lockup image, as fractions of the lockup box (measured from the artwork).
const M_BOX = { left: 0.0235, top: 0.1597, width: 0.2299, height: 0.6306 };

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
  const lockup = section.querySelector('.intro__lockup');
  const word = section.querySelector('.intro__word');
  const mark = section.querySelector('.intro__m');
  const tagline = section.querySelector('.intro__tagline');
  const cue = section.querySelector('[data-cue]');
  const framesEl = section.querySelector('.intro__frames');

  if (prefersReduced()) {
    section.classList.add('intro--static');
    // no film: the cue jumps straight to what follows it
    cue?.addEventListener('click', () => section.nextElementSibling?.scrollIntoView({ behavior: 'auto' }));
    return;
  }

  // ?capture: deterministic scrubbing at full quality, header hidden, for recording a film of the intro
  const params = new URLSearchParams(location.search);
  const capture = params.has('capture');
  if (capture) document.documentElement.classList.add('capture');
  const mobile = !capture && window.matchMedia('(max-width: 760px), (pointer: coarse)').matches;
  const useGL = webglAvailable() && !params.has('nogl');
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
    lenis = new Lenis({ lerp: 0.085, wheelMultiplier: 0.8, anchors: { offset: -72 } });
    lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add((t) => lenis.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
  }
  // the cue starts the film: a gentle glide of one screen into it
  cue?.addEventListener('click', () => {
    const to = window.scrollY + window.innerHeight;
    if (lenis) lenis.scrollTo(to, { duration: 1.6 });
    else window.scrollTo({ top: to, behavior: 'smooth' });
  });

  const state = { p: 0 };
  let scene = null;
  let canvas = section.querySelector('.intro__canvas');
  let size = { w: stage.clientWidth, h: stage.clientHeight };

  /* ----------------------------------------------- logo → M → coil geometry */
  // Measured once per resize (never during the scroll): where the M sits inside
  // the lockup, and where it has to go to line up with the coil's end face.
  let geo = null;
  function measure() {
    const sr = stage.getBoundingClientRect(), lr = lockup.getBoundingClientRect();
    const lw = lr.width, lh = lr.height;
    const lx = lr.left - sr.left, ly = lr.top - sr.top;
    const m = { x: lx + M_BOX.left * lw, y: ly + M_BOX.top * lh, w: M_BOX.width * lw, h: M_BOX.height * lh };
    // target: the M centred on the coil face, its height a little under the face's diameter
    const face = scene ? scene.coilFace(0.1) : { x: size.w / 2, y: size.h / 2, r: size.h * 0.2 };
    const k = (face.r * 2 * 0.86) / m.h;
    geo = {
      dx: face.x - (m.x + m.w / 2),
      dy: face.y - (m.y + m.h / 2),
      k,
    };
    mark.style.left = `${m.x}px`;
    mark.style.top = `${m.y}px`;
    mark.style.width = `${m.w}px`;
    mark.style.height = `${m.h}px`;
    section.classList.add('is-split');
  }

  let dirty = true;
  let lastP = -1;
  // Time-warp: the logo -> coil -> slitting opening (film 0-0.38) plays over the
  // first 28% of the scroll, the rest keeps its pace. With the section 15% shorter
  // (460vh / 350vh, main.css) only the opening speeds up.
  const WARP_IN = 0.28, WARP_OUT = 0.38;
  const warp = (r) => (r <= WARP_IN ? r * (WARP_OUT / WARP_IN) : WARP_OUT + (r - WARP_IN) * ((1 - WARP_OUT) / (1 - WARP_IN)));
  function apply(raw) {
    const p = warp(raw);
    window.__introP = p;
    window.__introReady = (!!scene && scene.ready()) || frameEls.length > 0;
    if (!geo) measure();

    // the wordmark and tagline step aside; the M moves to the centre and grows
    const go = smooth(seg(p, 0.018, 0.072));
    const wordOut = smooth(seg(p, 0.012, 0.05));
    word.style.opacity = (1 - wordOut).toFixed(3);
    word.style.transform = `translate3d(${(wordOut * 3).toFixed(2)}%, 0, 0)`;
    // then it shrinks into the bore of the coil that winds up around it, and is gone
    const into = smooth(seg(p, 0.075, 0.14));
    const dissolve = smooth(seg(p, 0.11, 0.15));
    const s = lerp(1, geo.k, go) * lerp(1, 0.34, into);
    mark.style.transform = `translate3d(${(geo.dx * go).toFixed(1)}px, ${(geo.dy * go).toFixed(1)}px, 0) scale(${s.toFixed(4)})`;
    mark.style.opacity = (1 - dissolve).toFixed(3);
    const hidden = dissolve >= 1;
    if (mark.hidden !== hidden) { mark.hidden = hidden; word.hidden = hidden; }

    // the scroll cue says how to start, then gets out of the way at the first scroll
    if (cue) {
      const c = 1 - smooth(seg(p, 0, 0.012));
      cue.style.opacity = c.toFixed(3);
      cue.style.visibility = c > 0 ? 'visible' : 'hidden';
    }

    // the close: the tagline settles in under the finished core
    if (tagline) {
      const t = smooth(seg(p, 0.93, 0.985));
      tagline.style.opacity = t.toFixed(3);
      tagline.style.transform = `translate3d(0, ${((1 - t) * 14).toFixed(1)}px, 0)`;
    }

    if (scene) {
      scene.update(p);
    } else if (frameEls.length) {
      frameEls.forEach((el, i) => {
        const [a, b] = FRAME_WINDOWS[i];
        el.style.opacity = fade(p, a, b);
      });
    }
  }

  /* -------------------------------------------- render loop + adaptive quality */
  // Render in the same ticker frame the scroll value changes (after Lenis), so
  // there is no extra frame of latency between the wheel and the picture.
  const samples = [];
  let lastFrameAt = 0;
  function tick() {
    if (!dirty && state.p === lastP) return;
    dirty = false;
    lastP = state.p;
    const now = performance.now();
    apply(state.p);
    if (!scene || capture) return;
    // While the scene renders frame after frame, watch the frame interval.
    // If it stays long, the GPU is the bottleneck: drop the resolution a step.
    const dt = now - lastFrameAt;
    lastFrameAt = now;
    if (dt > 0 && dt < 120) {
      samples.push(dt);
      if (samples.length >= 45) {
        samples.sort((a, b) => a - b);
        const median = samples[samples.length >> 1];
        samples.length = 0;
        const ratio = scene.pixelRatio();
        const floor = mobile ? 0.75 : 1;
        if (median > 24 && ratio > floor) scene.setPixelRatio(Math.max(floor, ratio - 0.25));
      }
    }
  }
  gsap.ticker.add(tick);

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
      scene = createScene(canvas, { mobile, capture, hdri: STUDIO_HDRI.url, onChange: () => { dirty = true; } });
      scene.resize(size.w, size.h);
      geo = null;
      section.classList.add('is-ready');
      dirty = true;
    } catch (err) {
      console.warn('[intro] WebGL scene failed, using fallback frames', err);
      section.classList.remove('intro--gl');
      section.classList.add('intro--frames');
      buildFrames();
      dirty = true;
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
    geo = null;
    dirty = true;
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
      // Lenis already smooths the wheel on desktop. On touch, a short catch-up
      // turns uneven native scroll steps into continuous motion.
      scrub: lenis || capture ? true : 0.6,
      invalidateOnRefresh: true,
    },
  });

  apply(0);
  window.addEventListener('pagehide', () => { stopScene(); io.disconnect(); ro.disconnect(); gsap.ticker.remove(tick); });
}
