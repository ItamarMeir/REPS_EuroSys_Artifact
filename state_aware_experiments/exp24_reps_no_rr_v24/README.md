# exp24 — Does REPS's first-window round-robin explain its FCT gap vs FREEZING?

## Motivation

exp21 (`state_aware_experiments/exp21_srv6_buffer_sweep_k16_v21/`) found plain REPS
consistently slower than every FREEZING buffer size (B=8..64) on K=16 tornado, both CC
modes, across all 3 seeds — a systematic, reproducible direction. exp21's README attributed
this to "REPS's unbounded deque accumulates stale path IDs." Re-checking that claim against
the raw per-ACK logs (`exp21/data/buf_freezing_b64_nscc_s42.csv`,
`buf_reps_nscc_s42.csv`, after fixing a logger bug that had made REPS's `buf_contents`/
`buf_size` columns always empty/constant) showed the opposite: REPS's recycle-pool depth
(avg 4.99, empty 14.8% of ACKs) and FREEZING's (avg fresh 5.29, empty 16.6%) are
statistically indistinguishable. Buffer occupancy is not the driver.

Alternative hypothesis: REPS's first-window phase (`nextEntropy_REPS`, `uec.cpp:3046-3054`)
is a **deterministic round-robin** — `_crt_path++` every call, no randomness, identical
sequence for every flow. Tornado is a synchronized-start permutation workload (all 1024
flows begin at t≈0). If many flows round-robin through path indices in lockstep, they
converge on the same physical core-switch/uplink during the same time slice, then shift
together — a self-inflicted, correlated hotspot. FREEZING has no such phase: its buffer
starts empty, so it draws `random()` from packet 1, desynchronizing flows' path choices
immediately.

**Test**: temporarily disable REPS's round-robin so it falls straight to the existing
steady-state logic (`random()` if pool empty, else recycle) — i.e. make REPS's first-window
behavior match FREEZING's (no explore phase, immediate random fallback). Re-run REPS only,
3 seeds × 2 CC modes, and compare FCT against FREEZING B=64 and original (round-robin) REPS.

## Code change (temporary — applied, run, then reverted)

`htsim/sim/uec.cpp:3044-3073`, single-line change:

```cpp
if (_mss * _highest_sent < min((uint64_t)_cwnd, allpathssizes)) {   // original
if (false && _mss * _highest_sent < min((uint64_t)_cwnd, allpathssizes)) {  // exp24 temp
```

Built into a one-off Docker image, run, then reverted (`git checkout -- htsim/sim/uec.cpp`)
and rebuilt back to the canonical binary immediately after. No CLI flag added — this was a
throwaway ablation, not a permanent feature (no MODIFICATIONS.md row).

## Design matrix

Reuses exp21's exact topology/workload/flags (`fat_tree_1024_1os_3t_400g.topo`,
`tornado_n1024_s8388608.cm`, SRv6, `-paths 64`) — only the algorithm differs.

| Label | LB algorithm | New runs? |
|---|---|---|
| `path_static` | PATH_STATIC (greedy oracle) | reused from exp21 |
| `freezing_b64` | FREEZING, B=64 | reused from exp21 |
| `reps` | REPS, original (with round-robin) | reused from exp21 |
| `reps_no_rr` | REPS, round-robin disabled (this exp) | **6 new runs** |

CC modes: NSCC (`-sender_cc_algo nscc -cwnd 100`), CONSTANT (`-sender_cc_algo constant -cwnd 1000`).
3 seeds (42, 43, 44) × 2 CC modes = 6 new `reps_no_rr` runs, built and run inside a Docker
container (`reps-artifact` image, rebuilt with the temp code change) per this repo's
documented Docker workflow.

## Results

All FCTs normalized to PATH_STATIC+CONSTANT mean FCT (185.36 µs) — same reference exp21
used, so the two are directly comparable. Mean over 3 seeds, ±95% CI (t-distribution).
Every FREEZING buffer size from exp21 (B=1..64) is included, reused read-only.

### Mean FCT (× PATH_STATIC+CONSTANT)

| Algorithm | NSCC | ±95% CI | CONSTANT | ±95% CI |
|---|---|---|---|---|
| PATH_STATIC | 1.037 | 0.000 | 1.000 | 0.000 |
| FREEZING B=1 | 1.1065 | 0.0018 | 1.0739 | 0.0054 |
| FREEZING B=2 | 1.1113 | 0.0013 | 1.0841 | 0.0006 |
| FREEZING B=4 | 1.1087 | 0.0005 | 1.0842 | 0.0011 |
| FREEZING B=8 | 1.1089 | 0.0016 | 1.0839 | 0.0026 |
| FREEZING B=16 | 1.1090 | 0.0014 | 1.0837 | 0.0025 |
| FREEZING B=32 | 1.1090 | 0.0013 | 1.0838 | 0.0025 |
| FREEZING B=64 | 1.1090 | 0.0013 | 1.0838 | 0.0025 |
| REPS (round-robin, original) | **1.1411** | 0.0014 | **1.0994** | 0.0024 |
| **REPS (no round-robin, exp24)** | **1.1090** | **0.0013** | **1.0838** | **0.0025** |

