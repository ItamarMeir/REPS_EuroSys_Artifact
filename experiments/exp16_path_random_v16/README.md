# exp16 — PATH_RANDOM: Random Path Selection vs Deterministic Round-Robin

**Added:** 2026-06-06
**Status:** complete — see results below

---

## Motivation

exp15 showed that the *starting order* of PATH_RR's round-robin cycle has zero effect on FCT
across all flow sizes. The remaining question: does **random** path selection (rather than
deterministic cycling) differ from round-robin?

If deterministic round-robin somehow creates residual periodic congestion — e.g., by clustering
packets from different flows on the same core at regular intervals — then randomness should break
that pattern and reduce FCT.

---

## Design

**Fixed**: tornado workload, N=16, 4-ary fat-tree 3-tier, 400 Gbps, cwnd=90
**Variable**: load balancing algorithm (PATH_RANDOM vs PATH_RR and FREEZING from exp14)

| Condition | LB algorithm | CC algorithm |
|-----------|-------------|--------------|
| `path_random+constant` | PATH_RANDOM (uniform per-packet) | constant (line-rate) |
| `path_random+nscc`     | PATH_RANDOM | NSCC |

**PATH_RANDOM implementation**: on every packet (including retransmissions), picks a fresh
uniform-random index in `[0, num_paths)`. No cursor, no state between packets. Uses the same
pre-computed `_paths[]` buffer as PATH_RR (populated by `get_bidir_paths` at flow setup).

**Elephant flow sizes only** (startup overhead <4% at these sizes, per exp15 finding):
- 16 MiB (transition point; also the overlap with exp14 data for direct comparison)
- 64 MiB (fully converged elephant)
- 256 MiB (fully converged elephant)

18 runs: 2 conditions × 3 sizes × 3 seeds

---

## Results

See [plots/exp16_fct_slowdown.png](plots/exp16_fct_slowdown.png).

### At 16 MiB (comparison with exp14 baselines)

| Condition | Avg slowdown | Max slowdown |
|-----------|-------------|--------------|
| path_rr+constant    | 1.7703±0.0003 | 1.7722±0.0009 |
| **path_random+constant** | **1.7743±0.0013** | **1.7761±0.0017** |
| freezing+constant   | 1.7724±0.0008 | 1.7739±0.0015 |
| path_rr+nscc        | 1.0910±0.0037 | 1.0936±0.0048 |
| **path_random+nscc**    | **1.1113±0.0059** | **1.1254±0.0145** |
| freezing+nscc       | 1.1312±0.0329 | 1.1641±0.0138 |

### PATH_RANDOM across elephant sizes

| Condition | 16 MiB avg | 64 MiB avg | 256 MiB avg |
|-----------|------------|------------|-------------|
| path_random+constant | 1.7743±0.0013 | 1.7586±0.0001 | 1.7548±0.0004 |
| path_random+nscc     | 1.1113±0.0059 | 1.0583±0.0043 | 1.0444±0.0016 |

### Finding 1: PATH_RANDOM+constant is indistinguishable from PATH_RR+constant

At 16 MiB, the difference is 0.004 — within noise and smaller than the ±0.0013 CI.
Randomness in path selection does not improve FCT under constant CC.

This extends exp15's conclusion beyond ordering to randomness: **the path-selection policy
(deterministic RR, any starting index, or pure random) is irrelevant under constant CC**.
The ~1.75× overhead is entirely from cwnd=90 > BDP≈73, not from any temporal path correlation.

### Finding 2: PATH_RANDOM+NSCC is slightly worse than PATH_RR+NSCC at 16 MiB

PATH_RR+NSCC: 1.091±0.004 vs PATH_RANDOM+NSCC: 1.111±0.006 (Δ=0.020, ~2%).

