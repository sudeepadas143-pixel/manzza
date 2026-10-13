# Style reference

Each style lists its palette convention, parameters (`default · range`), the
gallery looks it reproduces, and tuning tips. Every style also accepts the
global options `speed`, `grain`, `seed`, `quality`, `animate`.

Contents: [flow](#flow) · [mesh](#mesh) · [aurora](#aurora) · [silk](#silk) · [sky](#sky) ·
[waves](#waves) · [mist](#mist) · [bars](#bars) · [prism](#prism) · [rings](#rings) ·
[glow](#glow) · [stripes](#stripes) · [forms](#forms) · [watercolor](#watercolor) · [swirl](#swirl)

---

## flow
Liquid, iridescent field. This is the "Stripe hero" / "Fluid." / "Iridescent cloud" look.
**Technique:** three rounds of domain warping (`f(p + f(p + f(p)))`) on 2-octave simplex
noise, mapped through an OKLab ramp.
**Palette:** any order, 3–5 colours. The ramp is swept end to end, so put the colour you
want the most of in the middle. Light-dominant palettes read as pastel and airy. Alternating
light and dark reads as chrome or marble.

| param | default · range | effect |
|---|---|---|
| `scale` | 1 · 0.3–3 | feature size; <1 = bigger, calmer shapes |
| `warp` | 1 · 0–2 | how much the field folds into itself; 0 = plain soft noise |
| `contrast` | 1 · 0.3–2 | how much of the ramp is used; lower = hazier, flatter |

Tips: behind body text use `contrast: 0.6, warp: 0.7, speed: 0.6`. For a dark hero, use
`['#0B0F2A', '#3B2D8F', '#E26DB0', '#FFC7A1']` with `contrast: 1.2`.

## mesh
Soft colour points blended by inverse-distance weighting in OKLab, which is the Figma/Apple
"mesh gradient". **Palette:** one colour per control point (2–6).

| param | default · range | effect |
|---|---|---|
| `points` | 6 preset spots | `[[x, y], …]` in 0..1, y from the top; one per colour |
| `blend` | 2.4 · 1–6 | IDW power; low = everything melts together, high = distinct regions |
| `drift` | 1 · 0–3 | how far points wander |
| `warp` | 1 · 0–3 | organic wobble of the blend boundaries |

Tips: put the background colour first and position its point in an empty corner. Mesh renders at
quality 0.35 by default because it is nearly free, so use it for many cards at once.

## aurora
Night sky with two curtains of vertical rays and a bright lower edge, plus optional
twinkling stars. **Palette:** brightest highlight → … → night background (4–5).
Example: `['#EDFFEB', '#5FE896', '#2E7A6A', '#132B45']`.

| param | default · range | effect |
|---|---|---|
| `scale` | 1 · 0.3–3 | ray density |
| `fold` | 1 · 0–2.5 | how much the curtain swoops |
| `height` | 1 · 0.3–2.5 | how far rays reach upward |
| `intensity` | 1 · 0.2–2 | overall brightness |
| `stars` | 0.6 · 0–1 | star field amount (0 to hide) |

Tips: place headings in the dark upper third or over the dark bottom band.

## silk
Lit satin folds: a sine heightfield warped by noise, with normals from finite differences,
wrapped diffuse lighting, a sheen highlight and AO. **Palette:** darkest shadow → lightest
sheen (4–6). Monochrome ramps of one hue look the most luxurious.

| param | default · range | effect |
|---|---|---|
| `folds` | 4 · 1–10 | number of folds across the frame |
| `angle` | 40 · −90–90 | fold direction in degrees |
| `warp` | 1 · 0–2.5 | how irregular the folds are |
| `sheen` | 1 · 0–2 | specular highlight strength |
| `scale` | 1 · 0.4–2.5 | zoom |

## sky
Vertical sky gradient with domain-warped clouds. **Palette:** cloud white → … → deepest sky (3–5).

| param | default · range | effect |
|---|---|---|
| `cover` | 0.5 · 0–1 | cloud coverage |
| `streak` | 1 · 0–3 | vertical squash, which stretches clouds into wisps |
| `wind` | 1 · 0–4 | drift speed |
| `scale` | 1 · 0.3–3 | cloud size |

Tips: `streak: 2.2, cover: 0.6` gives cirrus-like story backgrounds. Sunset skies work too:
`['#FFF4E6', '#FFC59E', '#F28C8C', '#6B4C9A']`.

## waves
Horizontal colour layers separated by soft, gently undulating boundaries (each colour is
one band). **Palette:** top band → bottom band (3–6). Light-to-dark reads as dusk over water.

| param | default · range | effect |
|---|---|---|
| `amplitude` | 1 · 0–3 | wave height |
| `frequency` | 1 · 0.2–3 | waves across the frame |
| `softness` | 1 · 0–3 | blur of each boundary; 0 = crisp paper-cut layers |

## mist
Sky, a sun disc, and 2–6 ridge layers of ridged noise. Each ridge fades into mist below
its crest, with slow parallax drift. **Palette:** sky → … → nearest/darkest ridge (4–6).

| param | default · range | effect |
|---|---|---|
| `layers` | 5 · 2–6 | ridge count |
| `haze` | 1 · 0–2 | mist between ridges |
| `rough` | 1 · 0.2–2.5 | mountain amplitude |
| `sun` | 1 · 0–1.5 | sun disc + glow (0 hides it) |
| `drift` | 1 · 0–4 | parallax speed |

## bars
A row of bars rising left to right, filled with a vertical gradient, with a soft glow above
each cap and a gentle bounce. **Palette:** background first, then bar colour top → bottom (4–6).

| param | default · range | effect |
|---|---|---|
| `bars` | 8 · 3–24 | number of bars |
| `gap` | 0 · 0–0.6 | gap between bars (fraction of bar width) |
| `rise` | 1 · 0–1 | 1 = staircase; 0 = all bars equal height |
| `wobble` | 1 · 0–3 | equaliser bounce |

## prism
Quantised columns whose heights follow a bell (or valley) envelope. Each column is a soft
vertical glow, so the result reads as a pixelated aurora/spectrum. **Palette:** dark
background → brightest glow (4–6).

| param | default · range | effect |
|---|---|---|
| `bars` | 11 · 3–40 | column count (high counts look smooth) |
| `angle` | 0 · −180–180 | 0 = rising from the bottom; −90 = extending from the left |
| `spread` | 1 · 0.3–2.5 | width of the bell |
| `valley` | 0 · 0–1 | 1 inverts the envelope (tall at the edges) |
| `softness` | 1 · 0.2–2 | how gradually each column fades at its tip |

## rings
Concentric rings expanding slowly from an off-canvas centre. Bands shade toward their outer
edge, with a crisp bright rim. **Palette:** inner → outer (4–6); the last colour mixed with
white lights the rims.

| param | default · range | effect |
|---|---|---|
| `rings` | 9 · 2–30 | ring density |
| `cx`, `cy` | −0.9, −0.75 · ±1.5 | ring centre in centred units (0,0 = middle) |
| `glow` | 1 · 0–2 | rim brightness |
| `depth` | 1 · 0–3 | in-band shading (3D-ness) |

## glow
Up to three wobbling orbs (or a crescent) on a dark ground. Bodies use a light-direction
gradient, and the lit edge gets a thin rim, an inner glow and an outer halo.
**Palette:** background, body shadow → body lit side, rim colour last (4–6).

| param | default · range | effect |
|---|---|---|
| `blobs` | 3 · 1–3 | how many orbs |
| `size` | 1 · 0.4–2 | orb scale |
| `light` | 60 · −180–180 | light direction in degrees |
| `rim` | 1 · 0–2 | rim + glow strength |
| `crescent` | 0 · 0/1 | 1 cuts the orb into a crescent moon |
| `x`, `y` | 0 · ±1 | shift the whole composition |

## stripes
The ramp stepped into soft horizontal bands with a wave, like retro packaging.
**Palette:** top → bottom (3–6).

| param | default · range | effect |
|---|---|---|
| `bands` | 7 · 2–24 | number of steps |
| `softness` | 0.6 · 0–1 | 0 = hard steps, 1 = nearly smooth |
| `wave` | 1 · 0–3 | band undulation |
| `angle` | 0 · −90–90 | rotate the bands |

## forms
One large blurred shape with a centre-to-edge gradient and a halo on a flat ground.
**Palette:** background, then shape centre → edge (4–6).

| param | default · range | effect |
|---|---|---|
| `shape` | 0 · 0–5 | 0 burst · 1 four-petal flower · 2 heart · 3 clover · 4 blob · 5 star |
| `size` | 1 · 0.3–2.5 | shape scale (1 ≈ 84% of the short side) |
| `blur` | 1 · 0–3 | edge softness; 2+ gives the out-of-focus look |
| `halo` | 1 · 0–2 | glow around the shape |
| `x`, `y` | 0.5 · 0–1 | centre position (y from the top) |
| `rotate` | 0 · −180–180 | rotation in degrees |

Tips: put the shape off-centre (`x: 0.65`) and set the type in the open space. Shapes
that run off the canvas edge feel more editorial.

## watercolor
Washes of pigment on paper. Colours combine by **Beer–Lambert absorption**
(`paper × e^(−absorbance)`), so overlaps mix subtractively like real paint. Washes have
darker drying edges and paper-tooth granulation. **Palette:** paper first, then one
pigment per colour (3–6).

| param | default · range | effect |
|---|---|---|
| `scale` | 1 · 0.4–2.5 | wash size |
| `wetness` | 0.6 · 0–1.5 | edge softness / bleed |
| `edges` | 1 · 0–2 | dark drying ring |
| `granulation` | 1 · 0–2 | paper texture in the pigment |

Tips: keep `speed` low (≤ 0.5); watercolour should barely breathe.

## swirl
A slow vortex twisting a linear gradient, like stirred paint. **Palette:** light → dark (3–6).

| param | default · range | effect |
|---|---|---|
| `twist` | 1 · −3–3 | strength and direction of the twist |
| `scale` | 1 · 0.4–2.5 | vortex size |
| `cx`, `cy` | 0.25, −0.05 · ±1 | vortex centre (centred units) |
