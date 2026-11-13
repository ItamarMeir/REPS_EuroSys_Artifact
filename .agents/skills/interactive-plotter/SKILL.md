---
name: interactive-plotter
description: Build an interactive Plotly HTML page for an experiment (plot selection, order, theme, palette, copy buttons, sanity chips). Use when creating or editing plots/interactive.html or any build_interactive*.py.
---

Builder: `experiments/tools/plot_common.py`. Templates: `experiments/tools/demo_interactive_plotter.py` (every element, exp29 data) and the curated pages `experiments/meeting_26_10_26/scripts/build_page_t1.py`, `build_page_t2.py`, `build_page_t3.py` (max-FCT-first order, shared `PC.fctVsB`, `fct_series`, `knee_fct`). Checklists, palette table and type scale: `reference.md` next to this file. Read the matching demo before writing a page.

## 1. Plan the page before any code

Write this in the experiment README (or the plan) first; a page that skips it is noise.

1. **Question**: one sentence, what the experiment finds out. It becomes the `question()` brief at the top (find out / test / compare, one sentence each).
2. **Primary metric**: max FCT here (p99/p50 only if the claim is about them; say so in the lede). Every claim "X moves the knee / matters / does not" is shown first on this metric. Mechanism metrics (k, overwrites, random-EV share, ECN, RTOs, freeze) only explain a result already visible there; a mechanism-only effect is a Caveat, never the headline.
3. **Claims**: the 2-5 statements the page must let a reader verify (the lede and tiles state them with primary-metric numbers).
4. **One plot per claim.** Keep a plot only if removing it leaves a claim unsupported or a prediction unchecked. Drop plots that repeat another with different axes, show lines that all overlap, or exist because the data was there.
5. **Order**: primary metric against the swept variable with the knee marked (one line per config, 95% CI), then the knee against the variable, then the mechanism that explains it, then `tag="supporting check"` sections (transients, drain, resolvability), then the table. Compare on the same axes, one control (dropdown or buttons) instead of N panels.
6. **Predictions**: Prediction callout before the Result callout; a missed prediction is stated as missed.

## 2. Build

1. Aggregate in Python with the experiment plotter's `load()` / `agg_ci()` (numbers must equal the PNGs); pass rows through `records(df)` into `payload`.
2. Body = ordered blocks: `h2`, `plot`, `controls`, `note`, `callout`, `aside`, `table`, `end`. An explanation between plots is a `note`/`callout`/`aside` block, not template HTML. Keep each note to about 3 sentences (the builder warns); longer reasoning goes in an `aside`.
3. Page JS uses `PC` (`lineTrace`, `draw`, `radio`, `select`, `vmarks`, `onRedraw`). Every series gets color, marker shape and dash from `STYLES` by entity (B ladder = exp28 map); never choose colors per plot. New entity: add one row to `STYLES`.
4. Header: `cfg` = only flags that differ from baseline (small mono line), `full_cmd` collapsed, `chips` for every check below. Derive flags from the runner's `flags()`, never retype.
5. Sanity chips (warn, do not hard-fail): seeds per point and single-seed points (filled marker, no CI); `-sender_cc_only` without `-disable_tor_ecn`; `n_flows` vs expected and `unfinished`; load balancer (`freezing`) and CC; mark any cell outside the clean regime.
6. Title format `<metric> - <condition> (<n> seeds, 95% CI)`; units in axis titles as `(us)`; clip count-metric CI bands at 0.

## 3. Verify

Build, then render headless in light and dark (`chrome --headless=new --screenshot`) and look at it. Check: no console error, copy title/data/image and PNG work, legend state survives a control change, output is ASCII with one `const DATA =` blob (thesis-sync packs it), no `.html` staged. Publishing to the thesis repo is skill `thesis-sync`, only on request.
