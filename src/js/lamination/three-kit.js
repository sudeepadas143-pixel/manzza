/**
 * Three.js building blocks shared by the scroll intro and the product visuals.
 * Everything here is procedural: no model files, no image textures.
 */
import * as THREE from 'three';
import { ShapeUtils } from 'three';
import { ccw, signedArea } from './geometry.js';

export const BRAND = {
  blue: new THREE.Color('#2f6bea'),
  blueGlow: new THREE.Color('#5b8fff'),
  // steel's F0 reflectance (physicallybased.info), in linear: a metal's colour is its reflectance
  steel: new THREE.Color().setRGB(0.56, 0.57, 0.58),
};

/* ------------------------------------------------------------------------ */
/* Geometry                                                                  */
/* ------------------------------------------------------------------------ */

/**
 * Extrude many flat lamination polygons into ONE BufferGeometry.
 * items: [{ poly, holes?, z, t, layer, dir }]
 *   z     – bottom face height (along +Z), t – thickness
 *   layer – stack index (drives the step-lap "explode" in the shader)
 *   dir   – 'x' | 'y': rolling direction, so the brushed grain follows it
 * Adds attributes aSide (0 = face, 1 = cut edge, 2 = 45° mitre edge) and aLayer.
 */
export function extrudeLaminations(items, { uvScale = 1.6 } = {}) {
  const pos = [], nor = [], uv = [], side = [], lay = [];
  const push = (x, y, z, nx, ny, nz, u, v, s, l) => {
    pos.push(x, y, z); nor.push(nx, ny, nz); uv.push(u, v); side.push(s); lay.push(l);
  };
  for (const it of items) {
    const outer = ccw(it.poly);
    const holes = (it.holes || []).map((h) => (signedArea(h) > 0 ? h.slice().reverse() : h));
    const z0 = it.z, z1 = it.z + it.t;
    const l = it.layer || 0;
    const uvOf = (x, y) => (it.dir === 'y' ? [y * uvScale, x * uvScale] : [x * uvScale, y * uvScale]);
    const contour = outer.map(([x, y]) => new THREE.Vector2(x, y));
    const holeV = holes.map((h) => h.map(([x, y]) => new THREE.Vector2(x, y)));
    const tris = ShapeUtils.triangulateShape(contour, holeV);
    const all = [...outer, ...holes.flat()];
    for (let [a, b, c] of tris) {
      const [ax, ay] = all[a], [bx, by] = all[b], [cx, cy] = all[c];
      if ((bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0) [b, c] = [c, b]; // force CCW
      // top face (+Z), CCW
      for (const i of [a, b, c]) { const [x, y] = all[i]; const [u, v] = uvOf(x, y); push(x, y, z1, 0, 0, 1, u, v, 0, l); }
      // bottom face (-Z)
      for (const i of [a, c, b]) { const [x, y] = all[i]; const [u, v] = uvOf(x, y); push(x, y, z0, 0, 0, -1, u, v, 0, l); }
    }
    // cut edges: outer contour is CCW, holes CW → outward normal = (dy, -dx)
    for (const ring of [outer, ...holes]) {
      for (let i = 0; i < ring.length; i++) {
        const [x0, y0] = ring[i];
        const [x1, y1] = ring[(i + 1) % ring.length];
        const dx = x1 - x0, dy = y1 - y0;
        const len = Math.hypot(dx, dy) || 1;
        const nx = dy / len, ny = -dx / len;
        const sd = Math.abs(Math.abs(dx) - Math.abs(dy)) < 0.02 * len ? 2 : 1; // mitre edge?
        push(x0, y0, z0, nx, ny, 0, 0, 0, sd, l);
        push(x1, y1, z0, nx, ny, 0, len, 0, sd, l);
        push(x1, y1, z1, nx, ny, 0, len, 1, sd, l);
        push(x0, y0, z0, nx, ny, 0, 0, 0, sd, l);
        push(x1, y1, z1, nx, ny, 0, len, 1, sd, l);
        push(x0, y0, z1, nx, ny, 0, 0, 1, sd, l);
      }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setAttribute('aSide', new THREE.Float32BufferAttribute(side, 1));
  g.setAttribute('aLayer', new THREE.Float32BufferAttribute(lay, 1));
  g.computeBoundingSphere();
  return g;
}

/* ------------------------------------------------------------------------ */
/* Textures                                                                  */
/* ------------------------------------------------------------------------ */

let brushedCache = null;
/** Brushed-steel roughness texture: fine streaks along U (the rolling direction). */
export function brushedTexture() {
  if (brushedCache) return brushedCache;
  const S = 256;
  const c = document.createElement('canvas');
  c.width = S; c.height = S;
  const ctx = c.getContext('2d');
  const img = ctx.createImageData(S, S);
  // value noise per row, stretched along x
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const rows = new Float32Array(S);
  for (let y = 0; y < S; y++) rows[y] = rnd();
  for (let y = 0; y < S; y++) {
    for (let x = 0; x < S; x++) {
      const streak = rows[y] * 0.55 + rows[(y + 1) % S] * 0.25 + rnd() * 0.2;
      const v = 150 + streak * 70;
      const i = (y * S + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.NoColorSpace;
  t.anisotropy = 4;
  brushedCache = t;
  return t;
}

/* ------------------------------------------------------------------------ */
/* Materials                                                                 */
/* ------------------------------------------------------------------------ */

/**
 * Uniforms shared by every steel material, so one value change (edge glow,
 * step-lap explode) updates the whole scene.
 */
export function createSteelUniforms() {
  return {
    uExplode: { value: 0 },
    uLayerMid: { value: 0 },
    uEdge: { value: 0.0 },
    uEdgeColor: { value: BRAND.blueGlow.clone() },
    uDim: { value: 1 },
    uFade: { value: 0 }, // mix the final colour towards uFadeColor (light theme: fade into the page)
    uFadeColor: { value: new THREE.Color(0xf3f5f8) },
  };
}

/** Dark brushed electrical steel, with optional electric-blue light on cut edges. */
export function createSteelMaterial(uniforms, opts = {}) {
  // Physically based electrical steel: brushed along the rolling direction
  // (anisotropic highlights follow UV u, which the extruder aligns with each
  // lamination's grain) under the faint sheen of its insulation coating.
  const m = new THREE.MeshPhysicalMaterial({
    // Metallic is a switch, not a slider: anything below 1 mixes in a diffuse
    // layer and steel reads as grey plastic or paper.
    color: opts.color || BRAND.steel,
    metalness: 1,
    roughness: opts.roughness ?? 0.26, // brushed
    roughnessMap: brushedTexture(),
    anisotropy: opts.anisotropy ?? 0.55,
    // the thin glassy insulation coating of electrical steel
    clearcoat: opts.clearcoat ?? 0.12,
    clearcoatRoughness: 0.18,
    envMapIntensity: opts.envMapIntensity ?? 1,
    side: THREE.FrontSide,
  });
  m.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>
        attribute float aSide; attribute float aLayer;
        uniform float uExplode; uniform float uLayerMid;
        varying float vSide;`)
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        transformed.z += (aLayer - uLayerMid) * uExplode;
        vSide = aSide;`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
        varying float vSide; uniform float uEdge; uniform vec3 uEdgeColor; uniform float uDim; uniform float uFade; uniform vec3 uFadeColor;`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        diffuseColor.rgb *= mix(1.0, 0.42, min(vSide, 1.0)) * uDim;`)
      // the cut edge of a stack is hundreds of sheared sheet edges: darker and far less
      // mirror-like than the rolled faces
      .replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>
        roughnessFactor = min(1.0, roughnessFactor + 0.32 * min(vSide, 1.0));`)
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        totalEmissiveRadiance += uEdgeColor * uEdge * (vSide > 1.5 ? 1.0 : 0.12 * vSide);`)
      .replace('#include <dithering_fragment>', `#include <dithering_fragment>
        gl_FragColor.rgb = mix(gl_FragColor.rgb, uFadeColor, uFade);`);
  };
  m.customProgramCacheKey = () => 'manzza-steel';
  return m;
}

/* ------------------------------------------------------------------------ */
/* Lighting                                                                  */
/* ------------------------------------------------------------------------ */

/**
 * Reflections for the film and the product visuals: a room in the site's own navy (near-black underfoot,
 * a blue lift overhead) lit by long, soft-edged strip boxes. Polished steel and
 * the clear-coated blue frame read by the clean lines of light they pick up, and
 * by the navy around them, which ties the metal to the backdrop it plays over.
 */
export function navyStudio(renderer, { steel = false } = {}) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = new THREE.Scene();
  const trash = [];
  const dome = new THREE.SphereGeometry(20, 48, 24);
  // a dusky steel-blue horizon (what the sides of the coil and the core's faces see),
  // near-black underfoot, a cooler lift overhead
  // steel: a neutral grey room for small parts on the page, so they read silver, not navy
  const bot = new THREE.Color(steel ? '#08090c' : '#04060b');
  const mid = new THREE.Color(steel ? '#5a606b' : '#344055');
  const top = new THREE.Color(steel ? '#7a8496' : '#4a5f86');
  const pos = dome.attributes.position, cols = [], c = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    const y = pos.getY(i) / 20;
    if (y < 0) c.copy(mid).lerp(bot, Math.min(1, -y * 2.2)); else c.copy(mid).lerp(top, y ** 0.8);
    cols.push(c.r, c.g, c.b);
  }
  dome.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
  trash.push(new THREE.Mesh(dome, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide })));
  env.add(trash[0]);
  // soft-edged strip: bright core, feathered ends and sides
  const cv = document.createElement('canvas'); cv.width = 256; cv.height = 64;
  const g = cv.getContext('2d');
  const gx = g.createLinearGradient(0, 0, 256, 0);
  gx.addColorStop(0, 'rgba(255,255,255,0)'); gx.addColorStop(0.12, '#fff'); gx.addColorStop(0.88, '#fff'); gx.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gx; g.fillRect(0, 0, 256, 64);
  g.globalCompositeOperation = 'destination-in';
  const gy = g.createLinearGradient(0, 0, 0, 64);
  gy.addColorStop(0, 'rgba(0,0,0,0)'); gy.addColorStop(0.3, '#000'); gy.addColorStop(0.7, '#000'); gy.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gy; g.fillRect(0, 0, 256, 64);
  const soft = new THREE.CanvasTexture(cv);
  const strip = (w, h, at, gain, color = '#ffffff', roll = 0) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: soft, transparent: true, side: THREE.DoubleSide }));
    m.material.color.set(color).multiplyScalar(gain); // > 1: brighter than white (half-float target)
    m.position.set(...at); m.lookAt(0, 0, 0); m.rotateZ(roll);
    env.add(m); trash.push(m);
  };
  // flat steel seen from above mirrors what is overhead: narrow lines with dark between
  // them give the sheets bands of light and shadow instead of one white glare
  strip(20, 0.7, [0, 10, -5], 3.0); //                   key line, overhead, a little behind
  strip(20, 0.45, [0, 10, -1], 1.7); //                  second line
  strip(20, 0.35, [0, 9, 5], 1.6); //                    third, in front
  strip(12, 3.2, [-12, 2.5, 4], 2.4, '#eef3ff', Math.PI / 2); // big soft box, left: silver on faces turned to the viewer
  strip(11, 1.0, [12, 4, -8], 3.8, '#cfe0ff', Math.PI / 2); // rim strip, right and behind
  strip(16, 4.5, [0, 3.5, 15], 2.0, '#e9efff'); //       large soft box behind the camera: end faces and front faces read silver
  strip(26, 1.2, [0, -1.2, 14], 0.9, '#3169e3'); //      low blue bounce from the front: the brand on every edge
  const rt = pmrem.fromScene(env, 0.035);
  pmrem.dispose(); soft.dispose();
  trash.forEach((m) => { m.geometry.dispose(); m.material.dispose(); });
  return rt.texture;
}


export function addLights(scene) {
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(4, 8, 6);
  const fill = new THREE.HemisphereLight(0xffffff, 0xd3d8e0, 0.5);
  scene.add(key, fill);
  return { key, fill };
}

/** Dispose everything under an object. */
export function disposeTree(root) {
  root.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) {
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach((m) => {
        for (const k of Object.keys(m)) if (m[k] && m[k].isTexture && m[k] !== brushedCache) m[k].dispose();
        m.dispose();
      });
    }
  });
}

export function releaseShared() {
  if (brushedCache) { brushedCache.dispose(); brushedCache = null; }
}
