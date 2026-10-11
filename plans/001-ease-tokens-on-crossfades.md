# 001 — Use the shared ease-out curve on the two remaining crossfades

- **Status**: TODO
- **Commit**: 896967b
- **Severity**: LOW
- **Category**: Cohesion & tokens
- **Estimated scope**: 1 file, 2 lines

## Problem

Two opacity crossfades still use the browser's default `ease` while every other
transition on the site uses the shared tokens defined at the top of
`src/styles/main.css` (`--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`).

```css
/* src/styles/main.css (search: .mini__fallback) — current */
.mini__fallback { position: absolute; inset: 0; display: grid; place-items: center; padding: 8%; transition: opacity 0.6s; }
/* src/styles/main.css (search: .intro--gl .intro__canvas) — current */
html.js:not(.rm) .intro--gl .intro__canvas { display: block; opacity: 0; transition: opacity 0.4s; }
```

## Target

```css
.mini__fallback { …; transition: opacity 0.6s var(--ease-out); }
html.js:not(.rm) .intro--gl .intro__canvas { display: block; opacity: 0; transition: opacity 0.4s var(--ease-out); }
```

Durations stay: both are one-time reveals on a marketing page, where longer than
300 ms is allowed.

## Repo conventions to follow

- Tokens: `--ease-out` and `--ease-drawer` in `:root` at the top of `src/styles/main.css`.
- Exemplar: `.dd` (search: `transition: opacity 0.12s var(--ease-out)`).

## Steps

1. Append ` var(--ease-out)` after `opacity 0.6s` in the `.mini__fallback` rule.
2. Append ` var(--ease-out)` after `opacity 0.4s` in the `.intro--gl .intro__canvas` rule.

## Boundaries

- Do NOT change durations, selectors or any other rule.
- If either rule no longer matches the excerpt above, STOP and report.

## Verification

- **Mechanical**: `npx vite build` succeeds.
- **Feel check**: load `/` and a product page with DevTools Animations at 10%; the
  3D visuals should appear quickly and settle, with no slow start.
- **Done when**: `grep -n "transition: opacity 0\.[46]s;" src/styles/main.css` returns nothing.
