/**
 * About transition: a dotted-steel Earth that turns to India and dollies into
 * Bengaluru, then dissolves into the page. Plays on every load of the About page
 * (the head script sets html.globe-intro and window.__revealGo). ~4.1 s; the only
 * text is the city's pin.
 *
 * Motion review (animate / animation-performance / emil-design-eng / apple-design):
 * the site's own curves (--ease-in-out for the flight, --ease-out for fades and the
 * exit); any tap, key or scroll skips from the current frame in 260 ms; phones
 * render at <=1.5x without MSAA; the page's backdrops wait for the globe; reduced
 * motion gets a still frame that cross-fades instead of a camera flight.
 *
 * Pacing: one camera path in four beats, glide to India, drift, glide to
 * Bengaluru, drift, then dissolve. Each channel (turn, zoom, tilt) is a cubic
 * Hermite track through timed keys whose slopes match on both sides, so speed
 * changes are always continuous: the camera never stops dead or jolts, it
 * settles into a slow drift over India and over the pinned city, and flows out
 * again. Zoom is in log space, so it reads at a constant perceived speed.
 */
import * as THREE from 'three';

const BLR = [12.9716, 77.5946];
const START = [14, 38];
const INDIA = [22.5, 79.5]; // the country's middle: the India beat is framed on it

/** cubic-bezier(x1, y1, x2, y2) as a function of t, like CSS. */
function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const X = (u) => ((ax * u + bx) * u + cx) * u;
  const Y = (u) => ((ay * u + by) * u + cy) * u;
  const dX = (u) => (3 * ax * u + 2 * bx) * u + cx;
  return (t) => {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    let u = t;
    for (let i = 0; i < 6; i++) { const d = dX(u); if (Math.abs(d) < 1e-6) break; u -= (X(u) - t) / d; }
    return Y(Math.min(1, Math.max(0, u)));
  };
}
// the site's tokens (main.css): --ease-in-out for movement on screen, --ease-out for entering/leaving
const easeInOut = bezier(0.65, 0, 0.35, 1);
const easeOut = bezier(0.16, 1, 0.3, 1);
const seg = (p, a, b) => Math.min(1, Math.max(0, (p - a) / (b - a)));

/**
 * A timed track: cubic Hermite through [ms, value, slope per ms] keys. Equal slopes
 * either side of a key keep the motion's speed continuous through it.
 */
function track(keys) {
  return (t) => {
    if (t <= keys[0][0]) return keys[0][1];
    for (let i = 1; i < keys.length; i++) {
      const [t1, v1, m1] = keys[i];
      if (t > t1) continue;
      const [t0, v0, m0] = keys[i - 1];
      const h = t1 - t0, s = (t - t0) / h, s2 = s * s, s3 = s2 * s;
      return (2 * s3 - 3 * s2 + 1) * v0 + (s3 - 2 * s2 + s) * h * m0 + (-2 * s3 + 3 * s2) * v1 + (s3 - s2) * h * m1;
    }
    return keys[keys.length - 1][1];
  };
}
const span = (t, a, b) => Math.min(1, Math.max(0, (t - a) / (b - a)));

