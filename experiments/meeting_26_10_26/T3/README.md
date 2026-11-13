# T3: where does "8" come from?

Mission T3 of [`../README.md`](../README.md). In [T1](../T1/README.md) the max FCT settled at B = 8 for every gate-clear degradation (25/75, 10/90, 5/95). Chen's reading: 8 comes from path length and RTT through the variance of the ACK arrival rate, not from the radix. T3 holds the failure at 5/95 (even agg 0.05, odd agg 0.95, mean 0.5) and moves one thing at a time: radix and host count, path count, tiers, link latency, ACK spacing. "k-level" in the request is read as fat-tree radix and tiers; REPS `k` (valid EVs in the buffer before a draw) is reported separately as the mechanism metric.

## Setup
- Flags are `meeting_23_10_26/M4` `run_m4.flags("matched", "healthy", B, seed)` with these keys overridden per config: `-topo -tm -paths -rate_const_gbps -q -ecn -sack_threshold`, plus `-degrade_links_file`. Everything else is M4's: constant-rate sender, trimming, `-disable_tor_ecn`, `freezing`, `-exit_freeze 200000000`, tornado 16 MiB, `-linkspeed 400000`.
- Inputs come from `scripts/make_configs.py` (`data/configs/`): H hosts per ToR, U uplinks, P = `-paths`; matched rate R = 0.5 * S * U / H = 200G in every config (1:1); `-q/-ecn` from exp26 `get_bdp` at 1 us links (2-tier 101 / 25 76, 3-tier 152 / 38 114) and held fixed in the latency axis; degrade file `0 a r` (even a) / `0 a 1-r` (odd a) over ToR0's U uplinks, mean 0.5 asserted. Generated baseline files are byte-identical to the repo's 1024-host topology, the n1024 tornado matrix and T1's `degrade_r005.txt`.
- Runner `scripts/run_t3.py`; one pass per cell with `-log_reps_events` on the first min(8, H) hosts of ToR0 and `-log_queue_stats`; traces, queue TSVs and stdout kept gzip'd in `traces/` (gitignored). Container `m23-dev`, inputs copied by `scripts/setup_container.sh`.
- Axes (one variable at a time from the baseline 1024 hosts, 2-tier, 32 paths, 1 us links, `-sack_threshold 4000`):

| Axis | Configs |
|---|---|
| A. hosts / radix (2-tier, paths = radix) | 128h/8p, 256h/16p, 512h/32p, 2048h/32p |
| B. path count at 1024 hosts | 16p (64 ToRs), 64p (16 ToRs) |
| C. tiers (6 hops) | 3-tier 128h (16 paths), 3-tier 1024h (64 paths); degrade is first hop only (ToR0 to aggs 0..U-1), a different shape than 2-tier |
| D. link latency | x4, x16 (only `Downlink_Latency_ns` changes) |
| E. ACK spacing | `-sack_threshold` 8000, 16384 |

- B grid {2, 4, 6, 8, 12, 16, 32, 128}; screen with seed 42, confirm the axes that move something with seeds 43-44 (95% t-CI, t(2) = 4.30). Gate per cell: whole-run RTOs = 0 and freeze entries = 0.

## Predictions (written before any run)
1. Uncapped k (B = 128) is a rate-driven walk (investigate_k), so it does not grow with latency: the k tail and the knee stay near 8 for x4 and x16. This contradicts the RTT reading.
2. Fewer, larger ACK batches (`-sack_threshold` 16384) widen k and move the knee up.
3. Host count and path count move the knee weakly; paths matter through the share of sends on degraded paths (about r).
4. 3-tier adds queueing hops, so the k tail grows and the knee is at least 8, possibly 12 to 16 at 1024h.
5. B = 2 shows an FCT penalty over B = 8 in every config. The 5/95 gate may fail on 3-tier or on the latency x16 cells; such cells are reported, not dropped.
6. The FCT knee and the uncapped-k tail need not coincide (T1: 25/75 has uncapped k p99 = 12 but flat FCT from 8). Three knees are reported: `B_fct` (max FCT within CI or 0.2% of B = 128), `B_ow` (pct_overwrite < 0.1%), `B_k99` (smallest B at or above the uncapped k p99).

