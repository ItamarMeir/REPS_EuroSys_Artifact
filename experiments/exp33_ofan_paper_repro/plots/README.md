# plots/ layout

`plots/<experiment>/<figure>/<files>.png`, one folder per reproduced paper figure (Ofan, arXiv 2610.07230). All plots use the paper's visual style
(`scripts/paperstyle.py`: horizontal bars / marker lines, REPS teal inverted triangle, AR green square, Ofan purple diamond, SEM error bars, legend row on top,
bold serif captions). 4Ofan is not implemented and is omitted from every plot.

| folder | paper figure | files | script |
|---|---|---|---|
| `e1_fig1/` | Fig 1 (utilisation, max queue, CCT vs load) | `fig1.png` (3 panels), `fig1a_util.png`, `fig1b_maxq.png`, `fig1c_cct.png`, `extra_*.png` (busiest-link util, CCT increase) | `scripts/plot_e1.py` |
| `e4_fig12/` | Fig 12 (4 MiB permutation, DCTCP / NSCC / MSwift) | per CCA `<cca>_fig12.png` (panels a-c / d-f / g-i), `<cca>_cct.png` (linear axis), `<cca>_util.png`, `<cca>_maxq.png` | `scripts/plot_e4.py` |

Other experiments add their own `e2_*/`, `e3_*/` folders (some older flat `e3_*.png` files may still sit in this directory).

Run plotting scripts inside container `ofan-dev` (matplotlib + pandas): `docker exec ofan-dev python3 /workspace/experiments/exp33_ofan_paper_repro/scripts/plot_e4.py`.

## E4 Fig 12 data provenance
* CCT bars: mean +- SEM over 10 seeds (`data/e4/e4_summary.csv`).
* Utilisation and max-queue time series: ONE seed (seed 1) per (CCA, LB) from `scripts/run_e4_ts.sh` (same command line as `run_e4.sh` + `-log_core_queues -log_tor_queues -log_link -end 150`,
  no simulator change), reduced by `scripts/ts_e4.py` into `data/e4/ts/<cca>_<lb>_s1_series.csv` (1 us bins). `-log_link` logs every switch forwarding decision (time, egress queue);
  per-queue FIFO service at 41.5 ns/packet is replayed offline to get busy time (utilisation) and packets in system (queue depth). Cross-check: reconstructed A->C max queue equals the
  simulator's own 1 us queue sampler (`-log_core_queues`).
  * Utilisation = mean busy fraction of the 432 ToR uplinks (E->A links) per 1 us bin. The paper's exact definition is not stated; the host-facing E->H links are not logged by the binary.
  * Max queue = max over all E->A, A->C, C->A, A->E queues (E->H not logged; its end-of-run max is lower than the fabric max in every run).
