/**
 * Scroll intro: from the MANZZA mark to a clamped transformer core.
 * Pure animation, no text: the story is told by the steel alone.
 *
 * Everything is a pure function of scroll progress p ∈ [0, 1]: update(p)
 * places every object from scratch, so scrubbing backwards reverses exactly.
 * The scene renders on demand (only when p or the size changes).
 *
 * Look: a dark studio. Physically based brushed steel (the grain follows each
 * lamination's rolling direction) reflecting large soft boxes, one soft
 * shadow-casting key light, a cool rim light to draw edges out of the black,
 * and a pool of light on the floor under the subject.
 *
 * Beats (keep in sync with ./index.js):
 *   0.00–0.075 the logo (HTML): the wordmark leaves, the M takes the centre
 *   0.075–0.16 the M shrinks into the bore of a coil that winds itself up around it
 *   0.13–0.22  the camera comes round to the coil
 *   0.22–0.38  the coil rolls out a sheet; slitting into strips
 *   0.38–0.50  45° mitre cuts
 *   0.50–0.62  the four laminations take their places in the core; the packets stack
 *   0.62–0.70  the core is stood up and raised onto its feet
 *   0.70–0.92  the clamping frame assembles: clamps, bolts, tie rods, nuts, lug
 *   0.92–1.00  the finished core, turning under the lights; the tagline (HTML)
 */
import * as THREE from 'three';
import {
  CORE, corePieces, cruciform, stepOffsets, clamp, smooth, seg, lerp,
} from '../lamination/geometry.js';
import {
  extrudeLaminations, createSteelUniforms, createSteelMaterial, studioEnvironment,
  brushedTexture, disposeTree, releaseShared, BRAND,
} from '../lamination/three-kit.js';
import { buildFrame, FRAME } from './frame.js';

const easeOut = (t) => 1 - (1 - t) ** 3;
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

export const STUDIO = new THREE.Color('#0a0b0d'); // matches --stage (ink-950) in main.css

