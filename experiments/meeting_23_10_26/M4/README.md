# M4 - Does REPS buffer size B matter at known constant send rates?

## Setup
- Sender: `-sender_cc_algo constant` with `-rate_const_gbps R` (timer-paced, no congestion control; see `../../RATE_CONST_ARCHITECTURE.md`). R = 100 / 200 / 400 Gbps per source = 0.25 / 0.5 / 1.0 of the 400G NIC ("under" / "matched" / "over").
- Fabric: `fat_tree_1024_1os_2t_400g`, tornado 16 MiB, 1024 flows, SRv6 32 paths, trimming on, `-disable_tor_ecn`, `-load_balancing_algo freezing`.
- Failure models (ToR0 uplinks only): `healthy`; `uniform50` (all 32 uplinks at 50%); `nonuniform` (even agg 25% / odd agg 75% of speed, mean 50%; see `../M3`).
- B in {1,2,4,8,16,32,64}, **seeds 42-44 (189 runs)**. Table values are means over 3 seeds; 95% CIs use t(2) = 4.30, so they are wide (FCT CIs 0.01-1.6 us, see `data/m4_summary.csv`).
- Capacity per source on degraded ToR0 is 200 Gbps, so under/matched/over = below / at / above the bottleneck. On the healthy fabric 400 Gbps is the matched case.
- Raw per-run results: `data/results.jsonl`; aggregation and plots: `scripts/plot_m4.py`, `plots/`. Runner: `scripts/run_m4.py`.

