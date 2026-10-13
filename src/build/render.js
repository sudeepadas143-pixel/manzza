/**
 * Build-time HTML renderer.
 *
 * Page files contain tags like  {{> header active="materials"}}  which are
 * replaced with markup generated from site.config.js and content/*.json.
 * Runs inside Vite (dev and build), so the output is plain static HTML:
 * every word is crawlable and nothing waits for JavaScript.
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { stepLapFaceSVG, stepLapSectionSVG, pathD, piecePathD, coreFace, coreAnatomySVG } from '../js/lamination/svg.js';
import { CORE, eShape, iShape, stripShape, corePieces, stepOffsets, clipHalfPlane, holesLeftOf, bounds } from '../js/lamination/geometry.js';

/* ------------------------------------------------------------------ data */

export async function loadData(root, { worst = false } = {}) {
  const read = (f) => JSON.parse(fs.readFileSync(path.join(root, 'content', f), 'utf8'));
  const cfgUrl = pathToFileURL(path.join(root, 'site.config.js')).href + `?t=${Date.now()}`;
  let config = (await import(cfgUrl)).default;
  if (worst) {
    // dev only (?data=worst): overlay the worst-case fixture at the data boundary
    const fx = (await import(pathToFileURL(path.join(root, 'fixtures/worst-case.js')).href + `?t=${Date.now()}`)).default;
    config = { ...config, contact: { ...config.contact, ...fx.contact }, quoteForm: { ...config.quoteForm, ...fx.quoteForm }, capacity: { ...config.capacity, ...fx.capacity } };
  }
  return {
    root,
    config,
    products: read('products.json').products,
    materials: read('materials.json').materials,
    company: read('company.json'),
  };
}

export const isTodo = (v) => v == null || (typeof v === 'object' && v.__todo);

/** Every placeholder still open in site.config.js, as [path, note]. */
export function listPlaceholders(config) {
  const out = [];
  const walk = (obj, trail) => {
    for (const [k, v] of Object.entries(obj)) {
      const p = [...trail, k];
      if (v && typeof v === 'object' && v.__todo) out.push([p.join('.'), v.note]);
      else if (v && typeof v === 'object' && !Array.isArray(v)) walk(v, p);
    }
  };
  walk(config, []);
  return out;
}

/* --------------------------------------------------------------- helpers */

const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const attrs = (s) => {
  const o = {};
  s.replace(/(\w+)="([^"]*)"/g, (_, k, v) => { o[k] = v; });
  return o;
};
const pad2 = (n) => String(n).padStart(2, '0');

const siteUrl = (d) => (isTodo(d.config.siteUrl) ? '' : String(d.config.siteUrl).replace(/\/$/, ''));

function telHref(phone) {
  return 'tel:' + String(phone).replace(/[^\d+]/g, '');
}
function whatsappHref(d, text) {
  const n = d.config.contact.whatsapp;
  if (isTodo(n)) return null;
  return `https://wa.me/${String(n).replace(/\D/g, '')}?text=${encodeURIComponent(text)}`;
}

const tbc = (label) => `<span class="tbc">${esc(label)} to be added</span>`;

function phoneLink(d, cls = '') {
  const p = d.config.contact.phone;
  return isTodo(p) ? tbc('Phone number') : `<a class="${cls}" href="${telHref(p)}">${esc(p)}</a>`;
}
function emailLink(d, cls = '') {
  const e = d.config.contact.email;
  return isTodo(e) ? tbc('Email address') : `<a class="${cls}" href="mailto:${esc(e)}">${esc(e)}</a>`;
}
function addressHTML(d) {
  const a = d.config.contact.address;
  if (isTodo(a)) return `${tbc('Street address')}<br>${esc(d.config.company.city)}, ${esc(d.config.company.state)}`;
  return (Array.isArray(a) ? a : [a]).map(esc).join('<br>');
}

const icon = {
  chevron: '<svg class="i i-chev" viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  arrow: '<svg class="i i-arrow" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.25 10.75 8 6 12.75" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  phone: '<svg class="i" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 2.5h3l1.2 4-2 1.3a10 10 0 0 0 4.5 4.5l1.3-2 4 1.2v3a1.5 1.5 0 0 1-1.6 1.5C9.4 15.6 4.4 10.6 4 4.1A1.5 1.5 0 0 1 5.5 2.5Z" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>',
  mail: '<svg class="i" viewBox="0 0 20 20" aria-hidden="true"><path d="M2.5 4.5h15v11h-15zM2.5 5l7.5 6 7.5-6" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>',
  pin: '<svg class="i" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 18s5.5-5.2 5.5-9.5a5.5 5.5 0 0 0-11 0C4.5 12.8 10 18 10 18Z M10 10.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>',
  wa: '<svg class="i" viewBox="0 0 20 20" aria-hidden="true"><path d="M3.2 16.8l1-3.4A7.3 7.3 0 1 1 7 16.1l-3.8.7Z" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M7.4 6.6c.3-.6.6-.6.9-.6h.5c.2 0 .4 0 .5.4l.6 1.4c.1.2 0 .4-.1.6l-.4.5c-.1.1-.2.3 0 .5.3.5.8 1.1 1.3 1.5.6.5 1.1.7 1.4.8.2.1.4 0 .5-.1l.6-.7c.2-.2.3-.2.5-.1l1.4.7c.2.1.3.2.3.3 0 .4-.1 1-.6 1.3-.5.4-1.4.6-2.6.1a8.6 8.6 0 0 1-4.2-4c-.5-1-.4-1.8-.1-2.3Z" fill="currentColor"/></svg>',
  check: '<svg class="i i-check" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
  upload: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M4 15v4h16v-4" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
};

