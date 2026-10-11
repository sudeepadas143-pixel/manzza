import { defineConfig } from 'vite';
import path from 'node:path';
import fs from 'node:fs';
import { loadData, renderHTML, listPlaceholders, isTodo } from './src/build/render.js';

const root = path.resolve(import.meta.dirname);

// Every page of the site. Clean URLs: /products/mitre-core → products/mitre-core/index.html
const PAGES = {
  home: 'index.html',
  materials: 'materials/index.html',
  quote: 'quote/index.html',
  'mitre-core': 'products/mitre-core/index.html',
  'ei-laminations': 'products/ei-laminations/index.html',
  'strip-laminations': 'products/strip-laminations/index.html',
  notFound: '404.html',
};

const ROUTES = ['/', '/products/mitre-core', '/products/ei-laminations', '/products/strip-laminations', '/materials', '/quote'];

/** Serve /materials as /materials/ locally, like Vercel's cleanUrls does in production. */
function cleanUrls(baseDir) {
  return (req, _res, next) => {
    const [pathname, query = ''] = req.url.split('?');
    if (pathname !== '/' && !path.extname(pathname) && !pathname.endsWith('/')) {
      if (fs.existsSync(path.join(baseDir, pathname, 'index.html'))) req.url = `${pathname}/${query ? `?${query}` : ''}`;
    }
    next();
  };
}

/** Dev-only segmented control: Demo data / Worst case. Plain chrome, not part of the design. */
function dataToggle(mode) {
  const seg = (m, label) => `<a href="?data=${m}" style="padding:6px 12px;border-radius:999px;text-decoration:none;color:#111;white-space:nowrap;${m === mode ? 'background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.2);' : ''}">${label}</a>`;
  return `<div style="position:fixed;left:50%;bottom:14px;transform:translateX(-50%);z-index:9999;display:flex;gap:2px;padding:3px;border-radius:999px;background:#d4d4d8;font:500 13px system-ui,sans-serif">${seg('demo', 'Demo data')}${seg('worst', 'Worst case')}</div>`;
}

function manzzaContent() {
  let warned = false;
  return {
    name: 'manzza-content',
    transformIndexHtml: {
      order: 'pre',
      async handler(html, ctx) {
        // dev server only: ?data=worst renders the page with fixtures/worst-case.js
        const dev = !!ctx.server;
        const mode = dev && /[?&]data=worst\b/.test(ctx.originalUrl || '') ? 'worst' : 'demo';
        const data = await loadData(root, { worst: mode === 'worst' });
        const out = renderHTML(html, data);
        return dev ? out.replace('</body>', `${dataToggle(mode)}</body>`) : out;
      },
    },
    configurePreviewServer(server) {
      const out = path.resolve(root, server.config.build.outDir);
      server.middlewares.use(cleanUrls(out));
      // like Vercel: unknown pages get 404.html with a 404 status
      return () => server.middlewares.use((req, res, next) => {
        const pathname = req.url.split('?')[0];
        if (path.extname(pathname) || fs.existsSync(path.join(out, pathname, 'index.html'))) return next();
        res.statusCode = 404;
        res.setHeader('Content-Type', 'text/html; charset=utf-8');
        res.end(fs.readFileSync(path.join(out, '404.html')));
      });
    },
    configureServer(server) {
      server.middlewares.use(cleanUrls(root));
      const watched = [path.join(root, 'content'), path.join(root, 'site.config.js'), path.join(root, 'src/build'), path.join(root, 'public/images')];
      server.watcher.add(watched);
      server.watcher.on('all', (_evt, file) => {
        if (watched.some((w) => file.startsWith(w))) server.ws.send({ type: 'full-reload' });
      });
    },
    async generateBundle() {
      const data = await loadData(root);
      const base = isTodo(data.config.siteUrl) ? 'https://YOUR-DOMAIN' : String(data.config.siteUrl).replace(/\/$/, '');
      const today = new Date().toISOString().slice(0, 10);
      const urls = ROUTES.map((r) => `  <url><loc>${base}${r === '/' ? '/' : r}</loc><lastmod>${today}</lastmod></url>`).join('\n');
      this.emitFile({ type: 'asset', fileName: 'sitemap.xml', source: `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n` });
      // which build is live: https://<site>/version.txt
      const commit = process.env.VERCEL_GIT_COMMIT_SHA || '';
      this.emitFile({ type: 'asset', fileName: 'version.txt', source: `built ${new Date().toISOString()}${commit ? `\ncommit ${commit.slice(0, 7)}` : ''}\n` });
      this.emitFile({ type: 'asset', fileName: 'robots.txt', source: `User-agent: *\nAllow: /\n\nSitemap: ${base}/sitemap.xml\n` });
      if (!warned) {
        warned = true;
        const open = listPlaceholders(data.config);
        if (open.length) {
          const lines = open.map(([k, note]) => `   • ${k.padEnd(22)} ${note}`).join('\n');
          this.warn(`\n\n  MANZZA: ${open.length} placeholder(s) in site.config.js still to fill:\n${lines}\n`);
        }
      }
    },
  };
}

export default defineConfig({
  appType: 'mpa',
  plugins: [manzzaContent()],
  build: {
    target: 'es2020',
    rollupOptions: {
      input: Object.fromEntries(Object.entries(PAGES).map(([k, f]) => [k, path.join(root, f)])),
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/three')) return 'three';
          if (id.includes('node_modules/gsap') || id.includes('node_modules/lenis')) return 'scroll';
        },
      },
    },
    chunkSizeWarningLimit: 800,
  },
  server: { host: true },
  preview: { host: true },
});
