/**
 * Clamping structure for the assembled core: blue-painted steel channel clamps on both
 * yokes, front and back, vertical tie rods with nuts, through-bolts in the
 * yoke bolt holes, end tie bars, mounting feet and a lifting lug.
 *
 * Built in the core's own coordinates (x across, y up, z through the stack,
 * 0 → zT), so it can be added straight to the group that holds the core.
 * Every part is returned with the data the scene needs to animate it in.
 */
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { CORE } from '../lamination/geometry.js';

export const FRAME = {
  lift: 0.32, // the core is raised by this much onto its feet
  beamH: 1.0, // clamp channel depth (a little more than the yoke)
  flange: 0.34, // flange width
  tw: 0.045, // web / flange thickness
  gap: 0.03, // clearance between the core face and the web
  rodR: 0.032,
  nutR: 0.07,
};

/**
 * Hot-dip galvanising: a mottled crystalline "spangle". One canvas drives a
 * roughness map (crystals reflect a little differently) and a faint colour map.
 */
function spangleTextures() {
  const S = 512;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const g = c.getContext('2d');
  g.fillStyle = '#b4b4b4'; g.fillRect(0, 0, S, S);
  let seed = 3;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 2600; i++) {
    const x = rnd() * S, y = rnd() * S, r = 3 + rnd() * 11;
    const v = Math.round(150 + rnd() * 70);
    g.fillStyle = `rgba(${v},${v},${v},${0.1 + rnd() * 0.18})`;
    g.beginPath();
    // crystals are faceted, not round
    const n = 5 + Math.floor(rnd() * 3);
    for (let k = 0; k < n; k++) {
      const a = (k / n) * Math.PI * 2 + rnd() * 0.6, rr = r * (0.6 + rnd() * 0.5);
      k ? g.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr) : g.moveTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
    }
    g.closePath(); g.fill();
  }
  const rough = new THREE.CanvasTexture(c);
  rough.wrapS = rough.wrapT = THREE.RepeatWrapping;
  rough.colorSpace = THREE.NoColorSpace;
  rough.repeat.set(5, 1.5);
  rough.anisotropy = 8;
  const col = rough.clone();
  col.colorSpace = THREE.SRGBColorSpace;
  col.needsUpdate = true;
  return { rough, col };
}

function threadTexture() {
  const c = document.createElement('canvas');
  c.width = 4; c.height = 64;
  const g = c.getContext('2d');
  const gr = g.createLinearGradient(0, 0, 0, 64);
  gr.addColorStop(0, '#000'); gr.addColorStop(0.5, '#fff'); gr.addColorStop(1, '#000');
  g.fillStyle = gr; g.fillRect(0, 0, 4, 64);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.NoColorSpace;
  return t;
}

/** Lifting lug: a plate with a rounded top and an eye. */
function lugGeometry(w, h, t) {
  const s = new THREE.Shape();
  const r = w / 2;
  s.moveTo(-r, 0); s.lineTo(r, 0); s.lineTo(r, h - r);
  s.absarc(0, h - r, r, 0, Math.PI, false);
  s.lineTo(-r, 0);
  const eye = new THREE.Path();
  eye.absarc(0, h - r, r * 0.42, 0, Math.PI * 2, true);
  s.holes.push(eye);
  const g = new THREE.ExtrudeGeometry(s, { depth: t, bevelEnabled: true, bevelThickness: 0.008, bevelSize: 0.008, bevelSegments: 2, curveSegments: 32 });
  g.translate(0, 0, -t / 2);
  return g;
}

