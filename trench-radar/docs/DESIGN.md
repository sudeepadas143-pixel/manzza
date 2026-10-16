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
- Tokens: a sortable research table with risk flags in their own column.
- Analyst: report at a reading measure (~68ch) beside an evidence comparison of chosen narratives.
- System: a diagnostic table of sources with 24-hour run timelines.
- Phone: the same content in one column, with a bottom tab bar and detail sheets.

## Motion

Only for state changes: panel content swap (opacity, 160ms), sheet open (320ms, iOS drawer
curve), and press feedback. No entrance choreography and no hover animation on rows.

## Performance modes (Settings, in System)

- **Premium**: everything above, live crosshairs, 2-minute refresh.
- **Low visual**: no transitions or blur. Chart buckets capped at about 100 bars; tooltips on
  tap/click instead of pointer tracking; 5-minute refresh; re-render skipped when the data hasn't
  changed. Every number and chart is still shown.
- **Auto** (default): Low visual if `prefers-reduced-motion`, Save-Data, ≤4 GB device memory,
  ≤4 CPU threads or a 2G/3G connection is reported; otherwise Premium. It can be overridden.

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
