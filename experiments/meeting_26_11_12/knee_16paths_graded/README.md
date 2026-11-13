# knee_16paths_graded: the N sweep on a 16-path fabric with graded degradation

The same experiment as `../../meeting_26_10_26/knee_16paths/` (N sweep: the link delay is the only parameter; REPS B ladder, god mode, DPS, speed of light, uplink-class and EV-distribution analyses), with one change: the degradation model of the ToR0 uplinks. Nothing in `knee_16paths/` is modified by this experiment's runs; the scripts here are copies, parametrised by `scripts/params.py`. Interactive page: `plots/nsweep.html` (built by `scripts/build_page_nsweep.py`; gitignored, never committed).

## What changed
- ToR0 uplink j (SRv6: EV j = path j = uplink j) runs at ratio `[0.05, 0.95, 0.10, 0.90, 0.15, 0.85, 0.20, 0.80]` repeated twice (`params.RATIOS`, `data/degrade/degrade_h512_p16g.txt`). Even j = slow half (20, 40, 60, 80 G, each twice), odd j = fast half (380, 360, 340, 320 G, each twice). Mean ratio 0.5, so the 200G constant-rate sender (16 x 200G = 3200G) is still matched to the ToR0 capacity. (The request said 75% for the last ratio; 80% was used because 20 + 80 = 100 and the mean stays at exactly 50%.)
- The slow half carries 800 x 0.125 / ... = 100 of 800 ratio-units = **12.5%** of the ToR0 capacity (5% before). A uniform draw still lands on the slow half with probability 50%.
- Queues and ECN thresholds scale with the ratio (`alloc_queue`): 5, 10, 15, 20 packets on the slow links, 96, 91, 86, 81 on the fast ones.
- God mode (`-reps_draw_weights capacity`) and DPS (`-dps_dist capacity`) read the weights from the simulated queue speeds, so they follow the degradation with no code change. Proof from stdout (mini gate): god weights `20000 380000 40000 360000 ...`, DPS pmf `0.00625 0.11875 0.0125 0.1125 ...` = ratio_j / 8.
- Everything else as in `knee_16paths`: 512 hosts, 16 per ToR, tornado i -> i + 256, 4 messages of 4 MiB 1000 us apart (`-connections_mapping`), MTU 4150, queues 101 packets, ECN 25/76, REPS = `-load_balancing_algo freezing`, `-disable_tor_ecn`, trimming on, metric = max FCT over hosts 0-15, mean of messages 2-4 per seed.

## Reduced run (stage 1)
The original is 1456 cells + 112 speed-of-light + 21 DPS cells. Stage 1 runs about 30% of that:
- 4 latencies (0.25, 1, 4, 16 us) instead of 7; the B ladder of each is the old one (52 B values per seed and arm), so cells pair with the 5/95 run.
- Seeds 42-45 (4) instead of 8; claims say "4 seeds", 95% CIs use t with 3 degrees of freedom.
- Speed of light: the network (ToR0 uplinks all 0.5) is identical to the old one, so only 2 smoke cells run (lat 250, 16000) and the old table is reused (labelled in the page).
- DPS: 3 seeds, B = 8 only, 4 latencies.
- ~430 cells. Stage 2 (latencies 0.5, 2, 8 us and seeds 46-49) only on request.

## Predictions (written before the sweep)
1. Gate: 0 RTOs, 0 freeze entries, 0 FAIL in every cell.
2. Identities: sends per `ev % 16` = data + trims + drops of ToR0 uplink j for all 16 j; NACKs per class = trims per class (0 mismatches).
3. Speed of light equals the 5/95 values exactly.
4. God mode: share of random draws on the slow half = 12.5%; per-EV frequency = ratio_j / 8; uniform = 50%.
5. The slow links are less starved (12.5% of capacity instead of 5%): small-B REPS is faster than in the 5/95 run at the same N and B, the REPS-minus-god gap is smaller, the knee at the same or smaller B. The 5% and 10% links stay the worst (5 and 10 packet queues), so the max-FCT host still concentrates its trims on them.
6. DPS (capacity) vs god: same conclusions as in the 5/95 run within the 3-seed interval.

