---
name: gradient-backdrops
description: >-
  Build animated or static gradient backgrounds for web projects — hero
  backdrops, section backgrounds, poster/social cards, story frames. Ships a
  drop-in, dependency-free WebGL runtime with 15 shader styles (flowing liquid
  gradients, mesh gradients, aurora, silk, sky/clouds, layered waves, misty
  mountains, glowing bars, prism columns, concentric rings, rim-lit glow orbs,
  soft stripes, blurred shapes like hearts/stars/flowers, watercolour washes,
  swirls), 29 gallery-style presets, CSS-only recipes (oklab mesh, iOS, conic,
  retro grain) and film grain. Use whenever someone wants a gradient
  background, animated backdrop, mesh/grainy/aurora/fluid gradient, a
  "Stripe-like" or "Apple-like" moving background, a shader background, or asks
  to recreate a look from a gradient generator site — even if they just say
  "make the hero background nicer" or "add a cool animated bg".
---

# Gradient Backdrops

Animated gradient backgrounds that look designed, not default. The runtime
(`assets/backdrop.js`) gives each backdrop **its own WebGL canvas and draws
straight into it** (the fast path in every browser, including Safari). Past 12
backdrops on one page, extras share one hidden context and are copied in, so
galleries still work. Colours are mixed in **OKLab** (no muddy grey
midpoints), every frame is **dithered** (no banding), and an optional **grain**
overlay adds the print-like texture that makes these looks feel expensive.

## Workflow

1. **Pick a look.** Match the brief to a style using the table below. When in
   doubt, start from a preset: `examples/gallery.html` shows every preset live.
   You can also open it for the user so they can tune it and copy the config.
2. **Pick colours.** Use the brand palette when there is one, and respect the
   style's **colour order** (table). Use 3–5 colours, 6 at most. Keep neighbouring
   stops reasonably close in lightness for soft looks. Put the extremes at the
   ends for dramatic ones.
3. **Install.** Copy `assets/backdrop.js` (plus `backdrop.mjs`/`backdrop.d.ts` for
   bundlers/TS) into the project, e.g. `src/lib/backdrop/`. Never hot-link it from
   the skill folder.
4. **Mount** declaratively or with JS (below). Give the element a CSS fallback
   background in the same colours so first paint isn't blank.
5. **Make text legible.** Check contrast over the busiest part of the backdrop.
   Add a scrim, lower `contrast`, or choose a calmer style if needed (see
   `references/recipes.md`).
6. **Respect motion & performance.** The defaults already pause off-screen, honour
   `prefers-reduced-motion`, and render soft styles at reduced resolution.
   Keep `speed` ≤ 1 for backgrounds behind reading content.

## Choosing a style

| Style | Looks like | Colour order | Good for |
|---|---|---|---|
| `flow` | liquid iridescent fluid, slow domain-warped swirls | any; the field sweeps the ramp | hero, SaaS landing, "always in motion" |
| `mesh` | soft blurred colour points (Figma/Apple mesh) | one colour per point | calm brand sections, cards |
| `aurora` | northern-lights curtains on a night sky | highlight → night bg | music, night/events, dark heroes |
| `silk` | lit satin folds with sheen | dark → light | luxury, fashion, posters |
| `sky` | blue sky with wispy clouds | cloud white → deep sky | travel, weather, "fresh" |
| `waves` | horizontal soft layered bands (sunset sea) | top → bottom | editorial, calm headers |
| `mist` | layered misty mountain ridges + sun | sky → nearest ridge | outdoors, wellness, editorial |
| `bars` | rising gradient bar chart / equaliser | bg, then bar top → bottom | music, data, launches |
| `prism` | stepped glowing columns (pixel aurora) | bg (dark) → glow (light) | tech, posters; `angle:-90, valley:1` for horizontal |
| `rings` | concentric glowing rings rippling out | inner → outer (rim light) | ambient, audio, calm tech |
| `glow` | rim-lit orbs / crescent moon on dark | bg, body dark → lit, rim | bold posters, dark mode, product |
| `stripes` | softly stepped horizontal bands | top → bottom | retro, supper-club, packaging |
| `forms` | one big blurred shape: burst, flower, heart, clover, blob, star | bg, centre → edge | social posts, playful brand moments |
| `watercolor` | pigment washes on paper with dark edges | paper, then pigments | craft, children's, editorial |
| `swirl` | slow twisting gradient vortex | light → dark | seasonal, organic, nature |

CSS-only (no JS at runtime, static): `cssBackdrop('mesh' | 'linear' | 'ios' | 'conic' | 'retro', colors)`.
Use these for small cards, emails/OG images, or when animation isn't wanted.

Full per-style parameter docs, gallery analogues and tuning tips are in
`references/styles.md`.

## Usage

**Declarative (plain HTML):** the script auto-mounts `[data-backdrop]` on load.

