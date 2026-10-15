import './main.js';

// The globe transition only runs when an About link was clicked (html.globe-intro).
if (document.documentElement.classList.contains('globe-intro')) {
  import('./globe.js').then((m) => m.playGlobe()).catch(() => {
    document.documentElement.classList.remove('globe-intro');
    document.querySelector('.globe-veil')?.remove();
    window.__revealGo?.();
  });
} else {
  document.querySelector('.globe-veil')?.remove();
}