/* --------------------------------------------------------- static visuals */

function miniSVG(type) {
  const V = (vb, body) => `<svg viewBox="${vb}" aria-hidden="true" focusable="false">${body}</svg>`;
  if (type === 'core') return V('0 0 800 600', coreFace({ box: { x: 60, y: 40, w: 680, h: 520 }, cls: 'f-steel' }));
  if (type === 'mitre-corner') {
    const offs = stepOffsets(5, 0.07);
    const top = corePieces({ w: 0.95, o: offs[4], gap: 0.014 });
    const limb = clipHalfPlane(top.find((p) => p.id === 'limb-l').poly, 0, 1, 1.9);
    const yokePc = top.find((p) => p.id === 'yoke-b');
    const yoke = clipHalfPlane(yokePc.poly, 1, 0, -0.7);
    const yokeHoles = holesLeftOf(yokePc.holes, -0.7);
    const b = bounds([limb, yoke]);
    const k = 440 / Math.max(b.w, b.h);
    const map = ([x, y]) => [180 + (x - b.x0) * k, 520 - (y - b.y0) * k];
    const ox = CORE.limbX[0] - 0.95 / 2;
    const joints = offs.slice(0, 4).map((o) => {
      const a = map([ox + Math.max(0, -o), Math.max(0, -o) + o]);
      const c = map([ox + 0.95, 0.95 + o]);
      return `<line x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}" x2="${c[0].toFixed(1)}" y2="${c[1].toFixed(1)}" class="f-hidden"/>`;
    }).join('');
    return V('0 0 800 600', `<path d="${pathD(limb, map)}" class="f-steel"/><path d="${piecePathD(yoke, yokeHoles, map)}" class="f-steel" fill-rule="evenodd"/>${joints}`);
  }
  if (type === 'ei') {
    const map = (dx, dy) => ([x, y]) => [250 + (x + dx) * 100, 470 - (y + dy) * 100];
    return V('0 0 800 600', `<path d="${pathD(eShape(1), map(0, 0))}" class="f-steel"/><path d="${pathD(iShape(1), map(0, 2.25))}" class="f-steel"/>`);
  }
  const s = stripShape({ length: 4.2, width: 0.62, holes: 3, holeR: 0.085 });
  const map = ([x, y]) => [85 + x * 150, 345 - y * 150];
  return V('0 0 800 600', `<path d="${pathD(s.outer, map)}${s.holes.map((h) => pathD(h, map)).join('')}" class="f-steel" fill-rule="evenodd"/>`);
}

function mini(type, cls = '', { frame = '', scrub = false } = {}) {
  // frame: where the part sits in a wide band ('right' leaves the left for the copy)
  // scrub: the part turns with the band's scroll progress
  return `<div class="mini ${cls}">
    <div class="mini__fallback">${miniSVG(type)}</div>
    <canvas data-mini="${esc(type)}"${frame ? ` data-frame="${esc(frame)}"` : ''}${scrub ? ' data-scrub' : ''} aria-hidden="true"></canvas>
  </div>`;
}

/** The one marketing CTA: a ghost pill (white fill wipes in on hover). */
function pill(href, label, { cls = '', attrs: extra = '', primary = false } = {}) {
  return `<a class="btn ${primary ? 'btn--primary' : 'btn--ghost'} ${cls}" href="${esc(href)}"${extra}><span class="btn__label">${esc(label)}</span></a>`;
}

/** Real-photo slot: shows /images/<id>.(webp|jpg|png) when present, else a neutral placeholder. */
function photo(d, { id, label, alt, ratio = '4/3' }) {
  const dir = path.join(d.root, 'public', 'images');
  const file = ['webp', 'jpg', 'jpeg', 'png'].map((ext) => `${id}.${ext}`).find((f) => fs.existsSync(path.join(dir, f)));
  if (file) {
    return `<figure class="photo" style="aspect-ratio:${ratio}"><img src="/images/${file}" alt="${esc(alt || label)}" width="1600" height="1000" loading="lazy" decoding="async"><figcaption>${esc(label)}</figcaption></figure>`;
  }
  return `<figure class="photo photo--slot" style="aspect-ratio:${ratio}" data-photo-slot="${esc(id)}">
    <div class="photo__hatch" aria-hidden="true"></div>
    <figcaption><span class="photo__tag">Photograph to follow</span>${esc(label)}</figcaption>
  </figure>`;
}

/* ------------------------------------------------------------------ head */

