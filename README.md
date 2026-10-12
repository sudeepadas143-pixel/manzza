# MANZZA Industry – website

Static website for **MANZZA Industry Pvt. Ltd.**, Bengaluru: transformer core laminations (mitre step-lap, E&I, strip) in CRGO and CRNO electrical steel. Dark theme throughout: black pages, deep-navy surfaces, electric blue as the single accent.

Plain HTML, CSS and JavaScript, built with [Vite](https://vite.dev). The home page intro is a scroll-driven Three.js scene (GSAP ScrollTrigger + Lenis). Every lamination on the site (3D, SVG diagrams, fallbacks) is drawn from one geometry module, so the pictures always agree with each other.

---

## Run it

Needs Node.js 20 or newer.

```bash
npm install
npm run dev        # http://localhost:5173, reloads when you edit content
```

Other commands:

```bash
npm run build         # production build into dist/
npm run preview       # serve dist/ at http://localhost:4173
npm run placeholders  # list what MANZZA still has to supply
```

## Pages

| URL | File |
|---|---|
| `/` | `index.html` |
| `/products/mitre-core` | `products/mitre-core/index.html` |
| `/products/ei-laminations` | `products/ei-laminations/index.html` |
| `/products/strip-laminations` | `products/strip-laminations/index.html` |
| `/materials` | `materials/index.html` |
| `/quote` | `quote/index.html` |
| 404 | `404.html` |

The page files are short. Tags like `{{> productPage slug="mitre-core"}}` are filled in at build time from the content files below (see `src/build/render.js`), so the published pages are complete static HTML that search engines can read without running JavaScript.

## Editing content (no layout code needed)

| What | Where |
|---|---|
| Phone, email, WhatsApp, address, office hours | `site.config.js` → `contact` |
| Live domain (canonical URLs, sitemap, Open Graph) | `site.config.js` → `siteUrl` |
| Quote form endpoint | `site.config.js` → `quoteForm.endpoint` |
| Indicative capacity figure and note | `site.config.js` → `capacity` (set `show: false` to hide it) |
| Product text, applications, customisation, "what to send us", SEO titles | `content/products.json` |
| Material names, thicknesses, grades, explanations | `content/materials.json` |
| About text, home headline, process steps, quality points, customer types, page titles | `content/company.json` |

Rules for content, from the brief:

- No certifications, test claims, guaranteed loss figures, awards, client logos, testimonials, years in business or employee counts unless MANZZA can back them up.
- No prices anywhere. Pricing goes through the quote form.
- Every number on the site comes from the brief. If you add one, make sure it is confirmed.

**Placeholders.** Anything in `site.config.js` written as `TODO('…')` is not yet known. The site shows a neutral "… to be added" note in its place (never a fake number), JSON-LD leaves it out, and `npm run build` prints the list. Replace the whole `TODO('…')` with the real value, e.g.

```js
phone: '+91 80 1234 5678',
whatsapp: '919876543210',   // digits only, with country code
address: ['Plot 00, Industrial Area', 'Bengaluru 560000, Karnataka'],
```

## Quote form

The form (`/quote`) posts `multipart/form-data` (all fields plus the drawing file) to `quoteForm.endpoint`. It has client-side validation, a hidden honeypot field against spam bots and a success message. No prices are shown or promised.

Until an endpoint is set, the form simulates success on `localhost` (so you can see the success state) and on a live site tells visitors to phone, email or WhatsApp instead.

**Option A: Formspree (simplest)**

1. Create a form at <https://formspree.io> with the address that should receive enquiries.
2. Copy its endpoint into `site.config.js`: `endpoint: 'https://formspree.io/f/abcdwxyz'`.
3. File uploads need a Formspree plan that includes them. Set `maxFileMB` to your plan's limit.

**Option B: Vercel function + Resend (included in `api/quote.js`)**

1. Create a free account at <https://resend.com>, verify your domain, and create an API key.
2. In the Vercel project → Settings → Environment Variables, add:
   - `RESEND_API_KEY`: the key
   - `QUOTE_TO_EMAIL`: where enquiries should go (comma-separate several)
   - `QUOTE_FROM_EMAIL`: e.g. `MANZZA website <website@yourdomain.in>`
3. Set `endpoint: '/api/quote'` in `site.config.js` and redeploy.
4. Keep `maxFileMB: 4` (Vercel caps request size at about 4.5 MB). The form asks visitors to email larger drawings.

Either way, the email arrives with the visitor's address as reply-to, so you can just press Reply.

## Photographs

No factory photos exist yet, so the site shows clearly labelled dark slots ("Photograph to follow"). To fill one, put an image in `public/images/` with the slot's name and rebuild. No code changes are needed:

| File name | Where it appears |
|---|---|
| `factory-cnc-line.jpg` | Home page, "How we work" |
| `product-mitre-core.jpg` | Mitre core page, "What you can specify" |
| `product-ei-laminations.jpg` | E&I page, "What you can specify" |
| `product-strip-laminations.jpg` | Strip page, "What you can specify" |

`.webp`, `.jpg` or `.png` all work. Use real photos of MANZZA's own floor and products, not stock images. About 1600 px on the long side is plenty. Landscape suits the home slot; portrait (4:5) suits the product slots.

## Logo

`public/brand/` holds the logo as supplied, cropped from the brand artwork:

- `manzza-logo.webp` and `manzza-logo-nav.webp`: the wordmark with its black background made transparent. On black it renders identically to the original. 
- `manzza-logo-lockup.webp`: wordmark with tagline, transparent; the opening frame of the intro.
- `manzza-logo-lockup.png`: wordmark with tagline (Open Graph, JSON-LD).
- `icon-512.png`, `apple-touch-icon.png`, `favicon.*`: the M mark.

These were cut from a screenshot, so they are sharp at nav size but soft on large retina screens. **Please send the original vector (SVG/AI/PDF) or a high-resolution PNG** and replace these files with the same names.

## Deploy to Vercel

1. Push this repository to GitHub.
2. In Vercel: **Add New → Project**, import the repository. Vercel reads `vercel.json` (Vite, `npm run build`, output `dist`, clean URLs). No other settings are needed.
3. Add your domain under Project → Settings → Domains, then set `siteUrl` in `site.config.js` to it and push, so canonical links and `sitemap.xml` use the real address.
4. If you use the Vercel quote function, add the environment variables above.

Every push to the main branch redeploys automatically, so editing a JSON file and pushing is all a content update needs.

## How the scroll intro works

`src/js/intro/` holds the intro: `index.js` handles scrolling and the logo layers, `scene.js` the 3D scene, `frame.js` the clamping frame. The intro is **pure animation, with no text**. The page's headline sits in the hero section right after it.

- A section about 600vh tall (460vh on phones) holds a sticky full-screen stage. GSAP ScrollTrigger maps scroll position to progress `p` from 0 to 1 (scrubbed). Lenis smooths wheel scrolling on desktop only.
- `scene.update(p)` sets every object from scratch for a given `p`, so scrolling back plays the story in reverse exactly. The scene renders only when `p` changes.
- Story: it opens on the MANZZA logo → the wordmark leaves and the M takes the centre → the M dissolves into the end face of a coil as the studio lights come up → the coil rolls out a sheet → slitting into strips → 45° mitre cuts → the four laminations glide into place as the yokes and outer limbs while the packets stack beneath them → the core is stood up and raised onto its feet → the clamping frame assembles (channel clamps, yoke through-bolts, end tie bars, tie rods, nuts, lifting lug) → the finished core turns under the lights.
- The M is its own, sharper image (`public/brand/manzza-m.webp`, cropped from the icon), laid exactly over the M of the lockup; both layers use `mix-blend-mode: screen` so their black backgrounds drop out over the 3D scene.
- Rendering: real metal, following the claude-blender skills (`.claude/skills/blender-*`): steel is fully metallic (metallic is a switch, not a slider) with steel's F0 reflectance (0.56, 0.57, 0.58) and brushed roughness; it reflects a photographed studio HDRI, Poly Haven "Studio Small 02" (CC0, `public/hdri/`, loaded after first paint with a procedural fallback); lit with the metal three-point profile (warm key, cool fill, cool rim at 4:1:2); AgX tone mapping. A dark studio. Physically based brushed steel (anisotropic highlights along each lamination's rolling direction, a clear-coat sheen for the insulation coating) reflecting soft boxes in a black room, a soft shadow-casting key light that sweeps slowly across the finished core, a rim light, a pool of light on the floor, ACES tone mapping. The frame is painted steel with zinc-plated threaded rods and hex nuts. The camera follows a Catmull-Rom path through its keyframes, so it glides instead of stopping at each one. Only the 45° mitre edges and cut lines use electric blue.
- Geometry is procedural and follows MANZZA's own cores: `src/js/lamination/geometry.js` builds the three-limb core with 45° mitre corners, a diamond-pointed centre limb in V-notched yokes, yoke bolt holes, step-lap joint offsets and a stepped (cruciform) limb section.
- Performance: the frame is drawn in the same GSAP tick as the scroll update (no extra frame of latency); every shader, including the shadow passes, is compiled up front so nothing stalls when it first appears; shadows use filtered PCF (no blur passes); the pixel ratio is capped at 1.5 and steps down automatically if frames run long. Phones get fewer layers and smaller shadow maps. Three.js loads only after first paint, and the WebGL context is released when the section is well off-screen.
- Without WebGL, SVG frames built from the same geometry crossfade on scroll (add `?nogl` to preview). With **prefers-reduced-motion**, nothing is pinned or animated: the page shows the logo.

**Recording a film of the intro.** Open `/?capture` in a browser: scrubbing becomes exact, quality is maxed and the site header is hidden, so a screen recorder (or a headless browser stepping through scroll positions) captures the animation alone.

The small rotating product visuals (`src/js/minis.js`, `src/js/mini-scenes.js`) share one offscreen WebGL renderer, use the same steel material and studio lighting, animate only while visible, and fall back to static SVG drawings.

## Project layout

```
site.config.js          contact details, form endpoint, capacity: the one config file
content/                products.json, materials.json, company.json
index.html, products/, materials/, quote/, 404.html
src/build/render.js     build-time templating ({{> partial}} tags)
src/js/lamination/      geometry.js (pure maths), svg.js (diagrams), three-kit.js (3D)
src/js/intro/           scroll intro
src/js/                 main.js (nav), quote.js (form), minis.js (product visuals)
src/styles/main.css     all styles; brand colours and theme tokens as CSS variables at the top
api/quote.js            optional Vercel function for the form
public/                 logo, icons, Open Graph image, photo slots
```
