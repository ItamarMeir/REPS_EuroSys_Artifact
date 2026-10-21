# E4 - Ofan paper Fig 12 reproduction (CCA sensitivity at 432 hosts)

Paper: arXiv 2610.07230 sec 6.5 / Fig 12. Closes exp32's open item "CCA at 432 hosts". Frozen `htsim_uec`, no simulator change. 10 seeds per cell (seed s = permutation s = simulator seed s), mean ± SEM. 134 runs total (4 single-flow bounds, 90 main, 10 hash ablation, 30 no-`-disable_tor_ecn` sensitivity).

## Setup

- Topology `topologies/fat_tree_432_1os_3t_800g.topo` (k=12, 432 hosts, 36 cores, 800 Gb/s). Plain random permutation (`exp32_ofan/scripts/gen_derangement.py ... perm`, intra-pod pairs allowed), one 4 MiB (4,194,304 B) flow per host, all start at 0.
- Buffers: `-q 193` = 800,950 B per port (simulator prints `queues with size 800950`); ECN `-ecn 19 19` = 78,850 B (about 80 KB). No `-mtu` flag (4150 B wire packets, as in exp32).
- CCAs: `-sender_cc_algo dctcp | nscc | mswift`, all with `-sender_cc_only`.
- LB: REPS = `-load_balancing_algo freezing -paths 65535`; AR = `-strat ecmp_ar -load_balancing_algo ecmp`; Ofan = `-strat ofan -load_balancing_algo ecmp`. Ablation: Ofan with `-ofan_ack_mode hash` (NSCC only).
- `-disable_tor_ecn` decision: used in all main runs (project rule: `-sender_cc_only` alone re-enables ToR-downlink ECN; verified by `enable on tor downlink 0/1` in the outputs). Sensitivity: NSCC without it (`*_noDTE`, `tor downlink 1`), as exp26-31 did.
- Lower bound per CCA config: one flow 0->216 (inter-pod) with the same flags. It is 48.81 us for dctcp, nscc, mswift and nscc-noDTE alike (window-limited by the initial window of about 0.94 MB; ideal serialisation of 4.196 MB at 800G is 42.0 us). "CCT increase" = CCT / 48.81 - 1. CCT = last flow finish.
- Link utilisation definition: per switch egress link, (data + header bytes) * 8 / (800 Gb/s * CCT), i.e. the average over [0, CCT]; "fabric max" = max over all switch-switch links (E->A, A->C, C->A, A->E). Time series (Fig 12 b/e/h, c/f/i) were obtained WITHOUT changing the binary for ONE seed (seed 1) per (CCA, LB) with `scripts/run_e4_ts.sh` (`-log_link -log_core_queues -log_tor_queues -end 150`) and `scripts/ts_e4.py` (offline FIFO replay of the per-switch forwarding log, 1 us bins; reconstructed A->C max queue equals the simulator's own 1 us sampler). Utilisation there = mean busy fraction of the 432 ToR uplinks (E->A); E->H host links are not in the log. The run-average figure here is capped near 42.0 / CCT = 85-86% by ramp-up and tail of a 4 MiB message, so only the ordering is informative (Ofan 86.8% is at that cap).
- Queue = max occupancy of the data queue in 4150 B packets (193 = full buffer), max over all queues of the layer per run, then averaged over seeds.

## Results (main, `-disable_tor_ecn`, 10 seeds)

| CCA | LB | CCT us | CCT increase % | fabric max util % | max queue E>A / A>C / C>A / A>E / E>H (pkts) | trims / drops / RTOs | ecn_acks |
|---|---|---|---|---|---|---|---|
| DCTCP | REPS | 61.99 ± 0.64 | 26.99 ± 1.32 | 76.3 ± 0.9 | 61 / 46 / 44 / 52 / 30 | 0 / 0 / 0 | 58,775 ± 530 |
| DCTCP | AR | 57.22 ± 0.21 | 17.23 ± 0.43 | 80.5 ± 0.3 | 18 / 16 / 56 / 73 / 24 | 0 / 0 / 0 | 58,734 ± 697 |
| DCTCP | Ofan | 49.39 ± 0.01 | 1.19 ± 0.01 | 86.8 ± 0.01 | 6 / 7 / 8 / 8 / 8 | 0 / 0 / 0 | 0 |
| NSCC | REPS | 53.16 ± 0.09 | 8.90 ± 0.18 | 86.9 ± 0.2 | 86 / 58 / 59 / 68 / 21 | 0 / 0 / 0 | 172,195 ± 1,853 |
| NSCC | AR | 53.17 ± 0.20 | 8.92 ± 0.41 | 87.4 ± 0.2 | 19 / 17 / 70 / 89 / 19 | 0 / 0 / 0 | 100,232 ± 857 |
| NSCC | Ofan | 49.39 ± 0.01 | 1.19 ± 0.01 | 86.8 ± 0.01 | 6 / 7 / 8 / 8 / 8 | 0 / 0 / 0 | 0 |
| MSwift | REPS | 53.16 ± 0.09 | 8.90 ± 0.18 | 86.9 ± 0.2 | identical to NSCC | 0 / 0 / 0 | 172,195 ± 1,853 |
| MSwift | AR | 53.17 ± 0.20 | 8.92 ± 0.41 | 87.4 ± 0.2 | identical to NSCC | 0 / 0 / 0 | 100,232 ± 857 |
| MSwift | Ofan | 49.39 ± 0.01 | 1.19 ± 0.01 | 86.8 ± 0.01 | identical to NSCC | 0 / 0 / 0 | 0 |

All 130 permutation runs: 432/432 flows finished, rc=0, no abort/assert/`uecMaxInFlightPkts`, zero trims, drops and RTOs (the 193-packet buffer is never full; worst queue is 89 packets, 46% of the buffer). Per-seed ranges of CCT increase: DCTCP-REPS 22.6-35.9, DCTCP-AR 15.3-19.2, NSCC-REPS 8.1-9.8, NSCC-AR 7.6-11.3, NSCC-Ofan 1.16-1.25. Full tables: `data/e4/e4_summary.md`, per-run rows `data/e4/e4_runs.csv`.

### Ablation and sensitivity (NSCC, 10 seeds)

| config | CCT us | increase % | max queue E>A / A>C / C>A / A>E / E>H | drops / RTOs |
|---|---|---|---|---|
| Ofan `-ofan_ack_mode hash` | 49.67 ± 0.01 | 1.75 ± 0.03 | 15 / 10 / 11 / 15 / 9 | 0 / 0 |
| REPS, no `-disable_tor_ecn` | 53.19 ± 0.08 | 8.96 ± 0.16 | 87 / 58 / 60 / 68 / 21 | 0 / 0 |
| AR, no `-disable_tor_ecn` | 53.16 ± 0.20 | 8.90 ± 0.41 | 19 / 17 / 70 / 89 / 19 | 0 / 0 |
| Ofan, no `-disable_tor_ecn` | 49.39 ± 0.01 | 1.19 ± 0.01 | 6 / 7 / 8 / 8 / 8 | 0 / 0 |

ToR-downlink ECN changes nothing measurable (E->H queues stay near the 19-packet threshold), so the `-disable_tor_ecn` decision is immaterial here. Hash-ACK costs +0.56 pp CCT and about 2x the queues, with no loss, in line with exp32 S6.

## Comparison with the paper

| CCA | | REPS | AR | Ofan | best baseline / Ofan |
|---|---|---|---|---|---|
| DCTCP | paper | 309% | 205% | 0.44% | 466x |
| DCTCP | here | 27.0% | 17.2% | 1.19% | 14.5x |
| NSCC | paper | 16% | 9.9% | 1% | 9.9x |
| NSCC | here | 8.9% | 8.9% | 1.19% | 7.5x |
| MSwift | paper | 17% | 16% | 0.81% | 20x |
| MSwift | here | 8.9% | 8.9% | 1.19% | 7.5x |

(The task brief spoke of >=16x / >=39x for NSCC / MSwift; from the paper numbers as given, the best-baseline ratios are 9.9x and 20x, and vs REPS 16x and 21x. Either way, ours is lower.)

Match / mismatch:

- **Qualitative ordering matches** for every CCA: Ofan < AR <= REPS in CCT; Ofan queues 6-8 packets versus 16-89 for AR and 29-86 for REPS; Ofan has zero ECN-marked ACKs; no run aborts. For NSCC and MSwift REPS and AR tie (paper: REPS slightly worse); for DCTCP REPS > AR > Ofan as in the paper.
- **Ofan's absolute value matches**: 1.19% vs 1% (NSCC) / 0.81% (MSwift) / 0.44% (DCTCP). It is identical across CCAs because Ofan never queues, so the CCA never acts.
- **Baseline inflation mismatches**: REPS/AR are 2-4x lower than the paper for NSCC/MSwift (8.9% vs 16-17% / 9.9-16%) and 8-12x lower for DCTCP (27% / 17% vs 309% / 205%). The paper's reduction factors (up to 466x) are not reproduced: here 7.5x (NSCC, MSwift) and 14.5x (DCTCP).
- **Utilisation (Fig 12 b/e/h)**: now available as 1 us time series for seed 1 (`plots/e4_fig12/<cca>_util.png`; ToR-uplink mean utilisation, E->H not logged). Ofan holds ~98% until its (earlier) end and drops first; REPS/AR sag to ~80% in the tail with DCTCP (the straggler tail, as in the paper); with NSCC/MSwift all three are ~97-98% and differ only by the 1-9% CCT tail. Run averages (previous definition) order as the paper only for DCTCP (Ofan 86.8% > AR 80.5% > REPS 76.3%); for NSCC/MSwift REPS and AR (86.9% / 87.4%) are not below Ofan, because the difference lives in ramp-up/tail.
- **Max queue time series (Fig 12 c/f/i)**: `plots/e4_fig12/<cca>_maxq.png` (log y, max over E->A, A->C, C->A, A->E queues): Ofan flat at ~30 KB, REPS/AR 150-450 KB growing during the transfer, as in the paper.

Hypotheses for the mismatch (not tested):

1. **Possibly little CCA action (unverified; an earlier version of this note wrongly said a 4 MiB flow fits in one window).** A 4 MiB flow is about 6.4-6.8 RTTs here (BDP about 625-640 KB, as in the paper's 150-packet RTT; max cwnd 0.94 MB = 1.5 BDP; single-flow CCT 48.8 us vs 42 us serialisation), the same as the paper. Whether the CCAs act little because of the initial window / target-delay parameters has not been tested. NSCC and MSwift are bit-identical in every cell (CCT, queues, ECN counts). A 309% DCTCP inflation implies many RTTs of CCA-driven recovery (small initial window, collapse, or loss); here there is no loss.
2. **No loss path.** All queues stay under 46% of the buffer, so no trim, drop or RTO occurs. htsim's `dctcp` is a simplified rule (`updateCwndOnAck_DCTCP`: cwnd -= acked/3 per ECN-marked ACK, +1 MTU/RTT otherwise, no alpha) with no dup-ACK threshold, so reordering from spraying costs nothing; a faithful dup-ACK-threshold DCTCP would penalise REPS (and AR) far more and is the first thing to compare. The paper's huge DCTCP numbers more likely stem from such reorder-triggered retransmits / window cuts than from queueing.
3. **NSCC/MSwift parameterisation.** Defaults at 800G with a BDP-sized initial window and our `-target_q_delay`/`-ecn 19 19`; the paper may start below BDP or react to ECN differently. A sweep over message size (S5 showed AR/REPS queues growing to buffer overflow at 16-64 MB) and initial window would test hypothesis 1.
4. The 100-170k ECN-marked ACKs for REPS/AR do not slow NSCC/MSwift (the windows never shrink in this regime); the +8.9% is queueing delay only.

Bottom line: the Ofan side reproduces (about 1.2%, queues of 6-8 packets, no ECN), and the ordering holds; the paper's large baseline inflation, hence the claimed 10-466x reduction, does not appear in the frozen simulator at 4 MiB / 432 hosts, where baselines lose 9-27% and the reduction is 7.5-14.5x.

## Files and reproduce

`scripts/run_e4.sh` (driver, idempotent, `E4_PAR=2`), `scripts/aggregate_e4.py`, `scripts/plot_e4.py`; `plots/e4_fig12/{dctcp,nscc,mswift}_{cct,util,maxq,fig12}.png` (paper style, linear CCT axis; `scripts/paperstyle.py`), `scripts/run_e4_ts.sh` + `scripts/ts_e4.py` (time series), `data/e4/ts/<cca>_<lb>_s1_series.csv`; `data/e4/e4_summary.{md,csv}`, `e4_runs.csv`, `runs.tar.gz` (raw `.out` and `-log_queue_stats` TSVs; extract to `data/e4/runs/` before re-aggregating); `workloads/perm432_4mb_s{1..10}.cm`, `single432_4mb.cm`.

```bash
docker exec ofan-dev bash /workspace/experiments/exp33_ofan_paper_repro/scripts/run_e4.sh 10   # about 60 min on a shared box
cd experiments/exp33_ofan_paper_repro && python3 scripts/aggregate_e4.py && python3 scripts/plot_e4.py
```