## Interactive page
`../scripts/build_page_t3.py` -> `plots/interactive.html` (gitignored; built with `experiments/tools/plot_common.py`, skill `interactive-plotter`). Primary metric is max FCT, so the order is: (1) max FCT vs B per config with the knee `B_fct` ringed, axis dropdown; (2) `B_fct` per config against B=8, configs outside the clean regime (>= 10% random EVs at B=8) in grey; (3) mechanism: steady k p99, `B_ow`, `B_ks99` against the same axis; (4) supporting check: k against time (why the knees use the steady-state window); (5) knee table. The earlier page (gate table, per-uplink panels, M4 per-config panels) is `../scripts/legacy_build_interactive_t3.py`.

## Checks that changed the analysis (after the seed-42 screen)
- The first knee function was two-sided and returned B = 12 for the baseline although B = 8 was better than B = 128; it is now one-sided (smallest B from which every larger B is within tolerance or better).
- Whole-run uncapped k max (27, 32, 91, 128 in `h1024_p16`, `h1024_p64`, `lat4`, `lat16`) is a flow-drain effect: retransmit draws after the last send meet a buffer full of already-returned EVs. `scripts/steady_k.py` recomputes k from the B = 128 traces with the same definition as `run_m4.analyze`, dropping the first and last 15% of each traced source's span. On the seed-42 screen steady-state k p99 was 6 to 8 and max 8 to 10 in every config; the 3-seed data refine this (see Results): the lat16 fixed-threshold cell keeps a steady max of 27 to 45 in every seed, and `lat4_bdpq` has p99 11.
- Latency (q/ECN fixed) and ACK-spacing cells are not clean knee measurements: random-EV share at B = 8 is 22% and 31% (lat16, lat4) and 60% to 74% (sack), against 1.5% to 3.3% elsewhere, with 5000+ retransmits. The latency cells keep `-q/-ecn` at the 1 us BDP; the scaled cells (D2) were added to test that. The p50 FCT rise in the latency cells (724, 819 us against 700) is the extra round-trip propagation (RTT = 8 x link latency in 2-tier: +24 us at x4, +120 us at x16) and is identical with fixed and scaled thresholds, so it is not a threshold effect.

## Results (344 cells: 15 configs x 8 B; 3 seeds 42-44 except `h2048_p32`, 1 seed; B = 128 is the reference)
Config proofs from output pass in all 344 cells: `distinct_paths` = P, `Failure:` lines = U with 20 and 380 Mbps, flows = hosts, no `enable on tor downlink 1`, 0 reconstruction and add mismatches, trace not capped. Gate: 0 RTOs and 0 freeze entries in every cell. Table: `data/t3_knees.csv`; per-cell data `data/t3_summary.csv`.

| config | steady k p99 (max) | B_ow | B_fct (max / p99) | p50 FCT | % random EVs at B=8 |
|---|---|---|---|---|---|
| baseline 1024h/32p | 6.0 (8.7) | 8 | 6 / 6 | 700.3 | 3.1 |
| 128h/8p, 256h/16p, 512h/32p | 7.7, 6.7, 6.7 (9.3, 8.7, 9.3) | 6, 8, 8 | 4, 6, 6 / 4, 6, 6 | 700 | 1.8 to 3.3 |
| 1024h/16p, 1024h/64p | 6.7, 6.0 (9.3, 9.3) | 8, 8 | 6, 6 / 6, 6 | 700 | 2.2, 3.4 |
| 3-tier 128h, 1024h | 7.7, 8.0 (9.3, 10.0) | 8, 8 | 6, 6 / 4, 2 | 704 | 2.1, 2.4 |
| latency x4, q/ECN fixed | 6.7 (9.3) | 128 | 2 / 2 | 724 | 31 |
| latency x16, q/ECN fixed | 6.0 (37) | never | 4 / 4 | 819 | 22 |
| latency x4, q/ECN scaled to BDP | **11.0 (14.7)** | **12** | **12 / 12** | 724 | 6.8 |
| latency x16, q/ECN scaled to BDP | 6.7 (10.3) | 12 | 6 / 6 (CI 37 us) | 819 | 19.6 |
| `-sack_threshold` 8000, 16384 | 2.0 (3.7, 3.3) | 12, 8 | 2 / 4, 2 | 695, 692 | 60, 74 |
| 2048h/32p (1 seed) | 7.0 (9.0) | 8 | 8 / 6 | 700 | 2.3 |