function head(d, a) {
  const pages = d.company.pages;
  let title, description, pathName;
  if (a.product) {
    const p = d.products.find((x) => x.slug === a.product);
    title = p.seo.title; description = p.seo.description; pathName = `/products/${p.slug}`;
  } else {
    const pg = pages[a.page];
    title = pg.title; description = pg.description; pathName = a.path || '/';
  }
  const base = siteUrl(d);
  const abs = (u) => (base ? base + u : u);
  const c = d.config;
  const org = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: c.company.legalName,
    alternateName: c.company.shortName,
    slogan: c.company.tagline,
    description: d.company.about,
    address: {
      '@type': 'PostalAddress',
      addressLocality: c.company.city,
      addressRegion: c.company.state,
      addressCountry: c.company.country,
      ...(isTodo(c.contact.address) ? {} : { streetAddress: Array.isArray(c.contact.address) ? c.contact.address.join(', ') : c.contact.address }),
    },
    areaServed: c.company.serviceRegions.map((name) => ({ '@type': 'State', name })),
    knowsAbout: ['Transformer core laminations', 'CRGO electrical steel', 'CRNO electrical steel', 'Mitre core step-lap laminations', 'E&I laminations', 'Strip laminations'],
    ...(base ? { url: base, logo: `${base}/brand/manzza-logo-lockup.png` } : {}),
    ...(isTodo(c.contact.phone) ? {} : { telephone: c.contact.phone }),
    ...(isTodo(c.contact.email) ? {} : { email: c.contact.email }),
  };
  const ld = [org];
  if (a.product) {
    const p = d.products.find((x) => x.slug === a.product);
    ld.push({
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: abs('/') },
        { '@type': 'ListItem', position: 2, name: p.name, item: abs(pathName) },
      ],
    });
  }
  return `<meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">
  <script>(function(d){d.classList.add('js');if(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)d.classList.add('rm')})(document.documentElement)</script>
  <title>${esc(title)}</title>
  <meta name="description" content="${esc(description)}">
  ${base ? `<link rel="canonical" href="${esc(abs(pathName))}">` : ''}
  ${a.noindex ? '<meta name="robots" content="noindex">' : ''}
  <meta name="theme-color" content="#06080d">
  <meta name="color-scheme" content="dark">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="${esc(c.company.legalName)}">
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(description)}">
  <meta property="og:locale" content="en_IN">
  ${base ? `<meta property="og:url" content="${esc(abs(pathName))}">` : ''}
  <meta property="og:image" content="${esc(abs('/brand/og-image.png'))}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="MANZZA – Engineered for Power">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="icon" href="/favicon.ico" sizes="32x32">
  <link rel="icon" href="/favicon.png" type="image/png">
  <link rel="apple-touch-icon" href="/brand/apple-touch-icon.png">
  <link rel="preload" as="image" href="/brand/manzza-logo-nav.webp" type="image/webp">
  <script type="application/ld+json">${JSON.stringify(ld.length === 1 ? ld[0] : ld).replace(/</g, '\\u003c')}</script>`;
}

/* ------------------------------------------------------- header / footer */

function header(d, a) {
  const active = a.active || '';
  const cur = (k) => (k === active ? ' aria-current="page"' : '');
  const prodLinks = d.products.map((p) => `<li><a href="/products/${p.slug}"${a.product === p.slug ? ' aria-current="page"' : ''}>${esc(p.navLabel)}</a></li>`).join('');
  return `<a class="skip-link" href="#main">Skip to main content</a>
<header class="site-header" data-header>
  <div class="container header__inner">
    <a class="brand" translate="no" href="/" aria-label="${esc(d.config.company.legalName)} – home">
      <img src="/brand/manzza-logo-nav.webp" alt="MANZZA" width="363" height="80">
    </a>
    <nav class="nav" aria-label="Main">
      <ul class="nav__list">
        <li class="nav__item has-dd" data-dd>
          <button class="nav__link dd-toggle${active === 'products' ? ' is-current' : ''}" type="button" aria-expanded="false" aria-controls="dd-products">Products ${icon.chevron}</button>
          <div class="dd" id="dd-products">
            <ul class="dd__list">${prodLinks}</ul>
          </div>
        </li>
        <li class="nav__item"><a class="nav__link" href="/materials"${cur('materials')}>Materials</a></li>
        <li class="nav__item"><a class="nav__link nav__link--cta" href="/quote"${cur('quote')}>Request a quote</a></li>
      </ul>
    </nav>
    <a class="header__cta" href="/quote"${cur('quote')}>Request a quote</a>
    <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="mobile-menu"><span class="menu-toggle__bars" aria-hidden="true"><i></i><i></i></span><span class="menu-toggle__label">Menu</span></button>
  </div>
</header>
  <div class="mobile-menu" id="mobile-menu" hidden>
    <div class="container">
      <ul class="mobile-menu__list">
        ${d.products.map((p) => `<li><a href="/products/${p.slug}">${esc(p.navLabel)}</a></li>`).join('')}
        <li><a href="/materials">Materials</a></li>
        <li><a href="/quote">Request a quote</a></li>
      </ul>
      <p class="mobile-menu__contact">${phoneLink(d)}</p>
    </div>
  </div>
`;
}