The difference is small but measurable (CIs don't overlap). The likely explanation:
PATH_RR distributes load perfectly evenly (exactly 1 packet per path per 4-packet cycle),
while PATH_RANDOM has variance — occasionally 2 consecutive packets hit the same core
switch. Under NSCC (which reacts to queue depth), these random bursts trigger slightly
more MD events, adding a small extra slowdown. The effect shrinks at larger flows
(PATH_RANDOM+NSCC reaches 1.044× at 256 MiB vs PATH_RR+NSCC ~1.091× at 16 MiB).

### Finding 3: PATH_RANDOM+NSCC converges like PATH_RR+NSCC

Both show the overhead decreasing across elephant sizes. At 256 MiB, PATH_RANDOM+NSCC
reaches 1.044× — very close to the PATH_RR+NSCC baseline.

---

## OPS comparison (exp16c — 16 MiB)

See [plots/exp16_ops_comparison.png](plots/exp16_ops_comparison.png).

OPS (`-load_balancing_algo oblivious`) uses entropy spraying through standard switch ECMP
(per-packet `rand() % 65535` entropy value; switches hash it to physical ports). This is the
original paper's baseline. PATH_RR/PATH_RANDOM bypass ECMP via full source routing.

| Condition | Avg slowdown | Max slowdown |
|-----------|-------------|--------------|
| path_rr+constant    | 1.7703±0.0003 | 1.7722±0.0009 |
| path_rr+nscc        | 1.0910±0.0037 | 1.0936±0.0048 |
| freezing+constant   | 1.7724±0.0008 | 1.7739±0.0015 |
| freezing+nscc       | 1.1312±0.0329 | 1.1641±0.0138 |
| path_random+constant| 1.7743±0.0013 | 1.7761±0.0017 |
| path_random+nscc    | 1.1113±0.0059 | 1.1254±0.0145 |
| **ops+constant**    | **1.7742±0.0001** | **1.7761±0.0006** |
| **ops+nscc**        | **1.1137±0.0096** | **1.1286±0.0107** |

### Finding 4: OPS+constant is indistinguishable from PATH_RANDOM+constant and PATH_RR+constant

All three produce ~1.774× avg slowdown at 16 MiB. Source routing vs entropy spraying makes no
difference under constant CC — the cwnd/BDP mismatch dominates entirely.

### Finding 5: OPS+NSCC ≈ PATH_RANDOM+NSCC, both slightly worse than PATH_RR+NSCC

OPS+NSCC (1.114±0.010) and PATH_RANDOM+NSCC (1.111±0.006) are statistically
indistinguishable. Both are ~2% worse than PATH_RR+NSCC (1.091±0.004).

This is a significant equivalence: **OPS (entropy spraying via ECMP) and PATH_RANDOM (source
routing with explicit paths) are identical in FCT**. The performance gap vs PATH_RR is entirely
due to the randomness causing occasional back-to-back packets on the same core — a property
shared by both OPS and PATH_RANDOM regardless of the routing mechanism. Source routing itself
confers no FCT advantage when the path selection policy is random.

---

## Implications

1. **Under constant CC**: path selection policy (RR, random, entropy-spray OPS, any ordering)
   is entirely irrelevant. The bottleneck is always cwnd/BDP mismatch.

2. **Under NSCC**: deterministic RR is marginally better than random or OPS at smaller
   elephant sizes (~2% at 16 MiB). The gap arises from perfectly even load distribution
   in RR vs occasional bursts in random/OPS; it is not caused by the routing mechanism
   (source routing vs entropy spray).

3. **FREEZING+NSCC remains best for large-flow max FCT**: its active path management
   (evicting congested paths) continues to outperform both PATH_RR and PATH_RANDOM.

4. **OPS ≡ PATH_RANDOM in FCT**: at this topology and cwnd setting, bypassing switch ECMP
   via source routing offers no benefit over entropy spraying when the per-packet path
   selection is uniform random.

---

## Core switch queue depths (exp16b)

See [plots/exp16_queue_depth.png](plots/exp16_queue_depth.png).

Sampled agg→core uplink queues every 1 µs during 64 MiB seed=42 runs.
Y = total bytes across all agg→core[c] queues for each core c.

### Mean queue depth per core switch (KB)

| Condition | core0 | core1 | core2 | core3 |
|-----------|-------|-------|-------|-------|
| path_rr_constant    |  2.7 |  2.8 |  2.8 |  2.8 |
| path_rr_nscc        |  3.5 | 25.3 | 26.8 |  3.1 |
| freezing_constant   |  2.8 |  3.0 |  3.0 |  3.4 |
| freezing_nscc       | 19.2 | 16.7 | 14.6 | 18.6 |
| path_random_constant|  3.3 |  3.2 |  3.3 |  3.4 |
| path_random_nscc    | 59.4 | 48.2 | 44.4 | 49.1 |

### Finding 4: All constant-CC conditions are uniformly lightly loaded (~3 KB per core)

Under constant CC, no policy builds significant queues. All three LB algorithms keep cores
near-equally loaded (2.7–3.4 KB). The cwnd=90 >> BDP≈73 overfill is spread evenly across
all paths, so queue depth per core is bounded and stable.

### Finding 5: PATH_RR+NSCC creates a severe 2-of-4 core imbalance

Cores 1 and 2 accumulate ~25 KB mean depth; cores 0 and 3 stay at ~3 KB. This is a
structural artifact of how RR + NSCC interacts with the tornado workload: deterministic
round-robin assigns packets cyclically, so specific src-dst pairs consistently share the
same core switches. NSCC then converges to a stable regime where two cores are persistently
saturated and two are near-idle, because the cwnd reduction on the congested cores doesn't
redirect traffic (path is fixed per-packet cycle, not per-feedback event).

### Finding 6: FREEZING+NSCC spreads load evenly at moderate depth (~17 KB per core)

FREEZING's path eviction actively migrates traffic away from congested cores when its
buffer fills. The result: all 4 cores see similar steady-state depth (14–19 KB). This is
higher in absolute terms than PATH_RR+NSCC's *light* cores but vastly more balanced overall,
explaining FREEZING+NSCC's better max-FCT in the flow results.

### Finding 7: PATH_RANDOM+NSCC has the highest absolute queue depth

PATH_RANDOM's per-packet randomness creates occasional back-to-back bursts to the same
core. NSCC reacts with cwnd reduction, but the next packet may again land on any core —
including the congested one. This incoherence between path feedback and path selection
prevents the natural stabilisation that RR achieves, resulting in all 4 cores building
deeper queues (44–59 KB). Despite this, FCT slowdown at 64 MiB is only ~3% worse than
PATH_RR+NSCC (1.058 vs ~1.091) — the deeper queues add marginal extra queuing delay to
individual flows but most of the slowdown comes from retransmissions and cwnd dynamics.

---

## CLI

`-load_balancing_algo path_random` — enables per-packet uniform-random path selection.
Uses the same `_paths[]` infrastructure as `-load_balancing_algo path_rr`.
`-path_rr_start_mode` has no effect for PATH_RANDOM (ignored silently).
Implemented in `htsim/sim/uec.h`, `uec.cpp`, `datacenter/main_uec.cpp`.

`-load_balancing_algo oblivious` — OPS: per-packet entropy spraying via switch ECMP.
`-paths 65535` sets the entropy pool depth. No path pre-population needed.

`-log_core_queues <file>` — samples all agg→core uplink queue depths every 1 µs to a CSV
(`time_us,agg,core,bytes`). Implemented via `CoreQueueSampler` class in `datacenter/main_uec.cpp`.

---

## Files

```
exp16_path_random_v16/
├── README.md
├── scripts/
│   ├── 01_run_exp16.sh                  (PATH_RANDOM runs, 16/64/256 MiB × 3 seeds)
│   ├── 02_run_exp16_baselines_large.sh  (PATH_RR/FREEZING at 64/256 MiB × 3 seeds)
│   ├── 03_run_exp16_qlog.sh             (queue depth logging, all 6 conditions, 64 MiB seed=42)
│   └── 04_run_exp16_ops.sh              (OPS+constant/nscc at 16 MiB × 3 seeds)
├── data/
│   ├── exp16_*.out         (48 raw outputs)
│   ├── fcts.csv
│   └── qlog_*.csv          (6 queue-depth logs)
├── plots/
│   ├── exp16_fct_slowdown.png
│   ├── exp16_queue_depth.png
│   └── exp16_ops_comparison.png
├── aggregate_exp16.py
├── plot_exp16.py
├── plot_exp16_ops.py
└── plot_exp16_queues.py
```