export function createIntroScene(canvas, { mobile = false, capture = false } = {}) {
  /* ---------------------------------------------------------------- setup */
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  // Pixel ratio is capped: a 2× full-screen buffer of physically based steel is
  // the single biggest cost per frame. index.js lowers it further if frames run long.
  const maxRatio = capture ? 2 : 1.5;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, maxRatio));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.localClippingEnabled = true;
  renderer.shadowMap.enabled = true;
  // PCF with a radius: soft shadows from 5 hardware-filtered taps, no blur passes (VSM needed two per frame)
  renderer.shadowMap.type = THREE.PCFShadowMap;

  const scene = new THREE.Scene();
  scene.background = STUDIO.clone();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 80);
  const envTex = studioEnvironment(renderer, { dark: true });
  scene.environment = envTex;
  scene.environmentRotation.set(0, -0.6, 0);

  const key = new THREE.DirectionalLight(0xffffff, 0);
  key.castShadow = true;
  key.shadow.mapSize.set(mobile ? 1024 : 2048, mobile ? 1024 : 2048);
  key.shadow.bias = -0.0004;
  key.shadow.normalBias = 0.02;
  key.shadow.radius = mobile ? 3 : 5;
  key.shadow.camera.near = 0.5;
  key.shadow.camera.far = 40;
  scene.add(key, key.target);
  // cool rim from behind: draws the edges out of the black
  const rim = new THREE.DirectionalLight(0xffffff, 0);
  scene.add(rim, rim.target);
  // electric-blue light, only for the moment the M becomes the coil
  const spark = new THREE.PointLight(BRAND.blueGlow, 0, 9, 1.4);
  scene.add(spark);
  const fill = new THREE.HemisphereLight(0xffffff, 0x000000, 0);
  scene.add(fill);

  const LIGHT = { key: 3.4, rim: 2.6, fill: 0.2, env: 1.0 };

  // Floor: a soft pool of light under the subject, plus the shadow it receives.
  const poolTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 256;
    const g = c.getContext('2d');
    const gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.35, 'rgba(255,255,255,0.45)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  })();
  const poolMat = new THREE.MeshBasicMaterial({ map: poolTex, color: 0x1c2230, transparent: true, depthWrite: false, toneMapped: false });
  const pool = new THREE.Mesh(new THREE.PlaneGeometry(22, 22), poolMat);
  pool.rotation.x = -Math.PI / 2;
  pool.position.y = -0.002;
  scene.add(pool);
  const floorMat = new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.6 });
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  const shadowed = (m, receive = true) => { m.castShadow = true; m.receiveShadow = receive; return m; };

  const uniforms = createSteelUniforms();
  // a touch darker than raw steel: the insulation coating, and contrast with the painted frame
  const STEEL = { color: new THREE.Color(0x8a919a) };
  const steel = createSteelMaterial(uniforms, STEEL);

  const W0 = 0.95; // widest lamination = strip width
  const blueLine = (opacity = 1) => new THREE.MeshBasicMaterial({
    color: BRAND.blue, transparent: true, opacity, toneMapped: false, depthWrite: false,
  });

  /* ----------------------------------------------------------------- coil */
  const coil = new THREE.Group();
  const R = 1.0, r = 0.42, CW = W0 * 4; // coil radius, bore, width (= 4 strips)
  const coilMats = [];
  {
    const tex = brushedTexture().clone();
    tex.repeat.set(6, 1);
    tex.needsUpdate = true;
    // dark rolled steel, not a pale roll: low albedo, strong metallic reflections
    const outerMat = new THREE.MeshPhysicalMaterial({
      color: 0x5c626a, metalness: 0.96, roughness: 0.34, roughnessMap: tex,
      anisotropy: 0.4, clearcoat: 0.05, clearcoatRoughness: 0.4,
      envMapIntensity: 0.45, // the soft boxes read as a sheen on dark steel, not a white wash
    });
    const outer = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(R, R, CW, mobile ? 96 : 160, 1, true), outerMat));
    outer.rotation.x = Math.PI / 2;
    const boreMat = new THREE.MeshStandardMaterial({ color: 0x3a414c, metalness: 0.6, roughness: 0.55, side: THREE.BackSide });
    const bore = new THREE.Mesh(new THREE.CylinderGeometry(r, r, CW, 64, 1, true), boreMat);
    bore.rotation.x = Math.PI / 2;
    // end faces: the wraps of strip, as fine concentric rings
    const c = document.createElement('canvas');
    c.width = c.height = mobile ? 1024 : 2048;
    const g = c.getContext('2d');
    const S = c.width / 2;
    g.fillStyle = '#4c525b'; g.fillRect(0, 0, c.width, c.height);
    const wraps = mobile ? 90 : 180;
    let seed = 11;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i <= wraps; i++) {
      const rr = (r / R + (1 - r / R) * (i / wraps)) * S;
      g.beginPath(); g.arc(S, S, rr, 0, Math.PI * 2);
      // each wrap's edge catches the light a little differently
      g.strokeStyle = i % 2 ? `rgba(14,17,22,${0.45 + rnd() * 0.25})` : `rgba(196,204,214,${0.12 + rnd() * 0.18})`;
      g.lineWidth = Math.max(1, (S / wraps) * (0.25 + rnd() * 0.2));
      g.stroke();
    }
    const ringTex = new THREE.CanvasTexture(c);
    ringTex.colorSpace = THREE.SRGBColorSpace;
    ringTex.anisotropy = 8;
    const endMat = new THREE.MeshPhysicalMaterial({ map: ringTex, metalness: 0.8, roughness: 0.34, clearcoat: 0.25, clearcoatRoughness: 0.35 });
    // winding: the end faces show only the wraps laid so far (radius <= uWind)
    endMat.userData.wind = { value: R };
    endMat.onBeforeCompile = (sh) => {
      sh.uniforms.uWind = endMat.userData.wind;
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying float vRad;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvRad = length(position.xy);');
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying float vRad; uniform float uWind;')
        .replace('#include <clipping_planes_fragment>', '#include <clipping_planes_fragment>\nif (vRad > uWind) discard;');
    };
    endMat.customProgramCacheKey = () => 'coil-end';
    const endA = shadowed(new THREE.Mesh(new THREE.RingGeometry(r, R, mobile ? 96 : 160, 1), endMat));
    endA.position.z = CW / 2;
    const endB = endA.clone();
    endB.rotation.y = Math.PI;
    endB.position.z = -CW / 2;
    const spin = new THREE.Group();
    spin.add(outer, bore, endA, endB);
    coil.add(spin);
    coil.userData.spin = spin;
    coil.userData.outer = outer;
    coil.userData.endMat = endMat;
    coilMats.push(outerMat, boreMat, endMat);
  }
  scene.add(coil);
  // the strip being wound on: it feeds in over the top of the coil from the right
  const feedMat = createSteelMaterial(uniforms, { color: new THREE.Color(0x6a7079), clearcoat: 0.1, envMapIntensity: 0.5 });
  const feedGeo = new THREE.PlaneGeometry(9, CW);
  feedGeo.rotateX(-Math.PI / 2);
  feedGeo.translate(4.5, 0, 0);
  const feed = shadowed(new THREE.Mesh(feedGeo, feedMat), false);
  coil.add(feed);

  /* ---------------------------------------------- sheet → strips → laminations */
  // 2D layout: x along the strip (rolling direction), y across. Group is laid
  // flat on the floor: (x, y, z) → world (x, z, -y).
  const XS0 = -4.2; // where the coil stops rolling (left end of the sheet)
  const XS1 = 3.4; // where the coil starts (right end of the sheet)
  const XA = -1.6, XB = 1.6; // lamination cut centres
  const T_SHEET = 0.03;
  const strips = new THREE.Group();
  strips.rotation.x = -Math.PI / 2;
  strips.position.y = 0.002;
  scene.add(strips);

  const clip = new THREE.Plane(new THREE.Vector3(1, 0, 0), -XS1); // keeps x >= the coil's position
  const SHEET = { color: new THREE.Color(0x6a7079), clearcoat: 0.1, envMapIntensity: 0.5 }; // fresh-cut sheet: darker, less glossy than a white roll
  const sheetMat = createSteelMaterial(uniforms, SHEET);
  sheetMat.clippingPlanes = [clip];
  sheetMat.clipShadows = true;
  const offcutMat = createSteelMaterial(uniforms, SHEET);
  offcutMat.clippingPlanes = [clip];
  offcutMat.clipShadows = true;
  offcutMat.transparent = true;

  const STRIPS = 4;
  const stripRows = [];
  for (let i = 0; i < STRIPS; i++) {
    const y0 = -W0 / 2, y1 = W0 / 2;
    const lam = [[XA - W0 / 2, y0], [XB + W0 / 2, y0], [XB - W0 / 2, y1], [XA + W0 / 2, y1]];
    const offL = [[XS0 - 0.6, y0], [XA - W0 / 2, y0], [XA + W0 / 2, y1], [XS0 - 0.6, y1]];
    const offR = [[XB + W0 / 2, y0], [XS1, y0], [XS1, y1], [XB - W0 / 2, y1]];
    const mk = (poly, mat) => shadowed(new THREE.Mesh(extrudeLaminations([{ poly, z: 0, t: T_SHEET, dir: 'x' }]), mat), false);
    const row = new THREE.Group();
    const mLam = mk(lam, sheetMat);
    const mL = mk(offL, offcutMat);
    const mR = mk(offR, offcutMat);
    row.add(mLam, mL, mR);
    row.userData = { baseY: (i - (STRIPS - 1) / 2) * W0, lam: mLam, offL: mL, offR: mR };
    strips.add(row);
    stripRows.push(row);
  }

  // Slitting lines (lengthwise): fine electric-blue cuts, drawn as they run
  const slitMat = blueLine(1);
  const slits = [];
  for (let i = 1; i < STRIPS; i++) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(1, 0.012, 0.004), slitMat);
    m.userData.y = (i - STRIPS / 2) * W0;
    strips.add(m);
    slits.push(m);
  }
  // Cutting-head glow
  const glowTex = (() => {
    const cv = document.createElement('canvas'); cv.width = cv.height = 64;
    const g = cv.getContext('2d');
    const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, 'rgba(235,242,255,1)'); gr.addColorStop(0.22, 'rgba(91,143,255,0.85)'); gr.addColorStop(1, 'rgba(47,107,234,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
    const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; return t;
  })();
  const headMat = new THREE.SpriteMaterial({ map: glowTex, transparent: true, depthWrite: false, toneMapped: false });
  const heads = [];
  const mkHead = () => { const s = new THREE.Sprite(headMat); s.scale.setScalar(0.22); scene.add(s); heads.push(s); return s; };

  // Mitre cut lines (45°) – one per lamination end
  const mitreMat = blueLine(1);
  const mitreLines = [];
  stripRows.forEach((row) => {
    for (const end of [-1, 1]) {
      const m = new THREE.Mesh(new THREE.BoxGeometry(1, 0.012, 0.004), mitreMat);
      m.userData = { end, len: W0 * Math.SQRT2 };
      row.add(m);
      mitreLines.push(m);
    }
  });
  slits.forEach(mkHead);
  mitreLines.forEach(mkHead);

  // 45° angle mark on the front lamination's right end (a drawn arc, no text)
  const dim = new THREE.Group();
  {
    const mat = new THREE.MeshBasicMaterial({ color: BRAND.blue, transparent: true, toneMapped: false, depthWrite: false, side: THREE.DoubleSide });
    const arc = new THREE.Mesh(new THREE.RingGeometry(0.47, 0.49, 48, 1, (3 * Math.PI) / 4, Math.PI / 4), mat);
    const ext = new THREE.Mesh(new THREE.PlaneGeometry(0.8, 0.01), mat);
    ext.position.x = -0.4;
    dim.add(arc, ext);
    dim.userData.mat = mat;
    dim.position.set(XB + W0 / 2, -W0 / 2, T_SHEET + 0.004);
  }
  stripRows[0].add(dim);

  /* ------------------------------------------------------------------ core */
  // turn (about vertical) → upend (about the bottom edge) → packets + frame
  const turn = new THREE.Group();
  const upend = new THREE.Group();
  turn.add(upend);
  scene.add(turn);
  const PIVOT_Z = (CORE.yokeY[1] + 0.475) / 2; // half the core height
  turn.position.set(0, 0, PIVOT_Z);

  const widths = mobile ? [0.95, 0.7] : [0.95, 0.85, 0.7, 0.5];
  const packets = cruciform(CORE.D, widths);
  const stackHalf = packets[packets.length - 1].z1;
  const zTop = stackHalf * 2;
  const layerT = mobile ? 0.034 : 0.0175;
  const offsets = stepOffsets(5, 0.05);
  const coreMeshes = [];
  let layerIndex = 0;
  packets.forEach((pk, pi) => {
    const n = Math.max(1, Math.round((pk.z1 - pk.z0) / layerT));
    const t = (pk.z1 - pk.z0) / n;
    const byPiece = {};
    for (let k = 0; k < n; k++) {
      const o = offsets[layerIndex % offsets.length];
      const z = pk.z0 + k * t + stackHalf;
      for (const piece of corePieces({ w: pk.w, o, gap: 0.014, holeSeg: mobile ? 14 : 24 })) {
        (byPiece[piece.id] ||= []).push({ poly: piece.poly, holes: piece.holes, z, t: t * 0.82, layer: layerIndex, dir: piece.dir });
      }
      layerIndex++;
    }
    for (const [id, items] of Object.entries(byPiece)) {
      const mesh = shadowed(new THREE.Mesh(extrudeLaminations(items), steel));
      const dir = { 'limb-l': [-1, 0], 'limb-r': [1, 0], 'limb-c': [0, 1], 'yoke-b': [0, -1], 'yoke-t': [0, 1] }[id];
      mesh.userData = { pi, id, dir };
      upend.add(mesh);
      coreMeshes.push(mesh);
    }
  });
  uniforms.uLayerMid.value = layerIndex / 2;

  // Where each of the four cut laminations goes in the core (strips-local
  // coordinates; the core lies flat under the strips with its bottom yoke
  // nearest the camera): two yokes, two outer limbs.
  const [cy1, cy2] = CORE.yokeY;
  const LAM_TARGETS = [
    { x: 0, y: cy1 - PIVOT_Z, rot: 0, len: (CORE.limbX[2] - CORE.limbX[0] + W0) / (XB - XA + W0) },
    { x: CORE.limbX[0], y: 0, rot: -Math.PI / 2, len: (cy2 - cy1 + W0) / (XB - XA + W0) },
    { x: CORE.limbX[2], y: 0, rot: Math.PI / 2, len: (cy2 - cy1 + W0) / (XB - XA + W0) },
    { x: 0, y: cy2 - PIVOT_Z, rot: Math.PI, len: (CORE.limbX[2] - CORE.limbX[0] + W0) / (XB - XA + W0) },
  ];

  /* ---------------------------------------------------------- clamp frame */
  const frame = buildFrame({ zT: zTop, mobile });
  upend.add(frame.group);

  /* ---------------------------------------------------------------- camera */
  // [p, position, target]. A Catmull-Rom path runs through the keys, so the
  // camera glides through each one instead of stopping at it.
  const KEYS = [
    [0.0, [3.4, 1.0, 10.6], [3.4, 1.0, 0]],
    [0.155, [3.4, 1.0, 10.6], [3.4, 1.0, 0]],
    [0.215, [5.4, 2.4, 8.0], [3.4, 0.95, 0]],
    [0.31, [0.9, 6.4, 9.6], [0.1, 0, 0.3]],
    [0.37, [1.2, 7.6, 7.4], [0.6, 0, 0.2]],
    [0.445, [3.1, 3.9, 5.4], [1.7, 0, 1.9]],
    [0.505, [0.5, 6.6, 8.8], [0.2, 0, 1.2]],
    [0.57, [0.2, 10.4, 4.0], [0, 0, 0.1]],
    [0.63, [4.6, 4.8, 8.6], [0, 0.6, 0.8]],
    [0.71, [5.8, 3.4, 11.6], [0, 2.1, 2.0]],
    [0.8, [3.0, 3.7, 12.6], [0, 2.45, 2.0]],
    [0.9, [-3.8, 3.6, 13.8], [0, 1.9, 2.0]],
    [1.0, [-5.8, 3.3, 13.6], [0, 1.25, 2.0]],
  ];
  const holdEnd = 1; // keys[0..1] are a hold: keep that stretch still
  const camPath = new THREE.CatmullRomCurve3(KEYS.slice(holdEnd).map((k) => new THREE.Vector3(...k[1])), false, 'centripetal');
  const tgtPath = new THREE.CatmullRomCurve3(KEYS.slice(holdEnd).map((k) => new THREE.Vector3(...k[2])), false, 'centripetal');
  const tmpP = new THREE.Vector3(), tmpT = new THREE.Vector3(), tmpL = new THREE.Vector3();

  function placeCamera(p) {
    const ks = KEYS.slice(holdEnd);
    let i = 0;
    while (i < ks.length - 2 && p > ks[i + 1][0]) i++;
    const local = clamp((p - ks[i][0]) / (ks[i + 1][0] - ks[i][0]));
    // ease only the first and last legs (start and end of the move); glide through the rest
    const t = i === 0 ? smooth(local) * 0.5 + local * 0.5 : i === ks.length - 2 ? 1 - (1 - local) ** 2 : local;
    const u = (i + t) / (ks.length - 1);
    camPath.getPoint(u, tmpP);
    tgtPath.getPoint(u, tmpT);
    // portrait screens: back off so the subject still fits
    const aspect = size.w / size.h;
    if (aspect < 1.25) tmpP.sub(tmpT).multiplyScalar((1.25 / aspect) ** 0.8).add(tmpT);
    camera.position.copy(tmpP);
    camera.lookAt(tmpT);
    // portrait screens: sit the subject a little lower, nearer the visual centre
    if (size.w < size.h) camera.setViewOffset(size.w, size.h, 0, -size.h * 0.08, size.w, size.h);
    else camera.clearViewOffset();
    camera.updateMatrixWorld();

    // lights travel with the subject so the soft shadow and the rim stay in frame
    const dist = tmpP.distanceTo(tmpT);
    tmpL.copy(tmpT).setY(0);
    key.target.position.copy(tmpL);
    // a slow sweep of the key across the finished core, for a highlight that glides
    const sweep = smooth(seg(p, 0.86, 1)) * 1.1;
    key.position.set(tmpL.x - 3.6 * Math.cos(sweep) + 4.6 * Math.sin(sweep), 9, tmpL.z + 5.2 * Math.cos(sweep) + 3.6 * Math.sin(sweep));
    rim.target.position.copy(tmpL);
    rim.position.set(tmpL.x - 5, 7, tmpL.z - 8);
    pool.position.set(tmpL.x, -0.002, tmpL.z);
    const half = THREE.MathUtils.clamp(dist * 0.6, 3.5, 9);
    const sc = key.shadow.camera;
    if (sc.right !== half) { sc.left = -half; sc.right = half; sc.top = half; sc.bottom = -half; sc.updateProjectionMatrix(); }
  }

  /* ---------------------------------------------------------------- state */
  const size = { w: 1, h: 1 };
  const v3 = new THREE.Vector3();
  let coilFadeLast = -1;

  // Bare steel (coil, sheet) reflects the studio at reduced strength. three.js only
  // honours a material's own envMapIntensity when the material carries the envMap
  // itself, so these get it explicitly and follow the lights-up ramp by hand.
  const dimSteel = [coilMats[0], sheetMat, offcutMat, feedMat].map((m) => {
    const base = m.envMapIntensity;
    m.envMap = envTex;
    return { m, base };
  });

  function setLights(level) {
    for (const d of dimSteel) d.m.envMapIntensity = d.base * level * LIGHT.env;
    key.intensity = LIGHT.key * level;
    rim.intensity = LIGHT.rim * level;
    fill.intensity = LIGHT.fill * level;
    scene.environmentIntensity = LIGHT.env * level;
    poolMat.opacity = level;
    floorMat.opacity = 0.6 * level;
  }

  function update(p) {
    /* lights up: the M (HTML) dissolves into the coil's end face */
    const lights = smooth(seg(p, 0.06, 0.13));
    setLights(lights);
    // the coil and sheet chapters are lit lower, so bare steel stays dark and metallic;
    // the key comes up to full for the painted frame
    key.intensity *= lerp(0.5, 1, smooth(seg(p, 0.5, 0.62)));
    // the M collapses into the bore as a flash of the brand's blue
    const sp = Math.sin(Math.PI * seg(p, 0.085, 0.16));
    spark.intensity = 4 * sp * sp;
    spark.position.set(XS1, R, CW / 2 + 0.7);

    /* coil: rolls left laying the sheet, then rolls away */
    const roll = easeInOut(seg(p, 0.22, 0.31));
    const away = easeInOut(seg(p, 0.355, 0.42));
    const coilX = lerp(XS1, XS0, roll) - away * 3.2;
    coil.visible = away < 1;
    coil.position.set(coilX, R + 0.002, 0);
    // a slow turn while it waits; rolling without slipping: angle = distance / radius
    // winding: wraps build outward from the bore while the strip feeds in
    const wind = easeInOut(seg(p, 0.075, 0.16));
    const curR = lerp(r + 0.015, R, wind);
    coil.userData.outer.scale.set(curR / R, 1, curR / R);
    coil.userData.endMat.userData.wind.value = curR + 0.001;
    feed.visible = wind > 0 && wind < 1;
    feed.position.set(0, curR + 0.002, 0);
    feed.scale.x = Math.max(0.0001, 1 - wind); // the tail runs onto the coil as it finishes
    coil.userData.spin.rotation.z = wind * 9 + seg(p, 0.16, 0.21) * 0.6 + (XS1 - coilX) / R;
    const coilFade = 1 - smooth(seg(p, 0.375, 0.42));
    if (coilFade !== coilFadeLast) {
      coilFadeLast = coilFade;
      for (const m of coilMats) { m.transparent = coilFade < 1; m.opacity = coilFade; }
    }

    /* sheet */
    strips.visible = roll > 0 && p < 0.64;
    clip.constant = -Math.min(coilX, XS1 - 0.001);
    const slit = seg(p, 0.305, 0.35);
    const split = easeInOut(seg(p, 0.345, 0.38));
    slits.forEach((m, k) => {
      const t = clamp(slit * 1.25 - k * 0.12);
      m.visible = t > 0 && split < 1;
      const len = (XS1 - XS0) * t;
      m.scale.x = Math.max(0.0001, len);
      m.position.set(XS0 + len / 2, m.userData.y, T_SHEET + 0.003);
      slitMat.opacity = 1 - split;
      const head = heads[k];
      head.visible = t > 0 && t < 1;
      if (head.visible) { v3.set(XS0 + len, m.userData.y, T_SHEET + 0.01); strips.localToWorld(v3); head.position.copy(v3); }
    });
    const gapGrow = split * 0.42;
    stripRows.forEach((row, k) => { row.position.y = row.userData.baseY + (k - (STRIPS - 1) / 2) * gapGrow; });

    /* mitre cuts */
    const cut = seg(p, 0.39, 0.45);
    const fall = easeOut(seg(p, 0.44, 0.5));
    mitreLines.forEach((m, k) => {
      const row = Math.floor(k / 2);
      const t = clamp(cut * 1.6 - row * 0.18 - (k % 2) * 0.06);
      const { end, len } = m.userData;
      // from the long-edge corner (y = -W/2) towards the short edge, at 45°
      const x0 = end > 0 ? XB + W0 / 2 : XA - W0 / 2;
      const ang = end > 0 ? (3 * Math.PI) / 4 : Math.PI / 4;
      const l = len * t;
      m.visible = t > 0 && fall < 1;
      m.scale.x = Math.max(0.0001, l);
      m.rotation.z = ang;
      m.position.set(x0 + (Math.cos(ang) * l) / 2, -W0 / 2 + (Math.sin(ang) * l) / 2, T_SHEET + 0.003);
      mitreMat.opacity = 1 - fall;
      const head = heads[slits.length + k];
      head.visible = t > 0 && t < 1;
      if (head.visible) { v3.set(x0 + Math.cos(ang) * l, -W0 / 2 + Math.sin(ang) * l, T_SHEET + 0.01); stripRows[row].localToWorld(v3); head.position.copy(v3); }
    });
    stripRows.forEach((row) => {
      row.userData.offL.position.set(-fall * 0.9, 0, 0);
      row.userData.offR.position.set(fall * 0.9, 0, 0);
      row.userData.offL.visible = row.userData.offR.visible = fall < 1;
    });
    offcutMat.opacity = 1 - fall;

    const dimOn = smooth(seg(p, 0.43, 0.45)) * (1 - smooth(seg(p, 0.47, 0.49)));
    dim.visible = dimOn > 0;
    dim.userData.mat.opacity = dimOn;

    /* the four laminations become the first layer of the core: each glides,
       turns and rises to its place, the packets stack in beneath them */
    const form = easeInOut(seg(p, 0.5, 0.565));
    const merge = smooth(seg(p, 0.6, 0.625));
    stripRows.forEach((row, k) => {
      const tg = LAM_TARGETS[k];
      const lam = row.userData.lam;
      const t = clamp(form * 1.25 - k * 0.08);
      const e = easeInOut(t);
      lam.position.set(tg.x * e, (tg.y - row.position.y) * e, (zTop + 0.012) * easeOut(clamp(form * 1.6 - k * 0.1)));
      lam.rotation.z = tg.rot * e;
      lam.scale.x = lerp(1, tg.len, e);
      lam.visible = merge < 1;
    });
    sheetMat.transparent = merge > 0;
    sheetMat.opacity = 1 - merge;

    /* core: stacking */
    const stack = seg(p, 0.54, 0.615);
    const nP = packets.length;
    coreMeshes.forEach((m) => {
      const { pi, dir } = m.userData;
      const t = clamp((stack - (pi / nP) * 0.72) / 0.28);
      m.visible = t > 0;
      const e = 1 - easeOut(t);
      m.position.set(dir[0] * e * 1.3, dir[1] * e * 1.3, e * 0.2);
    });

    /* core: stood up, then raised onto its feet; a slow turn at the end */
    const up = easeInOut(seg(p, 0.625, 0.695));
    upend.rotation.x = (-Math.PI / 2) * (1 - up);
    upend.position.z = -stackHalf * up; // turn about the middle of the stack once upright
    turn.position.y = FRAME.lift * easeInOut(seg(p, 0.7, 0.745));
    turn.rotation.y = lerp(0, 0.2, smooth(seg(p, 0.8, 1)));

    /* clamping frame */
    const arrive = (g, t, from) => {
      g.visible = t > 0;
      if (!g.visible) return;
      const e = easeOut(t);
      const { home } = g.userData;
      g.position.set(lerp(from.x, home.x, e), lerp(from.y, home.y, e), lerp(from.z, home.z, e));
    };
    frame.feet.forEach((g, i) => {
      const { home } = g.userData;
      arrive(g, clamp(seg(p, 0.715, 0.765) * 1.3 - i * 0.08), v3.set(home.x + Math.sign(home.x) * 7, home.y, home.z));
    });
    frame.beams.forEach((g) => {
      const { home, which, front } = g.userData;
      const t = which === 'bottom'
        ? clamp(seg(p, 0.73, 0.785) * 1.2 - (front ? 0.2 : 0))
        : clamp(seg(p, 0.765, 0.82) * 1.2 - (front ? 0.2 : 0));
      // bottom clamps slide in from the sides, top clamps drop in from above
      const from = which === 'bottom' ? v3.set(front ? -8 : 8, home.y, 0) : v3.set(0, home.y + 5.5, 0);
      arrive(g, t, from);
    });
    frame.bolts.forEach((g, i) => {
      const { home } = g.userData;
      arrive(g, clamp(seg(p, 0.805, 0.845) * 1.3 - i * 0.07), v3.set(home.x, home.y, home.z + 1.4));
    });
    frame.ties.forEach((g, i) => {
      const { home } = g.userData;
      arrive(g, clamp(seg(p, 0.815, 0.855) * 1.3 - i * 0.07), v3.set(home.x, home.y, home.z + 1.4));
    });
    frame.rods.forEach((g) => {
      const { home, nuts, k } = g.userData;
      arrive(g, clamp(seg(p, 0.835, 0.885) * 1.5 - (k % 4) * 0.1 - (k >= 4 ? 0.12 : 0)), v3.set(home.x, home.y + 6, home.z));
      // nuts run down the thread and seat
      const tn = easeOut(clamp(seg(p, 0.875, 0.915) * 1.4 - (k % 4) * 0.08));
      for (const nt of nuts) {
        nt.n.position.y = nt.home + nt.dir * (1 - tn) * 0.22;
        nt.n.rotation.y = (1 - tn) * 7;
        nt.wsh.position.y = nt.wHome + nt.dir * (1 - tn) * 0.18;
      }
    });
    arrive(frame.lug, seg(p, 0.89, 0.93), v3.set(0, 3.2, 0));

    placeCamera(p);
    renderer.render(scene, camera);
  }

  /** Screen position and radius (CSS px) of the coil's end face at progress p, for lining up the M. */
  function coilFace(p = 0.1) {
    placeCamera(p);
    const c = new THREE.Vector3(XS1, R, CW / 2).project(camera);
    const e = new THREE.Vector3(XS1, R + R, CW / 2).project(camera);
    return {
      x: (c.x * 0.5 + 0.5) * size.w,
      y: (-c.y * 0.5 + 0.5) * size.h,
      r: Math.abs(e.y - c.y) * 0.5 * size.h,
    };
  }

  function resize(w, h) {
    size.w = Math.max(1, w); size.h = Math.max(1, h);
    renderer.setSize(size.w, size.h, false);
    camera.aspect = size.w / size.h;
    camera.updateProjectionMatrix();
  }

  function setPixelRatio(ratio) {
    renderer.setPixelRatio(ratio);
    renderer.setSize(size.w, size.h, false);
  }

  function dispose() {
    disposeTree(scene);
    frame.dispose();
    glowTex.dispose();
    poolTex.dispose();
    headMat.dispose();
    envTex.dispose();
    releaseShared();
    renderer.dispose();
    renderer.forceContextLoss();
  }

  // Warm-up: compile every shader (including the shadow passes) now, with
  // everything visible, so nothing stalls the first time it appears mid-scroll.
  scene.traverse((o) => { o.visible = true; });
  setLights(1);
  for (const m of coilMats) { m.transparent = true; }
  sheetMat.transparent = true;
  placeCamera(0.6);
  renderer.setSize(64, 64, false);
  renderer.render(scene, camera);
  coilFadeLast = -1;

  return { update, resize, dispose, coilFace, setPixelRatio, pixelRatio: () => renderer.getPixelRatio() };
}
