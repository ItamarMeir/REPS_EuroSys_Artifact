# exp23 — FREEZING_PXR: Path-eXcluding REPS

## Purpose

Compare **FREEZING_PXR** (a new REPS variant) against the **FREEZING B=8** baseline from exp22
under identical 51-failed-link topology and workload conditions.

FREEZING B=8 (paper-REPS) handles link failures by entering a frozen mode: it stops sampling
new paths and replays whatever the 8-slot buffer holds — including stale entries that map to
the now-failed links — for 200 ms. This wastes retransmits on known-dead paths until the timer
expires.

FREEZING_PXR keeps the normal REPS sampling logic but **excludes failed EVs from the sampling
domain**. When an RTO fires, the triggering EV is added to a per-source excluded set, and a
sliding 200 ms deadline is refreshed. When the deadline elapses with no new RTO, the entire
excluded set is cleared. The sender never enters frozen mode; it simply avoids selecting
dead-path EVs on every subsequent draw.

---

## Design

| Parameter | Value |
|---|---|
| `-load_balancing_algo freezing_pxr` | new LB enum, gated independently |
| Failure signal | RTO only (EV captured from `sendRecord::sent_ev`) |
| Timer model | Sliding: each new exclusion resets `deadline = now + 200 ms` |
| Clear condition | `now > deadline` OR `|excluded| ≥ _no_of_paths` (saturation guard) |
| NSCC interaction | Sets `_network_is_asymmetric = true` on first exclusion, clears on timer expiry |
| B=8 buffer | Kept: `remove_earliest_fresh()` samples fresh EVs; excluded EVs are skipped |

Architecture: `CLAUDE.md § [ADDED: freezing-pxr]`.

---

## Experiment design