```html
<section class="hero" data-backdrop="fluid" data-grain="0.14">…</section>
<section data-backdrop="aurora" data-colors="#EDFFEB #5FE896 #2E7A6A #132B45"
         data-params='{"fold":1.4}' data-speed="0.8">…</section>
<script src="/lib/backdrop/backdrop.js"></script>
```

**JS / bundlers:**

```js
import { createBackdrop } from './lib/backdrop/backdrop.mjs';

const bd = createBackdrop(document.querySelector('.hero'), {
  style: 'flow',                       // or preset: 'iridescent-cloud'
  colors: ['#F6F9FF', '#9BE0E8', '#C4B5F7', '#F8B8D9'],
  params: { scale: 0.9, warp: 1 },     // per-style knobs
  speed: 1, grain: 0.12, seed: 0,
});
bd.set({ colors: [...] });  bd.pause();  bd.play();  bd.snapshot();  bd.destroy();
```

The runtime inserts a `<canvas>` (and a grain `<div>`) as the element's first
children with `z-index:-1`, and sets `isolation:isolate` (plus `position:relative`
if static) on the element, so the existing content stays on top with no extra CSS.
Pass a `<canvas>` element instead if you want to control placement yourself.

Framework wrappers (React/Next, Vue, Svelte, Astro) are in `references/frameworks.md`.

## Presets

`fluid`, `iridescent-cloud`, `lagoon`, `solar-flare`, `orchid` (flow) · `soft-signal`, `any-words` (mesh) ·
`night-swim`, `violet-veil` (aurora) · `amethyst`, `pearl-silk` (silk) · `blue-sky`, `start-here` (sky) ·
`tidal` (waves) · `field-notes` (mist) · `after-hours` (bars) · `citron`, `glacier` (prism) ·
`ambient` (rings) · `edge`, `moons` (glow) · `gather` (stripes) · `solstice`, `petal`, `with-love`,
`celtics`, `bloom` (forms) · `verdant` (swirl) · `paper-garden` (watercolor).
CSS presets: `slow-days`, `rosa`, `atelier`, `soft-signal`, `halo`.

Presets are a starting point. Swap in the project's colours while keeping the order convention.

## Showing the user options

To let the user choose, serve the skill's gallery and open it:
`python3 -m http.server <port> --directory ~/.claude/skills/gradient-backdrops`
→ `/examples/gallery.html`. Clicking a card opens a playground with colour pickers
and sliders, plus **Copy JS / Copy HTML** buttons that produce a ready-to-paste config.
`examples/hero.html` is a minimal full-page example.

## Adding or modifying a style

Each style is a GLSL fragment `main()` appended to a shared prelude that provides
`fragUV()`, `fragP()`, `rampLab(t)`, `lab(i)`, `col(i)`, `snoise`, `fbm`,
`fbmLo`, `rot`, `hash12/22`, `labToSRGB`, and `finish()` (dither). Register it in
`STYLES` with `params` (each becomes a `u_<name>` uniform). Recipes, the prelude
API, and the underlying techniques (domain warping, SDF shapes, Beer–Lambert
pigment, etc.) are in `references/techniques.md`. Keep project-specific styles in
the project's copy of `backdrop.js`, and update this skill's copy only for
general-purpose improvements.

## Gotchas

- **Colour order matters.** The same palette looks inverted in `aurora` vs `silk`. Check the table.
- **Behind text, calm it down.** Lower `contrast`/`warp`/`speed`, or add a scrim. Busy fields kill readability.
- **Don't raise `quality` on soft styles.** Flow/mesh/sky are blurry by nature; 0.35–0.5 render scale is
  indistinguishable from full res and several times cheaper. Crisp-edged styles (bars, prism, rings) default to 1.
- **SSR:** create backdrops only on the client (inside `useEffect`/`onMount`).
- **No WebGL:** the element automatically gets a static CSS mesh in the same colours.
- **Slow frame rate?** Open `examples/bench.html` in the browser in question. It shows live fps,
  render size and mode, and lets you toggle style, `mode: 'direct' | 'shared'` and grain.
  Don't put `mix-blend-mode`, `filter` or `backdrop-filter` layers over a large animating canvas.
  Safari re-composites those every frame. A frosted panel over *part* of the page is fine.
- **Fonts on the canvas:** none. Typography stays in HTML, so it stays accessible and crisp.

## Reference files

- `references/styles.md`: every style's parameters, palette guidance, gallery analogues, and tuning tips.
- `references/recipes.md`: CSS-only gradients, grain (PNG and SVG), text legibility, layering, performance and accessibility checklists.
- `references/frameworks.md`: React/Next.js, Vue/Nuxt, Svelte, Astro and Tailwind integration.
- `references/techniques.md`: how the renderer and each technique work, the prelude API, how to write a new style, and video/PNG export.
