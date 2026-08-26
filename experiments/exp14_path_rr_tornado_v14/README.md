# exp14 — PATH_RR vs REPS on Tornado Workload

**Added:** 2026-06-04
**Status:** scripts ready; run `scripts/01_run_exp14.sh` to populate `data/`

---

## Motivation

PATH_RR (see [PATH_RR_ARCHITECTURE.md](../PATH_RR_ARCHITECTURE.md)) is a true round-robin over
distinct physical paths via source routing, bypassing per-hop ECMP entirely. In a 4-ary fat-tree,
there are exactly 4 distinct cross-pod paths. PATH_RR guarantees each successive packet takes the
next path, while paper-REPS (FREEZING) approximates load balancing through probabilistic
entropy recycling.

The tornado workload is the most adversarial pattern for ECMP-based LB: all hosts i send to
i+N/2 simultaneously, aligning all flows onto the same cross-pod routes. This experiment
measures how close each algorithm gets to the **theoretical minimum FCT** (non-blocking topology
+ full line-rate BW per flow).

---

## Design

| # | Condition | LB algo | CC algo |
|---|-----------|---------|---------|
| 1 | `path_rr+constant` | `path_rr` | `constant` (line-rate) |
| 2 | `path_rr+nscc`     | `path_rr` | `nscc` |
| 3 | `freezing+nscc`    | `freezing` | `nscc` |
| 4 | `freezing+constant`| `freezing` | `constant` (line-rate) |

- **Topology**: `fat_tree_16_1os_3t_400g.topo` — k=4, 16 hosts, 3-tier
- **Workload**: tornado N=16 (host i → host (i+8)%16), sizes 4/8/16 MiB
- **Simulator seeds**: 42, 43, 44 (varies ECMP hash salts; tornado pattern is deterministic)
- **Total runs**: 4 × 3 × 3 = 36

---

## Metric: FCT Slowdown from Optimal

The 4-ary fat-tree is non-blocking: with perfect LB every flow can get full line-rate
simultaneously. Theoretical minimum FCT:

```
optimal_fct_us = (flow_size_bytes × 8) / 400e9 × 1e6  +  6 × 0.5
               = transmission_us + propagation_us
```

Where 6 hops = `host→ToR→Agg→Core→Agg→ToR→host` (all tornado flows are cross-pod).
Example: 8 MiB at 400 Gbps → 167.8 + 3.0 = **170.8 µs**

**Slowdown** = actual_fct / optimal_fct (1.0 = perfect; lower is better)

This is more informative than an ECMP-relative speedup ratio because the ideal is
topology-grounded and does not depend on an arbitrary baseline.

---

## How to Run

```bash
# Build first (if needed)
cd htsim/sim && make -j8 && cd datacenter && make -j8 && cd ../../..

# Run all 36 simulations (idempotent — skips completed runs)
bash experiments/exp14_path_rr_tornado_v14/scripts/01_run_exp14.sh

# Aggregate FCTs
python3 experiments/exp14_path_rr_tornado_v14/aggregate_exp14.py

# Plot
python3 experiments/exp14_path_rr_tornado_v14/plot_exp14.py
```

Output: `plots/exp14_fct_slowdown.png`

---

## Simulation Parameters

Derived from Paper 1 (REPS, arXiv:2407.21625) base parameters, adapted for 16-host 3-tier:

| Flag | Value | Note |
|------|-------|------|
| `-linkspeed` | 400000 (400 Gbps) | Paper 1 value |
| `-hop_latency` | 0.5 µs | Paper 1 value |
| `-q` | 60 pkts | 1 BDP |
| `-ecn` | 12 48 | Kmin=20%, Kmax=80% of queue |
| `-cwnd` | 90 | Initial window; CONSTANT CC holds this |
| `-paths` | 65535 | Entropy space |
| `-sack_threshold` | 4000 | Paper 1 value |
| `-end` | 10000 µs | 10 ms; all flows finish well before |
| `-sender_cc_only` | — | Mandatory |
| `-disable_tor_ecn` | — | Mandatory with `-sender_cc_only` (avoids spurious CE on ToR downlinks) |

Flags **not used** (MPRDMA-specific): `-enable_qa_gate`, `-min_rto 70`

---

## Verification

