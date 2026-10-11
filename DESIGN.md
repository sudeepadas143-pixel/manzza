---
name: MANZZA
description: Transformer core laminations, presented with Apple's product-page grammar on black.
colors:
  bg: "#000000"
  surface: "#161617"
  surface-2: "#232325"
  text: "#f5f5f7"
  text-2: "#a1a1a6"
  text-3: "#86868b"
  line: "rgba(255, 255, 255, 0.12)"
  blue: "#2f6bea"
  blue-hover: "#3b77f5"
  blue-press: "#2458c9"
  blue-link: "#6ea2ff"
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
    backgroundColor: "{colors.blue}"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    height: "44px"
    padding: "0 22px"
  button-primary-hover:
    backgroundColor: "{colors.blue-hover}"
  button-primary-active:
    backgroundColor: "{colors.blue-press}"
  button-primary-lg:
    height: "52px"
    padding: "0 30px"
  button-primary-sm:
    height: "34px"
    padding: "0 16px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.blue-link}"
    rounded: "{rounded.pill}"
  link-chevron:
    textColor: "{colors.blue-link}"
  tile:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.tile}"
    padding: "32px 28px"
  field:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
---

## Overview
Apple's product-page grammar applied to an industrial component: the lamination is
presented like a flagship product. Black ground, one neo-grotesk family set large and
tight, quiet grey supporting copy, graphite tiles for grouped content, and electric blue
reserved for the things a visitor can act on. Sections open with a centred headline.
The home page begins with a WebGL scroll film; everything after it is calm by design.

## Colors
Black page, graphite `surface` tiles, `surface-2` for fields and hover. Text steps from
`text` (headlines) to `text-2` (body) to `text-3` (notes, secondary headline halves).
Electric blue `blue` fills the primary pill only; `blue-link` (lifted for contrast on
black) colours chevron links, the secondary pill and small accents. No other hues.

## Typography
Geist (self-hosted via @fontsource-variable/geist) for everything; figures use tabular
numerals rather than a monospace face. Sentence case throughout, no all-caps labels.
Headlines are semibold with tight negative tracking; a two-tone headline sets its second
sentence in `text-3`. `text-wrap: balance` on headings, `pretty` on paragraphs.

## Layout
Max content width 1180px. Section rhythm `section-y` top and bottom. Section heads are
centred; content below may be left-aligned when it is a table or prose. The product
lineup is three equal columns of centred picture, name, line and actions.

## Elevation & Depth
Flat. Depth comes from the graphite-on-black step, not shadows; only the translucent
header and dropdown use blur (saturate 180%, blur 20px) and the dropdown a soft shadow.

## Shapes
Pills for buttons, 28px tiles (22px on phones), 18px small cards, 12px fields, round
radio marks and status dots. No cut corners, no outlines around tiles.

## Components
- Primary button: blue pill, white sentence-case label, 44px minimum target; hover
  lightens, press darkens and scales to 0.97; focus is a 4px blue ring.
- Secondary button: outlined blue pill that fills on hover.
- Chevron link: blue text with a drawn chevron that nudges 2px on hover; underline on hover.
- Tile: graphite, 28px radius, no border.
- Product lineup item: picture tile, optional "Flagship" note in `blue-link`, name,
  one line, then "Request a quote" (small pill) and "Learn more ›".

## Do's and Don'ts
- Do keep one filled blue action per view; everything else is a link or outline.
- Do keep labels in sentence case and buttons free of arrows.
- Don't add labels above headings or 01/02/03 numbering unless the content is a real sequence.
- Don't use gradient text beyond the hero's product name.
- Don't outline tiles or add shadows to them.