export function buildFrame({ zT, mobile = false }) {
  const F = FRAME;
  const [x1, , x3] = CORE.limbX;
  const [y1, y2] = CORE.yokeY;
  const w0 = 0.95;
  const coreHalfW = x3 + w0 / 2; // 2.185
  const Lb = coreHalfW * 2 + 0.7; // beam length: overhangs the core at both ends
  const seg = mobile ? 16 : 28;

  // The frame (clamps, feet, lug) in the MANZZA logo blue: a metallic-flake paint
  // under a hard clear coat, so the studio's strip lights run along it as crisp
  // lines over a deeper, slightly sparkling blue. Core, rods and nuts stay bare metal.
  const spangle = spangleTextures();
  const paint = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color('#3169e3'), metalness: 0.45, roughness: 0.42, roughnessMap: spangle.rough,
    clearcoat: 1, clearcoatRoughness: 0.06,
  });
  const zinc = new THREE.MeshPhysicalMaterial({ color: new THREE.Color().setRGB(0.72, 0.73, 0.75), metalness: 1, roughness: 0.24 });
  const thread = threadTexture();
  const rodMat = zinc.clone();
  rodMat.bumpMap = thread;
  rodMat.bumpScale = 1.2;
  thread.repeat.set(1, 150);
  const black = new THREE.MeshPhysicalMaterial({ color: 0x15181d, metalness: 0.2, roughness: 0.55 });

  const mats = [paint, zinc, rodMat, black];
  const shadowed = (m) => { m.castShadow = true; m.receiveShadow = true; return m; };
  // rolled and cut steel never has knife edges: a small radius catches a line of light
  const box = (w, h, d, mat) => shadowed(new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 2, Math.min(0.012, Math.min(w, h, d) * 0.3)), mat));
  const nutGeo = new THREE.CylinderGeometry(F.nutR, F.nutR, 0.06, 6);
  const washerGeo = new THREE.CylinderGeometry(F.nutR * 1.25, F.nutR * 1.25, 0.012, seg);
  // small parts receive shadows but cast none: their shadows are too small to see,
  // and skipping them halves their draw calls (the shadow pass draws every caster again)
  const small = (m) => { m.castShadow = false; m.receiveShadow = true; return m; };
  const nut = () => small(new THREE.Mesh(nutGeo, zinc));
  const washer = () => small(new THREE.Mesh(washerGeo, zinc));

  // front web sits at z = zT + gap; back web mirrors it at z = -gap
  const zWebF = zT + F.gap + F.tw / 2;
  const zWebB = -F.gap - F.tw / 2;
  const zRodF = zT + F.gap + F.tw + F.flange * 0.55;
  const zRodB = -(F.gap + F.tw + F.flange * 0.55);

  /** Channel clamp: web against the core, flanges pointing away from it. */
  function channel(front) {
    const g = new THREE.Group();
    const s = front ? 1 : -1;
    const web = box(Lb, F.beamH, F.tw, paint);
    const zw = front ? zWebF : zWebB;
    web.position.set(0, 0, zw);
    const fz = zw + s * (F.flange / 2 + F.tw / 2);
    const top = box(Lb, F.tw, F.flange, paint);
    top.position.set(0, F.beamH / 2 - F.tw / 2, fz);
    const bot = top.clone();
    bot.position.y = -top.position.y;
    g.add(web, top, bot);
    return g;
  }

  /* clamps: one group per yoke and side, so they can arrive separately */
  const beams = [];
  for (const [yc, which] of [[y1, 'bottom'], [y2, 'top']]) {
    for (const front of [true, false]) {
      const g = channel(front);
      g.userData = { home: new THREE.Vector3(0, yc, 0), from: new THREE.Vector3(0, which === 'top' ? 0.8 : 0, front ? 2.6 : -2.6), which, front };
      beams.push(g);
    }
  }

  /* through-bolts in the yoke bolt holes: head on the front web, nut behind */
  const bolts = [];
  const boltGeo = new THREE.CylinderGeometry(CORE.holeR * 0.85, CORE.holeR * 0.85, zT + 2 * (F.gap + F.tw) + 0.16, seg);
  boltGeo.rotateX(Math.PI / 2);
  const headGeo = new THREE.CylinderGeometry(0.085, 0.085, 0.055, 6);
  headGeo.rotateX(Math.PI / 2);
  for (const yc of [y1, y2]) {
    for (const x of [(x1 + 0) / 2, (x3 + 0) / 2]) {
      const g = new THREE.Group();
      const shank = small(new THREE.Mesh(boltGeo, rodMat));
      shank.position.z = zT / 2;
      const head = small(new THREE.Mesh(headGeo, zinc));
      head.position.z = zT + F.gap + F.tw + 0.03;
      const back = small(new THREE.Mesh(headGeo, zinc));
      back.position.z = -(F.gap + F.tw + 0.03);
      g.add(shank, head, back);
      g.userData = { home: new THREE.Vector3(x, yc, 0), from: new THREE.Vector3(x, yc, 2.4) };
      bolts.push(g);
    }
  }

  /* end tie bars: front to back, outside the core, one per clamp end */
  const ties = [];
  const tieLen = zWebF - zWebB + 0.3;
  const tieGeo = new THREE.CylinderGeometry(0.045, 0.045, tieLen, seg);
  tieGeo.rotateX(Math.PI / 2);
  for (const yc of [y1, y2]) {
    for (const x of [-(coreHalfW + 0.17), coreHalfW + 0.17]) {
      const g = new THREE.Group();
      const bar = small(new THREE.Mesh(tieGeo, rodMat));
      bar.position.z = zT / 2;
      g.add(bar);
      for (const z of [zWebF + F.tw / 2 + 0.03, zWebB - F.tw / 2 - 0.03]) {
        const n = nut();
        n.rotation.x = Math.PI / 2;
        n.position.z = z;
        g.add(n);
      }
      g.userData = { home: new THREE.Vector3(x, yc, 0), from: new THREE.Vector3(x, yc, 2.4) };
      ties.push(g);
    }
  }

  /* vertical tie rods through the clamp flanges, with nuts top and bottom */
  const rods = [];
  const yTopFl = y2 + F.beamH / 2; // top face of the top clamp's upper flange
  const yBotFl = y1 - F.beamH / 2; // bottom face of the bottom clamp's lower flange
  const rodLen = yTopFl - yBotFl + 0.34;
  const rodGeo = new THREE.CylinderGeometry(F.rodR, F.rodR, rodLen, seg);
  const rodXs = [-(coreHalfW + 0.17), -(x3 / 2), x3 / 2, coreHalfW + 0.17];
  for (const z of [zRodF, zRodB]) {
    rodXs.forEach((x, i) => {
      const g = new THREE.Group();
      const rod = small(new THREE.Mesh(rodGeo, rodMat));
      rod.position.y = (yTopFl + yBotFl) / 2;
      g.add(rod);
      const nuts = [];
      for (const [y, dir] of [[yTopFl, 1], [yBotFl, -1]]) {
        const wsh = washer();
        wsh.position.y = y + dir * 0.006;
        const n = nut();
        n.position.y = y + dir * (0.012 + 0.03);
        g.add(wsh, n);
        nuts.push({ n, wsh, home: n.position.y, wHome: wsh.position.y, dir });
      }
      g.userData = { home: new THREE.Vector3(x, 0, z), from: new THREE.Vector3(x, 3.4, z), nuts, k: i + (z > 0 ? 0 : 4) };
      rods.push(g);
    });
  }

  /* feet: a base plate and an upright under each end of the bottom clamps */
  const feet = [];
  const footH = F.lift + (y1 - F.beamH / 2) ; // from the floor to the clamp's lower flange
  for (const z of [zRodF + 0.02, zRodB - 0.02]) {
    for (const x of [-1.25, 1.25]) {
      const g = new THREE.Group();
      const base = box(0.62, 0.05, 0.46, paint);
      base.position.set(0, -F.lift + 0.025, 0);
      const up = box(0.5, footH - 0.05, 0.05, paint);
      up.position.set(0, -F.lift + 0.05 + (footH - 0.05) / 2, z > 0 ? -0.08 : 0.08);
      const rib = box(0.05, footH - 0.05, 0.3, paint);
      rib.position.set(0, up.position.y, 0);
      g.add(base, up, rib);
      for (const dx of [-0.22, 0.22]) {
        const b = small(new THREE.Mesh(headGeo, zinc));
        b.rotation.x = 0;
        b.position.set(dx, -F.lift + 0.065, z > 0 ? 0.12 : -0.12);
        b.rotation.set(Math.PI / 2, 0, 0);
        g.add(b);
      }
      g.userData = { home: new THREE.Vector3(x, 0, z), from: new THREE.Vector3(x, 0, z + (z > 0 ? 1.6 : -1.6)) };
      feet.push(g);
    }
  }

  /* lifting lug, standing on a bridge plate across the top clamps */
  const lug = new THREE.Group();
  {
    const span = zRodF - zRodB + 0.16;
    const bridge = box(0.7, 0.05, span, paint);
    bridge.position.set(0, yTopFl + 0.025, zT / 2);
    const plate = shadowed(new THREE.Mesh(lugGeometry(0.5, 0.62, 0.05), paint));
    plate.position.set(0, yTopFl + 0.05, zT / 2);
    lug.add(bridge, plate);
    for (const z of [zRodF - 0.06, zRodB + 0.06]) {
      for (const dx of [-0.24, 0.24]) {
        const n = nut();
        n.position.set(dx, yTopFl + 0.08, z);
        lug.add(n);
      }
    }
    lug.userData = { home: new THREE.Vector3(0, 0, 0), from: new THREE.Vector3(0, 2.2, 0) };
  }

  const all = [...beams, ...bolts, ...ties, ...rods, ...feet, lug];
  const group = new THREE.Group();
  all.forEach((g) => group.add(g));

  return {
    group, beams, bolts, ties, rods, feet, lug, mats,
    dispose() { thread.dispose(); spangle.rough.dispose(); spangle.col.dispose(); nutGeo.dispose(); washerGeo.dispose(); },
  };
}
