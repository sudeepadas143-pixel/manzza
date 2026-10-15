/**
 * Heavy WebGL work (three.js scenes, shader compiles, PMREM) waits for this:
 * the visitor's first touch, scroll, wheel or key, or the page settling after
 * load, whichever comes first. During load that work blocks the main thread on
 * phones with weak GPUs, and what it draws is not needed for the first frame:
 * the intro opens on HTML, the product visuals on their static drawings.
 */
const EVENTS = ['pointerdown', 'touchstart', 'wheel', 'keydown', 'scroll'];
const SETTLE_MS = 2500;

let ready = null;
export function whenEngaged() {
  ready ||= new Promise((resolve) => {
    let done = false;
    const go = () => {
      if (done) return;
      done = true;
      EVENTS.forEach((t) => removeEventListener(t, go, true));
      resolve();
    };
    EVENTS.forEach((t) => addEventListener(t, go, { capture: true, passive: true }));
    const settle = () => setTimeout(() => (window.requestIdleCallback || setTimeout)(go, { timeout: 1000 }), SETTLE_MS);
    if (document.readyState === 'complete') settle(); else addEventListener('load', settle, { once: true });
  });
  return ready;
}
