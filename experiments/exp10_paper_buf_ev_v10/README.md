# exp10 — Paper-workload buffer-size / EV-domain sweep

Replaces the aborted CDF-workload variant (`exp10_cdf_buf_ev_v10`) with a paper-faithful run on the 4 workloads from "Congestion Control for Spraying with Congested Paths" (Gerstein, Silberstein, Keslassy — arXiv:2509.07907). Vanilla REPS+NSCC; 128-host 3-tier fat-tree at **800 Gbps** (paper topology).

## Design

Two orthogonal sweeps, same axes as exp05 but on paper workloads.

| Axis | Values | Fixed |
|---|---|---|
| Part A: `-reps_buffer_size` | 1, 2, 4, 8, 1024 | `-paths 65535` |
| Part B: `-paths`            | 32, 256, 65535 | `-reps_buffer_size 8` |

Workloads × sev × seeds:

| Axis | Values |
|---|---|
| workload | `baseline` (4 ECMP 64 MB + 124 sprayed 8 MB), `perm` (128 × 8 MB), `hsdp` (128 ring flows × 13.7 MB, i → (i+8) mod 128), `incast32` (32 → 1, 8 MB) |
| sev | 0 (healthy), 4 (one Agg↔Core link fail at t=50 µs, recovers at t=200 µs) |
| seed | 42, 43, 44 |

**Total: 5×4×2×3 + 3×4×2×3 = 120 + 72 = 192 cells**, ~25 min wall-clock on J=4.

Simulator flags (vanilla — no smart-filter / WTD / state-aware):
```
-sack_threshold 4000 -end 5000 -sender_cc_only -sender_cc_algo nscc
-load_balancing_algo freezing -exit_freeze 200000000
-topo .../fat_tree_128_1os_3t_800g.topo -linkspeed 800000
-ecn 25 76 -q 100 -cwnd 151 -disable_tor_ecn
```

## Results

### Headline: routing-quality is the entire story; transport never engages

**Zero ECN ACKs in every one of the 192 cells.** At 800 Gbps with these flow sizes, queues never cross the 25 % ECN threshold before flows complete. NSCC stays in its initial cwnd regime end-to-end. So Part A and Part B isolate the *pure LB effect* with no CC interaction.

### Part A — buffer size sweep

p99 FCT slowdown (mean over 3 seeds, sev=0):

| Workload | buf=1 | buf=2 | buf=4 | buf=8 | buf=∞ (1024) |
|---|---|---|---|---|---|
| baseline | 1.51 | 1.51 | 1.51 | 1.50 | 1.50 |
| perm     | 1.38 | 1.33 | 1.32 | 1.33 | 1.33 |
| hsdp     | 1.27 | 1.28 | 1.27 | 1.27 | 1.27 |
| incast32 | 31.49 | 31.59 | 31.63 | 31.49 | 31.57 |

**Buffer size is irrelevant** across all four paper workloads — same finding as exp05 (paper synthetic workloads) and the buffer-axis portion of exp04. Even pure-permutation, the most "REPS-friendly" workload, sees only ~5 % p99 improvement going from buf=1 to buf=2, then flat. The 8-slot paper default and the unbounded "∞" are indistinguishable.

Class breakdown for baseline (all buf sizes pooled, sev=0):

| Class | mean FCT (µs) | mean size (B) | mean slowdown vs ideal |
|---|---|---|---|
| ECMP elephants (ids 1-4) | 718 | 67,108,864 | 1.11× (essentially uncongested) |
| Sprayed perm (ids 5-128) | 112 | 8,388,608 | 1.33× |

The 4 ECMP-elephant ids finish at ~718 µs (vs 644 µs ideal) — they last just past the sprayed-flow tail. Sufficient "background congestion" for the 80–120 µs sprayed flows.

### Part B — EV domain sweep

p99 FCT slowdown (sev=0, buf=8):

| Workload | paths=32 | paths=256 | paths=64K | 64K/32 ratio |
|---|---|---|---|---|
| baseline | 1.60 | 1.58 | 1.50 | 0.937 (**6.3 % win**) |
| perm     | 1.43 | 1.40 | 1.33 | 0.932 (**6.8 % win**) |
| hsdp     | 1.31 | 1.28 | 1.27 | 0.974 (2.6 % win) |
| incast32 | 31.60 | 31.56 | 31.49 | 0.997 (no effect) |

