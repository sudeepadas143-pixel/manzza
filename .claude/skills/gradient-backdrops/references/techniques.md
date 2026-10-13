# Techniques & extending the runtime

How the pieces work, so you can tune existing styles or write new ones.

## Architecture

```
createBackdrop(el) ──► <canvas> in el with its OWN WebGL context  (direct, default)
                       <div grain> (plain alpha, no blend mode)
          …after 12 per page ──► <canvas 2d> ◄── drawImage ── one hidden shared WebGL canvas  (shared overflow)

one requestAnimationFrame loop ─► for each visible, playing backdrop:
     time += dt × speed → set uniforms → draw (→ copy, shared mode only)
```

- **Why direct by default:** drawing straight into the visible canvas needs no copy. Copying a WebGL
  canvas into a 2D canvas is nearly free in Chromium (~0.3 ms), but in Safari it can force a GPU→CPU
  readback every frame, which tanks frame rate on a full-screen hero.
- **Why a shared overflow:** browsers cap live WebGL contexts at around 16 per page and drop the oldest.
  Past `MAX_DIRECT` (12) backdrops, extras render in one hidden context and are copied into 2D canvases.
  Pass `mode: 'direct'` or `mode: 'shared'` to force either.
- **Grain without blend modes:** the grain tile stores the noise in its alpha channel (white/black specks),
  so it composites with plain alpha. `mix-blend-mode: overlay` over an animating canvas makes the
  compositor re-blend the full area every frame, which is expensive in Safari.
- **No black flash:** a direct WebGL canvas is drawn synchronously on creation and on every resize
  (resizing clears it), before the next paint.
- **Full-screen triangle:** vertices `(-1,-1) (3,-1) (-1,3)` cover the viewport with a single
  triangle (no diagonal seam, slightly faster than a quad).
- **Render scale:** soft styles render at 35–60% of CSS px × DPR and are upscaled by the browser.
  Blurry content hides the upscale completely.
- **Pausing:** IntersectionObserver marks off-screen backdrops invisible, and rAF stops in hidden tabs.
  When nothing animates, the loop stops entirely.
- **Uniforms every style receives:** `u_res` (px), `u_time` (s × speed, offset by seed),
  `u_seed`, `u_count` (palette size), `u_rgb[6]` (sRGB 0..1), `u_lab[6]` (OKLab), plus
  `u_<param>` for each declared param.

## Colour: OKLab ramps

Colours are converted to OKLab on the CPU. Shaders mix in OKLab (`rampLab`, `mix(lab(a), lab(b), t)`)
and convert back with `labToSRGB`. Lightness changes evenly and hues don't pass through grey,
so blue→orange goes through a clean, desaturated warm grey instead of mud.
Lighten or darken with `L.x += 0.05` (L is perceptual lightness). Mix toward white with `mix(L, LAB_WHITE, k)`.

**Dither:** `finish()` adds ±0.5/255 hash noise before quantisation. Without it, slow gradients show
8-bit contour bands, especially on dark palettes.

## Noise toolbox (prelude)

| function | use |
|---|---|
| `snoise(vec3)` | simplex noise, −1..1, smooth. Use z for time to get evolving 2D noise |
| `fbm(vec3)` | 4 octaves, about ±0.9: detailed clouds, textures |
| `fbmLo(vec3)` | 2 octaves: big soft shapes (flow, mesh wobble) |
| `hash12/hash22(vec2)` | per-cell randoms (stars, per-bar jitter, layout) |

Rules of thumb: low frequency combined with few octaves reads as premium and soft, while high frequency
with many octaves reads as busy marble. Most "designed" backdrops live at 0.5–1.5 cycles per screen.

## Technique notes per style

- **Domain warping (flow, sky, watercolour):** instead of `f(p)`, sample `f(p + k·g(p))` where `g` is
  more noise. Nesting it two or three times (`q = fbm(p)`, `r = fbm(p + q)`, `f = fbm(p + r)`)
  produces folded, liquid shapes. This is Inigo Quilez's "warp" article technique. The amount `k`
  is the `warp` knob.
- **Inverse-distance mesh:** `col = Σ wᵢ·cᵢ / Σ wᵢ` with `wᵢ = 1/dᵢᵖ`. The power `p` (`blend`)
  controls how regional the blend is. Blending in OKLab keeps it clean.
- **Curtains (aurora):** take noise with high x-frequency and very low y-frequency, which gives
  vertical rays. Multiply by an exponential falloff above a wavy baseline and a sharp step below it.
- **Heightfield shading (silk):** define `h(p)`, then get normals from finite differences
  (`N = normalize(-dh/dx·k, -dh/dy·k, 1)`) and apply wrapped diffuse + Blinn specular. Map the
  *shading value* (not the height) through the palette ramp, so the palette is the light.
