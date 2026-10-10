/**
 * Scroll intro: a transformer core assembling itself from a coil of steel.
 * Pure animation, no text: the story is told by the steel alone.
 *
 * Everything is a pure function of scroll progress p ∈ [0, 1]: update(p)
 * places every object from scratch, so scrubbing backwards reverses exactly.
 * The scene renders on demand (only when p or the size changes).
 *
 * Look: a light, seamless studio. Physically based brushed steel (the grain
 * follows each lamination's rolling direction, with the faint sheen of its
 * insulation coating), a studio environment for reflections, and one soft
 * shadow-casting key light. At the end the studio goes dark for the logo.
 *
 * Beats (keep in sync with ./index.js):
 *   0.00–0.22  coil, turning slowly in the studio
 *   0.22–0.38  the coil rolls out a sheet; slitting into strips
 *   0.38–0.52  45° mitre cuts; E, I and strip profiles
 *   0.52–0.70  step-lap: exploded corner (one step cycle), packets stacked
 *   0.70–0.86  the core is stood up and turns
 *   0.86–1.00  lights down: the core resolves to its outline, logo (HTML)
 */
import * as THREE from 'three';
import {
  CORE, corePieces, coreOutline, cruciform, stepOffsets, eShape, iShape, stripShape,
  clipHalfPlane, holesLeftOf, clamp, smooth, seg, lerp,
} from '../lamination/geometry.js';
import {
  extrudeLaminations, createSteelUniforms, createSteelMaterial, studioEnvironment,
  brushedTexture, disposeTree, releaseShared, BRAND,
} from '../lamination/three-kit.js';

const easeOut = (t) => 1 - (1 - t) ** 3;
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

export const STUDIO = new THREE.Color('#eef1f5'); // matches --stage in main.css
const NIGHT = new THREE.Color('#000000');