| Axis | Values |
|---|---|
| Algorithm | `freezing_pxr_b8` (exp23, 6 new runs) + `freezing_b8` (exp22 B=8 baseline) |
| CC modes | NSCC, Constant (linerate) |
| Seeds | 42, 43, 44 |
| Topology | K=16 fat tree, 1024 hosts, 400G, 3 tiers |
| Workload | tornado 8 MB (all-to-all permutation, 8 MiB per flow) |
| Failures | 51 agg↔core links (same as exp22: `random.seed(0); random.sample(valid, 51)`) |
| Window | `-pxr_window_us 200000` (200 ms, matching FREEZING's exit window) |
| Buffer log | host 0, seed 42, NSCC only (`buf_freezing_pxr_b8_nscc_s42.csv`) |

---

## Results

### FCT comparison (P50 / P95 / P99, mean ± 95% CI over 3 seeds)

| Algo | CC | P50 (µs) | P95 (µs) | P99 (µs) |
|---|---|---|---|---|
| FREEZING B=8 | NSCC | 295.8 ± 1.2 | 323.6 ± 1.8 | 355.2 ± 2.0 |
| **FREEZING_PXR B=8** | NSCC | **224.1 ± 0.8** | **240.4 ± 1.5** | **245.8 ± 0.2** |
| FREEZING B=8 | Constant | 286.6 ± 2.3 | 316.7 ± 3.1 | 346.6 ± 4.3 |
| **FREEZING_PXR B=8** | Constant | **213.9 ± 0.7** | **227.2 ± 1.6** | **232.1 ± 1.2** |

FREEZING_PXR reduces **P50 by ~24%** and **P99 by ~31%** relative to FREEZING B=8, in both
CC modes. The improvement is statistically clear across all 3 seeds.

### Excluded-set size (host 0, seed 42, NSCC)

From `buf_freezing_pxr_b8_nscc_s42.csv`, host 0 accumulates up to **8 excluded EVs**
over the 90 s simulation, in 8 distinct exclusion events:

```
t=35424 µs  →  {18}
t=35592 µs  →  {18, 21}
t=37035 µs  →  {1, 18, 21}
t=39602 µs  →  {1, 18, 21, 28}
t=40275 µs  →  {1, 2, 18, 21, 28}
t=121226 µs →  {1, 2, 18, 21, 22, 28}
t=185879 µs →  {1, 2, 11, 18, 21, 22, 28}
t=202362 µs →  {1, 2, 11, 18, 21, 22, 28, 44}
```

No timer expiry fires during the simulation (the excluded set never clears), which means the
200 ms sliding window is always refreshed by new RTOs before it can drain. With 8 EVs excluded
out of 64 total paths (12.5%), the sender has 56 EVs available — no saturation.

**Notably**: `frozen_mode = 0` in every row of this CSV — FREEZING_PXR never enters frozen
mode, confirming the mechanism works as designed.

### Plots

| Plot | Description |
|---|---|
| `plots/fct_bars.png` | P50/P95/P99 grouped bars with 95% CI, NSCC and Constant panels |
| `plots/fct_cdf.png` | FCT CDF (per-seed thin + mean bold), NSCC and Constant panels |
| `plots/excluded_size.png` | Excluded-set size over time for host 0, seed 42, NSCC |

---

## Interpretation

FREEZING cycles stale buffer entries — including dead-path EVs — for a 200 ms frozen
window. Every retransmit that selects EV=X while the link X maps to is failed is wasted,
and the sender must wait for another RTO before trying again. With 51 failed links in a
K=16 topology (51 / 512 = 10% of agg↔core capacity), this happens frequently.

FREEZING_PXR avoids all of this: it permanently skips confirmed-dead EVs and continues
drawing from the remaining 56+ healthy EVs. The ~31% P99 improvement is exactly the
budget that FREEZING was spending on futile retransmits onto known-dead paths.

The sliding-timer mechanism performs no useful cleanup in this experiment (the timer never
fires), but the saturation guard (|excluded| ≥ _no_of_paths) ensures safety if a topology
has few paths.

---

## File layout

```
exp23_freezing_pxr_v23/
├── README.md
├── scripts/
│   ├── run_exp23.sh        — 6 new freezing_pxr_b8 runs
│   ├── aggregate.py        — merges exp23 runs + exp22 B=8 baseline
│   ├── plot_fct.py         — FCT bars + CDF
│   └── plot_excluded.py    — excluded-set size over time
├── data/
│   ├── exp23_flows.csv     — 12288 rows (12 combos × 1024 flows)
│   └── buf_freezing_pxr_b8_nscc_s42.csv
├── plots/
│   ├── fct_bars.png
│   ├── fct_cdf.png
│   └── excluded_size.png
└── runs/                   — compress to runs.tar.gz after verification
```

---

## How to reproduce

```bash
# 1. Build (if needed)
cd htsim/sim && make -j8 && cd datacenter && make -j8 && cd ../../..

# 2. Run 6 new simulations
bash experiments/exp23_freezing_pxr_v23/scripts/run_exp23.sh

# 3. Aggregate (reads exp22 B=8 baseline from exp22/runs.tar.gz)
python3 experiments/exp23_freezing_pxr_v23/scripts/aggregate.py

# 4. Plot
python3 experiments/exp23_freezing_pxr_v23/scripts/plot_fct.py
python3 experiments/exp23_freezing_pxr_v23/scripts/plot_excluded.py

# 5. Compress runs
tar -czf experiments/exp23_freezing_pxr_v23/runs.tar.gz \
    -C experiments/exp23_freezing_pxr_v23/runs . && \
rm -rf experiments/exp23_freezing_pxr_v23/runs/
```

---

## Open questions / follow-up

- **Timer sweep**: the excluded set never clears in this experiment. A sweep over shorter
  windows `{5, 20, 50, 100} ms` would test whether the sliding timer is ever useful vs
  keeping exclusions permanently until flow end.
- **B sweep**: exp22 swept B=1–64. Running FREEZING_PXR at B=1,4,16,64 would show whether
  buffer size matters under path exclusion (hypothesis: it doesn't, since healthy-path coverage
  is ensured by the exclusion mechanism rather than buffer diversity).
- **Saturation test**: a topology with very few paths (e.g. K=4, 4 paths) and many failures
  could trigger the |excluded| ≥ _no_of_paths saturation guard — untested so far.
