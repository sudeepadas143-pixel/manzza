# Recipes: CSS-only gradients, grain, legibility, performance

## CSS-only backdrops

Use these when you don't need motion, for many small cards, for email/OG images, or as
the first-paint fallback under a shader backdrop. `cssBackdrop(kind, colors)` generates
them, and the patterns below can be hand-written.

**Always interpolate in OKLab.** `in oklab` avoids the grey, desaturated midpoint you get
when blending complementary colours in sRGB. Supported in all evergreen browsers since
2023. Put a plain fallback declaration first for older engines:

```css
.card {
  background: linear-gradient(180deg, #ED6D3D, #FFF1CF);              /* fallback */
  background: linear-gradient(180deg in oklab, #ED6D3D, #FFF1CF);
}
```

**Mesh (stacked radial blobs)**: the most useful static look:

```css
.mesh {
  background:
    radial-gradient(80% 70% at 15% 12% in oklab, #B28FCE, transparent 58%),
    radial-gradient(90% 80% at 85% 16% in oklab, #F4B3C2, transparent 58%),
    radial-gradient(100% 90% at 24% 88% in oklab, #A0D8EF, transparent 58%),
    #EAF4FC;
}
/* optional airy wash on top: add as the first layer */
/* linear-gradient(rgba(255,253,250,.4), rgba(255,253,250,.4)), */
```

**iOS wallpaper**: a diagonal linear gradient plus a soft white highlight in the top-left:
```css
background:
  radial-gradient(90% 70% at 12% 8%, rgba(255,255,255,.28), transparent 60%),
  linear-gradient(135deg in oklab, #A0D8EF, #EAF4FC, #F4B3C2, #FDEFF2);
```

**Conic halo**:
```css
background: conic-gradient(from 210deg at 50% 50% in oklab, #F6D5F7, #FBE9D7, #C6E6F5, #D9CCF4, #F6D5F7);
```

**Retro / risograph**: big warm blobs plus heavy grain (0.3–0.4) for a 70s print feel.

**Animating CSS gradients cheaply:** register custom properties so the browser can
interpolate them, then animate positions or colours:

```css
@property --x { syntax: '<percentage>'; inherits: false; initial-value: 20%; }
.mesh-anim {
  background: radial-gradient(80% 70% at var(--x) 20% in oklab, #B28FCE, transparent 60%), #EAF4FC;
  animation: drift 18s ease-in-out infinite alternate;
}
@keyframes drift { to { --x: 80%; } }
```

This is fine for one or two layers. For anything richer, use the shader runtime, which is cheaper
than repainting many large radial gradients every frame.

## Grain

Grain hides banding, adds tactility, and makes flat gradients feel printed.
The runtime's `grain` option overlays a 256² tiled noise PNG whose noise lives in the alpha channel
(white/black specks), so it uses plain alpha compositing and no blend mode, which keeps Safari fast.
Use 0.08–0.15 for subtle grain, 0.2–0.3 for visible grain, and 0.35+ for a retro look.

**CSS-only grain (no JS)** using an inline SVG turbulence filter:

```css
.grain::after {
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 .5  0 0 0 0 .5  0 0 0 0 .5  0 0 0 1.2 -0.1'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
  mix-blend-mode: overlay; opacity: .25;
}
```
That's fine over static CSS gradients. Over an *animating* canvas, prefer the runtime's `grain` option:
a blend-mode layer the size of the viewport costs Safari a full re-blend every frame.

**JS grain without the runtime:** `GradientBackdrop.grainURL()` returns a PNG data URL you can
use anywhere: `el.style.background = \`url(${grainURL()}) 0 0/256px, ${cssBackdrop('mesh', cols)}\``.

## Text legibility on backdrops

1. **Choose ink from the palette's extreme**: the darkest stop on light looks, the lightest on dark looks.
   Tinted ink (e.g. `#323F78` on a pastel flow) looks far more designed than pure black.
2. **Check contrast at the worst spot.** Moving backdrops pass under the text, so check against the lightest
   and darkest colours the text can sit over, not the average. WCAG AA requires 4.5:1 for body text and 3:1 for large text.
3. **Calm the field behind text:** lower `contrast` (flow), `warp`, `intensity`, or `speed`.
4. **Scrims**: a soft gradient between backdrop and text:
   ```css
   .hero::before { content:''; position:absolute; inset:0; z-index:-1; pointer-events:none;
     background: radial-gradient(60% 50% at 50% 50%, rgba(255,255,255,.55), transparent 70%); }
   ```
   (z-index −1 inside the isolated hero puts it above the canvas but below content: the canvas is
   inserted first, so later siblings with the same z-index paint on top.)
5. **Frosted panel**: `backdrop-filter: blur(20px) saturate(1.2); background: rgb(255 255 255 / .35);`
   works well over moving gradients.
6. Large display type (serif or tight grotesk, 64px+) survives busy backgrounds far better than body copy.
   Keep paragraphs on calmer areas.

## Layering patterns

- **Hero + content:** backdrop on the hero `<section>`; content are normal children.
- **Whole page:** a fixed full-viewport element behind everything:
  ```html
  <div class="page-bg" data-backdrop="mesh" data-colors="…" aria-hidden="true"></div>
  <style>.page-bg{position:fixed;inset:0;z-index:-1}</style>
  ```
- **Cards:** one backdrop per card is fine. The first 12 get their own context and the rest fall back to the shared renderer. Use `mesh`/`flow`
  (cheap) and set `speed: 0.5`.
- **Blend with UI chrome:** set the page `background-color` to the backdrop's first or last stop so
  overscroll and edges don't flash white.
- **Theme switch:** `bd.set({ colors: dark ? darkPalette : lightPalette })`. It updates instantly with no rebuild.

## Performance checklist

- The defaults handle the big things: direct rendering with no copies, pause when off-screen (IntersectionObserver),
  pause when the tab is hidden (rAF), per-style render scale, and a cap of 2.4 MP per backdrop.
- On mobile, prefer `flow`, `mesh`, `waves`, `stripes` or `sky`. `silk`, `mist` and `watercolor` do more work per pixel.
- If you need more speed, lower `quality` (e.g. 0.35) and `maxPixels`. Soft styles show no visible difference.
- `animate: false` renders exactly one frame, which is ideal for static sections or print/OG output.
- Avoid putting the backdrop element inside something with CSS `filter`/`transform` animations,
  because that forces extra compositing.

## Accessibility checklist

- `prefers-reduced-motion: reduce` freezes backdrops by default (`respectReducedMotion: true`).
  Keep it on.
- Any animated backdrop visible for more than 5 seconds next to content should have a pause control
  (WCAG 2.2.2). The API makes this a one-liner: `button.onclick = () => bd.toggle()`.
- The canvas and grain layers are `aria-hidden` and `pointer-events: none`. Never put meaning only in
  the backdrop.
- Avoid fast, high-contrast flicker (`speed` > 3 with dark/light palettes).