function footer(d) {
  const c = d.config;
  const wa = whatsappHref(d, 'Hello MANZZA, I would like to discuss a lamination requirement.');
  return `<footer class="site-footer">
  <div class="container">
    <div class="footer__grid">
      <div class="footer__brand">
        <a href="/" class="footer__logo" aria-label="MANZZA – home"><img src="/brand/manzza-logo.webp" alt="MANZZA" width="930" height="205" loading="lazy"></a>
        <p class="footer__sub">A ${esc(c.company.city)}-based manufacturer of transformer laminations.</p>
      </div>
      <nav class="footer__col" aria-label="Products">
        <p class="footer__h">Products</p>
        <ul>${d.products.map((p) => `<li><a href="/products/${p.slug}">${esc(p.name)}</a></li>`).join('')}</ul>
      </nav>
      <nav class="footer__col" aria-label="Company">
        <p class="footer__h">Information</p>
        <ul><li><a href="/materials">Materials: CRGO and CRNO</a></li><li><a href="/quote">Request a quote</a></li><li><a href="/#about">About MANZZA</a></li></ul>
      </nav>
      <div class="footer__col">
        <p class="footer__h">Contact</p>
        <ul>
          <li>${phoneLink(d)}</li>
          <li>${emailLink(d)}</li>
          ${wa ? `<li><a href="${esc(wa)}" target="_blank" rel="noopener">WhatsApp</a></li>` : ''}
          <li>${addressHTML(d)}</li>
        </ul>
        ${isTodo(c.contact.hours) || !c.contact.hours ? '' : `<p class="footer__hours">${esc(c.contact.hours)}</p>`}
      </div>
    </div>
    <div class="footer__base">
      <p>© <span data-year>${new Date().getFullYear()}</span> ${esc(c.company.legalName.replace(/\.$/, ''))}. All rights reserved.</p>
      <p>${esc(c.company.city)}, ${esc(c.company.state)}, India</p>
    </div>
  </div>
</footer>`;
}

/* ------------------------------------------------------------- home page */

function intro(d) {
  // Pure animation: no captions or labels. It opens on the logo; the M is a
  // separate, sharper image laid exactly over the M of the lockup, because it
  // grows to fill the centre of the screen. The page's headline lives in the
  // hero section right after the animation.
  return `<section id="intro" class="intro" aria-label="Animation: the MANZZA mark becomes a coil of electrical steel, which is cut into laminations and assembled into a clamped transformer core">
  <div class="intro__stage">
    <canvas class="intro__canvas" aria-hidden="true"></canvas>
    <div class="intro__frames" aria-hidden="true"></div>
    <div class="intro__brand">
      <div class="intro__lockup">
        <img class="intro__word" src="/brand/manzza-logo-lockup.webp" alt="MANZZA" width="950" height="290" fetchpriority="high">
      </div>
      <img class="intro__m" src="/brand/manzza-m.webp" alt="" width="430" height="360" fetchpriority="high">
    </div>
    <img class="intro__tagline" src="/brand/manzza-tagline.webp" alt="" aria-hidden="true" width="902" height="34" decoding="async">
    <button class="intro__cue" type="button" data-cue aria-label="Scroll down">
      <span class="intro__cue-label" aria-hidden="true">Scroll</span>
      <span class="intro__cue-line" aria-hidden="true"></span>
    </button>
  </div>
</section>`;
}

function hero(d) {
  const ix = d.company.intro;
  return `<section class="band hero" aria-labelledby="hero-h">
  <div class="container hero__inner">
    <p class="eyebrow" data-line>${esc(d.config.company.legalName)} · ${esc(d.config.company.city)}</p>
    <h1 id="hero-h" class="d-xxl" data-rise>${esc(ix.headline)}</h1>
    <p class="body-lg hero__lede">${esc(ix.lede)}</p>
    ${pill('/quote', 'Request a quote', { primary: true })}
  </div>
</section>`;
}

/** Home: each product is a full-bleed band, the render as its photograph. */
function productCards(d) {
  return d.products.map((p, i) => `
  <section class="band band--product${i === 1 ? ' band--flip' : i === 2 ? ' band--wide' : ''}" aria-labelledby="pb-${p.slug}">
    <a class="band__media" href="/products/${p.slug}" tabindex="-1" aria-hidden="true">${mini(p.cardVisual, 'band__mini', { frame: i === 1 ? 'left' : i === 2 ? '' : 'right', scrub: true })}</a>
    <div class="container band__copy">
      <h2 id="pb-${p.slug}" class="d-xl" data-rise>${esc(p.name)}</h2>
      <p class="band__line">${esc(p.cardLine)}</p>
      ${pill(`/products/${p.slug}`, 'Learn more', { attrs: ` aria-label="Learn more about ${esc(p.name.toLowerCase().replace('e&i', 'E&I'))}"` })}
    </div>
  </section>`).join('');
}