- **Layered silhouettes (mist, waves):** paint far→near. Each layer is
  `smoothstep(h + aa, h − aa, y)` with `h` from ridged noise `(1 − |n|)²`. Mist is the layer colour
  mixed toward the sky colour as you go down from the crest.
- **Quantised envelopes (bars, prism):** `i = floor(x·n)`. Compute an envelope at the column centre,
  then do continuous work inside the column. The stepped edges come from `floor`, the softness from
  the in-column `smoothstep`.
- **Polar SDF shapes (forms):** `R(θ)` gives shapes like `R·(1 + a·cos(kθ))` (burst/star) or
  `|cos(2θ)|^p` (petals). `d = r − R(θ)` and `smoothstep(b, −b, d)` with a large `b` gives the
  out-of-focus look. Fill with `r/R` so the gradient follows the shape.
- **Rim light (glow):** `exp(−|d|/w)` makes a thin line on the SDF boundary, multiplied by
  `smoothstep(dot(normal, lightDir))` so only the lit side glows. Add an inner `exp(d/w₂)` and an outer
  halo `exp(−d·k)`.
- **Beer–Lambert (watercolour):** absorbance per pigment is `A = −ln(pigment/paper)`, and
  `colour = paper · exp(−Σ Aᵢ·densityᵢ)`. Overlaps darken and shift hue the way real glazes do. Edge
  darkening is a gaussian ridge at the wash boundary.

## Writing a new style

1. Add an entry to `STYLES` in `backdrop.js`:

```js
STYLES.plasma = {
  label: 'Plasma',
  order: 'any order, cycles through the ramp',
  quality: 0.5,
  params: { scale: [1, 0.3, 3, 0.05], bands: [2, 0.5, 6, 0.1] },
  frag: `
uniform float u_scale, u_bands;
void main() {
  vec2 p = fragP() * 3.0 * u_scale;
  float t = u_time * 0.2;
  float v = sin(p.x + t) + sin(p.y * 1.3 - t) + sin(length(p) * 1.7 + t * 0.7)
          + 0.6 * snoise(vec3(p * 0.5, t * 0.3));
  float k = 0.5 + 0.5 * sin(v * u_bands * 0.5);   // 0..1
  gl_FragColor = finishLab(rampLab(k));
}`,
};
```

2. Use it: `createBackdrop(el, { style: 'plasma', colors: [...] })`. It also appears automatically in the
   gallery playground.
3. Compile errors are logged to the console with the shader info log. The style then falls back to a
   static CSS mesh.

GLSL ES 1.00 constraints (WebGL1, for maximum compatibility):
- Loops need constant bounds. Use `for (int i = 0; i < 6; i++) { if (float(i) > u_count - 0.5) break; … }`.
- Index uniform arrays only with loop indices or constants. Use `lab(i)`/`col(i)` for computed indices.
- No implicit int↔float conversion: write `float(i)`, `1.0`, not `1`.
- Arrays can't be initialised. Use a function with `if` chains (see `blobDef` in `glow`).

Seamless loops (for exported video): drive time-varying noise around a circle instead of linearly,
e.g. `snoise(vec3(p + 0.6 * vec2(cos(TAU*phase), sin(TAU*phase)), 0.0))` where `phase = time / loopSeconds`.

## Exporting video

**Quick (WebM):**
```js
const stream = bd.canvas.captureStream(60);
const rec = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp9', videoBitsPerSecond: 12e6 });
const chunks = []; rec.ondataavailable = (e) => chunks.push(e.data);
rec.start(); setTimeout(() => rec.stop(), 8000);
rec.onstop = () => { const url = URL.createObjectURL(new Blob(chunks, { type: 'video/webm' })); /* download */ };
```
**Frame-exact MP4:** step `bd.time` manually (`bd.pause(); bd.time = i / fps; bd.render()`), wait a
frame, then feed `new VideoFrame(bd.canvas, { timestamp })` into a WebCodecs `VideoEncoder`
(`avc1.640028`) and mux with the `mp4-muxer` npm package. Render at `quality: 1` for export.
This is how dedicated gradient tools produce MP4 "reels" in the browser.

## Lineage / credits

- Simplex noise: Ashima Arts & Stefan Gustavson (MIT), `webgl-noise`.
- Hash without sine: Dave Hoskins (MIT).
- Domain warping, heart SDF: Inigo Quilez, iquilezles.org articles.
- OKLab: Björn Ottosson.
- Look & feel inspired by feralui.dev's gradient gallery. The implementation here is original;
  their code and their compositions are their own.