Steady k is k at B = 128 with the first and last 15% of each traced source's span dropped (`scripts/steady_k.py`); whole-run k max is a drain effect and is not used. Baseline detail: B = 6 and B = 8 are the same within noise (713.97 +- 3.5 and 712.79 +- 1.0 us), B >= 12 is identical to B = 128, B = 4 costs +1.4% and B = 2 +5.9%; overwrites 0.26% at B = 6 and 0.01% at B = 8.

### Predictions against outcomes
1. k does not grow with latency: **missed at x4**, the nearest-to-clean latency cell (q/ECN scaled to the BDP, 6.8% random EVs): steady p99 11.0 in all three seeds and all three knees at 12. **Untested at x16**: even with scaled thresholds that cell keeps 19.6% random EVs and is not a clean measurement (p99 6.7, overwrite knee 12 because overwrites are 0.12% at B = 8). With fixed thresholds the p99 stays 6.0 to 6.7, but those cells are in a different regime, so that is not a pass.
2. Fewer ACKs widen k: **missed**. k collapses (p99 2, 60 to 74% random EVs) because fewer ACKs recycle fewer EVs; max FCT rises 46%, flat in B. Supply, not variance.
3. Hosts and paths move the knee weakly: **held** (steady p99 6 to 7.7, B_ow 6 to 8 in all six cells).
4. 3-tier raises the k tail and the knee to 12 to 16: **missed**: p99 7.7 to 8.0, B_ow 8. (The degrade is first-hop only, a different shape.)
5. B = 2 pays an FCT penalty everywhere: **held in clean cells, missed in sack cells** (flat in B). The 5/95 gate was predicted to possibly fail: **missed**, it held in every cell.
6. The knees need not coincide: **held**: in clean cells B_fct (4 to 6) is below B_ow (8); they coincide at 12 only in the x4 scaled-threshold cell.

### What this says about "why 8" (consistent with, not proven)
- In every clean 2-tier and 3-tier cell the steady uncapped k p99 is 6 to 8, so a buffer of 8 holds the typical valid-EV backlog and overwrites fall below 0.1% there. Radix, host count, path count and tier count do not change that, which fits the k walk being driven by the send rate and the degraded share rather than by topology size. Max FCT is flat from B = 6 (4 on the 128-host cell), so 8 sits slightly above the FCT knee and exactly at the overwrite knee.
- Configuration proof for the D2 cells, from the output: `Setting queuesize to 394 packets` with ECN low/high 406700/1228400 bytes (x4; fixed cell: 101 packets, 103750/315400), trims fall from 20131 to 4613 per run at B = 8.
- The knee moved once: latency x4 with the queue and ECN thresholds scaled to the BDP (394, 98/296). Steady k p99 is 11 in every seed, overwrites are 0.93% at B = 8 and 0.05% at B = 12, and max FCT improves 2% from B = 8 to B = 12 (772 to 758 us; every seed improves, by 11 to 18 us: 768.1 to 757.3, 772.7 to 760.0, 774.5 to 756.2). So 8 is not universal. A deeper queue with higher ECN thresholds lets the ACK stream arrive in larger bursts, and a larger buffer keeps more of them; that mechanism is a hypothesis, no run isolates it. It is not monotonic: x16 scaled shows p99 6.7.
- The fixed-threshold latency cells and the sack cells operate in a different regime (20 to 74% random EVs, 1000 to 16000 retransmits at B = 8); their knees are not comparable to the baseline.
- RTT vs queue depth vs ECN thresholds is now separated by control D3 (below): the ECN thresholds drive it.
- Open: why x16 scaled still has 19.6% random EVs and p50 FCT 819 (against 700); whether the x4 result is the BDP-sized queue or the ECN thresholds; the 2048-host cell has one seed.