// The beats (ms): glide to India, drift over India, glide to Bengaluru, drift over the pinned city, dissolve.
const BEAT = { india: 1250, leave: 2050, city: 3050, out: 3600, end: 4100 };
// turn to India (0..1, drifting on through its beat), then on from India to Bengaluru
// (0..1; its starting slope carries the same angular speed, see globe()); log-space
// zoom (0 = whole globe, 1 = the city); tilt across the surface for the last stretch
const TO_INDIA = track([[0, 0, 0], [BEAT.india, 0.94, 7.5e-5], [BEAT.leave, 1, 7.5e-5]]);
const ZOOM = track([[0, 0, 0], [BEAT.india, 0.38, 8e-5], [BEAT.leave, 0.444, 8e-5], [BEAT.city, 0.95, 5e-5], [BEAT.end, 1, 5e-5]]);
const TILT = track([[0, 0, 0], [BEAT.leave, 0, 0], [BEAT.city, 0.9, 1e-4], [BEAT.end, 1, 0]]);

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
    dispatchEvent(new Event('globe:done'));
  };
  if (!veil) return done();
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  try {
    const [world, india, lines] = await Promise.all([
      dots('/globe/world.bin'), dots('/globe/india.bin'),
      fetch('/globe/lines.json').then((r) => { if (!r.ok) throw new Error('lines'); return r.json(); }),
    ]);
    const canvas = veil.querySelector('canvas');
    // phones: a full-screen canvas at 3x on a 120 Hz panel blows the frame budget; 1.5x is indistinguishable here
    const touch = matchMedia('(pointer: coarse)').matches;
    const dpr = Math.min(window.devicePixelRatio || 1, touch ? 1.5 : 2);
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: dpr < 1.5, alpha: false, powerPreference: 'high-performance' });
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

    // the pin: an HTML overlay anchored to the city each frame, in the site's own type
    const pin = document.createElement('div');
    pin.className = 'globe-pin';
    pin.setAttribute('aria-hidden', 'true');
    pin.innerHTML = '<svg class="globe-pin__mark" viewBox="0 0 24 32" aria-hidden="true"><path d="M12 31s10-11.1 10-18.5C22 6.2 17.5 1.5 12 1.5S2 6.2 2 12.5C2 19.9 12 31 12 31z"/><circle cx="12" cy="12.5" r="4"/></svg><span class="globe-pin__label">Bengaluru</span>';
    veil.append(pin);
    const pinAt = blr.clone().multiplyScalar(1.0065), pinScreen = new THREE.Vector3();

    const onResize = () => {
      renderer.setSize(innerWidth, innerHeight, false);
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      uniforms.uPix.value = innerHeight * dpr * 0.5;
    };
    addEventListener('resize', onResize);

    const startDir = dir(...START);
    const indiaDir = dir(...INDIA);
    const qI = new THREE.Quaternion().setFromUnitVectors(startDir, indiaDir);
    const qB = new THREE.Quaternion().setFromUnitVectors(indiaDir, blr);
    const qa = new THREE.Quaternion(), qId = new THREE.Quaternion();
    // India → Bengaluru starts at the angular speed the India drift ends with
    const a1 = startDir.angleTo(indiaDir), a2 = indiaDir.angleTo(blr);
    const TO_CITY = track([[BEAT.leave, 0, 7.5e-5 * a1 / a2], [2900, 1, 0], [BEAT.end, 1, 0]]);
    const aim = new THREE.Vector3();
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
    // Any input skips: the film's own clock speeds up (smoothly, to 9x), so it
    // finishes in a few hundred ms from wherever it is, along the same path.
    let skipAt = 0, vt = 0, lastNow = 0, rate = 1;
    const skip = () => { if (!skipAt) skipAt = performance.now(); };
    const skipEvents = ['pointerdown', 'keydown', 'wheel', 'touchstart'];
    skipEvents.forEach((ev) => addEventListener(ev, skip, { passive: true }));
    // reduced motion: hold one still frame over the pinned city, then cross-fade (no camera flight)
    const STILL = BEAT.city + 250;
    await new Promise((resolve) => {
      const frame = (now) => {
        // window.__globeP (0..1) freezes the film at a point: used for frame review
        const held = typeof window.__globeP === 'number';
        const dt = lastNow ? Math.min(100, now - lastNow) : 0;
        lastNow = now;
        if (skipAt) rate += (9 - rate) * Math.min(1, dt / 90);
        vt += dt * rate;
        const t = held ? window.__globeP * BEAT.end : reduced ? STILL : Math.min(BEAT.end, vt);

        // camera direction: start → over India → over Bengaluru, one continuous turn
        const ti = Math.min(1, TO_INDIA(t)), tc = t > BEAT.leave ? Math.min(1, TO_CITY(t)) : 0;
        qa.slerpQuaternions(qId, qI, ti);
        camDir.copy(startDir).applyQuaternion(qa);
        if (tc > 0) camDir.applyQuaternion(qa.slerpQuaternions(qId, qB, tc));
        aim.copy(indiaDir);
        if (tc > 0) aim.applyQuaternion(qa); // qa now holds the India → city part of the turn
        const dist = Math.exp(Math.log(far) + (Math.log(near) - Math.log(far)) * Math.min(1, ZOOM(t)));
        const tilt = Math.min(1, TILT(t));
        camera.position.copy(camDir).multiplyScalar(dist).addScaledVector(south, (dist - 1) * 0.75 * tilt);
        // the aim moves from the globe's centre onto India, then onto the city with the turn
        target.copy(aim).multiplyScalar(ti);
        camera.up.copy(north);
        camera.lookAt(target);

        const fadeIn = reduced ? 1 : easeOut(span(t, 0, 380));
        // leaving: the veil dissolves while the camera is still drifting, pushing in a touch
        const out = reduced ? easeOut(Math.min(1, Math.max(0, (now - t0 - 1700) / 600))) : easeOut(span(t, BEAT.out, BEAT.end));
        const fadeOut = 1 - out;
        canvas.style.transform = out > 0 ? `scale(${1 + out * 0.05})` : '';
        uniforms.uFade.value = fadeIn;
        // the atmosphere's rim fades as we come down close to the surface
        rimU.uFade.value = fadeIn * (1 - easeInOut(span(t, 1500, 2600)));
        // India lights up on the way in; its border and states settle in before the drift
        uniforms.uIndia.value = easeInOut(span(t, 380, 1150));
        indiaWall.uOpacity.value = easeInOut(span(t, 550, 1250));
        stateMat.opacity = 0.32 * easeInOut(span(t, 800, 1450)) * (1 - 0.5 * easeInOut(span(t, 2300, 3000)));
        kaWall.uOpacity.value = easeInOut(span(t, 1850, 2550));
        // Bengaluru: the boundary rises out of the ground as we arrive, then fills
        const rise = easeOut(span(t, 2450, 3100));
        blrWall.uOpacity.value = easeOut(span(t, 2400, 2750));
        blrWall.uH.value = 0.0045 * rise;
        blrCapU.uH.value = 0.0045 * rise;
        blrCapU.uOpacity.value = 0.45 * easeOut(span(t, 2700, 3200));
        // a slow, soft ring breathing out from the city (the pin marks the place)
        const s = (dist - 1) * 0.008;
        core.scale.setScalar(s);
        core.material.opacity = 0;
        const r = span(t, 2750, 3900);
        ring.scale.setScalar(s * (3.2 + easeOut(r) * 6));
        ring.material.opacity = r > 0 ? Math.sin(Math.PI * r) * 0.3 : 0;
        // the pin settles onto the city as its boundary finishes rising; the label follows
        const drop = easeOut(span(t, 2850, 3250));
        const label = easeOut(span(t, 3000, 3450));
        if (drop > 0) {
          pinScreen.copy(pinAt).project(camera);
          const x = (pinScreen.x * 0.5 + 0.5) * innerWidth, y = (-pinScreen.y * 0.5 + 0.5) * innerHeight;
          pin.style.transform = `translate3d(${x.toFixed(1)}px, ${(y - (1 - drop) * 12).toFixed(1)}px, 0)`;
          pin.style.opacity = String(drop);
          pin.style.setProperty('--label', label.toFixed(3));
        } else pin.style.opacity = '0';
        veil.style.opacity = String(fadeOut);
        // the page's text starts rising while the veil dissolves
        if ((t >= BEAT.out + 150 || out > 0.3) && window.__revealGo) { window.__revealGo(); window.__revealGo = null; }

        renderer.render(scene, camera);
        const finished = reduced ? out >= 1 : t >= BEAT.end;
        if (!finished || held) requestAnimationFrame(frame); else resolve();
      };
      requestAnimationFrame(frame);
    });

    removeEventListener('resize', onResize);
    skipEvents.forEach((ev) => removeEventListener(ev, skip));
    renderer.dispose();
  } catch (err) {
    console.warn('[globe] skipped', err);
  }
  done();
}
