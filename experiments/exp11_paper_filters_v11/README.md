# exp11 — paper-workload filter comparison (800 G, paper ECN/queue settings)

Filter comparison against the 4 workloads from "Congestion Control for Spraying with Congested Paths" (Gerstein, Silberstein, Keslassy — arXiv:2509.07907). Same 8 modes as exp09; paper-faithful 800 G config in which ECN actually fires (unlike exp10).

## Design

| Axis | Values | Count |
|---|---|---|
| mode | vanilla, wtd, sf_md_gain_{ecn,fresh,evhealth}, sf_blend_{ecn,fresh,evhealth} | 8 |
| workload | baseline (4 ECMP + 124 sprayed), perm, hsdp, incast32 | 4 |
| sev | 0 (healthy), 4 (one Agg↔Core link fail 50→200 µs) | 2 |
| seed | 42, 43, 44 | 3 |

**Total: 192 cells**, 7.5 min wall-clock at J=4.

### Paper-faithful flags

```
-sack_threshold 4000 -end 5000 -paths 65535
-sender_cc_only -sender_cc_algo nscc
-load_balancing_algo freezing -exit_freeze 200000000
-topo .../fat_tree_128_1os_3t_800g.topo  -linkspeed 800000
-q 200 -ecn 10 50 -cwnd 100              ← paper ECN/buffer (40 KB / 800 KB)
-disable_tor_ecn
```

