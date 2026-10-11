# 002 — Light the small product visuals like the intro's dark studio

- **Status**: TODO
- **Commit**: 896967b
- **Severity**: LOW
- **Category**: Cohesion & tokens
- **Estimated scope**: 1 file, ~3 lines

## Problem

The scroll intro reflects a black room with soft boxes (`studioEnvironment(renderer, { dark: true })`
in `src/js/intro/scene.js`), but the small rotating product visuals still reflect the
mid-grey room made for the old light theme:

```js
// src/js/mini-scenes.js (search: studioEnvironment) — current
const env = studioEnvironment(renderer);
```

On the dark cards this makes the steel look flatter and greyer than the same
steel in the intro a scroll above.

## Target

```js
const env = studioEnvironment(renderer, { dark: true });
```
and raise `scene.environmentIntensity` from `1.25` to the value that matches the
intro's steel by eye (start at `1.6`; this is a feel decision, see Verification).

## Repo conventions to follow

- `studioEnvironment` lives in `src/js/lamination/three-kit.js`; the `dark` option already exists.

## Steps

1. In `src/js/mini-scenes.js`, pass `{ dark: true }` to `studioEnvironment`.
2. Change `scene.environmentIntensity = 1.25` to `1.6`.

## Boundaries

- Do NOT change `three-kit.js`, geometry, rotation speeds or the intro.

## Verification

- **Mechanical**: `npx vite build` succeeds.
- **Feel check**: open `/products/mitre-core` next to the end of the home intro.
  The hero visual's steel should read as the same material: dark faces, bright
  streaks, not uniformly grey. If faces go muddy, step the intensity up by 0.2.
- **Done when**: the two look like the same steel to a fresh pair of eyes.