/** Thickness scale: positions only at the values stated in materials.json. */
function thicknessScale(d) {
  const vals = new Set();
  d.materials.forEach((m) => {
    const s = m.thicknessScale || {};
    if (s.from != null) { vals.add(s.from); vals.add(s.to); }
    (s.points || []).forEach((v) => vals.add(v));
  });
  const list = [...vals].sort((a, b) => a - b);
  const lo = list[0], hi = list[list.length - 1];
  const X0 = 96, X1 = 470;
  const x = (v) => X0 + ((v - lo) / (hi - lo || 1)) * (X1 - X0);
  const rows = d.materials.map((m, i) => {
    const y = 40 + i * 52;
    const s = m.thicknessScale || {};
    let mark = '';
    if (s.from != null) mark += `<rect x="${x(s.from)}" y="${y - 6}" width="${x(s.to) - x(s.from)}" height="12" class="ts-bar"/>`;
    (s.points || []).forEach((v) => { mark += `<rect x="${x(v) - 6}" y="${y - 6}" width="12" height="12" class="ts-pt" transform="rotate(45 ${x(v)} ${y})"/>`; });
    return `<text x="0" y="${y + 6}" class="ts-name">${esc(m.code)}</text><line x1="${X0}" y1="${y}" x2="${X1}" y2="${y}" class="ts-track"/>${mark}`;
  }).join('');
  const axisY = 40 + d.materials.length * 52;
  const ticks = list.map((v) => `<line x1="${x(v)}" y1="${axisY - 8}" x2="${x(v)}" y2="${axisY}" class="ts-tick"/><text x="${x(v)}" y="${axisY + 24}" class="ts-val" text-anchor="middle">${v.toFixed(2)}</text>`).join('');
  return `<figure class="tscale">
    <svg viewBox="0 0 500 ${axisY + 44}" role="img" aria-label="Thickness ranges: ${d.materials.map((m) => `${m.code} ${m.thickness}`).join('; ')}">${rows}<line x1="${X0}" y1="${axisY}" x2="${X1}" y2="${axisY}" class="ts-axis"/>${ticks}</svg>
  </figure>`;
}

function compareTable(d) {
  const M = d.materials;
  const row = (label, fn) => `<tr><th scope="row">${label}</th>${M.map((m) => `<td>${fn(m)}</td>`).join('')}</tr>`;
  return `<div class="table-wrap"><table class="spec spec--compare">
    <caption class="sr-only">CRGO and CRNO electrical steel compared</caption>
    <thead><tr><td></td>${M.map((m) => `<th scope="col"><span class="spec__code">${esc(m.code)}</span></th>`).join('')}</tr></thead>
    <tbody>
      ${row('Full name', (m) => esc(m.name))}
      ${row('Thickness', (m) => `<span class="num spec__big">${esc(m.thickness)}</span>`)}
      ${row('Grades', (m) => esc(m.grades))}
      ${row('Magnetic properties', (m) => esc(m.summary))}
    </tbody>
  </table></div>`;
}

function specTable(d, codes) {
  const M = d.materials.filter((m) => !codes || codes.includes(m.code));
  return `<div class="table-wrap"><table class="spec spec--rows">
    <thead><tr><th scope="col">Material</th><th scope="col">Full name</th><th scope="col">Thickness</th><th scope="col">Grades</th></tr></thead>
    <tbody>${M.map((m) => `<tr><th scope="row" data-label="Material"><span class="spec__code">${esc(m.code)}</span></th><td data-label="Full name">${esc(m.name)}</td><td data-label="Thickness" class="num">${esc(m.thickness)}</td><td data-label="Grades">${esc(m.grades)}</td></tr>`).join('')}</tbody>
  </table></div>`;
}

function process(d) {
  return `<ul class="cols">${d.company.process.map((s) => `<li class="col" data-line>
      <h3 class="col__title">${esc(s.step)}</h3>
      <p class="col__text">${esc(s.text)}</p>
    </li>`).join('')}</ul>`;
}

function capacity(d) {
  const c = d.config.capacity;
  if (!c || !c.show) return '';
  // "Up to 160": the figure set large, its qualifier as a label above it
  const m = String(c.value).match(/^(.*?)(\d[\d,.]*)\s*$/);
  const [pre, num] = m ? [m[1].trim(), m[2]] : ['', String(c.value)];
  return `<div class="capacity">
    ${pre ? `<p class="eyebrow">${esc(pre)}</p>` : ''}
    <p class="capacity__value d-xxl"><span class="num"${/^\d+$/.test(num) ? ` data-count="${num}"` : ''}>${esc(num)}</span></p>
    <p class="eyebrow">${esc(c.unit)}</p>
    <p class="note">${esc(c.note)}</p>
  </div>`;
}

function quality(d) {
  return `<ul class="rows rows--2">${d.company.quality.map((q) => `<li data-line><h3 class="rows__title">${esc(q.title)}</h3><p>${esc(q.text)}</p></li>`).join('')}</ul>`;
}

