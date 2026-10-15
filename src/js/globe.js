/**
 * About transition: a dotted-steel Earth that turns to India and dollies into
 * Bengaluru, then dissolves into the page. Plays only when the visitor arrived
 * by clicking an About link (main.js sets the flag, the head script sets
 * html.globe-intro and window.__revealGo). ~1.8 s, no text.
 *
 * Pacing: one continuous move. Distance is eased in log space, so the zoom
 * reads at a constant perceived speed instead of lurching at the end; the turn
 * finishes early (by 70%) so the last stretch is a straight push-in.
 */
import * as THREE from 'three';

const DURATION = 2600;
const BLR = [12.9716, 77.5946];
const START = [14, 38];

const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const easeOut = (t) => 1 - (1 - t) ** 3;
const seg = (p, a, b) => Math.min(1, Math.max(0, (p - a) / (b - a)));

/** lat/lon (deg) -> unit vector; lon 0 faces +z, north is +y. */
function dir(lat, lon, out = new THREE.Vector3()) {
  const la = (lat * Math.PI) / 180, lo = (lon * Math.PI) / 180;
  return out.set(Math.cos(la) * Math.sin(lo), Math.sin(la), Math.cos(la) * Math.cos(lo));
}

async function dots(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(url);
  return new Int16Array(await res.arrayBuffer());
}

function pointsGeometry(world, india) {
  const n = world.length / 2 + india.length / 2;
  const pos = new Float32Array(n * 3);
  const grp = new Float32Array(n);
  let k = 0;
  const v = new THREE.Vector3();
  const add = (arr, g) => {
    for (let i = 0; i < arr.length; i += 2) {
      dir(arr[i] / 100, arr[i + 1] / 100, v);
      pos.set([v.x, v.y, v.z], k * 3);
      grp[k++] = g;
    }
  };
  add(world, 0);
  add(india, 1);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('aGroup', new THREE.BufferAttribute(grp, 1));
  return g;
}

const dotVert = /* glsl */ `
  attribute float aGroup;
  uniform float uPix, uIndia, uWorldSize, uIndiaSize, uMaxPx, uMinPx;
  varying float vGroup, vFace;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vFace = dot(normalize(normalMatrix * position), normalize(-mv.xyz));
    vGroup = aGroup;
    float s = mix(uWorldSize, uIndiaSize, aGroup);
    // India never drops below a visible dot, so it reads as a lit shape from afar
    gl_PointSize = clamp(s * uPix / -mv.z, mix(0.0, uMinPx, aGroup), uMaxPx);
    gl_Position = projectionMatrix * mv;
  }`;
const dotFrag = /* glsl */ `
  uniform float uIndia, uFade;
  uniform vec3 uSteel, uBlue, uBlueHi;
  varying float vGroup, vFace;
  void main() {
    vec2 c = gl_PointCoord - 0.5;
    float d = length(c);
    if (d > 0.5) discard;
    float edge = smoothstep(0.5, 0.32, d);
    float face = smoothstep(-0.05, 0.35, vFace);            // limb fades into the dark
    vec3 india = mix(uSteel, mix(uBlue, uBlueHi, 0.55), uIndia);
    vec3 col = mix(uSteel, india, vGroup);
    float a = mix(0.78, mix(0.78, 1.0, uIndia), vGroup) * edge * face * uFade;
    gl_FragColor = vec4(col, a);
  }`;
const rimVert = /* glsl */ `
  varying float vRim;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vRim = 1.0 - abs(dot(normalize(normalMatrix * normal), normalize(-mv.xyz)));
    gl_Position = projectionMatrix * mv;
  }`;
const rimFrag = /* glsl */ `
  uniform vec3 uBlue; uniform float uFade;
  varying float vRim;
  void main() { gl_FragColor = vec4(uBlue, pow(vRim, 3.0) * 0.55 * uFade); }`;

/* Borders as thin glowing walls standing on the surface: the 3D accent.
   position = unit direction; aV = 0 at the ground, 1 at the top edge. */
const wallVert = /* glsl */ `
  attribute float aV;
  uniform float uH;
  varying float vV, vFace;
  void main() {
    vec3 p = position * (1.0 + aV * uH);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vFace = dot(normalize(normalMatrix * position), normalize(-mv.xyz));
    vV = aV;
    gl_Position = projectionMatrix * mv;
  }`;
const wallFrag = /* glsl */ `
  uniform vec3 uColor; uniform float uOpacity;
  varying float vV, vFace;
  void main() {
    float face = smoothstep(-0.02, 0.2, vFace);
    float a = (vV * 0.35 + pow(vV, 10.0) * 0.9) * uOpacity * face; // faint curtain, bright crest
    gl_FragColor = vec4(uColor, a);
  }`;
const fillFrag = /* glsl */ `
  uniform vec3 uColor; uniform float uOpacity;
  varying float vV, vFace;
  void main() { gl_FragColor = vec4(uColor, uOpacity * smoothstep(-0.02, 0.2, vFace)); }`;

