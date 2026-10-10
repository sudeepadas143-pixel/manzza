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
  steel: new THREE.Color('#a9b2be'),
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
  const m = new THREE.MeshStandardMaterial({
    color: opts.color || BRAND.steel,
    metalness: 0.78,
    roughness: opts.roughness ?? 0.4,
    roughnessMap: brushedTexture(),
    envMapIntensity: opts.envMapIntensity ?? 0.9,
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
        diffuseColor.rgb *= mix(1.0, 0.55, min(vSide, 1.0)) * uDim;`)
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

/** Neutral studio environment for metal reflections, generated procedurally. */
export function studioEnvironment(renderer, { light = false } = {}) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = new THREE.Scene();
  const box = new THREE.BoxGeometry(1, 1, 1);
  const room = new THREE.Mesh(box, new THREE.MeshBasicMaterial({ color: light ? 0x535a66 : 0x15181f, side: THREE.BackSide }));
  room.scale.set(20, 12, 20);
  env.add(room);
  const panel = (w, h, x, y, z, ry, c) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: c, side: THREE.DoubleSide }));
    m.position.set(x, y, z); m.rotation.y = ry; m.lookAt(0, 0, 0); env.add(m);
  };
  // light theme: a softer overhead so highlights don't bleach into the white page
  panel(12, 4, 0, 5.5, 0, 0, light ? 0x9aa2ae : 0xe4e8f0); //  soft overhead light
  panel(5, 7, -9, 1, 2, 0, 0x8c95a8); //    neutral side fill
  panel(4, 6, 9, 1, -3, 0, 0x5d6b8c); //    cool bounce
  panel(8, 2, 2, -2, 8, 0, 0x4a4f5a); //    front floor bounce
  panel(9, 5, -2, 3, 9, 0, 0x8a93a5); //    soft front light, so faces turned to the viewer read as steel
  const rt = pmrem.fromScene(env, 0.035);
  pmrem.dispose();
  box.dispose();
  env.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
  return rt.texture;
}

export function addLights(scene) {
  const key = new THREE.DirectionalLight(0xffffff, 2.1);
  key.position.set(4, 8, 6);
  const rim = new THREE.DirectionalLight(0x9db8ff, 0.4);
  rim.position.set(-5, 3, -4);
  const fill = new THREE.HemisphereLight(0xdfe5f2, 0x0a0d14, 0.55);
  scene.add(key, rim, fill);
  return { key, rim, fill };
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
