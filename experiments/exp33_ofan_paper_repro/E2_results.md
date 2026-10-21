# E2: Ofan paper Fig 7 (CCT vs message size) and Fig 8 (CCT vs packet size)

Plots: `plots/e2_fig7/` (`fig7.png`, `fig7a.png`, `fig7b.png`, `fig7a_k8_128hosts.png`, `extra_ar_variants.png`), `plots/e2_fig8/` (`fig8.png`, `fig8_ownlb.png`, `fig8_k10_250hosts.png`, `fig8_ownlb_k10_250hosts.png`).
Data: `data/e2/` (432 hosts, 128-host all-to-all, trim cells), `data/e2_k8/` (128-host permutation), `data/e2_k10/` (250-host Fig 8); each has `e2_summary.csv` (mean, 95% CI), `e2_runs.csv` (one row per run) and `runs.tar.gz` (raw outputs, commands, queue stats, workloads).
Scripts: `scripts/run_e2.sh` (idempotent; binary from `$BIN`, default `/tmp/frozen/htsim_uec_frozen`; `OUT`, `PERM_N`, `PERM_POD` select data dir and topology), `aggregate_e2.py <dir> [N]`, `plot_e2.py`.

## Setup

- Topology `fat_tree_432_1os_3t_800g.topo` (k=12) for the permutation Figs 7a and 8; `fat_tree_128_1os_3t_800g.topo` for all-to-all (N=128 only; N=250 not run). Cross-checks: permutation Fig 7a on 128 hosts and Fig 8 on 250 hosts (the paper's figure file names suggest K8 for Fig 7 and K10 for Fig 8, see README).
- No CCA: `-sender_cc_only -sender_cc_algo constant -cwnd <pkts>`, `-mtu` = payload + 64, `-disable_trim`, infinite buffer (`-q 20000` at 4160 B). All packet-count flags are rescaled to constant bytes when `-mtu` varies: infinite buffer 83.2 MB, finite buffer 800,950 B, ECN 78,850 B, cwnd 4.16 MB (about 3x BDP). Single-flow 64 MB CCT is 687.8 us against 681.6 us serialization plus latency, so no window limit.
- `-disable_tor_ecn` on every run (project rule for `-sender_cc_only`). REPS therefore keeps step ECN (78.85 KB) on the fabric links; only ToR downlinks are unmarked. Not tested separately here (E1 showed no difference).
- Strategies: Ofan (`-strat ofan -load_balancing_algo ecmp`); REPS (`-load_balancing_algo freezing -paths 65535`); AR in three variants: `ar_q193` (quantized comparator on an 800 KB buffer, `-q 193` scale; loss-free below 64 MB; plotted as "AR"), `ar_q20000` (infinite buffer, so the 5/10/20% quantization never triggers and AR is effectively random; dotted gray), `ar_exact` (`-ar_method exact`, JSQ on exact queues; extra).
- Workload: random permutation (`gen_derangement.py ... perm`; the seed sets both the permutation and the sim seed), sizes in MiB. All-to-all: one shot, every pair, `gen_ata.py`.
- CCT = last flow finish. "Increase" is relative to an empirical single-flow run (host 0 to host N/2, 6 hops) with the same strategy family, size and MTU; for all-to-all the single flow carries (N-1) x size bytes (injection bound). Fig 8 uses a P-independent bound (minimum single-flow CCT over the MTUs, `inc_best`): with the same-MTU bound the header term cancels and no sweet spot can appear, only the queueing term (`fig8_ownlb.png`). The paper's analytic Appendix A bound was not implemented.
- Seeds: 0.5/2/8 MB: 5; 64 MB: 2; all-to-all: 3; Fig 8: 3 (432 and 250 hosts); 128-host permutation: 5 (64 MB: 2); trim cells: 1.

## Fig 7a: permutation, 432 hosts, CCT increase % (mean, 95% CI half-width)

| size | Ofan | AR (q193) | AR (inf buf) | AR (exact JSQ) | REPS |
|---|---|---|---|---|---|
| 0.5 MB | 3.42 (0.19) | 12.80 (1.85) | 14.71 (1.95) | 14.61 (1.50) | 13.96 (1.37) |
| 2 MB | 1.80 (0.08) | 10.36 (1.67) | 12.96 (1.28) | 25.40 (2.94) | 12.07 (0.85) |
| 8 MB | 0.81 (0.02) | 6.58 (0.98) | 8.52 (1.03) | 58.41 (17.3) | 7.12 (0.57) |
| 64 MB (2 seeds) | 0.44 (0.04) | 7.06 (0.81); 12,154 RTOs, 11,958 drops | 6.54 (4.04) | 25.69 (1.62) | 3.86 (1.23) |

Max E->A queue at 64 MB: Ofan 27 KB (6.5 packets), AR q193 83 KB (buffer-limited, drops), AR inf 3.4 MB, REPS 1.7 MB. `ar_exact` is large and noisy (exact JSQ on rapidly changing queues herds flows; 8 MB CI +-17); it is an extra, not a paper curve.

K8 cross-check (128 hosts), sizes 0.5 / 2 / 8 / 64 MB: Ofan 2.54 / 1.35 / 0.68 / 0.43; AR q193 10.7 / 8.9 / 5.3 / 6.9; REPS 12.7 / 9.4 / 6.3 / 3.4. Same ordering and trends.

## Fig 7b: all-to-all, N=128 (not 250), CCT increase %

| size per flow | Ofan | AR (q193) | AR (inf) | AR (exact) | REPS |
|---|---|---|---|---|---|
| 128 KB | 0.69 (0.12) | 2.80 (1.10) | 3.12 (0.61) | 2.04 (0.48) | 2.23 (0.10) |
| 256 KB | 0.54 (0.07) | 1.67 (0.33) | 1.96 (0.75) | 1.85 (0.56) | 1.56 (0.26) |
| 512 KB | 0.46 (0.03) | 1.17 (0.19) | 1.37 (0.06) | 1.21 (0.31) | 1.11 (0.05) |

Sizes are 128/256/512 KiB (the paper's 0.13/0.25/0.5 MB). The bound is the naive injection bound, as in the paper for non-permutation workloads.

## Trimming / freezing test (REPS conjecture of Fig 7a), 432 hosts, permutation, 1 seed

| config | 16 MB | 64 MB |
|---|---|---|
| REPS, infinite buffer, no trim | +5.20%, rtos 0, freeze 0 | +3.96%, rtos 0, freeze 0 |
| REPS, infinite buffer, trimming on | identical (+5.20%) | +3.96%, 0 trims |
| REPS, 800 KB buffer, no trim | +5.20%, 0 drops | +7.04%, 6,330 RTOs, 6,287 drops, freeze_entries 0 |
| REPS, 800 KB buffer, trimming on | +5.20%, 0 trims | +3.38%, 5,912 trims, rtos 0, freeze_entries 0 |

## Fig 8: permutation, CCT increase % vs packet size (-mtu), 432 hosts, over the P-independent bound

| P (B) | 0.5 MB Ofan | AR | REPS | 4 MB Ofan | AR | REPS |
|---|---|---|---|---|---|---|
| 1000 | 2.20 | 8.28 | 8.37 | 5.02 | 9.02 | 10.30 |
| 1500 | 1.74 | 8.41 | 8.29 | 3.13 | 8.16 | 8.85 |
| 2000 | 1.84 | 9.63 | 10.38 | 2.26 | 7.17 | 8.43 |
| 3000 | 2.60 | 12.01 | 11.57 | 1.58 | 8.93 | 9.37 |
| 4000 | 3.62 | 13.90 | 15.31 | 1.41 | 8.43 | 10.27 |
| 5000 | 4.47 | 14.76 | 15.50 | 1.43 | 9.88 | 9.62 |
| 6000 | 5.59 | 15.65 | 17.83 | 1.51 | 9.51 | 11.26 |
| 8000 | 7.64 | 18.79 | 22.48 | 1.86 | 11.13 | 12.16 |
| 10000 | 10.51 | 21.29 | 24.73 | 2.31 | 12.54 | 14.78 |

Paper model (Thm 6; H = 82 B, alpha = 10 packets, D in bytes with MiB): optimal payload sqrt(H D / alpha) = 2073 B (0.5 MB) and 5865 B (4 MB), i.e. **P* = 2155 B and 5947 B** (red dots; model curve H/(P-H) + alpha P / D). The simulator header is 64 B, so its x-axis is payload + 64 (about 18 B offset from the paper's P).
Measured Ofan minimum: 0.5 MB at P = 1500-2000 B (1.74 / 1.84%); 4 MB at P = 4000-5000 B (1.41 / 1.43%, flat from 3000 to 6000). 250-host cross-check: 0.5 MB minimum at 1500-2000 B (1.62 / 1.63%), 4 MB at 4000-5000 B (1.30 / 1.31%); AR/REPS values in `data/e2_k10/e2_summary.csv`.

## Comparison with the paper's claims

| claim | result |
|---|---|
| Ofan < AR, REPS at all sizes | Match at every size (432 and 128 hosts, all-to-all). |
| Absolute CCT gap shrinks with message size, Ofan keeps beating the others | Match: Ofan 3.4% to 0.44%, AR/REPS 13-14% to 4-7%. The absolute gap shrinks but the ordering persists; Ofan never reaches the bound exactly. |
| REPS notably worse at very large messages (freezing mode triggered by timeouts) | **Not reproduced.** REPS improves with size (14% to 3.9% at 64 MB). With trimming and finite buffers REPS had 5,900 trims, 0 RTOs and 0 freeze entries (freezing is entered on RTO) and +3.4%; with finite buffers and no trim there were 6,330 RTOs yet `freeze_entries` stayed 0 (+7.0%). Our NACK/trim recovery avoids timeouts; the paper's loss recovery is unspecified. One seed only. |
| Fig 8 has a sweet spot that the model roughly predicts | Match for Ofan: minimum at 1500-2000 B against P* = 2155 B (0.5 MB) and at 4000-5000 B against P* = 5947 B (4 MB). The model curve overestimates the increase at 4 MB (our Ofan queues are 6-9 packets, below alpha = 10). |
| Ofan prefers larger packets than spraying (Fig 8b, D^(1/3) vs D^(1/2)) | Partly: at 4 MB AR and REPS are nearly flat in P (minimum near 2000 B, within CI of 1500-5000 B) and at 0.5 MB they rise beyond 1500 B, so their optimum is at or below Ofan's. The D^(1/3) scaling cannot be resolved with 3 seeds and CIs of 1-3 points. |
| Ofan optimum larger for the larger message | Match (1500-2000 B to 4000-5000 B). |

## Problems and caveats

- AR variant ambiguity (README divergence 3): `ar_q20000` is random-like; `ar_q193` is the quantized AR but drops packets at 64 MB (its CCT includes RTO recovery, 7.06%); `ar_exact` is much worse. All are in `e2_summary.csv`.
- Lower bound is empirical (divergence 4); the analytic Appendix A bound was not computed. Wire format is a 64 B header without the 20 B gap (divergence 1), while the model uses the paper's H = 82 B.
- 64 MB has 2 seeds (wide CIs: AR inf +-4.0, REPS +-1.2); trim cells 1 seed; all-to-all only up to N=128.
- ECN threshold held at 78.85 KB for every MTU (constant bytes), not the paper's "10 packets at 64 KB packets" rule (irrelevant in the 1-10 KB range).
- The first sweep ran on the live binary, the later ones (K8, K10) on `/tmp/frozen/htsim_uec_frozen` (same code). No rebuild or simulator edit.
- README updated: unknown-column entries of the Fig 7 and Fig 8 rows now carry what E2 learned (no REPS freezing without RTOs; constant-byte scaling; P-independent bound needed for the sweet spot; K8/K10 cross-checks).
