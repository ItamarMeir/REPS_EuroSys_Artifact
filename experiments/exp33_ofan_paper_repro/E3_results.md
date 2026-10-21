# E3 - Ofan paper (arXiv 2610.07230) Fig 4 and Fig 5 reproduction

Status: complete. DRB cells (`drb_af_rand`, `drb_rand`) were run with `/tmp/frozen/htsim_uec_v2`; all earlier cells with the earlier frozen binary (v2 is regression-identical for existing flags). `BIN` env var in `run_e3.sh`. No simulator source was edited.

## Setup (common)

- 3-tier 1:1 fat-trees `topologies/fat_tree_<N>_1os_3t_800g.topo` (800G, 0.5 us links); `-mtu 4160`.
- No CCA: `-sender_cc_only -sender_cc_algo constant -cwnd 400` (400 packets, about 1.66 MB, never window-limited), `-q 20000 -disable_trim` (83 MB per port, "practically infinite", paper fn.6; 0 drops and 0 trims in every `-q 20000` cell), `-ecn 19 19` (only REPS reacts), `-disable_tor_ecn` everywhere (rule). REPS keeps fabric ECN on E->A/A->C/C->A/A->E. `reps_dl` (no `-disable_tor_ecn`) is bit-identical to `reps` (a permutation has no ToR-downlink congestion).
- CCT = last flow finish. CCT increase = (CCT / LB - 1), LB = empirical single-flow run in the same config (1 MB for permutations; (N-1) x per-flow bytes for all-to-all, i.e. the per-host volume through one NIC). Mean +- SEM over seeds. The seed changes hashing / random choices and the permutation (the all-to-all matrix is seed-independent).
- Max queue = max over every link of the per-run max data-queue occupancy (`-log_queue_stats`), in 4160 B packets. Only a per-run maximum is available, so Fig 4b is a bar chart, not a time series.
- Algorithms: Simple RR = `-strat ecmp_rr_fixed`; JSQ = `-strat ecmp_ar -ar_method exact`; RSQ = `-strat ecmp_random`; RPS = `-load_balancing_algo path_random`; Choice = `-strat ecmp_p2c`; REPS = `-load_balancing_algo freezing -paths 65535`; AR = `-strat ecmp_ar` with `-q 193` and with `-q 20000`; DRB-like = `-load_balancing_algo path_rr` (+ `-path_rr_start_mode src_mod|srcdst_hash`); Ofan = `-strat ofan`. All switch strategies use `-load_balancing_algo ecmp`. Skipped (not implemented): CONGA, DRILL, DLB, SGLB, Ethereal, 4Ofan.
- AR at `-q 20000` is identical to RSQ (quantisation is 5% of the buffer, so every queue reads 0 and ties are random); the `ar20000` and `rsq` rows match to all digits. The `-q 193` AR is the only meaningful quantised AR, but it has a real 800 KB buffer (see drops in Fig 5).

## Fig 4a / 4b - 432 hosts, 1 MB permutation, 5 seeds

Plots: `plots/e3_fig4/fig4a_cct_main.png` (one DRB bar), `fig4a_cct.png` (all variants), `fig4b_maxq.png`.

| algorithm | CCT increase % (ours) | paper % | max queue (pkts) |
|---|---|---|---|
| Simple RR | 86.1 +- 4.0 | 77 | 282 +- 18 |
| JSQ (exact) | 18.1 +- 1.1 | 43 | 62 +- 5 |
| Choice (P2C) | 11.9 +- 0.3 | 16 | 42 +- 2 |
| RSQ | 14.2 +- 0.7 | 13 | 56 +- 4 |
| RPS | 14.1 +- 0.9 | 13 | 50 +- 2 |
| REPS | 14.6 +- 1.0 | 14 | 51 +- 2 |
| AR (q=20000, = RSQ) | 14.2 +- 0.7 | 12 | 56 +- 4 |
| AR (q=193) | 12.6 +- 0.3 | 12 | 42 +- 2 |
| **DRB** (`drb_af_rand`: random per-flow phase + `-path_rr_order agg_fast`) | 4.29 +- 0.21 | 3.9 | 12.0 +- 0.6 |
| DRB-like, random phase, native order (`drb_rand`) | 8.2 +- 0.3 | 3.9 | 22.0 +- 1.2 |
| DRB-like, synchronised start (slot 0) | 15.0 +- 0.4 | 3.9 (DRB) | 34 +- 1 |
| DRB-like, start = src mod n | 8.5 +- 0.1 | 3.9 | 27 +- 0 |
| DRB-like, start = hash(src,dst) | 8.1 +- 0.3 | 3.9 | 22 +- 1 |
| Ofan | 2.56 +- 0.06 | 2.3 | 8 +- 0 |

