/**
 * One offscreen WebGL renderer draws every small product visual on the page
 * and copies each frame into that visual's 2D canvas. Only visible visuals
 * animate, at a gentle frame rate; with reduced motion they render once.
 */
import * as THREE from 'three';
import {
  corePieces, cruciform, stepOffsets, eShape, iShape, stripShape, CORE,
} from './lamination/geometry.js';
import {
  extrudeLaminations, createSteelUniforms, createSteelMaterial, studioEnvironment,
  loadStudioHDRI, STUDIO_HDRI,
} from './lamination/three-kit.js';

const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Metal three-point, as in the intro: warm key, cool fill, cool rim (4:1:2). */
function metalLights(scene) {
  const key = new THREE.DirectionalLight(new THREE.Color().setRGB(1.0, 0.95, 0.85), 2.4);
  key.position.set(4, 7, 6);
  const fill = new THREE.DirectionalLight(new THREE.Color().setRGB(0.85, 0.9, 1.0), 0.6);
  fill.position.set(-6, 2, 5);
  const rim = new THREE.DirectionalLight(new THREE.Color().setRGB(0.7, 0.85, 1.0), 1.2);
  rim.position.set(-3, 5, -7);
  scene.add(key, fill, rim);
}

function buildCore(mat) {
  const g = new THREE.Group();
  const packets = cruciform(CORE.D, [0.95, 0.7]);
  const offsets = stepOffsets(5, 0.05);
  const half = packets[packets.length - 1].z1;
  let layer = 0;
  const items = [];
  for (const pk of packets) {
    const n = Math.max(1, Math.round((pk.z1 - pk.z0) / 0.045));
    const t = (pk.z1 - pk.z0) / n;
    for (let k = 0; k < n; k++) {
      const o = offsets[layer % 5];
      for (const p of corePieces({ w: pk.w, o, gap: 0.012 })) items.push({ poly: p.poly, holes: p.holes, z: pk.z0 + k * t, t: t * 0.8, layer, dir: p.dir });
      layer++;
    }
  }
  const m = new THREE.Mesh(extrudeLaminations(items), mat);
  m.position.set(0, -2.15, 0);
  g.add(m);
  return { group: g, tilt: 0.42, spin: 0.22, swing: 0.45, half };
}

function buildEI(mat) {
  const g = new THREE.Group();
  const a = 1;
  const items = [];
  const layers = 14, t = 0.045;
  // grain along the E's legs, and along the length of the I
  for (let k = 0; k < layers; k++) {
    items.push({ poly: eShape(a), z: k * t, t: t * 0.8, layer: k, dir: 'y' });
  }
  const iItems = [];
  for (let k = 0; k < layers; k++) iItems.push({ poly: iShape(a), z: k * t, t: t * 0.8, layer: k, dir: 'x' });
  const e = new THREE.Mesh(extrudeLaminations(items), mat);
  const i = new THREE.Mesh(extrudeLaminations(iItems), mat);
  e.position.set(-1.5, -1.25, -layers * t / 2);
  i.position.set(-1.5, 0.95, -layers * t / 2);
  g.add(e, i);
  // upright, as the letters read: the E's back on the left, legs to the right, the I beside them
  g.rotation.z = -Math.PI / 2;
  return { group: g, tilt: 0.3, spin: 0.3, swing: 0.35 };
}

function buildStrip(mat) {
  const g = new THREE.Group();
  const s = stripShape({ length: 4.2, width: 0.62, holes: 3, holeR: 0.085 });
  const items = [];
  const layers = 8, t = 0.05;
  for (let k = 0; k < layers; k++) items.push({ poly: s.outer, holes: s.holes, z: k * t, t: t * 0.8, layer: k, dir: 'x' });
  const m = new THREE.Mesh(extrudeLaminations(items), mat);
  m.position.set(-2.1, -0.31, -layers * t / 2);
  g.add(m);
  return { group: g, tilt: 0.5, spin: 0.2, swing: 0.3 };
}

const BUILDERS = { core: buildCore, ei: buildEI, strip: buildStrip };