## Status
T3 screen and confirmation done; page `plots/interactive.html` built and checked headless (111 plots, no exceptions). Nothing committed.

## Control D3: queue depth vs RTT (predictions written before the run, 2026-10-30)
Goal: find why the knee is at B = 8. Two new configs on the baseline 1024-host, 1 us-link topology, seeds 42-44, B in {2,4,6,8,12,16,32,128}: `q394_ecn98` (queue 394, ECN 98/296, the thresholds of `lat4_bdpq`) and `q394_ecn25` (queue 394, ECN 25/76, the baseline thresholds).
Predictions: (1) `q394_ecn98`: if queue depth / ECN thresholds drive the tail, steady k p99 is about 11 and the knees (B_ow, B_fct) move to 12. If RTT at q = BDP drives it, p99 stays 6 to 8 and the knee stays 8. Lean: queue depth (a slow link marks only after 98 queued packets, about 160 us of delay, so unmarked EVs return late and in bursts). (2) `q394_ecn25`: ECN marks at the old depth, so p99 stays 6 to 8 and knee 8 if the ECN thresholds (not the queue size) are the cause; a knee at 12 would mean queue size alone matters. Misses are reported below.

### D3 results (48 cells, seeds 42-44, gate clear: 0 RTOs and 0 freeze entries; all traces kept in `traces/`, table `data/t3_knees.csv`)
| config (1 us links) | queue / ECN | uncapped k p99 (B=128) | B_ow | B_fct | max FCT B=8 / B=128 (us) | random EVs at B=8 |
|---|---|---|---|---|---|---|
| baseline `base_h1024_p32` | 101 / 25 76 | 6 | 8 | 6 | 712.8 / 713.9 | 3.1% |
| `q394_ecn25` | 394 / 25 76 | 6 | 8 | 4 | 714.7 / 719.0 | 5.9% |
| `q394_ecn98` | 394 / 98 296 | **11** | **12** | **12** | 722.7 / 714.7 | 2.9% |
| `lat4_bdpq` (x4 latency) | 394 / 98 296 | 12 | 12 | 12 | 771.8 / 757.0 | 6.8% |

Predictions: (1) held. `q394_ecn98` on 1 us links reproduces the x4 result (p99 11, knees 12) without any latency change, so RTT is not what moved the knee. (2) held. The deeper queue with the baseline ECN thresholds keeps p99 6 and B_ow 8.
Reading: the two cells differ only in the ECN thresholds (queue size 394 in both), and only the one with higher thresholds has the larger k tail and knee. This is consistent with the ECN thresholds on the degraded links setting the k tail (a slow link marks later, so more unmarked EVs return, with more spread in return time), and the knee follows k; the queue size alone and RTT are ruled out as the cause in this setup. The mechanism between thresholds and k (return-time spread of unmarked EVs from the slow links) is still a hypothesis, no run measures it. Limits: one topology (1024 hosts, 32 paths, 5/95), 3 seeds, steady-state k p99 for the new cells not tabulated (`t3_steady_k.csv` has seed 42 only; the uncapped B=128 p99 is whole-run).
Bottom line for "why 8" (revised): raising the ECN thresholds changes the knee, but only through the mark rate (fewer marks, more valid EVs to store), which is expected and says little. It shows that a badly set threshold moves the knee; it does not explain the 8. With the baseline thresholds the uncapped valid-EV backlog k has p99 6 to 8 across radix, hosts, paths and tiers. What sets that tail at well-configured thresholds (spread of clean-ACK arrivals relative to the send clock) is open and under investigation in `investigate_8/`.