Comparison with the paper:

- Match: the spray group (RPS, RSQ, REPS, AR, Choice) all at 12-15%; Ofan 2.6 vs 2.3; Simple RR clearly worst (86 vs 77; max queue 282 pkts).
- Match in queue grouping: Ofan has by far the smallest queue (8 pkts; proven E->A bound 7 data packets) and the others are 4-35x larger.
- Mismatch 1, JSQ (18% vs 43%): the paper puts JSQ in the linear-queue group with Simple RR; ours behaves like the spray group (62 pkt max queue). Hypotheses (untested): the paper's JSQ uses stale or deterministically tie-broken queue state (herding: all packets arriving in the same window pick the same shortest queue); ours reads the exact instantaneous queue and breaks ties uniformly at random.
- Mismatch 2, Choice (11.9 vs 16): small, same group; the paper's sampling rule may differ.
- DRB: the faithful stand-in (random per-flow phase, path order rotating the Agg fastest) gives 4.29% vs paper 3.9% (Ethereal 5.3% in the paper) - match. Native path order (even with random phase) gives 8.2%, src_mod / hash starts 8.1-8.5%, slot-0 synchronised start 15.0% (hosts hit the same links in lockstep). `agg_fast` only applies to 3-tier inter-pod flows; intra-pod pairs of a plain random permutation fall back to the native order, so a small residual is expected. DRB with `agg_fast` is the 'DRB' line in Fig 5a.
- AR reaches the paper's 12% only through the q=193 quantisation; with the huge buffer it degenerates to random (14.2).

## Fig 5 - CCT increase vs number of nodes (REPS, AR, Ofan)

Plots: `plots/e3_fig5/fig5_cct.png` (3 panels), per-panel `fig5{a,b,c}_cct.png`, `fig5{a,b,c}_maxq.png`. Numbers: `data/e3/summary.csv`, `runs_summary.csv`.

(a) Permutation, 1 MB, CCT increase % (5 seeds; N=1024: 3 seeds). DRB (`drb_af_rand`) by N = 1.08, 1.89, 2.70, 3.69, 4.29, 5.37 (+-0.1 to 0.2; max queue 3.8 -> 13.7 pkts): grows with N like Ofan but about 1.5-2x higher; the paper's Fig 5a does not show DRB, so this is extra.

| N | REPS | AR q=193 | AR q=20000 | Ofan |
|---|---|---|---|---|
| 16 | 9.1 +- 1.5 | 7.1 +- 1.2 | 8.5 +- 0.3 | 0.98 +- 0.05 |
| 54 | 9.1 +- 0.6 | 8.6 +- 0.3 | 10.1 +- 0.5 | 1.52 +- 0.06 |
| 128 | 11.7 +- 0.7 | 9.9 +- 0.8 | 11.9 +- 0.4 | 1.87 +- 0.05 |
| 250 | 12.9 +- 0.4 | 11.6 +- 0.3 | 13.6 +- 0.3 | 2.26 +- 0.06 |
| 432 | 14.6 +- 1.0 | 12.6 +- 0.3 | 14.2 +- 0.7 | 2.56 +- 0.06 |
| 1024 | 15.7 +- 1.5 | 13.7 +- 0.8 | 14.0 +- 0.3 | 2.91 +- 0.14 |

Max queue (pkts): Ofan 4 -> 9.7, REPS 28 -> 60, AR(193) 24 -> 46.

(b) All-to-all, constant per-flow 64 KB (N-1 flows per host, all at t=0; 3 seeds, N=250: 2 seeds):