### p99 FCT (× PATH_STATIC+CONSTANT)

| Algorithm | NSCC | ±95% CI | CONSTANT | ±95% CI |
|---|---|---|---|---|
| PATH_STATIC | 1.037 | 0.000 | 1.000 | 0.000 |
| FREEZING B=1 | 1.1235 | 0.0026 | 1.0922 | 0.0079 |
| FREEZING B=8 | 1.1284 | 0.0055 | 1.1006 | 0.0016 |
| FREEZING B=64 | 1.1293 | 0.0085 | 1.1004 | 0.0032 |
| REPS (round-robin, original) | **1.1622** | 0.0085 | **1.1137** | 0.0042 |
| **REPS (no round-robin, exp24)** | **1.1293** | **0.0085** | **1.1004** | **0.0032** |

`reps_no_rr` lands squarely inside the FREEZING B=1..64 band on every metric and CC mode —
not just matching B=64, matching *all* buffer sizes simultaneously, consistent with exp21's
own finding that buffer size doesn't matter on tornado. Original `reps` (round-robin) sits
clearly *above* the entire FREEZING band, outside every FREEZING variant's CI. Full plots:
`plots/mean_fct.png`, `plots/p99_fct.png`, `plots/slowdown.png` (same 3-panel layout as
`exp21/plots/`, with `reps_no_rr` added as a 9th bar group).

## Interpretation

**Hypothesis confirmed.** Disabling REPS's deterministic first-window round-robin closes
essentially the entire FCT gap to FREEZING B=64. Since occupancy/empty-rate stats were
already shown (this session, pre-exp24) to be statistically indistinguishable between REPS
and FREEZING, the round-robin phase — not buffer boundedness, not "stale EV accumulation" —
is the actual driver of exp21's REPS-vs-FREEZING gap on tornado.

Mechanism (not directly measured here, but consistent with the result): tornado's
synchronized flow starts mean every flow's `_crt_path` sequence (0, 1, 2, ...) runs in
lockstep across the whole fabric during the first-window phase. That correlates load onto
the same physical core switch/uplink across many flows simultaneously, then shifts it in
sync — a self-inflicted hotspot absent when path choice is randomized from packet 1 (both
FREEZING's default and REPS-no-RR's behavior here).

**Practical implication**: REPS's first-window sweep, as currently implemented
(`uec.cpp:3046-3054`), is not neutral or beneficial on synchronized-start workloads — it is
actively harmful relative to just randomizing from the start. This is a genuine algorithmic
finding, not a diagnostic-noise artifact (exp21's original "stale accumulation" explanation
is now superseded — README there should be corrected to point here).

**Caveat**: this was tested only on tornado (fully synchronized starts, K=16, no failures).
Unsynchronized or lower-fanout workloads may not exhibit the same lockstep correlation, so
this doesn't necessarily mean the first-window sweep is harmful everywhere — future work
could test a Poisson-arrival or partially-loaded workload to see if the effect persists or
disappears.

## Files

```
exp24_reps_no_rr_v24/
├── scripts/aggregate.py   parses the 6 new .out files + reuses exp21_flows.csv (read-only)
├── scripts/plot.py        plots mean/p99 FCT (normalized to PATH_STATIC+CONSTANT), path_static/freezing_b64/reps/reps_no_rr
├── scripts/plot_fct_raw.py absolute (non-normalized) mean FCT bar chart, same algos/data, value labeled per bar
├── data/exp24_flows.csv   60416 rows (6144 new reps_no_rr + 54272 reused from exp21)
├── plots/mean_fct.png
├── plots/mean_fct_raw.png
├── plots/p99_fct.png
└── runs/reps_no_rr_{nscc,constant}_s{42,43,44}.out   6 new raw simulator outputs
```

No files under `exp21_srv6_buffer_sweep_k16_v21/` were modified — reused read-only via
`exp21_flows.csv`. `htsim/sim/uec.cpp`'s temporary round-robin-disable edit was reverted
immediately after the 6 runs completed; `git diff` on that file post-revert contains only
this session's unrelated, permanent REPS buffer-contents-logger fix.

## Build/run environment note

Built and run via Docker (`docker compose build` → `reps-artifact` image), not the host or
WSL — CLAUDE.md's Docker section should be the default build path for anything beyond
trivial host `make`, since host/WSL cross-filesystem builds hit clock-skew and
GLIBC-version mismatches this session ran into. `.cm` connection-matrix files and some
topology files are `.dockerignore`d (generated/large artifacts) — `docker cp` them into a
running container before invoking `htsim_uec` if a workload file is missing from the image.
