# TRENCH//RADAR design system: "Signal Press"

## The idea

TRENCH//RADAR is an intelligence broadsheet printed from the chain every few minutes. It sits
between three worlds and borrows one discipline from each:

- **Financial press**: the precision of a newspaper's markets pages. A masthead and dateline, thick-over-thin
  rules, stock-table listings in monospaced figures, numbered sections, editorial headlines that
  state the finding instead of naming the widget.
- **Risograph print and zine culture**: the visual language of internet culture before it became a
  template. Spot inks on newsprint, a fluorescent pink house ink, halftone screens, hatching, hard offset
  shadows instead of soft ones, a slightly off-register energy.
- **Instrument plates**: radar scopes, seismographs and barometers. The flagship view is a scope;
  launch activity is a seismogram; the market regime is a barometer.

It is recognisable without the logo: newsprint paper, condensed all-caps headlines with a pink phrase,
mono figures, `//` and ruled sections, halftone and hatching where other dashboards use gradients.
There are no rounded cards, glow, glass or gradients-as-decoration.

Two editions share every rule: **Day** (newsprint, the default) and **Night** (blueprint navy with
paper-white ink). The masthead switch and System → Display toggle them; the choice is remembered.

## Type

| Role | Face | Use |
|---|---|---|
| Display | **League Gothic** (variable width, OFL) | Headlines, section slugs, narrative and token names, big numerals, stamps. Always uppercase. The newspaper headline face. |
| Text | **Newsreader** (OFL) | Decks (italic), explanations, quotes, report prose, empty states. |
| Interface | **IBM Plex Sans** (OFL) | Small UI copy and ledger labels. |
| Figures | **IBM Plex Mono** (OFL) | Every number, ticker and address; kickers and table headers in spaced caps. |

Hierarchy is carried by contrast between these four, not by weight alone: a 92px condensed headline
over a 19px italic deck over 10.5px spaced mono captions.

## Colour

| Token | Day | Night | Meaning |
|---|---|---|---|
| `--paper` | #eee8da | #121926 | the page |
| `--plane` | #e6dfce | #182133 | plates: the few feature surfaces |
| `--ink` / `-2` / `-3` / `-4` | #16130e … #9c9484 | #efe8d8 … #5f5d58 | text and line work; `-3` ≥ 4.5:1 on paper and plane |
| `--novel-ink` / `--novel` | #e0247f / #b8135f | #ff4fa3 / #ff63ae | the house ink: new, uncharted, selected; headline emphasis |
| `--buy` | #0a6e41 | #3cc387 | money in, buyers, accelerating |
| `--sell` | #b2331f | #f0735e | money out, danger, fading |
| `--caution` / `--marker` | #7f5900 / yellow highlighter | #e2b03a | saturation, warnings; the highlighter marks the selected row |

Launches print in plain ink, not a colour, so no category ink competes with a meaning colour.

### Category inks

Eight print pigments in a fixed order, validated with the dataviz palette checker against each
edition's paper: every adjacent pair separates under protan/deutan simulation (Day worst ΔE 11.5,
Night 9.2; target 8), normal vision worst ΔE 21.3 / 19.0 (floor 15), every ink ≥ 3:1. None is a red,
green or pink, which already mean something.

| Slot | Day | Night | Categories (circle / diamond) |
|---|---|---|---|
| 1 rust | #a44c1d | #dd713c | Characters & creatures |
| 2 teal | #03899d | #03899d | Technology & AI |
| 3 violet | #613ea6 | #9b7ee5 | Gaming, anime & entertainment |
| 4 umber | #8e5d11 | #a26e22 | Art & visual memes / Lifestyle & nostalgia |
| 5 cerulean | #0c82bf | #0d9de5 | Current events & news / Politics & geopolitics |
| 6 plum | #7f308c | #a258ae | Internet culture & slang / Communities & fandoms |
| 7 olive | #726c0f | #a09723 | Absurdist & surreal |
| 8 ultramarine | #5272d8 | #5473d2 | Crypto-native |

Categories the app creates share one grey square ("Created by the app"); a narrative no category
fits is the house pink ("New kind of meta"). Colour follows the category, never its rank, and every
mark also carries a name or sits in a labelled table, so identity never rests on colour alone.

### Lifecycle: fill, not colour

On every narrative mark the fill is the lifecycle: **solid ink** emerging (new, heating,
accelerating, bought), **halftone** established (steady), **hatched** saturating, **outline** fading,
and a dashed pink ring for new. Stamps repeat it in words with a glyph: ✦ new, △ heating,
⌃⌃ accelerating, ⊕ being bought, — steady, ▨ saturating, ⌄ fading.

## Surfaces and line work