## Verification so far (2026-11-12)
Mini gate (before the sweep): 2 latencies (0.25, 16 us) x 3 B x 2 seeds, REPS, god, DPS, plus speed-of-light cells; 36 cells, 0 FAIL, 0 RTOs, 0 freeze entries.
- Configuration from the output: 2048 flow-finish lines, 16 `Failure:` lines with speeds 20, 40, 60, 80, 320, 340, 360, 380 Mbit/s-scaled values, `distinct_paths = [16]`, `no_of_tor_uplinks: 512`, no `enable on tor downlink 1`, RTT 128.337 us at 16 us delay; maximum queues of the slow uplinks 20750, 41500, 62250, 83000 B (5, 10, 15, 20 packets), the same twice.
- Speed of light 172.613 us (lat 250) and 298.613 us (lat 16000), equal to the 5/95 run (prediction 3 holds).
- God weights and DPS pmf as in the list above (prediction 4, weights part).

## Results (stage 1, 2026-11-13)
Run: 208 REPS + 208 god + 12 DPS + 2 speed-of-light cells, all with 0 RTOs and 0 freeze entries. Identity checks (`scripts/run_checks.sh`, `data/identity_checks_final.log`, 9 cells per arm over all latencies and seeds): sends per `ev % 16` = data + trims + drops of ToR0 uplink j for all 16 j and NACKs per class = trims per class, 0 mismatches. DPS: `data/dps_identity_checks.log`, 4 cells, PASS. (The class labels "5%/95%" printed by `n_uplink_check.py` and `dps_compare.py` mean slow half / fast half here.) Numbers: `data/n_summary.txt`, `data/god_paired.csv`, `data/dps_compare.txt`; page `plots/nsweep.html` (gitignored). Comparison with the 5/95 run uses seeds 42-45 of both.

Predictions against the result:
1. Gate: held.
2. Identities: held on the 18 sampled cells (not on every cell).
3. Speed of light: held for the 2 smoke cells (172.613 and 298.613 us); the old table is reused for the page (`data/n_sol_sim.csv`; the 2 new cells are in `data/n_sol_graded_smoke.csv`).
4. God warmup share on the slow half: held pooled (12.4% of 63974 warmup sends, expected 12.5%; REPS 51.1%, uniform). **Partly missed per latency:** 18.2, 15.4, 12.0, 12.2% at 0.25, 1, 4, 16 us. Cause not isolated. The per-EV frequency (ratio_j / 8) was checked only through the weights printed in the mini gate, not on the sweep.
5. Slow links less starved: held. REPS max FCT at B = 8, new minus old: -1.6, -4.3, -5.0, -18.8 us at 0.25, 1, 4, 16 us (B = 2: -7.7, -7.7, -10.3, -19.7). REPS minus god at B = 2: 9.3, 13.2, 23.4, 85.0 us (5/95, 8 seeds: 15.8, 19.2, 29.8, 106.0); at B = 8: 0.8, 4.1, 16.2, 43.3 (1.7, 7.0, 18.9, 77.6). Knee (0.2% rule) B = 12, 64, 32, 64 (5/95: 16, 64, 96, 256); ring page rule 16, 64, 64, 128 (24, 64, 96, 256). The claim that the 5% and 10% links stay the worst was not tested separately.
6. DPS vs god: held within the 3-seed interval. DPS minus god B = 8: +6.6 +- 2.0, +7.1 +- 2.3, -3.7 +- 3.0, +17.0 +- 4.5 us (5/95: +5.8, +6.9, -2.6, +31.0).

N labels: the page uses the 5/95 values (25, 65, 208, 788) for 0.25, 1, 4, 16 us so the two pages line up; the measured median peak in flight of this run is 27, 66, 217, 790 (more packets fit in flight because the slow links carry 12.5% of the capacity). Line colours follow the latency colours of the 7-latency page.

Not done: stage 2 (latencies 0.5, 2, 8 us, seeds 46-49), the uplink-class and EV-distribution sections were built from the same tables as in the 5/95 page but not reviewed one by one, nothing committed.

## Rerun
Binary built in the `dps-dev` container (bind mount of the repo; `make clean` first). `bash scripts/setup_container.sh` inside the container, then `bash /kneework16g/run_mini.sh` (gate) and `bash /kneework16g/run_ladder16.sh` (stage 1); outputs `/k16g_reps`, `/k16g_god`, `/k16g_dps`, `/k16g_sol`. Extraction as in `knee_16paths` (`scripts/extract.sh`, then `god_paired.py`, `n_summary.py`, `build_page_nsweep.py`).