## Metric definitions (corrected)
The first version of this analysis was wrong in two ways and its numbers were discarded; this README is from the rerun.
- **k** = valid EVs in the REPS buffer immediately *before* a draw. The trace's `fresh` column is the post-event value, so k is the previous row's `fresh` for the same source (a row's own `fresh` is after the pop; using it made B=1 read k=0 on valid draws).
- Draws = SEND / RTX / RTS events, counted only **after the source's first ACK**. Before the first ACK the buffer is necessarily empty, so those draws are warmup, not a property of B (they inflated "random %" by ~0.7-3 points).
- Traces: ToR0 sources 0-7 (8 of the 32 ToR0 hosts). 0 reconstruction mismatches and no unexplained EV sources in the validation cells.
- FCT, retransmits, ECN-marked ACKs, RTOs are simulator outputs and are bit-identical to the first run for the same seeds (checked all 189 runs).

## Results (percent of post-warmup draws using a random EV, mean of 3 seeds)

| rate | fail | B=1 | B=2 | B=4 | B=8 | B=16..64 |
|---|---|---|---|---|---|---|
| under (100G) | healthy | 21.8 | 0.01 | 0.02 | 0.02 | 0.02 |
| under | uniform50 | 28.5 | 0.05 | 0.03 | 0.03 | 0.03 |
| under | nonuniform | 32.5 | 2.3 | 0.29 | 0.14 | 0.14 |
| matched (200G) | healthy | 33.0 | 6.2 | 0.04 | 0.04 | 0.04 |
| matched | uniform50 | 68.9 | 54.5 | 49.5 | 49.3 | 49.0 |
| matched | nonuniform | 49.3 | 29.0 | 20.4 | 19.9 | 19.7 |
| over (400G) | healthy | 25.3 | 3.9 | 0.81 | 0.69 | 0.69 |
| over | uniform50 | 99.7 | 99.7 | 99.7 | 99.7 | 99.7 |
| over | nonuniform | 99.4 | 99.4 | 99.3 | 99.4 | 99.4 |

ToR0 mean FCT (us):

| rate | fail | B=1 | B=8 | B=64 |
|---|---|---|---|---|
| under | any | 1371.3-1371.8 | 1371.4-1371.9 | same |
| matched | healthy | 689.8 | 689.8 | 689.8 |
| matched | uniform50 | 703.7 | 704.9 | 704.9 |
| matched | nonuniform | 710.0 | 696.6 | 696.5 |
| over | healthy | 357.6 | 356.2 | 356.2 |
| over | uniform50 | 711.1 | 711.1 | 711.1 |
| over | nonuniform | 700.6 | 700.9 | 700.9 |

## Findings
1. **B matters only below ~4.** Random %, FCT, retransmits and ECN marks are identical from B=16 to B=64 (and nearly so from B=4/8); only the peak k keeps growing. Peak k reaches B only up to B=16 at matched/uniform50 (k_max 8, 16, 22, 22 for B=8, 16, 32, 64), so B>16 is never filled and has no effect. This confirms the meeting's observation (B beyond 4-8 irrelevant), now with a known send rate instead of NSCC.
2. **B=1 is always bad** (22-69% random on every non-over cell): the single slot is empty between consuming an EV and the next recycled ACK. B=2 already removes it on a clean fabric (healthy / uniform50 under: <0.1%); matched/healthy needs B=4 (6.2% at B=2, 0.04% at B=4).
3. **Under capacity (100G):** <=0.3% random from B=4 on every failure model (non-uniform needs B>=4: 2.3% at B=2). FCT is rate-bound (~1371 us) and identical across B and failure models; no retransmits, no RTOs, no freezing. At B=8 the valid draws mostly find k=2-3 (healthy 51% / 13%), i.e. the rate is low enough that recycling keeps several EVs banked.
4. **Matched capacity (200G):** B and the failure model interact. Healthy: 0.04% random from B=4, FCT 690 us flat. Uniform50: **~49% random regardless of B** (49.5% at B=4, 49.0% at B=16+), ~400 retransmits and ~63k ECN-marked ACKs per run; the standing queue at the bottleneck marks about half the ACKs, so valid EVs are not available and a bigger buffer cannot help. FCT 704-705 us for B>=2 (healthy 690), B=1 slightly better at 703.7 (within CI, 1.1 us). Non-uniform: 20% random at B=8, better than uniform because the 75%-speed links keep returning valid EVs; B=1 to 8 improves ToR0 FCT 710.0 to 696.6 us (-1.9%), the only place B visibly moves FCT, and B=8 to 64 changes nothing.
5. **Over capacity (400G):** healthy is fine (0.69% random at B>=8, FCT 356 us; B=1 still 25% random). At line rate on a healthy fabric B=1 also causes about 33x more ECN marking than B=8 (244k vs 7.5k marked ACKs per run, whole run) even though ToR0 FCT moves only 1.4 us. On degraded fabrics the sender exceeds capacity: 99.4-99.7% random draws and ~32k retransmits per run (whole run) for every B; k is ~0 (0.0-0.01 mean), FCT 701-711 us independent of B. With no feedback to throttle the sender the buffer stays empty; B is irrelevant because the sender, not the load balancer, is the problem.
6. **Reconciling with NSCC (M1):** NSCC settles at the target-delay standing queue, which is the matched-degraded operating point, hence ~55-60% random draws; it sits in the matched/uniform50 row (49%), not at healthy-looking behaviour. A perfect CC reaches ~0% random on a 50%-degraded fabric only if it holds the rate clearly below capacity (under row), not at the matched knee, where marking itself is the cost of operating at capacity.
7. No RTOs and no freezing in any of the 189 runs, so the freezing mechanism plays no role in this grid.

## Caveats
- 3 seeds (user-requested reduction from 5); CIs are wide, differences of ~1 us in FCT are not significant. Random-draw 95% CIs (3 seeds) are 0.03-2.1 points for the B>=4 cells where random % exceeds 0.3 (e.g. matched/uniform50 B=8: 49.3 +/- 1.8; matched/nonuniform B=8: 19.9 +/- 2.1), small relative to the 50% vs 20% vs 0% gaps discussed.
- Single workload (tornado 16 MiB), single topology, trimming on. `rtx` at "over" counts retransmits charged against R by the constant-rate sender.
- Random/k statistics come from 8 of the 32 ToR0 source hosts' event traces. Retransmit and ECN-mark counts are whole-run (all 1024 flows), so at matched/over they include non-ToR0 flows and are not comparable to the ToR0 random %.
- M1's `pct_random` counts all sends including pre-first-ACK warmup; M4's excludes warmup (a few points lower at most), so the 55-60% (M1) vs 49% (M4) comparison in finding 6 is slightly apples-to-oranges, not enough to change the conclusion.
- Plots: `plots/m4_pct_random.png`, `m4_k_mean.png`, `m4_k_ge3.png`, `m4_fct_tor0.png`, `m4_fct_p99.png`, `m4_spray_width.png`; interactive page below has the full k distribution per cell.

## Interactive page
`python ../scripts/build_interactive.py` writes `plots/interactive.html` (Plotly from cdnjs; gitignored, publish via the thesis repo on request). Three sections (under / matched / over), each with valid-vs-random split, k distribution (B=1,2 included), FCT statistics, retransmits and ECN marks, for healthy / uniform50 / non-uniform.