**EV domain matters for permutation-like workloads, doesn't matter for incast.** Going from 32 paths to 64K paths buys ~6–7 % p99 slowdown reduction on permutation-pattern flows (baseline sprayed, pure perm). The benefit saturates between 256 and 64K — paths=256 already captures most of the gain. HSDP has lower benefit because its 8-ring structure already limits useful path diversity. Incast is unaffected because the bottleneck is the single destination link, not the LB.

### Severity (link failure) sensitivity

p99 slowdown × workload × sev (buf=8 from Part A):

| Workload | sev=0 | sev=4 | Δ |
|---|---|---|---|
| baseline | 1.50 | 1.58 | +5 % |
| perm     | 1.33 | 1.46 | +10 % |
| hsdp     | 1.27 | 1.48 | **+17 %** |
| incast32 | 31.49 | 31.56 | <0.3 % (receiver-bottleneck dominates) |

HSDP rings are the most failure-sensitive: a single fail at t=50 µs disrupts the closely-coupled ring pattern more than the looser permutation traffic. Incast is indifferent — the destination's port is already maxed out.

## Comparison with prior experiments

| Experiment | Workload type | Topology | Buffer effect | EV effect |
|---|---|---|---|---|
| exp04 (synthetic 3-tier) | perm 32/128 MB, composite | 128h × 400 G | flat | dramatic at EV≤8 |
| exp05 (paper-synth 2-tier) | perm_n128 8 MB, symm16 16 MB | 128h × 400 G | flat | +5 µs (+2.7 %) at EV=32 |
| **exp10 (this run)** | **paper baseline/perm/hsdp/incast32** | **128h × 800 G** | **flat** | **6–7 % (perm-like), 2–3 % (hsdp), 0 % (incast)** |

Consistent across all three: buffer size never matters in the regime where flows complete in 1–10 RTTs at 800 G/400 G. EV domain matters modestly and saturates by paths=256. Incast workloads bypass the LB entirely (bottleneck is at the receiver).

## Artifacts

| Path | Contents |
|---|---|
| `data/v10_fct.csv` | 19,967 rows — one per finished flow |
| `data/v10_events.csv` | 192 rows — one per cell (ECN counts, pipe fails, freeze events) |
| `plots/fig1_buf_baseline.png` | Part A baseline, class-split |
| `plots/fig2_buf_hsdp.png` | Part A HSDP, sev-split |
| `plots/fig3_buf_incast.png` | Part A incast32 |
| `plots/fig4_ev_baseline.png` | Part B baseline, class-split |
| `plots/fig5_ev_hsdp.png` | Part B HSDP |
| `plots/fig6_ev_incast.png` | Part B incast32 |
| `plots/fig7_buf_summary.png` | All 4 workloads, mean slowdown vs buf_size |
| `plots/fig8_ev_summary.png` | All 4 workloads, mean slowdown vs paths |
| `runs.tar.gz` | 192 raw `run.out` files compressed |

## Reproducibility

```bash
# Workloads must exist (generated by gen_paper_workloads.py)
python3 experiments/workloads/gen_paper_workloads.py

# Part A — buffer sweep (120 cells, ~10–15 min at J=4 on this hardware)
bash experiments/exp10_paper_buf_ev_v10/scripts/v10_run_matrix.sh --part_a --jobs 4

# Part B — EV sweep (72 cells, ~10 min at J=4)
bash experiments/exp10_paper_buf_ev_v10/scripts/v10_run_matrix.sh --part_b --jobs 4

# Aggregate + plot
python3 experiments/exp10_paper_buf_ev_v10/scripts/v10_aggregate.py
python3 experiments/exp10_paper_buf_ev_v10/scripts/v10_plot.py
```

## Caveats

- **ECMP elephants are sprayed**, not ECMP-routed (htsim has no per-flow LB selector; documented in `workloads/README.md`). Sufficient for testing buf/EV effect *on the sprayed perm class*; cannot reproduce the paper's actual ECMP-vs-spray throughput-collapse phenomenon.
- **`perm` workload reuses one TM across the 3 seeds** (`perm_n128_s8388608.cm` has no seed variants); only the simulator's RNG (`-seed`) varies. Cross-seed variance for `perm` is therefore narrower than for the other workloads.
- **Zero ECN at 800 G** with these flow sizes means transport-layer mechanisms (NSCC MD, WTD, smart-filter) are invisible here. A bandwidth/duration regime that drives ECN would require different sizing.