function wallGeometry(rings) {
  const pos = [], v = [], idx = [];
  const p = new THREE.Vector3();
  for (const ring of rings) {
    const base = pos.length / 3;
    ring.forEach(([lat, lon]) => {
      dir(lat, lon, p);
      pos.push(p.x, p.y, p.z, p.x, p.y, p.z);
      v.push(0, 1);
    });
    for (let i = 0; i < ring.length - 1; i++) {
      const a = base + i * 2;
      idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('aV', new THREE.Float32BufferAttribute(v, 1));
  g.setIndex(idx);
  return g;
}

/** A flat cap over a ring (lat/lon triangulated in 2D; fine for a city-sized area). */
function capGeometry(ring) {
  const pts = ring.slice(0, -1).map(([lat, lon]) => new THREE.Vector2(lon, lat));
  const tris = THREE.ShapeUtils.triangulateShape(pts, []);
  const pos = [], v = [], p = new THREE.Vector3();
  pts.forEach((q) => { dir(q.y, q.x, p); pos.push(p.x, p.y, p.z); v.push(1); });
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('aV', new THREE.Float32BufferAttribute(v, 1));
  g.setIndex(tris.flat());
  return g;
}

function borderLines(rings, r) {
  const pos = [], p = new THREE.Vector3();
  for (const ring of rings) for (let i = 0; i < ring.length - 1; i++) {
    dir(...ring[i], p); pos.push(p.x * r, p.y * r, p.z * r);
    dir(...ring[i + 1], p); pos.push(p.x * r, p.y * r, p.z * r);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  return g;
}

export async function playGlobe() {
  const root = document.documentElement;
  const veil = document.querySelector('.globe-veil');
  const done = () => {
    root.classList.remove('globe-intro');
    veil?.remove();
    window.__revealGo?.();
  };
  if (!veil) return done();

  try {
    const [world, india, lines] = await Promise.all([
      dots('/globe/world.bin'), dots('/globe/india.bin'),
      fetch('/globe/lines.json').then((r) => { if (!r.ok) throw new Error('lines'); return r.json(); }),
    ]);
    const canvas = veil.querySelector('canvas');
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    renderer.setSize(innerWidth, innerHeight, false);
    renderer.setClearColor(0x06080d, 1);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, innerWidth / innerHeight, 0.01, 50);
    const C = (h) => new THREE.Color(h);

    // occluder: hides the far side's dots behind a near-black sphere
    scene.add(new THREE.Mesh(new THREE.SphereGeometry(0.996, 96, 64), new THREE.MeshBasicMaterial({ color: 0x080d18 })));

    const uniforms = {
      uPix: { value: innerHeight * dpr * 0.5 }, uMaxPx: { value: 7 * dpr }, uMinPx: { value: 2.2 * dpr }, uIndia: { value: 0 }, uFade: { value: 0 },
      uWorldSize: { value: 0.024 }, uIndiaSize: { value: 0.0072 },
      uSteel: { value: C('#aab3c6') }, uBlue: { value: C('#3169e3') }, uBlueHi: { value: C('#80a3ef') },
    };
    const pts = new THREE.Points(pointsGeometry(world, india), new THREE.ShaderMaterial({
      vertexShader: dotVert, fragmentShader: dotFrag, uniforms, transparent: true, depthWrite: false,
    }));
    scene.add(pts);

    const rimU = { uBlue: { value: C('#3169e3') }, uFade: { value: 0 } };
    scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.05, 96, 64), new THREE.ShaderMaterial({
      vertexShader: rimVert, fragmentShader: rimFrag, uniforms: rimU, transparent: true, depthWrite: false,
      side: THREE.BackSide, blending: THREE.AdditiveBlending,
    })));

    // borders: state lines (flat, faint), India and Karnataka as low walls, Bengaluru rising highest
    const wall = (rings, color, h) => {
      const u = { uColor: { value: C(color) }, uOpacity: { value: 0 }, uH: { value: h } };
      const m = new THREE.Mesh(wallGeometry(rings), new THREE.ShaderMaterial({
        vertexShader: wallVert, fragmentShader: wallFrag, uniforms: u, transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
      }));
      scene.add(m);
      return u;
    };
    const stateMat = new THREE.LineBasicMaterial({ color: C('#80a3ef'), transparent: true, opacity: 0, depthWrite: false });
    scene.add(new THREE.LineSegments(borderLines(lines.states, 1.0012), stateMat));
    const indiaWall = wall(lines.india, '#80a3ef', 0.006);
    const kaWall = wall(lines.karnataka, '#80a3ef', 0.0035);
    const blrWall = wall(lines.blr, '#a9c1f5', 0);
    const blrCapU = { uColor: { value: C('#3169e3') }, uOpacity: { value: 0 }, uH: { value: 0 } };
    scene.add(new THREE.Mesh(capGeometry(lines.blr[0]), new THREE.ShaderMaterial({
      vertexShader: wallVert, fragmentShader: fillFrag, uniforms: blrCapU, transparent: true, depthWrite: false, side: THREE.DoubleSide,
    })));

    // Bengaluru: a bright point and one expanding ring, lying on the surface
    const blr = dir(...BLR);
    const marker = new THREE.Group();
    marker.position.copy(blr).multiplyScalar(1.0065);
    marker.lookAt(blr.clone().multiplyScalar(2));
    const core = new THREE.Mesh(new THREE.CircleGeometry(1, 40), new THREE.MeshBasicMaterial({ color: 0xf4f6fa, transparent: true, opacity: 0, depthWrite: false }));
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.82, 1, 64), new THREE.MeshBasicMaterial({ color: 0x80a3ef, transparent: true, opacity: 0, depthWrite: false }));
    marker.add(core, ring);
    scene.add(marker);

    const onResize = () => {
      renderer.setSize(innerWidth, innerHeight, false);
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      uniforms.uPix.value = innerHeight * dpr * 0.5;
    };
    addEventListener('resize', onResize);

    const startDir = dir(...START);
    const q0 = new THREE.Quaternion();
    const q1 = new THREE.Quaternion().setFromUnitVectors(startDir, blr);
    const qa = new THREE.Quaternion();
    const camDir = new THREE.Vector3();
    // start far enough that the whole globe (plus rim) fits the narrower screen side
    const halfFov = Math.tan((camera.fov * Math.PI) / 360);
    const far = Math.max(3.7, 1.22 / (halfFov * Math.min(1, camera.aspect)));
    const near = 1.06;
    // the last stretch tilts to look across the surface (south of the city, facing north),
    // so the raised borders read as 3D instead of a flat map
    const north = new THREE.Vector3(0, 1, 0);
    const south = north.clone().addScaledVector(blr, -north.dot(blr)).normalize().negate();
    const target = new THREE.Vector3();

    const t0 = performance.now();
    await new Promise((resolve) => {
      const frame = (now) => {
        // window.__globeP (0..1) freezes the film at a point: used for frame review
        const held = typeof window.__globeP === 'number';
        const p = held ? window.__globeP : Math.min(1, (now - t0) / DURATION);
        // turn toward Bengaluru, settled by 70% so the end is a straight push
        qa.slerpQuaternions(q0, q1, easeInOut(seg(p, 0, 0.7)));
        camDir.copy(startDir).applyQuaternion(qa);
        // constant perceived zoom: ease the distance in log space
        const z = easeInOut(seg(p, 0.02, 1));
        const dist = Math.exp(Math.log(far) + (Math.log(near) - Math.log(far)) * z);
        const tilt = easeInOut(seg(p, 0.55, 1));
        camera.position.copy(camDir).multiplyScalar(dist).addScaledVector(south, (dist - 1) * 0.75 * tilt);
        // aim moves from the globe's centre onto the city in step with the turn, so the city stays centred
        target.copy(blr).multiplyScalar(easeInOut(seg(p, 0, 0.7)));
        camera.up.copy(north);
        camera.lookAt(target);

        const fadeIn = easeOut(seg(p, 0, 0.14));
        const fadeOut = 1 - easeInOut(seg(p, 0.84, 1));
        uniforms.uFade.value = fadeIn;
        rimU.uFade.value = fadeIn * (1 - seg(p, 0.55, 0.85));
        uniforms.uIndia.value = easeInOut(seg(p, 0.16, 0.46));
        stateMat.opacity = 0.32 * easeInOut(seg(p, 0.3, 0.55)) * (1 - 0.5 * seg(p, 0.75, 0.95));
        indiaWall.uOpacity.value = easeInOut(seg(p, 0.22, 0.48));
        kaWall.uOpacity.value = easeInOut(seg(p, 0.42, 0.66));
        // Bengaluru: the boundary rises out of the ground, then fills
        const rise = easeOut(seg(p, 0.58, 0.85));
        blrWall.uOpacity.value = easeOut(seg(p, 0.56, 0.68));
        blrWall.uH.value = 0.0045 * rise;
        blrCapU.uH.value = 0.0045 * rise;
        blrCapU.uOpacity.value = 0.45 * easeOut(seg(p, 0.66, 0.86));
        // marker size tracks the camera so it reads the same on screen
        const s = (dist - 1) * 0.008;
        core.scale.setScalar(s);
        core.material.opacity = 0; // the city's own boundary marks the place
        const r = seg(p, 0.66, 0.97);
        ring.scale.setScalar(s * (3.2 + easeOut(r) * 6));
        ring.material.opacity = r > 0 ? (1 - r) * 0.7 : 0;
        veil.style.opacity = String(fadeOut);
        // the page's text starts rising while the veil dissolves
        if (p >= 0.88 && window.__revealGo) { window.__revealGo(); window.__revealGo = null; }

        renderer.render(scene, camera);
        if (p < 1 || held) requestAnimationFrame(frame); else resolve();
      };
      requestAnimationFrame(frame);
    });

    removeEventListener('resize', onResize);
    renderer.dispose();
  } catch (err) {
    console.warn('[globe] skipped', err);
  }
  done();
}
