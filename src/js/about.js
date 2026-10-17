// The globe transition only runs when an About link was clicked (html.globe-intro).
// It is requested first and in parallel with the page script, so the veil is not left empty.
const root = document.documentElement;
if (root.classList.contains('globe-intro')) {
  import('./globe.js').then((m) => m.playGlobe()).catch(() => {
    root.classList.remove('globe-intro');
    document.querySelector('.globe-veil')?.remove();
    window.__revealGo?.();
    dispatchEvent(new Event('globe:done'));
  });
} else {
  document.querySelector('.globe-veil')?.remove();
}
import('./main.js');
