# T1: extreme non-uniform degradation without Freezing Mode

Mission T1 of [`../README.md`](../README.md). Question: if half of the ToR0 uplinks are degraded to a very small fraction r and the other half to 1 - r (mean stays 0.5), does the REPS buffer size B keep mattering beyond 8, as long as no cell enters Freezing Mode?

## Setup
- Everything as in [M4](../../meeting_23_10_26/M4/README.md), matched rate only (`-rate_const_gbps 200`, NIC egress of all packet types, no CC), via `run_m4.flags()`: 2-tier 1024-host fat tree, tornado 16 MiB, SRv6 32 paths, trimming on, `-disable_tor_ecn`, `-load_balancing_algo freezing`, `-exit_freeze 200000000`.
- Failure shapes (ToR0 uplinks only, even agg ratio r, odd agg ratio 1 - r): r = 0.25 (the M4 `nonuniform` file), 0.10, 0.05, 0.01. Files `data/degrade_r*.txt` come from `scripts/make_degrade_files.py`. Total ToR0 uplink capacity is 16/32 of healthy in all of them.
- B in {1, 2, 4, 8, 16, 32, 64, 128}, seeds 42-44; B = 5 and 6 were added later (last section). r = 0.25 for B <= 64 is reused from M4 (same flags and seeds); B = 8 and B = 128 are rerun with the new runner (B = 8 is the reproduction check).
- Runner `scripts/run_t1.py` (wraps `run_m4.py`). One pass per cell with `-log_reps_events` (ToR0 hosts 0-7) and `-log_queue_stats`; traces and per-cell stdout are kept in `traces/` (gzip, gitignored). Extra fields on top of M4: `n_freeze_events`, `frozen_rows` (trace), `failure_lines`, `tor_dl_ecn_on`, `trace_capped`, `send_per_path` (sends per EV mod 32 of the traced hosts).
- Gate: a cell is "clear" only if whole-run `rtos == 0` and `freeze_entries == 0` (from the 1024 flow-finish lines). Cells that fail it are reported separately, not dropped.

## Predictions (written before the grid ran)
Written after one smoke cell (r = 0.01, B = 8, seed 42) had already shown the gate failing there (29 RTOs, 22 freeze entries), so prediction 3 is not independent.
1. The smaller r, the larger the max-FCT gap between B = 2 and B = 64, and the larger `pct_random` at B = 8.
2. `pct_overwrite` at B = 8 rises as r falls (0.13% at r = 0.25). FCT follows only if overwrites exceed about 1%.
3. The gate fails at r = 0.01; r = 0.05 and 0.10 are unknown. The lowest r that stays clear is a result.
4. Not predicted numerically: whether REPS steers load away from the degraded links. Compare the share of sends on the degraded (even-agg) paths with the capacity share r.

## Results
78 new runs (3 r x 8 B x 3 seeds, plus r = 0.25 at B = 8 and 128), 0 failed; 24 more runs for B = 5, 6 in the last section. Table = mean of 3 seeds; max FCT in us over all 1024 flows with 95% t-CI (t(2) = 4.30, wide). Full table `data/t1_summary.csv`; page `plots/interactive.html` (gitignored), PNGs `plots/t1_*.png`.

| r (even agg) | gate | max FCT B=1 | B=2 | B=4 | B=8 | B=16 | B=128 | random % B=8 | overwrite % B=8 | spray share on degraded paths B=8 (capacity share) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.25 (M4) | clear | 715.8 | 709.1 | 706.2 | 703.4 +-1.6 | 702.9 | 702.9 +-0.7 | 2.03 | 0.13 | 24.9% (25%) |
| 0.10 | clear | 804.4 | 731.1 | 714.2 | 707.5 +-0.4 | 707.8 | 707.8 +-0.3 | 1.87 | 0.11 | 9.4% (10%) |
| 0.05 | clear | 848.9 | 755.8 | 723.1 | 712.8 +-1.0 | 713.9 | 713.9 +-4.1 | 3.07 | 0.01 | 4.7% (5%) |
| 0.01 | **fails** (RTOs 20-27, freeze entries 12-17 per run for B >= 8; 1585 / 55 at B=1) | 1061 +-700 | 788.7 | 740.4 | 736.2 +-22 | 736.7 | 731.5 +-3.3 | 1.97 | 0.90 | 2.2% (1%) |

Gate: r = 0.25, 0.10, 0.05 have 0 RTOs and 0 freeze entries in all 3 seeds at every B (r = 0.01: B=2 clear, every other B enters Freezing Mode). The lowest r that stays clear is **0.05**.