function customers(d) {
  return `<ul class="index">${d.company.customers.map((c) => `<li data-line><h3 class="index__title">${esc(c.title)}</h3><p class="index__text">${esc(c.text)}</p></li>`).join('')}</ul>`;
}

function cta(d, a) {
  const wa = whatsappHref(d, 'Hello MANZZA, I would like to send a drawing for a quotation.');
  const phone = d.config.contact.phone;
  return `<section class="band cta" aria-labelledby="cta-h">
  <div class="container cta__inner">
    <h2 id="cta-h" class="d-xl cta__h" data-rise>${esc(a.title || 'Discuss your next requirement with our team.')}</h2>
    <p class="body-lg cta__p">${esc(a.text || 'Submit your requirements for an individual quotation.')}</p>
    ${pill(`/quote${a.product ? `?product=${esc(a.product)}` : ''}`, 'Request a quote', { primary: true })}
    ${wa || !isTodo(phone) ? `<p class="cta__alt">${wa ? `<a href="${esc(wa)}" target="_blank" rel="noopener">WhatsApp</a>` : ''}${!isTodo(phone) ? phoneLink(d) : ''}</p>` : ''}
  </div>
</section>`;
}

/* ---------------------------------------------------------- product page */

function productPage(d, a) {
  const p = d.products.find((x) => x.slug === a.slug);
  const others = d.products.filter((x) => x.slug !== p.slug);
  const quoteHref = `/quote?product=${p.slug}`;
  const facts = p.facts.map((f) => `<div class="fact" data-line><dt class="eyebrow">${esc(f.label)}</dt><dd>${esc(f.value)}${f.note ? `<span class="fact__note">${esc(f.note)}</span>` : ''}</dd></div>`).join('');
  const diagram = p.diagram ? `
  <section class="section" aria-labelledby="anatomy-h">
    <div class="container">
      <h2 id="anatomy-h" class="d-lg section__h" data-rise>Mitre, diamond tip and V-notch.</h2>
      <figure class="diagram-fig">${coreAnatomySVG({ id: 'core-anatomy' })}${coreAnatomySVG({ id: 'core-anatomy-c', compact: true })}
        <ol class="diagram-legend"><li>Yokes, top and bottom</li><li>Limbs: two outer and one centre</li><li>Mitre corner</li><li>Diamond tip of the centre limb</li><li>V-notch in the yoke, which seats the diamond tip</li><li>Bolt holes, punched to drawing</li></ol>
      </figure>
    </div>
  </section>
` : '';

  return `<main id="main" class="product">
  <section class="band band--phero">
    <div class="band__media">${mini(p.visual, 'band__mini', { frame: 'right', scrub: true })}</div>
    <div class="container band__copy">
      <nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="/">Home</a></li><li><a href="/#products">Products</a></li><li aria-current="page">${esc(p.name)}</li></ol></nav>
      <h1 class="d-xxl" data-rise>${esc(p.headline)}</h1>
      <p class="body-lg band__lede">${esc(p.intro)}</p>
      ${pill(quoteHref, 'Request a quote', { primary: true })}
    </div>
  </section>

  <section class="section section--soft" aria-label="Key facts">
    <div class="container"><dl class="facts" style="--n:${p.facts.length}">${facts}</dl></div>
  </section>

  <section class="section" aria-labelledby="apps-h">
    <div class="container split">
      <h2 id="apps-h" class="d-lg" data-rise>Applications</h2>
      <ul class="rows">${p.applications.map((x) => `<li data-line><p class="rows__strong">${esc(x)}</p></li>`).join('')}</ul>
    </div>
  </section>
  ${diagram}
  <section class="section section--soft" aria-labelledby="mat-h">
    <div class="container">
      <div class="section__head">
        <h2 id="mat-h" class="d-lg" data-rise>Material options</h2>
        <a class="link" href="/materials">Compare CRGO and CRNO</a>
      </div>
      ${specTable(d, p.materials)}
      <p class="note">Grades and thicknesses are supplied to your specification, subject to availability.</p>
    </div>
  </section>

  <section class="section" aria-labelledby="cust-h">
    <div class="container">
      <h2 id="cust-h" class="d-lg section__h" data-rise>Customisation</h2>
      <div class="custom-grid">
        <ul class="rows rows--2">${p.customisation.map((c) => `<li data-line><h3 class="rows__title">${esc(c.title)}</h3>${c.text ? `<p>${esc(c.text)}</p>` : ''}</li>`).join('')}</ul>
        ${photo(d, { id: `product-${p.slug}`, label: p.name, ratio: '4/5' })}
      </div>
    </div>
  </section>

  <section class="section section--soft section--tight" aria-label="Other products">
    <div class="container">
      <p class="eyebrow">Other products</p>
      <ul class="others">${others.map((o) => `<li><a href="/products/${o.slug}"><span class="others__name">${esc(o.name)}</span>${icon.arrow}</a></li>`).join('')}</ul>
    </div>
  </section>

  ${cta(d, { product: p.slug })}
  <div class="stickybar" data-stickybar>${pill(quoteHref, `Request a quote for ${p.name.replace(' laminations', '')}`, { cls: 'btn--block', primary: true })}</div>
</main>`;
}