export function createIntroScene(canvas, { mobile = false } = {}) {
  /* ---------------------------------------------------------------- setup */
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, mobile ? 1.5 : 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.localClippingEnabled = true;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = mobile ? THREE.PCFShadowMap : THREE.VSMShadowMap;

  const scene = new THREE.Scene();
  scene.background = STUDIO.clone();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 80);
  const envTex = studioEnvironment(renderer);
  scene.environment = envTex;
  scene.environmentIntensity = 0.9;
  scene.environmentRotation.set(0, -0.6, 0);

  // One soft key light that casts shadows, following the subject; a gentle fill.
  const key = new THREE.DirectionalLight(0xffffff, 2.6);
  key.castShadow = true;
  key.shadow.mapSize.set(mobile ? 1024 : 2048, mobile ? 1024 : 2048);
  key.shadow.bias = -0.0004;
  key.shadow.normalBias = 0.02;
  key.shadow.radius = mobile ? 3 : 9;
  key.shadow.blurSamples = 16;
  key.shadow.camera.near = 0.5;
  key.shadow.camera.far = 40;
  scene.add(key, key.target);
  const fill = new THREE.HemisphereLight(0xffffff, 0xd3d8e0, 0.55);
  scene.add(fill);

  // Seamless floor: invisible except for the shadows it receives.
  const floorMat = new THREE.ShadowMaterial({ color: 0x0a1532, opacity: 0.2 });
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  const shadowed = (m, receive = true) => { m.castShadow = true; m.receiveShadow = receive; return m; };

  const uniforms = createSteelUniforms();
  const steel = createSteelMaterial(uniforms);

  const W0 = 0.95; // widest lamination = strip width
  const blueLine = (opacity = 1) => new THREE.MeshBasicMaterial({
    color: BRAND.blue, transparent: true, opacity, toneMapped: false, depthWrite: false,
  });

  /* ----------------------------------------------------------------- coil */
  const coil = new THREE.Group();
  const R = 1.0, r = 0.42, CW = W0 * 4; // coil radius, bore, width (= 4 strips)
  {
    const tex = brushedTexture().clone();
    tex.repeat.set(6, 1);
    tex.needsUpdate = true;
    const outerMat = new THREE.MeshPhysicalMaterial({
      color: 0xb3bac4, metalness: 0.9, roughness: 0.32, roughnessMap: tex,
      anisotropy: 0.7, clearcoat: 0.3, clearcoatRoughness: 0.3,
    });
    const outer = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(R, R, CW, 160, 1, true), outerMat));
    outer.rotation.x = Math.PI / 2;
    const bore = new THREE.Mesh(
      new THREE.CylinderGeometry(r, r, CW, 64, 1, true),
      new THREE.MeshStandardMaterial({ color: 0x3a414c, metalness: 0.6, roughness: 0.55, side: THREE.BackSide }),
    );
    bore.rotation.x = Math.PI / 2;
    // end faces: the wraps of strip, as fine concentric rings
    const c = document.createElement('canvas');
    c.width = c.height = mobile ? 1024 : 2048;
    const g = c.getContext('2d');
    const S = c.width / 2;
    g.fillStyle = '#a3abb7'; g.fillRect(0, 0, c.width, c.height);
    const wraps = mobile ? 70 : 140;
    for (let i = 0; i <= wraps; i++) {
      const rr = (r / R + (1 - r / R) * (i / wraps)) * S;
      g.beginPath(); g.arc(S, S, rr, 0, Math.PI * 2);
      g.strokeStyle = i % 2 ? 'rgba(40,46,58,0.45)' : 'rgba(235,240,248,0.35)';
      g.lineWidth = Math.max(1, (S / wraps) * 0.3);
      g.stroke();
    }
    const ringTex = new THREE.CanvasTexture(c);
    ringTex.colorSpace = THREE.SRGBColorSpace;
    ringTex.anisotropy = 8;
    const endMat = new THREE.MeshPhysicalMaterial({ map: ringTex, metalness: 0.55, roughness: 0.42, clearcoat: 0.2, clearcoatRoughness: 0.4 });
    const endA = shadowed(new THREE.Mesh(new THREE.RingGeometry(r, R, 160, 1), endMat));
    endA.position.z = CW / 2;
    const endB = endA.clone();
    endB.rotation.y = Math.PI;
    endB.position.z = -CW / 2;
    const spin = new THREE.Group();
    spin.add(outer, bore, endA, endB);
    coil.add(spin);
    coil.userData.spin = spin;
  }
  scene.add(coil);

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
  const sheetMat = createSteelMaterial(uniforms);
  sheetMat.clippingPlanes = [clip];
  sheetMat.clipShadows = true;
  const offcutMat = createSteelMaterial(uniforms);
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

  /* ---------------------------------------------------- E, I, strip profiles */
  const profiles = new THREE.Group();
  profiles.rotation.x = -Math.PI / 2;
  scene.add(profiles);
  const profileMat = createSteelMaterial(uniforms);
  profileMat.transparent = true;
  const profileItems = [];
  {
    const a = 0.5;
    const stack = (poly, holes, n = 5) => Array.from({ length: n }, (_, k) => ({ poly, holes, z: k * 0.035, t: 0.028, dir: 'x', layer: 0 }));
    const e = shadowed(new THREE.Mesh(extrudeLaminations(stack(eShape(a))), profileMat));
    const i = shadowed(new THREE.Mesh(extrudeLaminations(stack(iShape(a))), profileMat));
    const s = stripShape({ length: 2.2, width: 0.36, holes: 3, holeR: 0.06 });
    const st = shadowed(new THREE.Mesh(extrudeLaminations(stack(s.outer, s.holes)), profileMat));
    // in front of the laminations (nearer the camera); tighter on narrow screens
    if (mobile) {
      e.position.set(-1.7, -3.95, 0);
      i.position.set(0.3, -3.5, 0);
      st.position.set(-1.1, -4.8, 0);
    } else {
      e.position.set(0.0, -4.0, 0);
      i.position.set(1.9, -3.55, 0);
      st.position.set(-2.7, -3.65, 0);
    }
    profiles.add(e, i, st);
    profileItems.push(e, i, st);
  }

  /* ------------------------------------------------------------------ core */
  // turn (about vertical) → upend (about the bottom edge) → packets
  const turn = new THREE.Group();
  const upend = new THREE.Group();
  turn.add(upend);
  scene.add(turn);
  const PIVOT_Z = (CORE.yokeY[1] + 0.475) / 2; // half the core height
  turn.position.set(0, 0, PIVOT_Z);

  const widths = mobile ? [0.95, 0.7] : [0.95, 0.85, 0.7, 0.5];
  const packets = cruciform(CORE.D, widths);
  const stackHalf = packets[packets.length - 1].z1;
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
      mesh.visible = false;
      upend.add(mesh);
      coreMeshes.push(mesh);
    }
  });
  uniforms.uLayerMid.value = layerIndex / 2;

  // Step-lap demonstrator: one cycle of corner laminations, fanned apart so
  // each layer's joint position can be seen, then pressed onto the core.
  const demo = new THREE.Group();
  const DEMO_T = 0.03;
  const demoPlates = [];
  const demoMat = createSteelMaterial(uniforms);
  demoMat.transparent = true;
  const demoLineMat = blueLine(1);
  {
    const w = W0;
    const ox = CORE.limbX[0] - w / 2, oy = CORE.yokeY[0] - w / 2;
    stepOffsets(5, 0.075).forEach((o, k) => {
      const plate = new THREE.Group();
      const items = [];
      for (const pc of corePieces({ w, o, gap: 0.016, holeSeg: 32 })) {
        if (pc.id === 'limb-l') items.push({ poly: clipHalfPlane(pc.poly, 0, 1, 1.95), z: 0, t: DEMO_T, dir: 'y' });
        if (pc.id === 'yoke-b') items.push({ poly: clipHalfPlane(pc.poly, 1, 0, -0.62), holes: holesLeftOf(pc.holes, -0.62), z: 0, t: DEMO_T, dir: 'x' });
      }
      plate.add(shadowed(new THREE.Mesh(extrudeLaminations(items), demoMat)));
      // this layer's 45° joint, picked out in electric blue
      const ax = ox + Math.max(0, -o), ay = oy + Math.max(0, -o) + o;
      const bx = ox + w, by = oy + w + o;
      const bar = new THREE.Mesh(new THREE.BoxGeometry(Math.hypot(bx - ax, by - ay), 0.022, 0.003), demoLineMat);
      bar.position.set((ax + bx) / 2, (ay + by) / 2, DEMO_T + 0.003);
      bar.rotation.z = Math.PI / 4;
      plate.add(bar);
      plate.visible = false;
      demo.add(plate);
      demoPlates.push(plate);
    });
  }
  upend.add(demo);

  // Core outline (front face), drawn in light for the logo moment
  const outlineMat = new THREE.LineBasicMaterial({ color: BRAND.blueGlow, transparent: true, opacity: 0, toneMapped: false, depthTest: false });
  {
    const o = coreOutline({ w: W0 });
    for (const loop of [o.outer, ...o.windows]) {
      const pts = loop.map(([x, y]) => new THREE.Vector3(x, y, stackHalf * 2 + 0.01));
      const line = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), outlineMat);
      line.renderOrder = 10;
      upend.add(line);
    }
  }

  /* ---------------------------------------------------------------- camera */
  // [p, position, target]
  const KEYS = [
    [0.0, [2.6, 1.9, 10.4], [3.4, 1.0, 0]],
    [0.1, [3.6, 2.0, 9.2], [3.4, 1.0, 0]],
    [0.2, [5.4, 2.4, 8.0], [3.4, 0.95, 0]],
    // the roll: camera and coil share the same easing, so the coil drifts left
    // across the frame while the sheet it lays fills the right
    [0.22, [5.3, 2.7, 8.4], [3.1, 0.8, 0]],
    [0.31, [0.9, 6.4, 9.6], [0.1, 0, 0.3]],
    [0.37, [1.2, 7.6, 7.4], [0.6, 0, 0.2]],
    [0.445, [3.1, 3.9, 5.4], [1.7, 0, 1.9]],
    [0.505, [0.4, 5.6, 9.6], [0.2, 0, 2.4]],
    [0.58, [-0.3, 3.8, 4.5], [-1.5, 1.3, 1.25]],
    [0.64, [-0.45, 3.6, 4.2], [-1.55, 1.2, 1.25]],
    [0.7, [0.4, 4.6, 6.4], [-0.6, 0.5, 0.4]],
    [0.8, [0.6, 2.7, 11.4], [0, 1.95, 2.15]],
    [0.88, [0, 2.4, 11.6], [0, 2.0, 2.15]],
    [1.0, [0, 2.3, 13.2], [0, 2.0, 2.15]],
  ];
  const tmpP = new THREE.Vector3(), tmpT = new THREE.Vector3();
  function cameraAt(p) {
    let i = 0;
    while (i < KEYS.length - 2 && p > KEYS[i + 1][0]) i++;
    const [p0, a0, b0] = KEYS[i];
    const [p1, a1, b1] = KEYS[i + 1];
    const t = easeInOut(clamp((p - p0) / (p1 - p0)));
    tmpP.set(lerp(a0[0], a1[0], t), lerp(a0[1], a1[1], t), lerp(a0[2], a1[2], t));
    tmpT.set(lerp(b0[0], b1[0], t), lerp(b0[1], b1[1], t), lerp(b0[2], b1[2], t));
    // portrait screens: back off so the subject still fits
    const aspect = size.w / size.h;
    if (aspect < 1.25) tmpP.sub(tmpT).multiplyScalar((1.25 / aspect) ** 0.72).add(tmpT);
    camera.position.copy(tmpP);
    camera.lookAt(tmpT);
    // key light travels with the subject so its soft shadow stays in frame
    const dist = tmpP.distanceTo(tmpT);
    key.target.position.copy(tmpT).setY(0);
    key.position.copy(key.target.position).add(new THREE.Vector3(3.2, 9, 4.6));
    const half = THREE.MathUtils.clamp(dist * 0.6, 3.5, 9);
    const sc = key.shadow.camera;
    if (sc.right !== half) { sc.left = -half; sc.right = half; sc.top = half; sc.bottom = -half; sc.updateProjectionMatrix(); }
  }

  /* ---------------------------------------------------------------- state */
  const size = { w: 1, h: 1 };
  const v3 = new THREE.Vector3();
  const bg = new THREE.Color();

  function update(p) {
    /* coil: appears on the right, rolls left laying the sheet, then rolls away */
    const coilIn = 1; // on screen from the first frame: no empty studio
    const roll = easeInOut(seg(p, 0.22, 0.31));
    const away = easeInOut(seg(p, 0.355, 0.42));
    const coilX = lerp(XS1, XS0, roll) - away * 3.2;
    coil.visible = coilIn > 0 && away < 1;
    coil.scale.setScalar(lerp(0.9, 1, coilIn));
    coil.position.set(coilX, R + 0.002, 0);
    coil.rotation.y = lerp(-0.95, 0, smooth(seg(p, 0.0, 0.215)));
    // rolling without slipping: angle = distance / radius
    coil.userData.spin.rotation.z = seg(p, 0.0, 0.21) * 0.8 + (XS1 - coilX) / R;
    const coilFade = coilIn * (1 - smooth(seg(p, 0.375, 0.42)));
    coil.traverse((o) => { if (o.material) { o.material.transparent = coilFade < 1; o.material.opacity = coilFade; } });

    /* sheet */
    const sheetGone = smooth(seg(p, 0.515, 0.55));
    strips.visible = roll > 0 && sheetGone < 1;
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
    });
    offcutMat.opacity = 1 - fall;
    // laminations slide away towards the stacking table
    const lift = easeInOut(seg(p, 0.512, 0.55));
    stripRows.forEach((row, k) => { row.userData.lam.position.set(lift * (3.2 + k * 0.4), 0, lift * 0.15); });
    sheetMat.transparent = sheetGone > 0;
    sheetMat.opacity = 1 - sheetGone;

    const dimOn = smooth(seg(p, 0.43, 0.45)) * (1 - smooth(seg(p, 0.47, 0.49)));
    dim.visible = dimOn > 0;
    dim.userData.mat.opacity = dimOn;

    /* profiles */
    const profIn = easeOut(seg(p, 0.478, 0.505));
    const profOut = smooth(seg(p, 0.512, 0.545));
    profiles.visible = profIn > 0 && profOut < 1;
    profileMat.opacity = profIn * (1 - profOut);
    profileItems.forEach((m, k) => { m.position.z = lerp(-0.25, 0.0, clamp(profIn * 1.4 - k * 0.15)) + profOut * 0.4; });

    /* step-lap demonstrator */
    const fanIn = seg(p, 0.548, 0.6);
    const press = easeInOut(seg(p, 0.622, 0.645));
    const demoOut = smooth(seg(p, 0.645, 0.66));
    demo.visible = fanIn > 0 && demoOut < 1;
    const zTop = stackHalf * 2;
    demoPlates.forEach((pl, k) => {
      const t = easeOut(clamp(fanIn * 1.6 - k * 0.15));
      pl.visible = t > 0;
      const fanned = zTop + k * (DEMO_T + 0.26) + 0.12;
      const pressed = zTop + k * DEMO_T;
      pl.position.set(-(1 - t) * 0.9, -(1 - t) * 0.4, lerp(fanned + 1.4, lerp(fanned, pressed, press), t));
    });
    demoMat.opacity = 1 - demoOut;
    demoLineMat.opacity = 1 - Math.max(press * 0.6, demoOut);

    /* core: stacking */
    const stack = seg(p, 0.648, 0.7);
    const nP = packets.length;
    coreMeshes.forEach((m) => {
      const { pi, dir } = m.userData;
      const t = clamp((stack - (pi / nP) * 0.72) / 0.28);
      m.visible = t > 0;
      const e = 1 - easeOut(t);
      m.position.set(dir[0] * e * 1.3, dir[1] * e * 1.3, e * 0.2);
    });
    const demoGlow = smooth(seg(p, 0.57, 0.6)) * (1 - press);

    /* core: stood up, then a slow turn */
    const up = easeInOut(seg(p, 0.71, 0.8));
    upend.rotation.x = (-Math.PI / 2) * (1 - up);
    turn.rotation.y = lerp(0, -0.42, smooth(seg(p, 0.7, 0.8))) + lerp(0, 0.42, smooth(seg(p, 0.79, 0.9)));

    /* lights down for the logo: studio → black, steel dims, outline glows */
    const night = smooth(seg(p, 0.872, 0.9)); // a quick, clean lights-down
    bg.copy(STUDIO).lerp(NIGHT, night);
    scene.background.copy(bg);
    floorMat.opacity = 0.2 * (1 - night);
    key.intensity = 2.6 * (1 - night * 0.9);
    fill.intensity = 0.55 * (1 - night * 0.9);
    scene.environmentIntensity = 0.9 * (1 - night * 0.85);
    uniforms.uDim.value = 1 - night * 0.75;
    uniforms.uEdge.value = demoGlow * 0.9 + night * 0.6;
    outlineMat.opacity = smooth(seg(p, 0.875, 0.91));

    cameraAt(p);
    // portrait screens: sit the subject a little lower, nearer the visual centre
    if (size.w < size.h) camera.setViewOffset(size.w, size.h, 0, -size.h * 0.08, size.w, size.h);
    else camera.clearViewOffset();
    renderer.render(scene, camera);
  }

  function resize(w, h) {
    size.w = Math.max(1, w); size.h = Math.max(1, h);
    renderer.setSize(size.w, size.h, false);
    camera.aspect = size.w / size.h;
    camera.updateProjectionMatrix();
  }

  function dispose() {
    disposeTree(scene);
    glowTex.dispose();
    headMat.dispose();
    envTex.dispose();
    releaseShared();
    renderer.dispose();
    renderer.forceContextLoss();
  }

  return { update, resize, dispose };
}
