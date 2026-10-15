/**
 * Heavy WebGL work (three.js scenes, shader compiles, PMREM) waits for this:
 * the visitor's first touch, scroll, wheel, key or mouse movement. During load
 * that work blocks the main thread on phones with weak GPUs, and what it draws
 * is not needed for the first frame: the intro opens on HTML, the product
 * visuals on their static drawings, the backdrops on their CSS gradients.
 * (A timed fallback was tried: on PageSpeed's slower mobile run it fired inside
 * the measured load and cost ~16s of blocking time.)
 */
const EVENTS = ['pointerdown', 'pointermove', 'touchstart', 'wheel', 'keydown', 'scroll'];

let ready = null;
export function whenEngaged() {
  ready ||= new Promise((resolve) => {
    let done = false;
    const go = (e) => {
      if (done) return;
      done = true;
      window.__engagedBy = e.type; // test hook
      EVENTS.forEach((t) => removeEventListener(t, go, true));
      resolve();
    };
    EVENTS.forEach((t) => addEventListener(t, go, { capture: true, passive: true }));
  });
  return ready;
}
