# exp27 plots

Split by source figure: **`fig2/`** (healthy symmetric fabric) and **`fig4/`**
(asymmetric, `-failed` degraded ToR uplinks). The BDP-sweep and flow-size-sweep
figures are rendered in **two forms** — `_lines.png` (line/graph) and
`_bars.png` (grouped bars) — from the same data via `scripts/sweep_render.py`.

**Marker convention (all line/scatter plots, exp26 + exp27):** OPS = filled
orange square; each REPS buffer B = its own **hollow** marker shape, cycled
`o D ^ v X P *` for B = 1, 2, 4, 8, 16, 32, 64 (`sweep_render._SHAPES` /
`exp26/scripts/plot.py:B_SHAPES` — identical lists). Bar plots use a hatch per B
instead (`plot_micro_bars.HATCH_POOL` / `plot.py:B_HATCH`).

**Buffer ladder:** every exp27 plot shows the **full** `B = 1, 2, 4, 8, …,
#paths` ladder (32-path fabrics → B ≤ 32, 64-path → B ≤ 64). B is flat above
B ≈ 2 everywhere; the B ≥ 2 series overlap. The speedup-vs-OPS panel of every
bar/line figure is zoomed to a tight window around 1.0.

## `fig2/` — healthy

| file | plot | what |
|---|---|---|
| `fig2_micro_bars.png` | 1 | raw-time transpose of `exp26/plots/fig2_micro.png`: 2×3 grid (Incast/Permutation/Tornado × 4/8/16 MiB), top row Max FCT (µs), bottom row speedup vs OPS. `scripts/plot_micro_bars.py`. |
| `fig2_micro_scatter.png` | 1 | the exp26/paper **original** form of the same slice — horizontal speedup-vs-OPS scatter (y = 9 workloads, first on top), hollow marker per B. `scripts/plot_micro_scatter.py --fig fig2 --condition healthy`. |
| `fig2_micro_bars_k16_3t.png` | 2 | same panel, new sims on the K=16 3-tier fabric (`-paths 64`, B≤64, 4–64 MiB). `plot_micro_bars.py --summary ../data/k16_3t/summary.csv`. |
| `fig2_tornado_k_sweep.png` | 3 | grouped bars: tornado 4 MiB, 3-tier, x = radix K = 4/8/16 (→ 4/16/64 paths). `plot_k_sweep.py`. |
| `fig2_tornado_bdp_sweep_{lines,bars}.png` | 4 | exp26 2-tier fabric fixed, sweep only the BDP feeding `-q B / -ecn B/4 3B/4 / -cwnd 1.5B` (B ∈ {50,75,101,152,250}); vlines at B=101 / B=152. The healthy REPS-vs-OPS gap is a resonance peaking at B=101. `plot_bdp_sweep.py`. |
| `fig2_tornado_small_flows_{2t_1024host,2t_128host,3t}_{lines,bars}.png` | 5 | tornado flow-size sweep 1–16/64 MiB (healthy). 2t_1024host shows a second resonance (lone 4-MiB spike); 2t_128host (exp26 fig4's 8-path fabric, healthy control); 3t none. `plot_small_flows.py --fabric {2t,2t128,3t}`. |

## `fig4/` — asymmetric (`-failed`)

The fig4 views test whether the asymmetric-regime REPS win is *also* a resonance.
It is not. Failure knob: `-failed 32 -skip_asy` on the 1024-host fabrics
(scaled from exp26 fig4's `-failed 4` on its 128-host micro fabric — same
degraded-uplinks-per-host ratio ≈ 3.1 %); condition string `asym32`. The
`plot_fig4_*` scripts show `asym32` only — pass `--healthy` to overlay the
matching fig2 healthy curves.

| file | view | what |
|---|---|---|
| `fig4_micro_{bars,scatter}_128host.png` | F1 | exp26 fig4's own **128-host / 8-path** fabric (`-failed 4`, `asym4`, B≤8), the 45-cell exp26 slice, 0 new sims. exp26-faithful; **different fabric from plot 1**. Transpose (bars) + paper-form scatter. |
| `fig4_micro_{bars,scatter}_1024host.png` | F1′ | fig4's micro matrix **rerun on the 1024-host / 32-path fig2 fabric** (`-failed 32`, `asym32`, B≤32, sizes 4/8/16) — clean same-fabric contrast with plot 1. `run_fig4_micro.py` → `plot_micro_{bars,scatter}.py --fig fig4 --condition asym32`. |
| `fig4_tornado_bdp_sweep_{lines,bars}.png` | F4 | twin of plot 4 under `asym32`: speedup is **monotone-increasing** in the derived BDP (1.26×→1.84×) and never collapses — anti-correlated with the healthy resonance. B=1 dips to ~1.0× at B=101 (exp26 fig4 B≤2 knee). `plot_fig4_bdp_sweep.py`. |
| `fig4_tornado_small_flows_{2t_1024host,2t_128host,3t}_{lines,bars}.png` | F5 | twin of plot 5 under failure. **2t_1024host** (`asym32`, spine 0 half-dead from every ToR): broad plateau ≥1.15× across all sizes. **2t_128host** (`asym4`, exp26 fig4's own 8-path fabric, spine 0 mildly degraded from 25% of ToRs): speedup **grows with size** 1.14→1.75× (1→16 MiB). **3t** (`asym32`): grows 1.0→~1.6×. `plot_fig4_small_flows.py --fabric {2t,2t128,3t}`. |

Full write-up + result tables: `../README.md` (§"fig4 (asymmetric) views").