/* --------------------------------------------------------- materials page */

function materialsDetail(d) {
  return `<div class="mats">${d.materials.map((m) => `
    <article class="mat" id="${m.code.toLowerCase()}" data-line>
      <p class="mat__code d-xxl">${esc(m.code)}</p>
      <h2 class="mat__name">${esc(m.name)}</h2>
      <p class="mat__summary">${esc(m.summary)}</p>
      <p class="mat__detail">${esc(m.detail)}</p>
      <dl class="mat__specs">
        <div><dt>Thickness</dt><dd class="num">${esc(m.thickness)}</dd></div>
        <div><dt>Grades</dt><dd>${esc(m.grades)}</dd></div>
      </dl>
    </article>`).join('')}</div>`;
}

function grainFigure() {
  // CRGO: aligned grain arrows; CRNO: arrows in many directions
  const arrows = (dirFn, ox) => {
    let s = '';
    for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) {
      const cx = ox + 40 + c * 52, cy = 50 + r * 42;
      const a = dirFn(r, c);
      const dx = Math.cos(a) * 16, dy = Math.sin(a) * 16;
      s += `<line x1="${(cx - dx).toFixed(1)}" y1="${(cy - dy).toFixed(1)}" x2="${(cx + dx).toFixed(1)}" y2="${(cy + dy).toFixed(1)}" class="g-arrow" marker-end="url(#g-ah)"/>`;
    }
    return s;
  };
  const ang = [0.4, 2.1, 3.9, 5.2, 1.1, 2.8, 4.6, 0.2, 3.3, 5.8, 1.7, 4.1, 0.9, 2.5, 5.5, 3.0, 0.6, 4.9, 2.2, 1.4];
  return `<figure class="grain">
    <svg viewBox="0 0 640 270" role="img" aria-label="Grain direction: CRGO is aligned with the rolling direction; CRNO has no strongly preferred direction.">
      <defs><marker id="g-ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10z" class="g-head"/></marker></defs>
      <rect x="10" y="20" width="290" height="180" class="g-sheet"/>
      <rect x="340" y="20" width="290" height="180" class="g-sheet"/>
      ${arrows(() => 0, 10)}
      ${arrows((r, c) => ang[r * 5 + c], 340)}
      <text x="10" y="238" class="g-label g-strong">CRGO</text><text x="10" y="258" class="g-label">grain along the rolling direction</text>
      <text x="340" y="238" class="g-label g-strong">CRNO</text><text x="340" y="258" class="g-label">no strongly preferred direction</text>
    </svg>
  </figure>`;
}

function matrix(d) {
  return `<div class="table-wrap"><table class="spec spec--matrix">
    <thead><tr><th scope="col">Product</th>${d.materials.map((m) => `<th scope="col"><span class="spec__code">${esc(m.code)}</span></th>`).join('')}</tr></thead>
    <tbody>${d.products.map((p) => `<tr><th scope="row"><a href="/products/${p.slug}">${esc(p.name)}</a></th>${d.materials.map((m) => `<td>${p.materials.includes(m.code) ? `<span class="yes">${icon.check}<span class="sr-only">Available</span></span>` : '<span class="no" aria-label="Not offered">–</span>'}</td>`).join('')}</tr>`).join('')}</tbody>
  </table></div>`;
}

/* ------------------------------------------------------------ quote page */