## Findings
1. **The knee is at B = 8 on the original grid for every gate-clear r; with B = 5, 6 and 7 added it reads 6 (r = 0.25, 0.10) and 5 (r = 0.05), but those moves are within the CIs (see the last sections).** On the original grid: max FCT is within 1 to 2% of its B=128 value at B=8 and flat from B=16 (r = 0.10: 707.5 vs 707.8; r = 0.05: 712.8 vs 713.9; r = 0.25: 703.4 vs 702.9). B >= 16 cells are identical to each other for r = 0.10 and 0.05 (same FCT, same counts): the buffer never holds more than 16 valid EVs there, so those runs do not differ.
2. **The cost of a too-small B grows as r falls.** Max FCT excess of B=1 over B=8: 12 us (r = 0.25), 97 us (0.10), 136 us (0.05); B=2 over B=8: 6, 24, 43 us. B matters more below the knee, not at a larger knee. Retransmits at B=1: 359, 4449, 6569.
3. **Prediction 1 half right** (gap grows, knee does not move above 8). **Prediction 2 missed:** overwrites at B=8 do not rise as r falls (0.13, 0.11, 0.01 %), and FCT stays flat for B >= 8 regardless. The overwrite proxy at B=8 stays near 0 in every gate-clear cell, so the meeting's question "is there a cell where overwrites at B=8 are large and FCT follows" has no such cell here. Only at r = 0.01 (gate failed) is it 0.90%.
4. **Prediction 3 right** (given the smoke cell): r = 0.01 enters Freezing Mode. Its FCT and p99 differ (736 us, CI +-22) and B = 1 shows 1585 RTOs per run, so it is a different mechanism and is not read as a buffer-size effect.
5. **REPS steers load almost in proportion to capacity**: the share of sends on the degraded paths tracks r (24.9, 9.4, 4.7%, against 25, 10, 5), only a little above at 0.01 (2.2%). Consistent with REPS avoiding an even 1/32 spray onto the slow links (not shown to be the cause of the flat knee). This is a measurement on 8 of 32 ToR0 hosts; per-uplink trims and queues (`plots/interactive.html`, per-uplink panel) show where the remaining loss is.
6. Reproduction check: the new runner's r = 0.25, B = 8, seed 42 run has 0 differing flow-finish lines against the stored M4 cell.

## Caveats
- 3 seeds, wide CIs (e.g. r = 0.05 at B=128: +-4.1 us), so differences under about 2 us are not resolved.
- Only matched 200G. The R = 190G slice in the plan was not run (not needed: gate-clear cells already show a flat knee).
- r = 0.01 was not refined between 0.01 and 0.05 (e.g. 0.02, 0.03); the gate boundary is therefore only bracketed.
- `add_mismatch` is nonzero in cells that enter Freezing Mode (the clean-ACK reconstruction assumes no freezing); it is 0 in gate-clear cells.
- Traces cover ToR0 hosts 0-7 only; RTO and retransmit counts are whole-run.



## B = 5 and 6 added 
The grid above has a gap between B = 4 and B = 8, which is where the knee sits. Added: B in {5, 6}, r in {0.25 (`matched_nonuniform`), 0.10, 0.05, 0.01}, seeds 42-44, same runner and flags (`run_t1.py --cells fail:5 fail:6`), 24 cells. Knee rule as in T2: `B_fct` = smallest B from which every larger B has mean max FCT <= the B=128 mean + max(CI of that B, CI of B=128, 0.2% of the B=128 mean) ("one-sided", `scripts/knee_t1.py`).
Predictions, from the interpolation between the stored B=4 and B=8 (curves fall roughly geometrically in that range; `pct_random` falls from about 9% to about 2% and overwrites from 3.8% to 0.01% between B=4 and 8):
1. Max FCT (us), r = 0.05: B=5 about 718, B=6 about 714.5 (B=4 723.1, B=8 712.8, B=128 713.9 +- 4.1). B=6 is inside the tolerance, B=5 is on its edge (tolerance about 4). Predicted `B_fct` on the finer grid: 6 (5 is possible).
2. r = 0.10 (B=4 714.2, B=8 707.5, B=128 707.8): B=5 about 709.5 (outside the 1.4 us floor), B=6 about 708 (inside). `B_fct` 6.
3. r = 0.25 (B=4 706.1, B=8 703.4, B=128 702.9): B=5 about 704.5, B=6 about 703.5; `B_fct` 5 or 6 (the B=4 gap is only 3 us, so this shape is the least resolvable).
4. r = 0.01 (gate fails by design): B=5, 6 enter Freezing Mode like every B >= 4; FCT between 740 (B=4) and 736 (B=8) within its +-12 to 22 us CI, so no knee is read from it.
5. `pct_random` at B=5 and 6 lies strictly between its B=4 and B=8 means (about 5 to 6% at B=5, 3 to 4% at B=6 for r = 0.05; B=4 is 8.7%, B=8 is 3.1%), for every r.
6. The gate stays clear (0 RTOs, 0 freeze entries) for r = 0.25, 0.10, 0.05 at B = 5, 6.

