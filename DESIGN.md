---
name: MANZZA
description: Transformer core laminations presented in SpaceX's design language (awesome-design-md, design/reference/spacex.DESIGN.md) in the client's black, deep navy and electric blue — condensed uppercase DIN-style display type, full-bleed imagery, one ghost pill per band.
source: design/reference/spacex.DESIGN.md (VoltAgent/awesome-design-md, MIT)
colors:
  canvas-night: "#000000"
  navy: "#081226"
  navy-deep: "#050b19"
  electric-blue: "#2f6bea"
  electric-blue-hover: "#4a82ff"
  electric-blue-text: "#6e9bff"
  on-primary: "#ffffff"
  on-primary-mute: "#eef2ff"
  body: "rgba(226, 234, 255, 0.74)"
  note: "rgba(226, 234, 255, 0.54)"
  hairline-on-dark: "#1d2a4a"
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
    hover: "electric-blue fill wipes in from the left, outline turns blue"
  button-filled:
    backgroundColor: "{colors.electric-blue}"
    textColor: "{colors.on-primary}"
    use: "quote form submit only"
  text-input:
    backgroundColor: "{colors.canvas-night}"
    border: "1px solid {colors.hairline-on-dark}"
    focus: "{colors.electric-blue} border"
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
- **One filled button:** the quote form's submit uses `button-filled`, electric blue (SpaceX keeps
  filled buttons for its shop's transactional actions; sending a quote is ours).
- **Colour:** SpaceX is black and white only. The client brief (§8) sets MANZZA's primaries
  as black, deep navy and electric blue, for a "premium black and electric-blue industrial
  design system", and the brand personality as powerful, innovative, technical and
  dependable. So: black is the stage (film, product bands, hero); deep navy carries the
  alternate chapters, footer and menus; electric blue (the logo's bolt, #2f6bea) is the
  one accent — button fills on hover, the submit button, rules, eyebrows, focus, the
  table head rule, and a glow rising behind the closing call to action. Small blue text
  uses a lighter tint (#6e9bff) to stay above 6:1 on black and navy.

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
- **Hairline draw:** section rules draw left to right in electric blue as their section
  enters, then settle to navy.
- **Ghost pill:** an electric-blue fill wipes in from the left on hover.
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
- Don't add colours beyond black, deep navy, electric blue and white; no shadows, rounded
  tiles or glass. The only gradient is the blue glow behind the closing call to action.
- Don't add copy that the client brief or the user did not supply.