| N | REPS | AR q=193 | AR q=20000 | Ofan |
|---|---|---|---|---|
| 16 | 4.5 +- 0.7 | 4.1 +- 0.8 | 3.9 +- 0.5 | 0.88 +- 0.09 |
| 54 | 4.3 +- 0.5 | 4.2 +- 0.6 | 5.5 +- 0.05 | 0.97 +- 0.03 |
| 128 | 3.9 +- 0.2 | 3.8 +- 0.5 | 3.8 +- 0.2 | 0.92 +- 0.01 |
| 250 | 3.7 +- 0.1 | 25.3 (buffer overflow: 6674 drops, RTOs) | 4.4 +- 0.6 | 0.78 +- 0.00 |

(c) All-to-all, constant per-host 32 MB (per-flow = 32 MB/(N-1)):

| N | REPS | AR q=193 | AR q=20000 | Ofan |
|---|---|---|---|---|
| 16 | 0.58 +- 0.02 | 0.58 +- 0.02 | 0.62 +- 0.05 | 0.41 +- 0.00 |
| 54 | 0.96 +- 0.03 | 1.09 +- 0.12 | 1.12 +- 0.06 | 0.44 +- 0.00 |
| 128 | 1.59 +- 0.12 | 1.65 +- 0.09 | 2.02 +- 0.13 | 0.52 +- 0.00 |
| 250 | 2.50 +- 0.08 | 15.1 (buffer overflow: 22364 drops) | 3.27 +- 0.07 | 0.57 +- 0.00 |

- N = 432 and 1024 all-to-all are dropped: simulator memory grows about N^2 (N=250: 1.4-1.9 GB and 250-280 s per run; N=128 about 0.5 GB), N=432 would be about 4.5 GB on the shared box. Nothing was subsampled.
- All-to-all N=250 uses 2 seeds only (cost). The matrix is seed-independent, so seeds only vary the random/ECMP choices.

Comparison with the paper (Fig 5a: REPS ~8-15%, AR ~6-13%, Ofan ~1-3% growing with N):

- (a) Match, quantitatively: REPS 9 -> 16%, AR 7-14%, Ofan 1.0 -> 2.9%, all rising with N, Ofan lowest by 4-9x.
- (b), (c): qualitative match only (Ofan best at every N, REPS/AR 2-8x worse); we have no paper numbers for absolutes. All-to-all increases are smaller than for permutations: with many concurrent flows per host the single-NIC bound dominates and per-flow imbalances average out. The AR(q=193) points at N=250 are loss events (800 KB buffers, trimming disabled), not load-balancing quality; use AR(q=20000) or REPS there. Ofan's all-to-all queue stays 6 -> 17 pkts while REPS/AR grow to 110-190 pkts.
- The gap between Ofan and REPS/AR grows with N in (a), as in the paper; in (b)/(c) Ofan is flat or slowly rising while REPS/AR rise in (c).

## Problems / caveats

- Fig 4b is per-run max queue bars, not the paper's time series.
- JSQ and DRB do not reproduce the paper's numbers (hypotheses above); CONGA/DRILL/DLB/SGLB/Ethereal/4Ofan not implemented.
- The Fig 4 N=432 results equal the Fig 5a N=432 results (same runs).
- Raw runs: `data/e3/runs.tar.gz` (extract with `tar -xzf` into `data/e3/` to re-aggregate).

## Reproduce

```bash
S=/workspace/experiments/exp33_ofan_paper_repro/scripts
docker exec ofan-dev bash -c "cd $S && PAR=2 bash run_e3.sh fig4"
docker exec ofan-dev bash -c "cd $S && NS='16 54 128 250 432' PAR=2 bash run_e3.sh fig5a && NS=1024 SEEDS='1 2 3' PAR=1 bash run_e3.sh fig5a"
docker exec ofan-dev bash -c "cd $S && export SIZE_PF=65536 && NS='16 54 128' bash run_e3.sh fig5b && NS=250 SEEDS_ATA='1 2' PAR=1 bash run_e3.sh fig5b"
docker exec ofan-dev bash -c "cd $S && NS='16 54 128' bash run_e3.sh fig5c && NS=250 SEEDS_ATA='1 2' PAR=1 bash run_e3.sh fig5c"   # 32 MB per host
python experiments/exp33_ofan_paper_repro/scripts/aggregate_e3.py && python experiments/exp33_ofan_paper_repro/scripts/plot_e3.py
```

DRB cells: `BIN=/tmp/frozen/htsim_uec_v2 ALGOS='drb_af_rand drb_rand' bash run_e3.sh fig4`, `ALGOS=drb_af_rand run_e3.sh fig5a`.