### Outcome (24 cells ran, 0 failed)
Gate: r = 0.25, 0.10, 0.05 clear at B = 5 and 6 in all 3 seeds (0 RTOs, 0 freeze entries). r = 0.01 fails it as before (RTOs 11-32 and freeze entries 11-23 per run). All 24 cells: 1024 flows finished, no `enable on tor downlink 1`, traces not capped, 32 Failure lines; `add_mismatch` is 0 in clear cells and nonzero only in the Freezing Mode cells (r = 0.01), as already caveated. Table = mean of 3 seeds, max FCT in us +- 95% t-CI (t(2) = 4.30); `B_fct` from `scripts/knee_t1.py` (`data/t1_knees.csv`).

| r | B=4 | B=5 | B=6 | B=8 | B=128 | B_fct (old grid -> new) |
|---|---|---|---|---|---|---|
| 0.25 | 706.2 +- 1.8 | 705.6 +- 0.7 | 704.4 +- 1.6 | 703.4 +- 1.6 | 702.9 +- 0.7 | 8 -> **6** |
| 0.10 | 714.2 +- 1.1 | 711.9 +- 2.1 | 709.6 +- 2.1 | 707.5 +- 0.4 | 707.8 +- 0.3 | 8 -> **6** |
| 0.05 | 723.1 +- 2.2 | 715.6 +- 3.1 | 714.0 +- 3.5 | 712.8 +- 1.0 | 713.9 +- 4.1 | 8 -> **5** |
| 0.01 (gate fails) | 740.4 +- 12.3 | 743.9 +- 27.7 | 745.7 +- 31.3 | 736.2 +- 22.5 | 731.5 +- 3.3 | not read (4) |

Random EV draws (mean of 3 seeds, post-warmup; columns `n_random_post_mean`, `n_random_degraded_mean`, `pct_random_degraded_mean` in `data/t1_summary.csv`, cells in `data/t1_random_stats_cells.csv`; the degraded set is parsed from the Failure lines and equals the even-agg parity in all 102 cells with a trace). The r = 0.25, B = 4 cell is an M4 cell without a kept trace, so its degraded count is missing.

| r | % random B=4 / 5 / 6 / 8 | n random B=4 / 5 / 6 / 8 | n random on degraded B=4 / 5 / 6 / 8 | % of sends on degraded paths B=4 / 5 / 6 / 8 (capacity share) |
|---|---|---|---|---|
| 0.25 | 9.12 / 5.66 / 3.48 / 2.03 | 2965 / 1838 / 1130 / 661 | - / 936 / 561 / 327 | - / 26.0 / 24.3 / 24.9 (25) |
| 0.10 | 9.72 / 6.14 / 3.41 / 1.87 | 3182 / 2008 / 1115 / 611 | 1600 / 1000 / 556 / 299 | 10.2 / 9.5 / 9.4 / 9.4 (10) |
| 0.05 | 8.73 / 5.71 / 3.76 / 3.07 | 2888 / 1878 / 1233 / 1005 | 1440 / 945 / 622 / 489 | 6.2 / 5.4 / 4.9 / 4.7 (5) |
| 0.01 | 5.12 / 3.73 / 2.61 / 1.97 | 1716 / 1243 / 868 / 654 | 858 / 626 / 426 / 324 | 3.5 / 2.9 / 2.6 / 2.2 (1) |

About half of the random draws land on the degraded paths at every B (48.7 to 51%): uniform draws over 16 of 32 paths, the design value. That does not isolate why random draws cost FCT: the rate is matched (the load is critical) and unevenness raises the cost per draw. Evidence: the uniform control r = 0.5 has a knee at 6 although no path is degraded relative to another.