export function startMinis(canvases) {
  const glCanvas = document.createElement('canvas');
  const renderer = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: true, alpha: true, preserveDrawingBuffer: false });
  renderer.setPixelRatio(1);
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.AgXToneMapping; // same colour pipeline as the intro
  renderer.toneMappingExposure = 1.1;
  const env = studioEnvironment(renderer, { dark: true }); // same black studio as the intro
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  const views = canvases.map((canvas) => {
    const scene = new THREE.Scene();
    scene.environment = env;
    // these pieces are tilted towards the camera, so their faces reflect the studio from
    // higher up than the intro's upright core: tip the studio to put a soft box there
    const [rx, ry] = STUDIO_HDRI.miniRotation;
    scene.environmentRotation.set(rx, ry, 0);
    // small, tilted pieces need more of the studio to read as metal; the full core's
    // broad faces catch the soft box whole, so it gets less or they burn out to white
    scene.environmentIntensity = { core: 0.85, strip: 3 }[canvas.dataset.mini] ?? 2.2;
    metalLights(scene);
    const uniforms = createSteelUniforms();
    const mat = createSteelMaterial(uniforms);
    const build = (BUILDERS[canvas.dataset.mini] || buildCore)(mat);
    const pivot = new THREE.Group();
    pivot.add(build.group);
    const centre = new THREE.Box3().setFromObject(build.group).getCenter(new THREE.Vector3());
    build.group.position.sub(centre);
    scene.add(pivot);
    const box = new THREE.Box3().setFromObject(pivot);
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 100);
    const view = { canvas, ctx: canvas.getContext('2d'), scene, camera, pivot, build, sphere, visible: false, w: 0, h: 0, phase: Math.random() * 6 };
    canvas.closest('.mini')?.classList.add('is-live');
    return view;
  });

  function fit(v) {
    const rect = v.canvas.getBoundingClientRect();
    // full-bleed bands are large: cap their backing store so a band costs no more than a card
    const k = Math.min(dpr, 2400 / Math.max(1, rect.width), 1600 / Math.max(1, rect.height));
    const w = Math.max(1, Math.round(rect.width * k));
    const h = Math.max(1, Math.round(rect.height * k));
    if (w !== v.w || h !== v.h) {
      v.w = w; v.h = h;
      v.canvas.width = w; v.canvas.height = h;
      const aspect = w / h;
      v.camera.aspect = aspect;
      // in a wide band the part sits to one side of the copy (data-frame)
      const side = aspect > 1.5 && window.innerWidth >= 720 ? ({ right: 1, left: -1 }[v.canvas.dataset.frame] || 0) : 0;
      const fov = THREE.MathUtils.degToRad(v.camera.fov);
      const fitH = v.sphere.radius / Math.sin(fov / 2);
      const fitW = fitH / Math.min(1, side ? aspect / 2 : aspect);
      const d = Math.max(fitH, fitW) * (side ? 0.86 : aspect < 1 ? 1.3 : 0.8);
      v.camera.position.set(0, d * 0.18, d);
      v.camera.lookAt(0, 0, 0);
      if (side) v.camera.setViewOffset(w, h, -side * w * 0.22, 0, w, h);
      else v.camera.clearViewOffset();
      v.camera.updateProjectionMatrix();
    }
  }

  // data-scrub: the part turns with its band's progress through the viewport
  function scrubOf(v) {
    if (!('scrub' in v.canvas.dataset)) return 0;
    const band = v.canvas.closest('.band') || v.canvas;
    const r = band.getBoundingClientRect();
    const vh = window.innerHeight;
    const prog = Math.min(1, Math.max(0, (vh - r.top) / (vh + r.height)));
    return (prog - 0.5) * 1.4;
  }

  function draw(v, time) {
    fit(v);
    const t = reduced ? 0.6 : time * 0.001 + v.phase;
    const scrub = reduced ? 0 : scrubOf(v);
    const idle = Math.sin(t * v.build.spin) * v.build.swing * (scrub ? 0.35 : 1);
    v.pivot.rotation.set(-v.build.tilt + scrub * 0.12, idle - 0.3 + scrub, 0);
    const W = glCanvas.width, H = glCanvas.height;
    if (v.w > W || v.h > H) renderer.setSize(Math.max(W, v.w), Math.max(H, v.h), false);
    renderer.setViewport(0, 0, v.w, v.h);
    renderer.setScissor(0, 0, v.w, v.h);
    renderer.setScissorTest(true);
    renderer.render(v.scene, v.camera);
    v.ctx.clearRect(0, 0, v.w, v.h);
    v.ctx.drawImage(glCanvas, 0, glCanvas.height - v.h, v.w, v.h, 0, 0, v.w, v.h);
  }

  // swap in the photographed studio once it has loaded, so the steel matches the intro
  loadStudioHDRI(renderer, STUDIO_HDRI.miniUrl).then((hdr) => {
    views.forEach((v) => { v.scene.environment = hdr; });
    env.dispose();
    views.forEach((v) => v.visible && draw(v, performance.now()));
  }).catch(() => {});

  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const v = views.find((x) => x.canvas === e.target);
      if (v) { v.visible = e.isIntersecting; if (v.visible) draw(v, performance.now()); }
    }
  });
  views.forEach((v) => io.observe(v.canvas));

  window.addEventListener('resize', () => views.forEach((v) => v.visible && draw(v, performance.now())));
  if (reduced) return;

  // ~30 fps is plenty for a slow turn. Where a frame is expensive (a weak GPU, or
  // software WebGL) wait at least four frames' worth of drawing time, so the turn
  // slows down instead of the page: the main thread stays mostly free.
  let last = 0, cost = 0;
  function loop(now) {
    requestAnimationFrame(loop);
    if (document.hidden || now - last < Math.max(33, cost * 4)) return;
    last = now;
    const t0 = performance.now();
    for (const v of views) if (v.visible) draw(v, now);
    const dt = performance.now() - t0;
    cost = cost ? cost * 0.8 + dt * 0.2 : dt;
  }
  requestAnimationFrame(loop);
}