- No radius anywhere except dots. Structure comes from rules: a 2px ink rule opens every section, dotted
  hairlines separate rows, vertical hairlines separate columns.
- Plates (the atlas, the barometer, the pulse) are the only toned surfaces; feature plates carry
  registration marks at opposite corners.
- Shadows are hard offsets (3px, ink) on tooltips and on buttons under the pointer, as if printed
  slightly off-register. A static paper grain sits under everything (off in Low visual).
- Tooltips are paper slips: ink border, offset shadow, display-face title, mono figures.

## Layout

- Masthead: wordmark, numbered sections (§01–§06), dateline with edition time and source freshness,
  live dot, edition switch, refresh; a thick-over-thin rule. Phones get a bottom tab bar with a pink
  marker on the current section.
- Every page opens with a folio: a numbered kicker, a generated headline that states the finding
  ("4 narratives in play. Trump Ocean leads."), an italic deck with the context and caveats.
- 12-column grid with asymmetric splits (8:4, 7:5); dense tables run full width.

### Pages

- **Briefing**: headline and run-in lede; launch activity as a seismograph with a graduation rug and
  hatched collector gaps; the barometer (dial plus driver readouts); "Emerging now" as front-page
  stories; readiness ledger, buying table, market data and 30-day volume.
- **Live wire**: launches this hour as the headline, an on-air stamp, figures, a per-minute seismograph,
  then three columns: the tape (new launches slide in with a pink wash), being bought now, dispatches
  (posts spawning coins, shared pictures, graduations).
- **Metas, the Atlas**: Plate I is a semantic radar. Each category holds a bearing on the rim; a
  narrative's bearing comes from its similarity to each category, its distance from the centre from
  how clearly it belongs, so narratives no category fits sit in the uncharted middle. Size is launches
  in six hours; fill is lifecycle; curves join sub-metas of one broad narrative, dotted curves join close
  relatives. Beside it: the specimen (popularity, traction and crowding kept apart) and the lifecycle
  column. Below: the pulse (stacked ridgelines of buyers per hour, each scaled to its own peak, halftone
  in its category ink), the index of categories with discovered sub-metas, broad narratives, merges and
  splits, and the full ledger. The narrative profile opens as a sheet: headline, stamp, state tracker,
  the source post as a pull quote, three vitals, drivers against risks, momentum, the token
  constellation (deterministic force layout; edges show same post, picture, name or nearest meaning),
  specimens, classification and evidence footnotes. "Keyword scores" keeps the readiness model as
  Plate II.
- **Tokens**: market listings. Mono figures, a graduation ruler, buy/sell bars; dangerous flags boxed in
  red, the rest quiet.
- **Analyst**: the report as a long read with a drop cap, the comparison table and narratives in play.
- **System**: headline names the failure count; four figures; sources as a table with 24-hour run
  strips (ink ran, red failed, hatched mixed); history, backtest, display and integrations.

## Motion

Motion only reports a change in the data.

- Atlas marks glide to their new bearing when a read moves them (650ms, ease-in-out); a new read
  sweeps the scope once; a newly formed narrative fades in. Nothing moves between reads.
- Changed numbers count (700ms ease-out); a changed ledger cell flashes once; a state that flipped
  since the previous read gets a "just turned" tag.
- New launches on the tape slide in with a pink wash; the pulse ridges draw in once.
- Section changes fade up 6px (320ms). Buttons lift onto their shadow under the pointer.
- Low visual and `prefers-reduced-motion` remove all of it, plus the grain and pointer tracking.

## Data visualisation rules

- One axis per chart; two measures get two aligned panels (profile momentum).
- Unobserved periods are hatched and break lines; they never read as zero.
- Every chart has a text alternative (table, ledger or list) and an `aria-label`.
- Labels that would collide are dropped, not overlapped; the selected item always keeps its label.
- Real data only. Empty states say what is missing and when it will arrive.

## Checked (2026-10-22)

Widths 360, 390, 820, 1024, 1280, 1366, 1440 and 1920 with no horizontal overflow; Day and Night
editions; Premium and Low visual; every page against the live chain stream and against a replayed
research day with 560 narratives. Interactions: atlas selection, profile, constellation to token
dossier, keyword view, edition switch, token search, sort and filters, hash navigation, Escape to
close; no console errors.

The React component libraries suggested as references (Magic UI, Motion Primitives, Tremor, React Bits)
need React, Tailwind and a build step this app does not have, so the few ideas worth having (number
ticker, category bar, tracker) are written in plain CSS and JS. ECharts was tried for one build and
removed: the custom SVG kit renders the print language (halftone, hatching, registration) that the
library's defaults fight, without a 1MB download.
