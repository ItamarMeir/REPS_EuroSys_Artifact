# M5 - REPS (small B) vs OPS on the M4 grid

Question (Chen's question 4): does REPS' memory of good EVs beat an oblivious sprayer (OPS) when B is small?

## Setup
- **OPS** = `-load_balancing_algo oblivious -use_srv6 -paths 32`: every packet (and every retransmission) gets a uniform random EV in [0,32) and goes over SRv6 path `ev % 32`; feedback is ignored. REPS = `-load_balancing_algo freezing -reps_buffer_size B`, same SRv6 path substrate. Only the load balancer differs.
- **Network = M4's, derived not retyped:** `scripts/run_m5.py` imports `flags()` from `M4/scripts/run_m4.py` and swaps only the LB flag (and drops `-reps_buffer_size` for OPS). Same topology (`fat_tree_1024_1os_2t_400g`), tornado 16 MiB / 1024 flows, trimming on, `-ecn 25 76 -q 101`, `-disable_tor_ecn`, constant sender with the NIC-egress shaper (R = 100/200/400 Gbps = data + ACK), same degrade files (`healthy`, `uniform50`, `nonuniform` = 25%/75%).
- Per-run assertions in the runner (a failing cell is not recorded): LB line says `oblivious`, no `enable on tor downlink 1`, a `rate_const` line, 1024 flows finished. In all runs: 0 RTOs, 0 freeze entries.
- Grid: OPS 3 rates x 3 fails x 3 seeds (42-44) = 27 runs. REPS **B = 1, 2, 4 only** (user decision), 81 runs.
- The REPS runs were repeated with the current binary (to add `-log_queue_stats`). **All 81 finish-line sets are byte-identical to the M4 runs** (`traces/` vs `M4/traces/`), so M4 results are valid for the current binary and nothing changed in the network.
- Spray check: OPS path shares over the 32 paths have CV 0.021-0.037 (the multinomial noise is ~0.03), so OPS is uniform. ACKs return over the same path substrate in both arms (the LB lives only in the source).
- Data: `data/results_ops.jsonl`, `data/results_reps_rerun.jsonl`, `data/m5_summary.csv` (mean and 95% t(2) CI), `data/m5_table.md`; raw traces, stdout and queue TSVs in `traces/` (gitignored); scripts `scripts/run_m5.py`, `scripts/plot_m5.py`; plots `plots/m5_fct_tor0.png`, `plots/m5_trims_matched.png`.
- k, percent-random and overwrite statistics are REPS-buffer quantities and do not exist for OPS (the OPS traces have `fresh = 0`, `ev_src` empty); they are not compared.

## Results (mean of 3 seeds)
ToR0 mean FCT (us); trims = packets trimmed anywhere in the fabric (all 1024 flows); ECN = ECN-marked ACKs of all flows:

| rate / fail | FCT REPS B=1 | B=2 | B=4 | FCT OPS | trims B=4 / OPS | ECN B=4 / OPS |
|---|---|---|---|---|---|---|
| under / healthy | 1392.2 | 1392.2 | 1392.2 | 1392.2 | 0 / 0 | 0 / 0 |
| under / uniform50 | 1392.3 | 1392.3 | 1392.3 | 1392.4 | 0 / 0 | 0 / 0 |
| under / nonuniform | 1392.9 | 1392.7 | 1392.4 | **1410.4** | 0 / 1.2k | 50 / 30k |
| matched / healthy | 700.3 | 700.3 | 700.3 | 700.3 | 0 / 0 | 0 / 0 |
| matched / uniform50 | 706.0 | 707.9 | 707.9 | 712.2 | 131 / 1.0k | 32k / 55k |
| matched / nonuniform | 713.6 | 706.4 | 703.9 | **941.5** | 205 / 44k | 5k / 43k |
| over / healthy | 357.4 | 356.4 | 356.2 | 362.2 | 0 / 6.3k | 6.6k / 1.06M |
| over / uniform50 | 710.7 | 711.0 | 711.2 | 711.2 | 132k / 138k | 137k / 1.15M |
| over / nonuniform | 700.7 | 700.5 | 700.7 | 701.7 | 127k / 133k | 136k / 1.14M |

Full tables (max FCT, all metrics) in `data/m5_table.md`.

## Findings
Pre-registered predictions (plan) vs outcome:
1. **matched / nonuniform is where REPS wins, as predicted, and by a lot.** OPS offers ~200G to every ToR0 uplink, so the 25% uplinks (100G) run at rho ~2: 2.8k trims per such uplink, 44k trims in total, 11k retransmissions from the 8 traced hosts, ToR0 FCT 941.5 us. REPS needs only ~0.2k trims and 54 retransmissions at B=4 (FCT 703.9 us, -25%); **even B=1 (713.6 us, 1.5k trims) beats OPS by 24%**. REPS steers away from the overloaded links: the 25% links see 13 trims/link at B=4 (OPS 2768), while the 75% links carry more load (max queue 126k vs 46k bytes).
2. **under / nonuniform:** same mechanism at lower load: OPS 1410 us (+1.3%), 1.2k trims, 300 retransmissions, 30k ECN marks; REPS at B>=2 has no trims and 50-157 marks, FCT at the sender rate (1392 us).
3. **Near-ties where there is no imbalance, as predicted:** healthy and uniform50 at under and matched. matched / uniform50 shows a small OPS cost (712.2 vs 706-708 us, +0.6-0.9%, 1.0k vs 0.1-0.2k trims, CIs ~1 us), because the degraded links sit at rho = 1 and random spraying makes some of them transiently worse.
4. **over / healthy is not a clean tie** (prediction was a tie): OPS FCT 362.2 vs 356.2 us (+1.7%), 6.3k trims vs 0 for REPS B=4, 1.06M vs 6.6k ECN marks. At line rate on the healthy fabric the fabric is exactly at capacity and OPS's random collisions queue; REPS B>=2 avoids them (B=1 has 251k marks, no trims).
5. **over / degraded: both arms overloaded (400G into 200G), no LB helps** (FCT 700-711 us for all, 127-138k trims, 32k retransmissions in traced hosts). OPS has ~8x more ECN marks than REPS (1.1M vs 0.14-0.37M) and ~5% more trims, but FCT is the same.
6. REPS already at B=1 is never worse than OPS in FCT; B=2-4 is within ~1 us of B=8 (M4) except on matched / uniform50 (707.9 vs 702.1 at B=8, 1.1% random draws).

Answer to question 4 for this workload: with no CC and a constant rate, the memory in REPS matters exactly when load is unbalanced across links (non-uniform degradation, or line rate on a healthy fabric); with symmetric degradation or sub-capacity load an oblivious sprayer is within ~1%. Even a 1-slot buffer already captures most of the nonuniform gain.

## Caveats
- 3 seeds, t(2) CIs (wide, but the main gaps are 20-240 us versus ~2 us noise); one workload and topology, trimming on, constant sender (no CC). With CC (M8) queues shrink and the gap may shrink too.
- FCT/ECN/trim figures are whole-run (1024 flows); retransmissions come from the 8 traced hosts only.
- `path_random` was not run as a cross-check: it selects `rand() % 32` directly, which is the same distribution as OPS's `ev % 32` over 32 EVs, and the OPS path histogram already shows uniformity.
- The optional LB-dependence-of-jitter test (receiver arrival CV on OPS matched / uniform50, `investigate_k`) was not run.
