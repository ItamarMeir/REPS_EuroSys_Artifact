# exp26 DC panels — 128-rank traffic variant

The main exp26 fig_2 / fig_4 **dc** panels run the 32-rank
`{40,60,80,100}load_ae.cm` matrices on the 128-host fat-tree, because that is
what the shipped `artifact_scripts/fig_2_symmetric.py` does (`run_dc.py`'s
`--ae_runs` argument defaults to `True` and no caller overrides it, so the
"artifact evaluation" matrices are loaded even though the topology has 128
hosts).

This directory holds the **128-rank** DC variant: the git-tracked
`{40,60,80,100}load.cm` matrices (`Nodes 128`, ~5.2k–12.3k flows, roughly 6x the
`_ae` flow count — these are the ones `gen_files_remote.py` regenerates and that
`run_dc.py` uses when `--ae_runs` is falsy). Everything else is identical to the
main dc panel: `fat_tree_128_1os_2t_400g`, seed 1019, `-q 100 -ecn 25 76
-cwnd 151`, `-sender_cc_only -sender_cc_algo mprdma`, `-connections_mapping
-disable_trim`, arms `ops` + `reps_b{1,2,4,8}` all with `-use_srv6 -paths 8`;
fig_4 adds `-failed 4`.

Produced with:

    D=experiments/exp26_srv6_buffer_sweep/plots/full_128_load
    EXP26_RUNS=$D/_runs EXP26_DATA=$D \
      python3 scripts/run_sym.py --figure fig2 --panels dc --dc-full
    EXP26_RUNS=$D/_runs EXP26_DATA=$D \
      python3 scripts/run_sym.py --figure fig4 --panels dc --dc-full
    EXP26_RUNS=$D/_runs EXP26_DATA=$D python3 scripts/aggregate.py
    EXP26_DATA=$D EXP26_PLOTS=$D EXP26_FIGS=fig2,fig4 EXP26_PANELS=dc \
      python3 scripts/plot.py

Contents:
- `fig2_dc.png`, `fig4_dc.png` — the reproduced DC line panels (x = Load Level %,
  y = Average FCT µs), one line per arm.
- `summary.csv` — per-cell aggregate (40 cells).
- `flows.csv.gz` — per-flow FCT rows.
- `runs.tar.gz` — raw htsim stdout for all 40 runs.

The 128-rank workload puts ~6x the flows over the same 8 SRv6 paths, so this is a
harder load-balancing problem than the paper's non-AE fig_2 (which used
`-paths 65535`, no SRv6). See the RESULTS section appended below after the run.

---

## RESULTS (128-rank DC, seed 1019, all 40 cells finished every flow)

Average FCT (µs), and speedup vs the `ops` arm:

### fig_2 (healthy)

| load | ops | B=1 | B=2 | B=4 | B=8 |
|---|---|---|---|---|---|
| 40 % | 67.5 | 67.8 | 67.8 | 67.8 | 67.5 |
| 60 % | 73.2 | 84.0 | 79.8 | 76.3 | 74.7 |
| 80 % | 93.4 | 115.7 | 108.8 | 98.3 | 95.0 |
| 100 % | 190.5 | 201.3 | 187.3 | 184.9 | 182.2 |

speedup vs ops @ 100 %: B=1 **0.95×**, B=2 1.02×, B=4 1.03×, B=8 **1.05×**.

Healthy: OPS and large-B REPS are within a few percent. **B=1 is worse than OPS at
every mid-to-high load** (0.81× at 80 %), B=2 still slightly behind, the knee is
again at **B=4**. Same shape as the 32-rank `_ae` panel, just larger absolute
FCTs (190 µs vs 160 µs at 100 %) and a slightly bigger B=1 penalty.

### fig_4 (`-failed 4`)

| load | ops | B=1 | B=2 | B=4 | B=8 |
|---|---|---|---|---|---|
| 40 % | 69.2 | 68.0 | 67.8 | 67.8 | 67.7 |
| 60 % | 87.9 | 88.7 | 82.7 | 77.4 | 76.1 |
| 80 % | 122.4 | 139.4 | 112.6 | 102.3 | 100.9 |
| 100 % | 230.7 | 206.5 | 201.1 | 196.3 | 195.7 |

speedup vs ops: @ 80 % B=1 **0.88×** → B=4 **1.20×** → B=8 1.21×;
@ 100 % B=1 1.12× → B=8 **1.18×**.

Under asymmetry the **B=4 knee is sharp**: B=1 is 12 % *slower* than OPS at
80 % load, B=2 barely ahead, B=4 jumps to 1.20×. Above B=4 flat. The 128-rank
win (≈1.2×) is very close to the 32-rank `_ae` result (1.17–1.26×) — heavier
traffic did not change the conclusion, it just raised every absolute FCT
(~230 µs vs ~199 µs for OPS at 100 %).

### Bottom line

The 128-rank DC traffic — 6× the flows over the same 8 SRv6 paths, OPS-hostile as
predicted — **reproduces the `_ae` panel's findings unchanged**: healthy ≈ 1×
(small B=1 penalty), asymmetric ≈ 1.2× with a clean knee at B=4, nothing above
B=4. So the choice of the 32-rank AE matrices in the main exp26 plots does not
bias the buffer-size conclusion. Every cell finished all 12331 flows inside the
90 ms window; no OPS collapse at this scale.
