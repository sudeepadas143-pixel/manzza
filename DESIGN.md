---
name: MANZZA
description: Transformer core laminations, presented with Apple's product-page grammar on black.
colors:
  ink-950: "#0a0b0d"
  elev-1: "color-mix(in srgb, #fff 4%, #0a0b0d)"
  elev-2: "color-mix(in srgb, #fff 7%, #0a0b0d)"
  elev-3: "color-mix(in srgb, #fff 10%, #0a0b0d)"
  elev-4: "color-mix(in srgb, #fff 13%, #0a0b0d)"
  steel-50: "#f4f5f7"
  steel-100: "#e4e7eb"
  steel-200: "#cfd4da"
  steel-300: "#aeb4bc"
  steel-400: "#8b929b"
  line: "rgba(255, 255, 255, 0.1)"
  brand-blue: "#2f6bea"
typography:
  display:
    fontFamily: "Geist Variable, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "clamp(2.75rem, 7.4vw, 6rem)"
    fontWeight: 600
    lineHeight: 1.02
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "clamp(2rem, 4.6vw, 3.5rem)"
    fontWeight: 600
    lineHeight: 1.07
    letterSpacing: "-0.028em"
  lead:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "clamp(1.1875rem, 1.7vw, 1.4375rem)"
    fontWeight: 500
    lineHeight: 1.38
    letterSpacing: "-0.016em"
  body:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "-0.011em"
  label:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  field: "12px"
  card-sm: "18px"
  tile: "28px"
  pill: "980px"
spacing:
  section-y: "clamp(88px, 12vw, 160px)"
  tile-gap: "16px"
  gutter: "20px / 32px / 44px"
components:
  button-primary:
    backgroundColor: "{colors.steel-100}"
    textColor: "{colors.ink-950}"
    rounded: "{rounded.pill}"
    height: "44px"
    padding: "0 22px"
  button-primary-hover:
    backgroundColor: "{colors.steel-50}"
  button-primary-active:
    backgroundColor: "{colors.steel-200}"
  button-primary-lg:
    height: "52px"
    padding: "0 30px"
  button-primary-sm:
    height: "36px"
    padding: "0 16px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.steel-100}"
    rounded: "{rounded.pill}"
  link-chevron:
    textColor: "{colors.steel-100}"
  tile:
    backgroundColor: "{colors.elev-2}"
    rounded: "{rounded.tile}"
    padding: "32px 28px"
  field:
    backgroundColor: "{colors.elev-3}"
    textColor: "{colors.steel-100}"
    rounded: "{rounded.field}"
---

## Overview
Apple's product-page grammar applied to an industrial component: the lamination is
presented like a flagship product. Black ground, one neo-grotesk family set large and
tight, quiet grey supporting copy, graphite tiles that lighten as they rise, and a light-steel
accent for the things a visitor can act on. Sections open with a centred headline.
The home page begins with a WebGL scroll film; everything after it is calm by design.

## Colors
Steel, built in three tiers in `main.css` (primitives → semantic → component), following
dark-mode-design-expert. The page is `ink-950`, a cool near-black (never #000). Raised
surfaces get lighter, not shadowed: `elev-1` for alternate chapters and the footer,
`elev-2` for tiles, `elev-3` for fields, hover and the dropdown, `elev-4` for pressed
states. Text is off-white `steel-100` (15.9:1, inside the 12–16:1 comfort band, never
pure white), `steel-300` for body (9:1) and `steel-400` for notes (6:1). The accent is
light steel: the primary pill, links, marks and highlights. Electric blue `brand-blue` is
kept for the logo's bolt and the intro film; it is not an interface colour.

## Typography
Geist (self-hosted via @fontsource-variable/geist) for everything; figures use tabular
numerals rather than a monospace face. Sentence case throughout, no all-caps labels.
Headlines are semibold with tight negative tracking; a two-tone headline sets its second
sentence in `text-3`. `text-wrap: balance` on headings, `pretty` on paragraphs.

## Layout
Max content width 1180px. Section rhythm `section-y` (clamp 72–128px) top and bottom. Section heads are
centred; content below may be left-aligned when it is a table or prose. The product
lineup is three equal columns of centred picture, name, line and actions.

## Elevation & Depth
Flat. Depth is tonal (lighter surfaces rise), not shadows; only the translucent
header and dropdown use blur (saturate 180%, blur 20px) and the dropdown a soft shadow.

## Shapes
Pills for buttons, 28px tiles (22px on phones), 18px small cards, 12px fields, round
radio marks and status dots. No cut corners, no outlines around tiles.

## Components
- Primary button: light-steel pill, near-black sentence-case label in regular weight, 44px minimum target (the 36px small pill gets an invisible 44px hit area); hover
  lightens, press darkens and scales to 0.97; focus is a 2px steel ring offset from the pill.
- Secondary button: steel-outlined pill; hover adds a faint fill.
- Chevron link: off-white text with a drawn chevron that nudges 2px on hover; underline on hover.
- Tile: graphite, 28px radius, no border.
- Product lineup item: picture tile, name,
  one line, then "Request a quote" (small pill) and "Learn more ›".

## Do's and Don'ts
- Do keep one filled steel action per view; everything else is a link or outline.
- Do keep labels in sentence case and buttons free of arrows.
- Don't add labels above headings or 01/02/03 numbering unless the content is a real sequence.
- Don't use gradient text beyond the hero's product name.
- Don't outline tiles or add shadows to them.
- Don't use pure black (#000) or pure white (#fff) for surfaces or text.
- Don't use blue for interface controls; it belongs to the logo and the film.