1. **PATH_RR path count**: grep `data/*.out` for `PATH_RR:` lines
   ```bash
   grep "PATH_RR:" data/exp14_path_rr+*.out | head -5
   ```
   All cross-pod pairs should show `distinct_paths=4`.

2. **Flow completion**: each run should have exactly 16 completed flows
   ```bash
   grep -c "finished at" data/exp14_path_rr+constant_tornado_n16_s4194304_seed42.out
   ```

3. **No ToR ECN re-enable**: grep for the gotcha warning
   ```bash
   grep "enable on tor downlink 1" data/*.out
   # should return empty
   ```

---

## Results

See [plots/exp14_fct_slowdown.png](plots/exp14_fct_slowdown.png).

### FCT Slowdown from Optimal (mean ± 95% CI, 3 seeds)

| Condition | 4 MiB avg | 4 MiB max | 8 MiB avg | 8 MiB max | 16 MiB avg | 16 MiB max |
|-----------|-----------|-----------|-----------|-----------|------------|------------|
| path_rr+constant  | 1.825±0.001 | 1.829±0.001 | 1.780±0.001 | 1.784±0.001 | 1.770±0.000 | 1.772±0.001 |
| path_rr+nscc      | 1.244±0.004 | 1.251±0.012 | 1.143±0.004 | 1.146±0.005 | 1.091±0.004 | 1.094±0.005 |
| freezing+nscc     | 1.275±0.010 | 1.289±0.016 | 1.183±0.041 | 1.231±0.034 | 1.131±0.033 | 1.164±0.014 |
| freezing+constant | 1.827±0.002 | 1.831±0.002 | 1.784±0.000 | 1.786±0.003 | 1.772±0.001 | 1.774±0.001 |

### Key Findings

**1. CC quality dominates LB quality for tornado workload.**
Switching from line-rate (constant) to NSCC reduces avg-FCT slowdown from ~1.78× to ~1.09–1.28×
regardless of LB algorithm. The LB mechanism alone (PATH_RR vs REPS) makes at most a ~4%
difference in avg-FCT when both use NSCC.

**2. PATH_RR+constant ≈ REPS+constant.**
The two line-rate conditions produce nearly identical FCT (within ±0.004). REPS's probabilistic
entropy cycling achieves essentially the same path distribution quality as PATH_RR's deterministic
round-robin under tornado. The 4 distinct paths are loaded equally in both cases.

**3. PATH_RR+NSCC consistently beats REPS+NSCC, improving with flow size.**
- 4 MiB: 1.244 vs 1.275 avg (−2.5%)
- 8 MiB: 1.143 vs 1.183 avg (−3.4%)
- 16 MiB: 1.091 vs 1.131 avg (−3.5%)

The margin is small but consistent and nearly zero-variance (PATH_RR CI: ±0.001–0.004 vs REPS CI:
±0.010–0.041). REPS's higher variance under NSCC comes from the interaction between probabilistic
path selection and NSCC's congestion-driven backoff — occasionally one path collects more traffic,
causing asymmetric MD events.

**4. Best combination: PATH_RR+NSCC at 16 MiB: 1.091× optimal.**
Only 9.1% overhead vs the theoretical minimum FCT for a non-blocking topology.

**5. The ~1.78× floor with line-rate CC is a queuing artifact, not a load-imbalance artifact.**
With all 16 flows starting simultaneously and cwnd=90 (≈1.2× BDP), every switch queue fills on
the initial burst. Even with perfectly balanced paths, queuing delay drives FCT to ~1.78× optimal.
NSCC's congestion response eliminates most of this overhead.

**6. Key question answered:** PATH_RR+constant does NOT beat REPS+NSCC (1.770 vs 1.131 at 16 MiB).
**CC quality (NSCC over constant) matters more than LB quality (PATH_RR over REPS) for tornado.**

---

## Files

```
exp14_path_rr_tornado_v14/
├── README.md                  (this file)
├── scripts/
│   └── 01_run_exp14.sh        (simulation driver, idempotent)
├── data/
│   ├── exp14_*.out            (raw simulator output, one per run)
│   └── fcts.csv               (aggregated per-flow FCTs)
├── plots/
│   └── exp14_fct_slowdown.png (avg and max FCT slowdown)
├── aggregate_exp14.py
└── plot_exp14.py
```
