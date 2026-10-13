---
name: MANZZA
description: Transformer core laminations presented in SpaceX's design language (awesome-design-md, design/reference/spacex.DESIGN.md) in the client's black, deep navy and electric blue — condensed uppercase DIN-style display type, full-bleed imagery, one ghost pill per band.
source: design/reference/spacex.DESIGN.md (VoltAgent/awesome-design-md, MIT)
colors:
  # calibrated with taste-skill (.claude/skills/taste-skill): no pure black or white,
  # one cool neutral family, one accent locked page-wide, accent saturation < 80%, no glows
  canvas: "#06080d"          # off-black, navy-cool
  navy: "#0b1426"            # deep navy
  navy-deep: "#080e1b"
  electric-blue: "#3169e3"   # the logo's hue (221°) at 76% saturation
  electric-blue-press: "#2a5bc9"
  electric-blue-text: "#80a3ef"
  on-primary: "#f4f6fa"      # off-white
  on-primary-mute: "#e6ebf3"
  body: "rgba(238, 241, 246, 0.74)"
  note: "rgba(238, 241, 246, 0.55)"
  hairline-on-dark: "#1c2438"
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
    hover: "off-white fill wipes in from the left, label turns ink"
  button-primary:
    backgroundColor: "#f4f6fa"
    textColor: "#06080d"
    hover: "lifts 1px; a 2px electric-blue inner ring draws in"
    use: "Request a quote (hero, closing CTA, product pages, sticky bar, header pill) and the form submit"
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
  dependable. So: off-black is the stage (film, product bands, hero); deep navy carries
  the alternate chapters, footer and menus; electric blue is the one accent — button
  fills on hover, the submit button, rules, eyebrows, focus, the table head rule and the
  rule that opens the closing call to action. Calibrated with taste-skill: off-black
  #06080d and off-white #f4f6fa instead of pure values (same cool family as the navy),
  the logo's blue hue at 76% saturation (#3169e3; the logo artwork itself is untouched),
  no glows, and small blue text in a lighter tint (#80a3ef, 7:1 on navy).

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
- Don't add colours beyond off-black, deep navy, electric blue and off-white; no glows,
  gradients, shadows, rounded tiles or glass.
- Don't add copy that the client brief or the user did not supply.

## Audit against the installed skills (what each one decided)
- **awesome-design-md / SpaceX:** the base system: bands, condensed caps, one ghost pill per band.
- **Client brief §8:** black, deep navy, electric blue; powerful, innovative, technical, dependable.
- **taste-skill:** off-black/off-white in one cool family; one accent at < 80% saturation; no
  glows; hero headline on two lines and inside the viewport; no split headers (a headline
  and its paragraph stack); no three image/text zigzags in a row (the third product band
  spans the width instead); no layout family used twice (process = columns, quality = two-up
  rows, customers = index list); eyebrows kept to the hero.
- **emil-design-eng / apple-design:** strong ease-out curves, press scale on buttons, hover
  effects only on fine pointers, one-shot reveals, everything still under reduced motion.
- **web-design-guidelines:** skip link, visible focus, labelled controls, 16px+ inputs,
  tabular figures, `color-scheme`/`theme-color`, no `transition: all`.
- **dark-mode-design-expert:** text tiers at 9:1 and 5.6:1 on navy; blue text tint at 7:1.
- **de-slop:** copy is the client's own wording; nothing invented.
- **Scroll cue:** "Scroll" over a hairline that runs to the bottom edge, a blue pulse travelling down it, at the foot of the opening
  logo; pressing it glides one screen into the film; it fades at the first scroll.

## Atmosphere (Gradient Backdrops)
`src/lib/backdrop` (nonlineartom/gradient-backdrops, MIT), mounted by `src/js/backdrops.js`
on six sections (home: hero, products intro, materials, about, closing CTA; inner pages:
the head); the product bands, capabilities, quality and the form stay flat.
- **Hero:** `silk`, navy-to-steel lit folds (#06080d -> #4d72b8, sheen 0.45), strongest on
  the right, masked to 25-40% behind the headline.
- **Products intro:** `mesh`, navy and electric-blue light pooling mid-section, fading out
  before the hero above and the first product band below.
- **Materials (home):** `mesh`, a calm, low-contrast navy field behind the spec table.
- **About:** `flow`, a dark current brightest on the open right side of the statement.
- Flat navy chapters (`.section--soft`) now fade in and out of the off-black at their top
  and bottom instead of starting as hard-edged blocks, so they sit with the backdrops.
- **Closing CTA:** `flow`, navy with a slow brand-blue current (contrast 0.82).
- **Inner-page heads (materials, quote, 404):** `mesh`, navy haze with a blue lift top-right.
- Grain 0.06-0.07 on all three. Motion 0.2-0.35 speed; frozen on one frame under
  `prefers-reduced-motion`; paused off-screen; mounted only when the section is near.
- Phones: 250k-pixel cap and 80% speed; soft styles render at 0.28-0.5 scale.
- Static fallback: each section has a soft radial in the same navy as its CSS background,
  sized to fade out before the section edges. It is the first paint, the no-WebGL view
  and the capture view; the canvas fades in over it.
- No auroras, no saturated glows, no neon; taste-skill's "no glows" rule still holds:
  these are deep, low-contrast tonal shifts, not lit halos.

## Primary button (decided after the backdrops)
Off-white pill (#f4f6fa) with an ink label (#06080d) for every "Request a quote" and the
form submit; electric blue moves to the hover ring and stays the accent for rules,
eyebrows and focus. Why: label contrast 18.5:1 (blue fill was 4.56:1), and the button
stands 6-9:1 off the brightest backdrop where the blue fill fell to 1.3:1 on the blue
current. Agreed by dark-mode-design-expert (the primary is the lightest element on dark),
web-design-guidelines/pixelslop (contrast), taste-skill (one accent, used for detail not
large fills) and the SpaceX/Apple reference (light pill on dark).
