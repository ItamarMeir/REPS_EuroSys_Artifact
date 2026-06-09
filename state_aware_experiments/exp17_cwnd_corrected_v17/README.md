# exp17 — Five-algorithm comparison at corrected cwnd=155

**Added:** 2026-06-07
**Status:** complete — see results below

---

## Motivation

exp16 used `cwnd=90` but the BDP for this topology (k=4 fat-tree, 400 Gbps, 6-hop RTT ~12.5 µs)
is ~150.7 MTUs. At cwnd=90 the sender operates at only ~60% BDP, inflating all FCTs. This
experiment repeats the 5-algorithm comparison at `cwnd=155` — the empirically-determined knee
where PATH_STATIC+constant first reaches its FCT plateau — and adds:

1. **PATH_STATIC** — a new greedy edge-load algorithm that pins each flow to a single fixed path
   for its entire lifetime, chosen to minimise the maximum link load. Needs a reverse-path routing
   fix for ACK/PULL packets (see `[ADDED: path-static]` in CLAUDE.md).
2. **OPS** — Oblivious Packet Spraying (random per-packet), included as a comparison baseline.
3. **256 MiB flows** — separate sub-experiment at 256 MiB (stored in `plot_exp17_256mib.py`).

---

## Design

**Fixed**: tornado workload, N=16, 4-ary fat-tree 3-tier, 400 Gbps, cwnd=155, seeds 42/43/44
**Variable**: LB algorithm × CC algorithm

| Condition | LB | CC |
|-----------|----|----|
| `path_rr_constant`     | PATH_RR     | constant |
| `path_rr_nscc`         | PATH_RR     | NSCC |
| `freezing_constant`    | FREEZING    | constant |
| `freezing_nscc`        | FREEZING    | NSCC |
| `path_random_constant` | PATH_RANDOM | constant |
| `path_random_nscc`     | PATH_RANDOM | NSCC |
| `ops_constant`         | OPS         | constant |
| `ops_nscc`             | OPS         | NSCC |
| `path_static_constant` | PATH_STATIC | constant |
| `path_static_nscc`     | PATH_STATIC | NSCC |

10 conditions × 2 sizes (16/64 MiB) × 3 seeds = 60 runs; plus 10 × 1 size (256 MiB) × 3 seeds = 30 runs.

---

## Key code addition: PATH_STATIC with reverse-path routing

PATH_STATIC's greedy algorithm assigns each flow to the path with the minimum maximum edge load.
For the tornado workload on a k=4 fat-tree with `np=4` paths per flow, all 16 flows are assigned
with `max_edge_load=0` — no shared data-path edges at all.

ACK/PULL return packets were originally routed via ECMP, causing hash collisions in bidirectional
tornado (two hosts exchange flows in both directions, so the return path is contested). The fix
overrides `UecSinkPort._route` with a full source-routed reverse path:

```cpp
const Route* orig_r = (*paths)[best_idx];
if (orig_r->reverse()) {
    Route* rev = new Route(*orig_r->reverse(), *uec_src->getPort(p));
    uec_snk->getPort(p)->setRoute(*rev);
}
```

This eliminates the ~80 µs bimodal FCT spread — all 16 flows finish at identical times (0.00 µs
spread) at 1.033× slowdown vs the theoretical floor.

---

## Results

See [plots/exp17_fct_slowdown.png](plots/exp17_fct_slowdown.png) (16/64 MiB) and
[plots/exp17_fct_slowdown_256mib.png](plots/exp17_fct_slowdown_256mib.png) (256 MiB).

### 16 MiB + 64 MiB summary (mean ± 95% CI across 3 seeds)