function quoteForm(d) {
  const maxMB = d.config.quoteForm.maxFileMB;
  const radio = (name, value, label, sub, req) => `<label class="choice"><input type="radio" name="${name}" value="${esc(value)}"${req ? ' required' : ''}><span class="choice__box"><span class="choice__label">${esc(label)}</span>${sub ? `<span class="choice__sub">${esc(sub)}</span>` : ''}</span></label>`;
  return `<form class="qform" id="quote-form" novalidate data-endpoint="${isTodo(d.config.quoteForm.endpoint) ? '' : esc(d.config.quoteForm.endpoint)}" data-max-mb="${maxMB}">
  <div class="qform__hp" aria-hidden="true"><label>Leave this field empty <input type="text" name="company_website" tabindex="-1" autocomplete="off"></label></div>

  <fieldset class="fs">
    <legend class="sr-only">Contact details</legend>
    <div class="fgrid">
      <div class="field"><label for="f-company">Company name <span class="req">required</span></label><input id="f-company" name="company" type="text" autocomplete="organization" required></div>
      <div class="field"><label for="f-name">Contact person <span class="req">required</span></label><input id="f-name" name="contact_person" type="text" autocomplete="name" required></div>
      <div class="field"><label for="f-email">Business email <span class="req">required</span></label><input id="f-email" name="email" type="email" autocomplete="email" inputmode="email" spellcheck="false" required></div>
      <div class="field"><label for="f-phone">Phone <span class="req">required</span></label><input id="f-phone" name="phone" type="tel" autocomplete="tel" inputmode="tel" required></div>
    </div>
  </fieldset>

  <fieldset class="fs">
    <legend class="sr-only">Product and material</legend>
    <div class="field" role="radiogroup" aria-labelledby="lbl-product">
      <p class="label" id="lbl-product">Product <span class="req">required</span></p>
      <div class="choices choices--3">
        ${d.products.map((p, i) => radio('product', p.slug, p.name.replace(' laminations', ''), '', i === 0)).join('')}
      </div>
    </div>
    <div class="field" role="radiogroup" aria-labelledby="lbl-material">
      <p class="label" id="lbl-material">Material <span class="req">required</span></p>
      <div class="choices choices--3">
        ${d.materials.map((m, i) => radio('material', m.code, m.code, '', i === 0)).join('')}
      </div>
    </div>
    <div class="fgrid">
      <div class="field"><label for="f-thk">Thickness (mm)</label><input id="f-thk" name="thickness" type="text" inputmode="decimal"></div>
      <div class="field"><label for="f-grade">Grade</label><input id="f-grade" name="grade" type="text"></div>
      <div class="field field--wide"><label for="f-rating">Transformer rating or application <span class="opt">optional</span></label><input id="f-rating" name="rating_or_application" type="text"></div>
    </div>
  </fieldset>

  <fieldset class="fs">
    <legend class="sr-only">Quantity</legend>
    <div class="fgrid">
      <div class="field"><label for="f-qty">Estimated quantity <span class="req">required</span></label><input id="f-qty" name="quantity" type="text" required></div>
      <div class="field"><label for="f-freq">Order frequency</label>
        <input id="f-freq" name="order_frequency" type="text">
      </div>
    </div>
  </fieldset>

  <fieldset class="fs">
    <legend class="sr-only">Drawing and notes</legend>
    <div class="field">
      <p class="label" id="lbl-file">Drawing or specification file</p>
      <label class="drop" for="f-file">
        <input id="f-file" name="drawing" type="file" accept=".pdf,.dwg,.dxf,.step,.stp,.igs,.iges,.png,.jpg,.jpeg,.zip" aria-describedby="lbl-file h-file">
        <span class="drop__icon">${icon.upload}</span>
        <span class="drop__text"><strong>Choose a file</strong> or drag it here</span>
        <span class="drop__file" data-file-name></span>
      </label>
    </div>
    <div class="field"><label for="f-notes">Additional requirements</label><textarea id="f-notes" name="notes" rows="5"></textarea></div>
  </fieldset>

  <div class="qform__submit">
    <button class="btn btn--filled" type="submit"><span class="btn__label">Send request</span></button>
    <p class="qform__fine">Prices are not displayed publicly. Each enquiry receives an individual quotation.</p>
  </div>
  <div class="qform__status" role="status" aria-live="polite" tabindex="-1"></div>
</form>

<div class="qdone" id="quote-done" hidden tabindex="-1">
  <p class="qdone__mark" aria-hidden="true">${icon.check}</p>
  <h2 class="d-lg">Thank you. Your request has been sent.</h2>
  <p class="body-lg">We will reply with an individual quotation.</p>
  <div class="btn-row"><a class="btn btn--ghost" href="/"><span class="btn__label">Back to home</span></a><button class="link" type="button" data-again>Send another request</button></div>
</div>`;
}

function contactCard(d) {
  const wa = whatsappHref(d, 'Hello MANZZA, I would like a quotation for laminations.');
  return `<aside class="qside">
    <h2 class="eyebrow">Contact</h2>
    <ul class="qside__list">
      <li>${phoneLink(d)}</li>
      <li>${emailLink(d)}</li>
      ${wa ? `<li><a href="${esc(wa)}" target="_blank" rel="noopener">WhatsApp</a></li>` : ''}
      <li>${addressHTML(d)}</li>
    </ul>
  </aside>`;
}

/* ------------------------------------------------------------- dispatch */

const PARTIALS = {
  head, header, footer, intro, hero, cta, productPage, quoteForm, contactCard,
  productCards: (d) => productCards(d),
  compareTable: (d) => compareTable(d),
  specTable: (d, a) => specTable(d, a.materials ? a.materials.split(',') : null),
  thicknessScale: (d) => thicknessScale(d),
  process: (d) => process(d),
  capacity: (d) => capacity(d),
  quality: (d) => quality(d),
  customers: (d) => customers(d),
  about: (d) => `<p class="statement" data-words>${esc(d.company.about)}</p>`,
  pill: (d, a) => pill(a.href, a.label),
  photo: (d, a) => photo(d, a),
  materialsDetail: (d) => materialsDetail(d),
  grainFigure: () => grainFigure(),
  matrix: (d) => matrix(d),
  regions: (d) => esc(d.config.company.serviceRegions.slice(0, -1).join(', ') + ' and ' + d.config.company.serviceRegions.slice(-1)[0]),
  icon: (d, a) => icon[a.name] || '',
};

export function renderHTML(html, data) {
  return html.replace(/\{\{>\s*(\w+)([^}]*)\}\}/g, (m, name, rest) => {
    const fn = PARTIALS[name];
    if (!fn) throw new Error(`Unknown partial "${name}"`);
    return fn(data, attrs(rest));
  });
}
