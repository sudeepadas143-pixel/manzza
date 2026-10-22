# TRENCH//RADAR design system

## Direction: the field dossier

A research instrument for reading memecoin narratives. Two registers, kept apart on purpose:

- **The story**: what narrative is forming and whether money is following it. Set in a reading
  serif, as in a research note.
- **The instrument**: counts, flows and freshness. Set in an engineered sans with tabular
  figures, in aligned columns, so numbers can be compared at a glance.

The one memorable element is the **narrative map**: attention against buying demand, with
crowding and evidence encoded in the marks. Everything around it stays quiet.

What this is not: a SaaS card grid, Web3 neon, or glass panels. Structure comes from tonal
planes and alignment. Boxes are used only where grouping needs one.

## Type

| Role | Face | Use |
|---|---|---|
| Display | **Newsreader** (Production Type, OFL) | Narrative names, the lead insight, report prose. Designed for news on screens; optical sizes keep it crisp from 15px to 44px. |
| Interface | **IBM Plex Sans** (OFL) | Controls, labels, tables, every number (`tnum`). Built for IBM's technical tooling and stays legible small. |
| Identifiers | **IBM Plex Mono** (OFL) | Token addresses and tickers only. Never used for labels. |

Scale (px): 11.5 caption · 13 label · 14 body-ui · 16 body · 19 lede · 24 h2 · 32 h1 · 44 display.
Labels are sentence case at weight 500. No all-caps eyebrows, and no mono labels.

## Colour

| Token | Hex | Role |
|---|---|---|
| `--paper` | #0e0f11 | page |
| `--plane` | #15171a | primary working plane (tables, map) |
| `--plane-2` | #1c1f23 | raised: selected row, open panel |
| `--rule` | #272a2f | separators |
| `--ink` | #edebe4 | primary text (bone, not pure white) |
| `--ink-2` | #b3b0a7 | secondary |
| `--ink-3` | #8a877f | muted; 5.4:1 on paper |
| `--attention` | #8fb0d6 | attention / launches series (steel blue) |
| `--demand` | #4fbf86 | buying, money in |
| `--sell` | #e56b5f | selling, money out, high risk |
| `--caution` | #d9a441 | warnings, crowding, provisional |

Strong colour appears only where it carries meaning: buying, selling, risk, caution. Blue means
"someone is talking or launching", and green means "someone is paying".

### Narrative categories: pigments

