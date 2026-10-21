// App-shell cache only. API responses are never cached: stale market data must look stale, not live.
const CACHE = "radar-shell-v5";
const SHELL = ["/", "/static/style.css", "/static/charts.js", "/static/app.js", "/manifest.webmanifest",
  "/static/icons/icon.svg", "/static/icons/icon-180.png", "/static/icons/icon-192.png",
  "/static/fonts/newsreader-latin-400-normal.woff2", "/static/fonts/newsreader-latin-500-normal.woff2", "/static/fonts/ibm-plex-sans-latin-400-normal.woff2",
  "/static/fonts/ibm-plex-sans-latin-500-normal.woff2"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(caches.keys()
  .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  // network first so updates land immediately; cache only when offline
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok) { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
    return r;
  }).catch(() => caches.match(e.request).then((m) => m || caches.match("/"))));
});