Predictions against outcomes:
1. r = 0.05: B=5 715.6 (predicted about 718, better than predicted), B=6 714.0 (about 714.5), `B_fct` **5** (predicted 6, "5 possible"). The B=5 point sits 1.7 us above B=128 with a CI of 3.1 and a reference CI of 4.1, so it is within noise of B=8 and B=128; with 3 seeds the data cannot separate 5 from 6 or 8 here. **Partly held.**
2. r = 0.10: B=5 711.9 (about 709.5, 2.4 us worse), B=6 709.6 (about 708, 1.6 us worse), `B_fct` 6 (predicted 6): **knee held, levels missed**. B=6 is 1.8 us above B=128 and just inside the tolerance (2.1).
3. r = 0.25: B=5 705.6 (about 704.5), B=6 704.4 (about 703.5), `B_fct` 6 (predicted 5 or 6): **held**.
4. r = 0.01: all 6 new cells enter Freezing Mode (the gate fails); FCT 743.9 and 745.7 at B = 5, 6 with CIs of 28 to 31 us, no trend resolved: **held**.
5. `pct_random` at B = 5, 6 strictly between the B=4 and B=8 means for all four r: **held** (r = 0.05: 5.71 and 3.76 against 8.73 and 3.07).
6. Gate clear at B = 5, 6 for r = 0.25, 0.10, 0.05: **held**.

Reading: on the finer grid `B_fct` moves from 8 to 6 for r = 0.25 and 0.10 and to 5 for r = 0.05, so "the knee stays at 8" is replaced by "the knee is between 5 and 8". These moves are within the 3-seed CIs: the B=5/6/8 differences are 0.5 to 4 us against CIs of 0.4 to 3.5 us, and for r = 0.05 and 0.25 the one-sided rule passes at the first B whose mean falls below the B=128 tolerance. What is outside noise is the earlier drop: r = 0.05 loses 7.5 us from B=4 to B=5 (723.1 +- 2.2 to 715.6 +- 3.1) and r = 0.10 2.3 us, while overwrites fall from about 3 to 5% at B=4 to 1.8 to 2.7% at B=5 and 0.3 to 1.1% at B=6 (0.01 to 0.13% at B=8). Random draws fall steadily with B (r = 0.05: 8.7, 5.7, 3.8, 3.1 %).

## Page plan: random-EV draws next to max FCT (interactive page)
Question: does the share of random EV draws (overwrites turned into uniform draws) flatten at the same B as max FCT? Primary metric stays max FCT (first plot). Plots: (1) max FCT vs B with knee; (2) random-draw metrics vs B on the same axis (share, count, count on degraded paths, overwrites; max-FCT knees as numbered marks); (3) max-FCT excess over B=128 vs random draws on degraded paths, with Pearson/Spearman (correlational only); then the existing mechanism plots and the table.
Predictions (before the plots): the random-share knee B_rand sits at the max-FCT knee (5 to 8); the correlation is high but driven by B (both fall with B), so it is not read as cause. Built by `scripts/build_page_*.py` with `scripts/page_random.py`.