The Narratives view gives each category a pigment (`web/nviz.js`, `FAMILY`). Eight families in a
fixed order, validated with the dataviz palette checker against `--plane` (#15171a): every
adjacent pair separates under protan/deutan simulation (worst ΔE 11.3, target ≥ 8), normal vision
worst ΔE 20.3 (floor 15), every pigment ≥ 3:1 on the plane. No pigment is a red or green, which
already mean selling and buying.

| Family | Hex | Categories (circle / diamond) |
|---|---|---|
| rose | #cb5589 | Art & visual memes / Lifestyle & nostalgia |
| blue | #5193f4 | Crypto-native |
| olive | #7b7c29 | Absurdist & surreal |
| violet | #8570dd | Gaming, anime & entertainment |
| teal | #27a7a8 | Technology & AI |
| purple | #9f52b1 | Internet culture & slang / Communities & fandoms |
| copper | #bf6d2c | Characters & creatures |
| cerulean | #3ca1c4 | Current events & news / Politics & geopolitics |

Eleven categories share eight hues; the second member of a family is a diamond, and every mark
on the map, line and table row also carries a name, so identity never rests on colour alone.
Categories the app creates fold into one "Created by the app" group (bone, dashed); a narrative
fitting no category is bone white. A colour follows its category, never its rank. A scatter of
eight hues cannot pass the all-pairs colour-blind check, which is why the field labels its larger
marks and the table lists the same data.

### Lifecycle: light

On the narrative field brightness is the lifecycle. Emerging narratives (new, heating,
accelerating, bought) are lit, with a soft halo in their own pigment; established ones are dim;
saturating and fading ones are hollow with a dashed rim. The tally above the map uses the same
code: bone, grey, hatched.

## Space and shape

- 4px base: 4, 8, 12, 16, 24, 32, 48.
- Radius by role: 2px on planes, 4px on controls, round only for status dots and map marks.
- No shadows except the floating sheet on phones. No gradients, glow or glass. The one blur is
  the phone tab bar, which sits over scrolling content.

## Layout

- Desktop rail (216px, 64px under 1280) holds the wordmark, navigation and **collection status**,
  so status is shown once instead of as a banner on every screen.
- Overview: a lead insight sentence and the regime instrument; a full-width launch-flow chart; then
  an asymmetric 7:5 split of narratives to watch against market conditions.
- Metas: a 7:5 master/detail. Map and ranked ledger on the left, a persistent dossier on the right.
  No overlay on desktop.
- Live: the chain stream as it happens. Launches per minute, tokens being bought in the last five
  minutes (sorted by proven wallets, then buyers), the launch tape with clone and serial-creator
  flags, and fresh graduations.
- Tokens: a sortable research table with risk flags in their own column.
- Analyst: report at a reading measure (~68ch) beside an evidence comparison of chosen narratives.
- System: a diagnostic table of sources with 24-hour run timelines.
- Phone: the same content in one column, with a bottom tab bar and detail sheets.

## Motion

Only for state changes: panel content swap (opacity, 160ms), sheet open (320ms, iOS drawer
curve), and press feedback. No entrance choreography and no hover animation on rows.

On the Narratives view motion reports a change in the data and nothing else:

- **Marks move** (650 ms, cubic in-out) from where the previous read put a narrative to where the
  new one does. Charts survive the page's re-render; an unchanged read moves nothing, and the
  token cluster's force layout runs once per narrative and read.
- **Numbers count** (700 ms ease-out) in the dossier and the tally when they changed since the
  last render, never on first view.
- **A changed cell flashes once** (1.6 s, green up / red down) in the ledger.
- **A state that flipped** since the previous read shows a "now …" badge that shines once.

Low visual and `prefers-reduced-motion` remove all of these and the halos; every value stays.

## Performance modes (Settings, in System)

- **Premium**: everything above, live crosshairs, 30-second refresh, Live screen every 3 seconds.
- **Low visual**: no transitions or blur. Chart buckets capped at about 100 bars; tooltips on
  tap/click instead of pointer tracking; 60-second refresh (Live screen every 6 seconds); re-render skipped when the data hasn't
  changed. Every number and chart is still shown.
- **Auto** (default): Low visual if `prefers-reduced-motion`, Save-Data, ≤4 GB device memory,
  ≤4 CPU threads or a 2G/3G connection is reported; otherwise Premium. It can be overridden.

## Narratives view (2026-10-22)

Metas → Narratives, left to right and top to bottom: the lifecycle tally and category band (share
of launches by category; click to filter), the narrative field (ECharts scatter: launch momentum
against buyers per launch, log scale, size = launches in 6 hours, quadrants named "Emerging with
buyers", "Launch rush, thin buying", "Bought without a rush", "Quiet or saturated"), momentum lines
(buyers per hour of the most-bought narratives, end-labelled, a second line of one family dashed),
and the ledger with a buyers sparkline. The dossier adds a pigment edge, a state tracker (one block
per read), the token cluster (force graph: size = buyers, faint = loosely related, edges show the
link: same post, picture, name, or nearest by meaning) and a two-panel trend (buyers, launches;
one axis each, never a dual axis).

ECharts 5.6.0 (Apache-2.0) is vendored in `web/vendor/` and loaded the first time Metas opens
(one ~54 ms parse task; refreshes add no long task). The React component libraries suggested as
references (Magic UI, Motion Primitives, Tremor, React Bits) need React, Tailwind and a build step
this app does not have; the few ideas worth having were written in plain CSS and JS instead:
the number ticker, the one-time shine, the category bar and the tracker.

Widths checked with no horizontal overflow: 390, 820, 1099, 1100, 1280, 1366, 1920. Below 1100 px
the dossier opens as a sheet; below 1600 px the table drops its category column (the swatch and
an accessible label carry it).

## Review record (2026-10-16)

Reviewed against anti-ai-slop-ui, Anthropic frontend-design and Microsoft frontend-design-review,
from screenshots at 1366×768, 1920×1080 and 393×852.

| | Before (mobile-first PWA) | After |
|---|---|---|
| AI slop score (0 best, 10 worst) | about 6: one rounded-card template everywhere, system type, mono all-caps labels, a stretched phone layout | about 1 |
| Distinctiveness (10 best) | about 3 | about 8 |
| `ui_lint.py` heuristic | 0.0 | 0.0 (it cannot see composition problems) |

Fixed during review: repeated hype text on every narrative row, a cramped buyers column,
unbalanced overview columns, competing serif headings, a ledger overflowing at 1366px, a
collapsed confidence meter, comparison-table overflow on Analyst, a backtest table colliding
with the display settings, alphabetical rather than severity source ordering, dead space in the
wide-screen lead, a CSS specificity bug, 14px of horizontal overflow on phones, the narrative name
shown twice in the phone sheet, and risk flags hidden on phones.

Performance (Chromium, 1366×768, 5 seconds of pointer movement over the launch chart):

| | Premium | Low visual |
|---|---|---|
| Script time | 73 ms | 2 ms |
| Layouts / style recalculations | 190 / 693 | 0 / 0 |
| DOM nodes after load | 1,698 | 1,035 |
| Unchanged refresh skips redraw | yes | yes |

Still open: the launch-flow chart reads as mostly hatched until a day of collection exists; the
narrative map overlaps marks when many narratives share a corner (tooltips and the ledger cover
it); light mode is not offered.
