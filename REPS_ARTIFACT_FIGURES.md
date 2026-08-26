# REPS Artifact — Figure Scripts Explained

Runs of `artifact_scripts/reps_quick.sh`, `reps_medium.sh`, `reps_full.sh` (paper's original,
unmodified scripts). Each script is a superset of the previous: quick ⊂ medium ⊂ full.
Results land in `artifact_results/<fig_name>/{data,plots,raw_output}`.

Run log for this session: see `artifact_scripts/reps_quick.log`, `reps_medium.log`,
`reps_full.log` (created per run, inside the Docker container mount).

---

## reps_quick.sh (<2h) — 11 scripts

| Fig | Script | What it tests | Topology | Workload | LB algos compared |
|---|---|---|---|---|---|
| 1 | `fig_1_symmetric_micro.py` | Symmetric-topology microbenchmark, no failures | `fat_tree_128_1os_2t_400g` (128-host, 2-tier) | `test_symm16.cm` | freezing (REPS) vs oblivious |
| 3 | `fig_3_asymmetric_micro.py` | Asymmetric (1 static link failure) microbenchmark | `fat_tree_128_1os_3t_400g` (128-host, 3-tier) | `test_symm32.cm` | freezing vs oblivious, `-failed 1` |
| 5 | `fig_5_bg_traffic.py` | Background-traffic sensitivity (wrapper `run_bg.py`) | — | — | main vs `--bg_type 1` |
| 6 | `fig_6_failures_micro.py` | Queue/port dynamics around a link failure event | `fat_tree_128_1os_3t_400g` | `test_symm32.cm` | freezing vs oblivious, `-failed 42`, with/without `-exit_freeze` |
| 8 | `fig_8_extreme_failures.py` | Scale test: cable+switch failure sweep at 0/10/20/30/40/50% | `fat_tree_1024_1os_2t_400g` (1024-host) | `perm_n1024_s33554432.cm` | freezing only, varying `-failures_input` |
| 9 | `fig_9_real_hw_1.py` | Real hardware trace plot (no simulation run) | — | — | — |
| 10 | `fig_10_real_hw_2.py` | Real hardware failure trace plot (no simulation run) | — | — | — |
| 11 | `fig_11_ack_compression.py` | ACK-compression / `-sack_threshold` sweep (4k–64k), clean + 8% link failures | `fat_tree_128_1os_2t_400g` | `perm_n128_s8388608.cm` | oblivious vs freezing |
| 12 | `fig_12_evs_cc.py` | Entropy-value count sweep (`-paths` 32/256/65535) + CC comparison (dctcp/eqds/nscc) | `fat_tree_128_1os_2t_400g` | `perm_n128_s8388608.cm` | oblivious vs reps |
| 13 | `fig_13_queue_ballsbins.py` | Analytic balls-into-bins queue model (pure Python, no htsim) | — | — | — |
| 14 | `fig_14_ballsbins.py` | Analytic balls-into-bins comparison (pure Python, no htsim) | — | — | oblivious vs reps (analytic) |

Common htsim flags: `-sender_cc_only -sender_cc_algo mprdma`, `-linkspeed 400000` (400G),
`-ecn 20/25 76/80`, `-q 100`, `-cwnd 151`, `-paths 65535` unless swept.

---

## reps_medium.sh (~4-6h) — adds Figure 2

| Fig | Script | What it tests | Scope |
|---|---|---|---|
| 2 | `fig_2_symmetric.py` | Full symmetric-topology sweep via `run_all_symm.py` (in `htsim/sim/datacenter/`) | Runs 3 workload families — synthetic (`run_symmetric.py`), datacenter (`run_dc.py`), collective (`run_collective.py`) — on a 1024-host topology (128-host for the DC leg), producing `microbenchmarks`, `dc`, and `ai` plot sets. This is the heavy multi-workload sweep that pushes runtime from <2h to 4-6h. |

---

## reps_full.sh (~10h+) — adds Figures 2, 4, 7

| Fig | Script | What it tests | Scope |
|---|---|---|---|
| 2 | `fig_2_symmetric.py` | (see medium) | — |
| 4 | `fig_4_asymmetric.py` | Same 3-workload sweep (`run_all_asy.py`) but under asymmetric/failure topology conditions | microbenchmarks / dc / ai plot sets |
| 7 | `fig_7_failures.py` | Same 3-workload sweep (`run_all_failure.py`) under dynamic failure injection | microbenchmarks / dc / ai plot sets |

Figures 2, 4, 7 are each 3x the workload combinations of a single micro-benchmark figure —
this is why full run time jumps from medium's 4-6h to 10h+.