## B = 7 and the uniform (r = 0.5) series on the finer grid (predictions, written before the runs)
Added: B = 7 for r in {0.25 (`nonuniform`), 0.10, 0.05} (r = 0.01 is not extended: it enters Freezing Mode and is not wanted in the plots), seeds 42-44; and the r = 0.5 series (`uniform50`, the uniform control: every ToR0 uplink at 50%, no unevenness) at B in {5, 6, 7, 128}, seeds 42-44 (its B = 1 to 64 cells are the M4 cells reused by `aggregate_t1.py`; B = 8 is M4's too). 21 cells, same runner and flags (`run_t1.py --cells ...`).
Predictions, from interpolating the stored cells:
1. B = 7 lies between B = 6 and B = 8 in max FCT for r = 0.25, 0.10, 0.05: about 703.8, 708.4 and 713.3 us. The knee does **not** move: `B_fct` stays 6 (r = 0.25), 6 (r = 0.10) and 5 (r = 0.05) unless a B = 7 mean falls outside its tolerance by noise (possible for r = 0.05, whose 3-seed CI is up to 4 us; B = 7 can only make a knee larger, never smaller, by the one-sided rule).
2. `pct_random` at B = 7 between its B = 6 and B = 8 means (r = 0.05: about 3.4%; r = 0.10 about 2.5%; r = 0.25 about 2.7%).
3. Gate clear at B = 7 for all three r. **r = 0.05 stays gate-clear** (0 RTOs, 0 freeze entries) in the 3 new cells as in the 30 earlier ones; this is a prediction, not an assumption (it was believed to enter Freezing Mode, the stored data says it does not).
4. r = 0.5 (uniform control). The coordinator's expectation is `B_fct` <= 4 as in T2 uniform. The stored M4 cells do not look like that: max FCT is 707.1 / 709.0 / 709.0 / 702.5 / 702.3 us at B = 1 / 2 / 4 / 8 / 16 and `pct_random` is 26% at B = 4 and 1.1% at B = 8, so B = 4 is 6.7 us above B = 128 and the existing `B_fct` is 8, not <= 4. Prediction: B = 5 about 706, B = 6 about 704, B = 7 about 703, B = 128 about 702.3, and `B_fct` 6 or 7 (not <= 4). If B = 5 comes out near 702.3 the prediction is wrong and the T2 pattern holds. The differences to B = 128 are small (under 1%) and the series is the control, not a result about unevenness.

### Outcome B = 7 and the r = 0.5 series (21 cells ran, 0 failed)
Gate: clear in all 21 cells (0 RTOs, 0 freeze entries); 1024 flows, no `enable on tor downlink 1`, traces not capped, 32 Failure lines, `add_mismatch` 0. **r = 0.05 gate status: clear in all 33 cells (11 B x 3 seeds, 0 RTOs, 0 freeze entries each); r = 0.01 fails in 26 of its 30 cells** (B = 2 is clear; the 26 fail by RTOs and freeze entries). The earlier belief that r = 0.05 enters Freezing Mode is not supported by the data. r = 0.01 was not extended to B = 7 and is left out of the new tables. Max FCT in us (mean +- 95% CI, 3 seeds); `B_fct` on the 11-point grid {1, 2, 4, 5, 6, 7, 8, 16, ...}:

| r | B=4 | B=5 | B=6 | B=7 | B=8 | B=128 | B_fct (before B=7 -> now) |
|---|---|---|---|---|---|---|---|
| 0.5 (uniform control) | 709.0 +- 0.3 | 708.1 +- 3.5 | 702.7 +- 0.5 | 702.7 +- 0.9 | 702.5 +- 0.6 | 702.3 +- 0.4 | 8 -> **6** |
| 0.25 | 706.2 +- 1.8 | 705.6 +- 0.7 | 704.4 +- 1.6 | 704.0 +- 1.1 | 703.4 +- 1.6 | 702.9 +- 0.7 | 6 -> 6 (8 without the 0.2% floor) |
| 0.10 | 714.2 +- 1.1 | 711.9 +- 2.1 | 709.6 +- 2.1 | 708.5 +- 1.8 | 707.5 +- 0.4 | 707.8 +- 0.3 | 6 -> 6 |
| 0.05 | 723.1 +- 2.2 | 715.6 +- 3.1 | 714.0 +- 3.5 | 713.3 +- 3.6 | 712.8 +- 1.0 | 713.9 +- 4.1 | 5 -> 5 |

`pct_random` at B = 4 / 5 / 6 / 7 / 8: r = 0.5 26.29 / 18.57 / 2.11 / 1.59 / 1.10; r = 0.25 9.12 / 5.66 / 3.48 / 2.31 / 2.03; r = 0.10 9.72 / 6.14 / 3.41 / 2.09 / 1.87; r = 0.05 8.73 / 5.71 / 3.76 / 3.25 / 3.07. Absolute random draws (same B): r = 0.5 8537 / 6030 / 685 / 515 / 358; r = 0.25 2965 / 1838 / 1130 / 750 / 661; r = 0.10 3182 / 2008 / 1115 / 683 / 611; r = 0.05 2888 / 1878 / 1233 / 1066 / 1005. On degraded paths: r = 0.25 1452 / 936 / 561 / 371 / 327; r = 0.10 1600 / 1000 / 556 / 335 / 299; r = 0.05 1440 / 945 / 622 / 531 / 489 (about 50% each; r = 0.5 has no slow set). With the M4 traces now read for the reused cells, the r = 0.25 B = 4 degraded count exists too (1452).

Predictions against outcomes:
1. B = 7 between B = 6 and B = 8: r = 0.25 704.0 (predicted 703.8), r = 0.10 708.5 (708.4), r = 0.05 713.3 (713.3): **held**; knee unchanged at 6, 6, 5: **held**. The r = 0.25 knee is 6 with the 0.2% tolerance floor and 8 without it (B = 7 is 1.1 us above B = 128 with a CI of 1.1): it sits on the tolerance edge, not a result.
2. `pct_random` at B = 7 between B = 6 and B = 8 in all three: **held** (r = 0.05 3.25).
3. Gate clear at B = 7, r = 0.05 stays clear: **held**.
4. r = 0.5: predicted `B_fct` 6 or 7, got 6 (the coordinator's <= 4 expectation, as for T2 uniform, did **not** hold): B = 4 is 6.7 us above B = 128 and B = 5 is 5.8 us above it with a CI of 3.5 (outside the 3.5 us tolerance by 2.3 us, so the rule fails at B = 5), B = 6 is the first point on the plateau. The T1 uniform series carries many more random draws at small B than the T2 uniform case (26% at B = 4, 18.6% at B = 5, against 4.8% / 1.9% in T2 A), because T1 has 32 paths and 8 traced hosts per ToR sharing a uniformly slow set; the B = 5 to 6 drop from 18.6% to 2.1% random draws is the steepest step in the set. Predicted levels for B = 5, 6, 7 were 706 / 704 / 703: actual 708.1 / 702.7 / 702.7 (B = 5 is 2 us higher with a wide CI, B = 6 and 7 are 1.3 and 0.3 us lower).
Reading: B = 7 moves no T1 knee. The r = 0.5 control reaches its plateau at B = 6, not at B <= 4, and its curve is the sharpest in the set (709.0 at B = 4, 702.7 at B = 6), so the uniform case is not "free" at B = 4 in this setup. r = 0.05 and 0.25 remain flat within their CIs from B = 5 or 6 on.

### Page additions (B = 7, r = 0.5 control, knee rule, max-FCT host view)
`plots/interactive.html` now shows B = 7, the r = 0.5 control, the knee rule with its tolerance band and a knee table, and (new) the random-draw plot for the host that set the max FCT of each run next to the average of all 32 ToR0 hosts (`scripts/maxhost_stats.py` -> `data/t1_maxhost_stats.csv`, from `traces/allhosts/`). r = 0.01 is excluded everywhere (Freezing Mode in 26 of 30 cells). Prediction before the plots: the max-FCT host's random share has its knee at B_fct and is higher than the average host's (selection effect). Outcome: knee one grid step after B_fct, equal to the average host's; slightly higher (see the page).

### Paired knee (`scripts/knee_paired.py` -> `data/t1_paired_excess.csv`, `data/t1_knees_paired.csv`) and the random-draw knee B_rand0
Paired rule: per seed, excess = max FCT(B) - max FCT(B=128, same seed); B is ok if the mean paired excess <= max(0.2% of the B=128 mean, 1.96 * SE of the paired differences); `B_fct_paired` = smallest B from which every larger B is ok (one-sided). The unpaired rule (`plot_common.knee_fct`, `knee_t1.py`) compares means with tolerance max(CI of that B, CI of B=128, 0.2%), so a noisy B passes more easily (r = 0.05: the knee 5 rests on B=5 at 715.6 +- 3.1 against B=128 at 713.9 +- 4.1). The page uses the paired knee for rings, tiles and callouts and shows both. `B_rand0` = smallest B from which the paired extra random draws over B=128 (same seed, hosts 0-7) stay inside their 95% t-CI of zero for every larger B (tolerance-dependent: few seeds give a wide CI). The max-FCT-host view pairs each cell's slowest host with the same host in the B=128 cell of the same seed (`max_extra_*_samehost` columns of `data/t1_maxhost_stats.csv`).

| config | B_fct unpaired (page rule) | B_fct paired | B_rand0 (all draws) | B_rand0 (degraded draws) | B_rand (share within 10%) |
|---|---|---|---|---|---|
| r = 0.5 (uniform control) | 6 | 6 | 7 | - (no degraded set) | 7 |
| r = 0.25 | 6 | 7 | 8 | 8 | 7 |
| r = 0.10 | 6 | 7 | 7 | 7 | 7 |
| r = 0.05 | 5 | 6 | 6 | 16 | 6 |

The two knee rules disagree for all three r (paired is one grid step larger) and agree for the control. B_rand0 equals the paired B_fct for r = 0.10 and 0.05 and is one step later for r = 0.25 and the control, so "random draws flatten about one step later than max FCT" is tolerance-dependent and not general. Max-FCT host: its B_rand0 (all draws) equals the 32-host average's in 3 of 4 configs. Wording: random draws cost FCT because the load is critical (matched rate) and unevenness raises the cost per draw; the uniform control has a knee at 6 although no path is degraded relative to another. The earlier statements that the cost comes from draws landing on degraded paths are withdrawn.