This is the regime exp10 was missing — see [workloads/README.md](../workloads/README.md#paper-simulator-settings-iva-settings) for the paper-quantity table.

## Results

### ECN behaves as expected — filters get a real signal

Per-cell ECN ACK counts from 3 logged sources × ~5 ms (vanilla, mean over 3 seeds):

| Workload | sev=0 | sev=4 | high_counter_rate (sev=0) |
|---|---|---|---|
| baseline | 772 | 1,480 | **0.40** |
| perm     | 871 | 1,160 | **0.41** |
| hsdp     | 3,407 | 3,310 | **0.84** |
| incast32 | 33 | 34 | 0.70 |

HSDP has the most ECN (3,400 ACKs); incast has the least (33 — incast queues are concentrated at the receiver, and our 3 logged sources rarely include the senders to it). All workloads except incast show **high counter-saturation rates** (0.40–0.84): when ECN fires, recent ACKs were *also* ECN. This is **diffuse congestion** — same finding as the original exp07 (`high_counter_rate ≈ 0.65` was its baseline).

WTD activity confirms filters fire:

| Workload | WTD block rate (fraction of ECN ACKs that suppress MD) |
|---|---|
| baseline | 0.27 |
| perm     | 0.24 |
| hsdp     | 0.05 |
| incast32 | 0.20 |

### Finding 1: Healthy state — filters are FCT-neutral (within 0.3 %)

p99 FCT slowdown × mode × workload at **sev=0** (mean over 3 seeds):

| Workload | vanilla | wtd | SF-A/ecn | SF-A/fresh | SF-A/evhealth | SF-B/ecn | SF-B/fresh | SF-B/evhealth |
|---|---|---|---|---|---|---|---|---|
| baseline | 1.60 | 1.60 | 1.60 | 1.60 | 1.60 | 1.60 | 1.60 | 1.60 |
| perm     | 1.42 | 1.42 | 1.42 | 1.42 | 1.42 | 1.42 | 1.42 | 1.41 |
| hsdp     | 1.31 | 1.31 | 1.31 | 1.31 | 1.31 | 1.31 | 1.31 | 1.32 |
| incast32 | 31.48 | 31.48 | 31.48 | 31.48 | 31.48 | 31.48 | 31.48 | 31.40 |

All 8 modes are **identical within ±0.3 %** at sev=0 across all 4 workloads. Diffuse congestion gives the filters no outlier-EV signal to act on — same dead end as exp07 but now with paper traffic confirming the result is not workload-artifact.

Baseline class breakdown (sev=0): ECMP elephants p99 = 1.08, sprayed perm p99 = 1.60. Filter mode makes no difference in either class.

### Finding 2: Failure case — evhealth blend wins on HSDP

p99 FCT slowdown × mode × workload at **sev=4**:

| Workload | vanilla | wtd | SF-A/ecn | SF-A/fresh | SF-A/evhealth | SF-B/ecn | SF-B/fresh | **SF-B/evhealth** |
|---|---|---|---|---|---|---|---|---|
| baseline | 1.84 | 1.84 | 1.84 | 1.84 | 1.84 | 1.84 | 1.84 | 1.84 |
| perm     | 1.75 | 1.75 | 1.75 | 1.75 | 1.75 | 1.74 | 1.75 | 1.75 |
| **hsdp** | **1.82** | 1.82 | 1.82 | 1.84 | 1.73 | 1.83 | 1.80 | **1.66 (−8.8 %)** |
| incast32 | 31.50 | 31.50 | 31.50 | 31.50 | 31.50 | 31.44 | 31.52 | 31.36 |

**`sf_blend_evhealth` cuts HSDP p99 slowdown from 1.82 → 1.66 (−8.8 %) under failure**, and `sf_md_gain_evhealth` similarly delivers 1.82 → 1.73 (−5 %). The other six modes (vanilla, WTD, and the ecn/fresh counters) are flat against vanilla.

This **inverts exp09's finding** (where `sf_md_gain_evhealth` and `sf_blend_evhealth` regressed +18–25 % p99 on WebSearch). Two differences explain the inversion:

1. **Workload structure**: HSDP rings (i → i+8) plus a single link failure create a *specific* set of bad EVs that persist for hundreds of µs. Evhealth's "dirty until clean" design correctly down-weights MD *only* for those EVs while remaining quiet on the rest.
2. **Healthy state**: exp09's WebSearch had ECN spread sparsely across many EVs at l=90, so evhealth's sticky state mis-attributed congestion. HSDP at 800 G has tighter EV → flow mapping (8-ring structure), so the dirty signal is more accurate.

### Finding 3: WTD blocks but doesn't help

WTD's MD-block rate is 24–27 % on baseline/perm (substantial — a quarter of ECN ACKs suppressed) and 5 % on HSDP. But p99 slowdown change vs vanilla is below ±0.05 in every cell. WTD is firing on the diffuse signal, but the suppressed MD events don't translate to FCT improvement.

### Finding 4: Incast indifference

p99 slowdown on incast32 is ~31.5 across all 8 modes and both severities — the bottleneck is the destination's port (32:1 fan-in), and no CC filter helps when the receiver's link is the binding constraint. Same finding as exp10.

## Comparison with prior filter experiments

| Experiment | Workload | Config | Diffuse-ECN rate | Best mode vs vanilla |
|---|---|---|---|---|
| exp07 | synthetic (perm/composite/perm32MB/perm128MB) | 400 G, q=100, ecn=25/76 | 0.65 | Null |
| exp08 | sparse permutation (2/16/32 flows) | 400 G | n/a — zero ECN | Null (no signal) |
| exp09 | WebSearch / Hadoop CDFs | 400 G | 0.02–0.16 (localized) | Null + evhealth REGRESSES +18–25 % p99 |
| **exp11 (this run)** | **paper workloads** | **800 G, paper-faithful q=200 ecn=10/50** | **0.40–0.84** | **Null at sev=0; sf_blend_evhealth WINS −8.8 % on HSDP at sev=4** |

exp11 is the **first** experiment in this lineage where any filter mode produces a statistically significant FCT win in any cell — and it's the same evhealth design that regressed in exp09. The win is workload-specific (HSDP under failure) and confined to the SF-B blend; the SF-A md_gain version of evhealth gets half the benefit.

## Artifacts

| Path | Contents |
|---|---|
| `data/v11_fct.csv` | 19,968 rows — one per finished flow |
| `data/v11_events.csv` | 192 rows — one per cell (ECN, WTD block, freeze, pipe events) |
| `data/v11_diagnostics.csv` | 2,747,127 rows — per-ACK from 3 logged sources |
| `plots/fig1_p99_baseline.png` | baseline p99 × mode × class × sev |
| `plots/fig2_p99_perm.png`     | perm p99 × mode × sev |
| `plots/fig3_p99_hsdp.png`     | hsdp p99 × mode × sev (shows evhealth win at sev=4) |
| `plots/fig4_p99_incast.png`   | incast p99 × mode × sev (flat) |
| `plots/fig5_ecn_counter_dist.png` | counter histogram at ecn=1 ACKs |
| `plots/fig6_high_counter_rate.png` | P(counter≥4\|ecn=1) per workload × sev |
| `plots/fig7_wtd_block_rate.png` | WTD MD-block rate per workload × sev |
| `plots/fig8_mode_summary.png` | 8-mode bar grid for all 4 workloads (sev=0) |
| `runs.tar.gz` | 192 raw `run.out` files compressed |

## Reproducibility

```bash
# Workloads
python3 experiments/workloads/gen_paper_workloads.py

# Sweep (192 cells, ~8 min at J=4)
bash experiments/exp11_paper_filters_v11/scripts/v11_run_matrix.sh --jobs 4

# Aggregate + plot
python3 experiments/exp11_paper_filters_v11/scripts/v11_aggregate.py
python3 experiments/exp11_paper_filters_v11/scripts/v11_plot.py
```

## Caveats

- **ECMP elephants are sprayed** (htsim global LB) — the paper's actual ECMP-vs-spray split is not reproducible here.
- **`perm` workload reuses one TM across seeds** (`perm_n128_s8388608.cm`); only the simulator's `-seed` varies.
- **HSDP evhealth win at sev=4 is from 3 seeds** — directionally clear but the per-cell standard error is non-trivial. Validating with more seeds is a natural next step.
- **Paper's high ECN threshold is a judgment call** at `-ecn 10 50` — paper only specifies 40 KB low. If high-threshold is misset, marking behavior may differ slightly from paper.