| Condition | 16 MiB avg | 64 MiB avg |
|-----------|-----------|-----------|
| path_rr_constant     | 1.0564±0.0018 | 1.0438±0.0026 |
| path_rr_nscc         | 1.0550±0.0037 | 1.0418±0.0038 |
| freezing_constant    | 1.0821±0.0077 | 1.0673±0.0069 |
| freezing_nscc        | 1.0890±0.0233 | 1.0821±0.0478 |
| path_random_constant | 1.1139±0.0036 | 1.1014±0.0018 |
| path_random_nscc     | 1.0745±0.0056 | 1.0482±0.0015 |
| ops_constant         | 1.1142±0.0039 | 1.1019±0.0031 |
| ops_nscc             | 1.0739±0.0035 | 1.0484±0.0020 |
| **path_static_constant** | **1.0490±0.0000** | **1.0366±0.0000** |
| **path_static_nscc**     | **1.0478±0.0000** | **1.0355±0.0000** |

### 256 MiB summary (mean ± 95% CI across 3 seeds)

| Condition | Avg-slowdown | Max-slowdown |
|-----------|-------------|-------------|
| path_rr_constant     | 1.0405±0.0029 | 1.0426±0.0058 |
| path_rr_nscc         | 1.0363±0.0028 | 1.0389±0.0040 |
| freezing_constant    | 1.0632±0.0065 | 1.0791±0.0070 |
| freezing_nscc        | 1.0812±0.0517 | 1.1085±0.0030 |
| path_random_constant | 1.0984±0.0013 | 1.0998±0.0003 |
| path_random_nscc     | 1.0419±0.0002 | 1.0437±0.0004 |
| ops_constant         | 1.0983±0.0013 | 1.0995±0.0006 |
| ops_nscc             | 1.0414±0.0004 | 1.0428±0.0010 |
| **path_static_constant** | **1.0334±0.0000** | **1.0334±0.0000** |
| **path_static_nscc**     | **1.0324±0.0000** | **1.0324±0.0000** |

---

## Findings

### Finding 1: PATH_STATIC is the best algorithm at all sizes

PATH_STATIC achieves the lowest avg FCT at every flow size — 1.049/1.037/1.033× at 16/64/256 MiB.
Its zero CI spread (all seeds identical) confirms structural collision elimination: with no shared
data-path edges in tornado, every flow runs at exactly the same rate, every seed.

### Finding 2: PATH_RR (both CCs) is second-best at cwnd=155

At cwnd=155, PATH_RR closes within 0.007× of PATH_STATIC at all sizes. FREEZING performs worse
than PATH_RR in this regime — NSCC+FREEZING has 5× larger CI than NSCC+PATH_RR at 256 MiB
(±0.052 vs ±0.003), suggesting that the entropy-spray randomness creates seed-to-seed variance
in which core links get shared.

### Finding 3: PATH_RANDOM ≈ OPS at all sizes (both equally worse than PATH_RR)

PATH_RANDOM and OPS are within 0.001× of each other at every data point. Deterministic round-robin
over paths outperforms random per-packet selection by ~3–4% at 16/64 MiB and ~6% at 256 MiB.

### Finding 4: CC matters but less at cwnd=155 than at cwnd=90

At cwnd=155, the constant vs NSCC gap is only ~0.001–0.007× (down from ~0.5× at cwnd=90), except
for OPS/PATH_RANDOM where NSCC helps by ~3%. PATH_RR+constant ≈ PATH_RR+NSCC.

---

## How to reproduce

```bash
# Build binary first (from repo root):
cd htsim/sim && make -j8 && cd ../..

# 16 MiB + 64 MiB runs:
bash state_aware_experiments/exp17_cwnd_corrected_v17/scripts/01_run_exp17.sh

# 256 MiB runs:
bash state_aware_experiments/exp17_cwnd_corrected_v17/scripts/02_run_exp17_256mib.sh

# Aggregate and plot:
python3 state_aware_experiments/exp17_cwnd_corrected_v17/aggregate_exp17.py
python3 state_aware_experiments/exp17_cwnd_corrected_v17/plot_exp17.py
python3 state_aware_experiments/exp17_cwnd_corrected_v17/plot_exp17_256mib.py
```