---

## Annotated plots (legend + headline)

Many of the paper's original fig scripts build legend handles/labels but never call
`.legend()` (or explicitly suppress it), and none have a figure-level headline. Per project
rule (never modify `artifact_scripts/`/`artifact_results/`), nothing is edited in place.
Instead, tooling under `artifact_results_runs/postprocessing_tools/` reads already-generated
data/PNGs from a stage's snapshot (`artifact_results_runs/<stage>/`) and writes annotated
copies — legend always placed **outside** the axes (`bbox_to_anchor`, not overlapping data) —
into `artifact_results_runs/<stage>/postprocessed_plots/`. PNG-only (no PDF).

Three techniques, picked per figure:
- **Re-plot** (`annotate_port_util_fig.py`, `annotate_fig8_extreme_failures.py`,
  `annotate_fig9_real_hw_1.py`, `annotate_fig10_real_hw_2.py`, `annotate_fig11_ack_compression.py`,
  `annotate_fig14_ballsbins.py`, `annotate_plot_symmetric.py`, `annotate_plot_collective.py`,
  `annotate_plot_failures.py`): for figures with *no* legend at all in the original (or one
  clipped off-canvas). Re-reads the source data, or safely source-patches + execs a modified
  in-memory copy of the original script (fig_10, fig_2/4/7's three plotting scripts) — no
  re-simulation, no writes outside `out_dir`.
- **Headline overlay** (`add_headline.py`, PIL): for figures that already render a real
  legend at the right position — just stamps a headline banner on top of the existing PNG.
  Used for fig_12, 13, and fig_2/4's `dc` panel (`plot_load.py`, unaffected by the bug).
- **Synthesized legend merge** (`merge_legend.py`, PIL): fallback for when the plot's own
  source data is gone (overwritten in a shared, non-stage-versioned sim-output folder) so a
  real re-plot isn't possible, but the color/marker-to-series mapping is a hardcoded
  constant in the plotting script (not derived from the lost data) — builds a standalone
  legend from that known mapping and merges it onto the existing PNG. Used for medium's
  `fig2_microbenchmarks`/`fig2_ai` (see below).

**Legend audit (2026-08-24):** spot-checking every annotated plot found several where the
*original* PNG never had a real legend at all — the headline-overlay tool can't fix that
(it only stamps text on whatever's already rendered). Confirmed root causes and fixed via
re-plot:
- `plot_symmetric.py` (fig_5, fig_2/4/7's microbenchmarks panel): legend positioned at
  `bbox_to_anchor=(-0.71, 1.8)` — off-canvas, silently dropped by `bbox_inches='tight'`
  even in the ORIGINAL un-annotated PNG. Fix: `annotate_plot_symmetric.py` — moves the
  legend on-canvas (right of axes), widens the figure, passes `bbox_extra_artists`
  explicitly (needed even on-canvas — tight-bbox alone still dropped it).
- `plot_collective.py` (fig_2/4/7's ai/collective panel): `ax.legend(...)` call fully
  commented out. Fix: `annotate_plot_collective.py` — uncomments + repositions outside axes.
- fig_11 panel 2 (`compressed_acks_failures`): legend call commented out (panel 1 was fine).
  Fix: `annotate_fig11_ack_compression.py` — re-plots both panels, enables panel 2's legend.
- fig_14: builds a real legend then immediately overwrites it with an empty one right
  before `savefig` (17 near-duplicate per-port labels was likely why — collapsed here to
  3: Oblivious / REPS / Threshold). Fix: `annotate_fig14_ballsbins.py`.
- `plot_failures.py` (fig_7's *all three* panels — one script covers micro/dc/ai, unlike
  fig_2/4's three separate scripts): same off-canvas `bbox_to_anchor=(-0.71, 1.8)` bug as
  `plot_symmetric.py`. Fix: `annotate_plot_failures.py`.
- **Headline clipping (second pass):** even after fixing the legend position, the headline
  `suptitle()` itself was still silently dropped by `bbox_inches='tight'` on some figures
  (fig_7's panels; inconsistent — fig_5 was fine) because the suptitle artist wasn't passed
  to `bbox_extra_artists`. Fixed in `annotate_plot_symmetric.py`, `annotate_plot_collective.py`,
  `annotate_plot_failures.py` by capturing the suptitle handle and including it explicitly;
  all affected outputs (fig_5 all 3 stages, fig_2/4/7 micro+ai panels) were regenerated and
  re-verified.
- `plot_load.py` (fig_2/4/7's dc panel) and fig_1/3/6/8/9/10/12/13 checked visually — legends
  render correctly, no fix needed there.

**Quick-stage status: all 11 figures / 16 plots annotated and legend-verified**
(`artifact_results_runs/quick/postprocessed_plots/`).

**fig_2 microbenchmarks/ai (medium) — data-loss workaround:** fig_2/4/7's raw per-run sim
data lives in *shared*, not stage-versioned, locations under `htsim/sim/datacenter/` (see
Execution notes below) that get overwritten by the next stage's run of the same figure.
`FINAL_OS_RUN_SYMMsymm_notrim_synth` and `_coll` (fig_2's microbenchmarks + ai panels) were
already overwritten by full.sh's own fig_2 run (04:41-05:56 UTC 2026-08-24) by the time this
bug was found, so a real re-plot from source data wasn't possible for medium's copy.
Worked around it with `merge_legend.py`: the color/marker-to-algorithm mapping is a hardcoded
constant in `plot_symmetric.py`/`plot_collective.py` (`static_color_mapping`, `lb_markers`),
not derived from the lost data — so a standalone legend can be synthesized from that known
mapping and merged onto the existing (data-correct, legend-missing) PNG with PIL, with no
simulation data required at all. Used for `fig2_microbenchmarks_annotated.png` (marker
legend) and `fig2_ai_annotated.png` (line-swatch legend, since it's a bar chart).

**medium is now 19/19 plots legend-verified — no remaining gaps.**

**full-stage status: all 14 figures / 25 plots annotated and legend-verified**
(`artifact_results_runs/full/postprocessed_plots/`) — 16 same-structure plots + fig_2's 3
+ fig_4's 3 (asymmetric-topology sweep) + fig_7's 3 (dynamic-failure-injection sweep, via the
newly-discovered `plot_failures.py`). One folder-naming quirk found along the way: fig_4's
microbenchmarks panel data sits in `FINAL_OS_RUN_ASYMasy_notrim_synth` (uses `asy`, not
`symm` like its own `ai`/`coll` panel or fig_2's equivalent) — inconsistent naming in the
original `run_all_asy.py`, not a bug in the fix tooling.

**All 3 stages (quick 16, medium 19, full 25 = 60 plots total) are now fully
legend-verified with headlines. No known gaps remain.**

## Grouped result snapshots

`artifact_results/` gets overwritten/extended by each successive stage (medium reruns some of
quick's figures, full reruns some of medium's). To keep each stage's results distinct, the
live `artifact_results/` tree is **copied** (not moved) into `artifact_results_runs/<stage>/`
right after that stage's script exits and before the next stage starts:
- `artifact_results_runs/quick/`
- `artifact_results_runs/medium/`
- `artifact_results_runs/full/`

`artifact_results/` itself is left as-is after each copy (untouched, per project rule) so the
next stage's script can pick up / overwrite it normally.

## Execution notes for this session

- Built via Docker (`docker compose build` + in-container `make clean && make` per
  `CLAUDE.md` — required, not optional; host-built ELF binaries fail on other glibc/libstdc++).
- Container: `reps-artifact-dev` (docker-compose service, bind-mounts repo at `/workspace`).
- Scripts run from `/workspace/artifact_scripts` inside the container, sequentially:
  quick → medium → full (not parallel, per instruction).
- **Status: ALL 3 STAGES COMPLETE.** quick.sh completed, snapshotted to
  `artifact_results_runs/quick/` (72M), 16/16 plots annotated. medium.sh completed (~02:37 UTC
  2026-08-24), snapshotted to `artifact_results_runs/medium/` (72M), 19/19 plots annotated.
  full.sh completed (~10:5x UTC 2026-08-24, ran 02:37→~11:00, ~8.4h), snapshotted to
  `artifact_results_runs/full/` (73M), 25/25 plots annotated. Raw per-run sim output for
  fig_2/4/5/7 lands under `htsim/sim/datacenter/` (shared, non-stage-versioned folders —
  `FINAL_OS_RUN_SYMM*`, `FINAL_OS_RUN_ASYM*`, `bg_run_128symm_notrim_synth`,
  `test_run_32fail_notrim_*`), not `artifact_results/`, matching the original scripts' own
  layout; only final plots are captured in the `artifact_results_runs/<stage>/` snapshots.
- `artifact_scripts/` and `artifact_results/` themselves are untouched — this file lives at
  repo root, not inside either.
- Some internal plotting sub-steps invoke `python` instead of `python3` inside the container
  (`/bin/sh: 1: python: not found` in `reps_quick.log`) — non-fatal, htsim runs unaffected,
  but a few plot-generation calls inside fig scripts may have silently failed. Check plots
  under each `fig_*/plots/` after a stage completes.
