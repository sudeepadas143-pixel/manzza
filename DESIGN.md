---
name: MANZZA
description: Transformer core laminations presented in SpaceX's design language (awesome-design-md, design/reference/spacex.DESIGN.md) — pure black, condensed uppercase DIN-style display type, full-bleed imagery, one ghost pill per band.
source: design/reference/spacex.DESIGN.md (VoltAgent/awesome-design-md, MIT)
colors:
  canvas-night: "#000000"
  canvas-night-soft: "#0a0a0a"
  on-primary: "#ffffff"
  on-primary-mute: "#f0f0fa"
  body: "rgba(240, 240, 250, 0.72)"
  note: "rgba(240, 240, 250, 0.52)"
  hairline-on-dark: "#3a3a3f"
  canvas-cool: "#f0f0fa"
  brand-blue: "#2f6bea"
typography:
  display-xxl:
    fontFamily: "Barlow Condensed, Arial Narrow, Arial, sans-serif"
    fontSize: "clamp(2.75rem, 8vw, 6.5rem)"
    fontWeight: 700
    lineHeight: 0.95
    letterSpacing: "0.02em"
    textTransform: uppercase
  display-xl:
    fontFamily: "Barlow Condensed"
    fontSize: "clamp(2.25rem, 5.4vw, 4.5rem)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.02em"
    textTransform: uppercase
  display-lg:
    fontFamily: "Barlow Condensed"
    fontSize: "clamp(1.75rem, 3.4vw, 3rem)"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "0.02em"
    textTransform: uppercase
  body-lg:
    fontFamily: "Barlow, Arial, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "0.02em"
  body-md:
    fontFamily: "Barlow"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "0.02em"
  button-cap:
    fontFamily: "Barlow"
    fontSize: "0.8125rem"
    fontWeight: 700
    letterSpacing: "0.09em"
    textTransform: uppercase
  micro-cap:
    fontFamily: "Barlow"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 2
    letterSpacing: "0.12em"
    textTransform: uppercase
rounded:
  xs: "4px"
  pill: "32px"
  full: "9999px"
components:
  button-ghost:
    backgroundColor: transparent
    border: "1px solid {colors.on-primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-cap}"
    rounded: "{rounded.pill}"
    padding: "18px 24px"
    hover: "white fill wipes in from the left, label turns black"
  button-filled-cool:
    backgroundColor: "{colors.canvas-cool}"
    textColor: "{colors.canvas-night}"
    use: "quote form submit only"
  text-input:
    backgroundColor: "{colors.canvas-night-soft}"
    border: "1px solid {colors.hairline-on-dark}"
    rounded: "{rounded.xs}"
  nav-bar-overlay:
    backgroundColor: transparent
    textColor: "{colors.on-primary}"
    typography: "{typography.micro-cap}"
---

## Overview
SpaceX's system applied to an industrial component. Every chapter is a band on pure
black, opened by one uppercase condensed headline and closed by at most one ghost pill.
The imagery is the design: until MANZZA supplies factory photographs, the steel is
shown by the site's own WebGL renders (the scroll film and the product scenes), lit by
a photographed studio and composed full-bleed like SpaceX's launch photography.

## Departures from the reference, and why
- **Imagery:** 3D renders stand in for photography; photo slots stay in place and take
  real factory photographs (`public/images/<id>.webp`) when they arrive.
- **Body text tiers:** SpaceX is white-only. Technical copy needs a reading tier, so body
  runs at 72% of `on-primary-mute` and notes at 52%. Headlines stay pure white.
- **Tables:** SpaceX's marketing pages have none. The client brief requires a technical
  specification table, so tables sit on `canvas-night-soft` with `hairline-on-dark` rules,
  values in display type.
- **One filled button:** the quote form's submit uses `button-filled-cool` (SpaceX keeps
  filled buttons for its shop's transactional actions; sending a quote is ours).
- **Brand blue:** stays in the logo's bolt and the scroll film. Never an interface colour.

## Typography
Barlow, one family in two widths: Barlow Condensed 700 for display, Barlow for body and
caps chrome. Barlow is drawn from highway signage like DIN 1451, which the reference's
D-DIN descends from, and is OFL-licensed. Display is always uppercase, tight leading
(0.95–1.05), positive tracking. Chrome (nav, buttons, eyebrows, labels) is caps with
wide tracking. Figures use tabular numerals.

## Layout
Full-width bands; type in a 1200px column. Product bands are at least one viewport tall
with the render filling the band and the copy anchored bottom-left. Sections are divided
by tone (`canvas-night` / `canvas-night-soft`) and 1px hairlines, never cards or shadows.

## Motion
Restrained and purposeful (the brief asks to avoid excessive animation). Each runs once
and is skipped entirely under `prefers-reduced-motion`.
- **Headline rise:** display headlines rise word by word out of a mask as they enter
  (700ms, ease-out-expo, 45ms stagger) — a film title card, not a bounce.
- **Hairline draw:** section rules draw left to right as their section enters.
- **Ghost pill:** a white fill wipes in from the left on hover; the label inverts.
- **Renders follow the scroll:** product renders turn with the band's scroll progress, so
  scrolling feels like walking round the part.
- **About statement:** words light up from 20% to full white as the paragraph scrolls
  through the viewport.
- **Capacity figure:** counts up once when it enters.
- **Navigation:** transparent over the film; hides while scrolling down, returns on
  scroll up; a solid black bar once past the first band.
- **Page change:** a short cross-fade between pages (view transitions).

## Do's and Don'ts
- Do keep display uppercase, condensed, tracked.
- Do keep one ghost pill per band; links elsewhere are underlined white text.
- Don't add accent colours, gradients, shadows, rounded tiles or glass.
- Don't add copy that the client brief or the user did not supply.
