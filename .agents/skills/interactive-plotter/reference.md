# interactive-plotter reference

## Page anatomy (top to bottom)
eyebrow, h1 (the finding, one line), lede (<= 2 sentences, about 220 chars), small mono `cfg` line, collapsed full command, status chips, `question()` brief, KPI tiles (3-5), numbered sections, footer (source data, regenerate command).

## Type scale (tokens in `plot_common.CSS`)
| Role | Size | Weight |
|---|---|---|
| h1 | 20px | 600 |
| lede | 14px | 400 |
| config line | 11px mono, muted | 400 |
| h2 | 15px | 600 |
| plot title (in figure) | 12px | 600 |
| axis, legend, tick | 11px | 400 |
| note, callout, aside | 13px | 400 |
| footer | 11px | 400 |

IBM Plex Sans body, IBM Plex Mono for flags and numbers. Prose measure about 70 characters; at most 3 lines between a heading and its plot.

## Primary metric
Max FCT is the headline outcome in this repo. The first plot answers the question on max FCT; knee claims use `B_fct` = smallest B from which every larger B is within the CI (or 0.2%) of the reference on max FCT. Mechanism knees (`B_ow`, `B_ks99`) and mechanism metrics appear after, as explanation. Lede, KPI tiles and Result callouts quote max-FCT numbers first.

## Blocks
`note` (1-3 sentences, `**bold**` and `` `code` `` only); `callout(kind, text)` with kind Prediction, Result, Caveat or Retracted (Retracted is struck through; remove a disproved explanation from every page and README); `aside(summary, text)` collapsed reasoning; `h2(..., tag="supporting check")` for sections that back a claim; `vmarks` numbered marks on a plot with a `footnotes=[...]` list under it; `synthetic_banner()` before any plot on invented data (only for style demos, never in results).

## Palette (one table, `plot_common.STYLES`; color + symbol + dash identify a series)
| Entity | Color | Symbol |
|---|---|---|
| B=1, 2, 4, 8, 16, 32 | `#440154 #414487 #2a788e #22a884 #7ad151 #fde725` (exp28) | circle, diamond, triangle-up, triangle-down, x, cross (all `-open`) |
| B=64, B=inf | `#c2185b`; ink, dashed | hexagon; square |
| dual-window, capped | `#dc2626` dash; `#2563eb` dash | star; pentagon |
| vanilla, state-aware | `#1f77b4`; `#ff7f0e` dash | circle; diamond |
| config series c0..c5 | ink, `#2a788e`, `#22a884`, `#d97706`, `#dc2626`, `#7c3aed` | per row |

Dark mode overrides only B=1, B=2, B=64, inf, c0, c5 (canonical hex has < 3:1 on the dark surface). Light-surface B=16/32 keep the canonical hex: darkening them cuts adjacent CVD separation from dE 10.5 to about 3, so shape, halo, legend and copy-data carry them. The validator (`dataviz` skill) flags the ordered B ladder on lightness band and chroma by design; CVD and normal-vision floors pass on the canonical set. Bars (`PC.barTrace`, grouped, error bars = 95% CI): first style solid, the others patterned, so bars differ by more than color; use bars for a metric read per B or per category (e.g. overwrites vs B), lines for the primary max-FCT curve. Series of different families (B ladder, algorithms, configs) do not share a figure. Direct end labels only when 4 or fewer series.

## Axes against B
Show the full B ladder on every plot against B, in order. A category axis drops a group with no bar or point, so set `xaxis.categoryarray` to the whole ladder and label a group that cannot be drawn (all zero on a log axis: `all 0`; not run: `not run`). Never let a missing B read as a B that was not measured. Exclude a failing cell family (e.g. gate failed) from every plot and the table, and say so once in a Caveat and a chip.

## Do not
a headline built on a mechanism metric; dual axes; per-plot colors; rainbow; a number on every point; more than about 8 series per figure (facet or fold into "other"); a plot whose lines all overlap; a plot added because the data exists; text in series color; unlabeled synthetic data; hand-edited HTML in the template for one-off notes.

## Known gaps (follow-ups, not done)
Existing pages (exp28-31, meeting_*) still use their own CSS/JS; migrate one family at a time. exp29/exp31 B ladders use shifted hexes. No index page or cross-page links. Plotly and fonts load from a CDN (not offline-safe).
