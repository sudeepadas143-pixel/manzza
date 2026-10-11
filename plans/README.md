# Animation plans

From an `improve-animations` audit of the site's motion. Each plan is
self-contained; run them in order with any agent.

## Audit result

| # | Severity | Category | Location | Finding | Status |
| --- | --- | --- | --- | --- | --- |
| – | HIGH | Performance | `src/js/intro/scene.js` | Camera stopped dead at every keyframe (eased per segment): read as choppy | DONE: Catmull-Rom path |
| – | HIGH | Performance | `src/js/intro/index.js` | Render scheduled one rAF after the scroll update: a frame of lag | DONE: render in the GSAP tick |
| – | HIGH | Performance | `src/js/intro/scene.js` | Shaders compiled the first time each part appeared: hitches mid-scroll | DONE: warm-up render |
| – | MEDIUM | Performance | `src/js/intro/scene.js` | VSM shadow blur passes and pixel ratio 2 on every frame | DONE: PCF, ratio 1.5, adaptive |
| – | MEDIUM | Physicality | `src/styles/main.css` `.dd` | Dropdown not anchored to its trigger; closed as slowly as it opened | DONE |
| – | MEDIUM | Accessibility | `src/styles/main.css` | Hover motion and colour changes not gated: stuck after tap | DONE |
| – | MEDIUM | Accessibility | `src/styles/main.css` | Reduced motion removed every transition, including fades | DONE: movement off, fades kept |
| – | MEDIUM | Purpose | `src/styles/main.css` `.btn` | No press feedback | DONE: `scale(0.97)` on `:active` |
| 001 | LOW | Cohesion | `src/styles/main.css` | Two crossfades on default `ease` | TODO |
| 002 | LOW | Cohesion | `src/js/mini-scenes.js` | Product visuals lit by the old light studio | TODO |

## Order

1. `001-ease-tokens-on-crossfades.md`
2. `002-minis-dark-studio.md` (independent of 001)
