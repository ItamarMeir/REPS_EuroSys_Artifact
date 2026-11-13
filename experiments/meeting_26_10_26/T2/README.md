# T2: 3-tier fat tree k=8, pod0 degradation (ToR->agg and agg->core)

T1 repeated on a 3-tier fat tree with k=8 (128 hosts, 16 paths): matched 200G constant-rate sender, REPS (`freezing`), 50% mean degradation with several splits, max FCT against the REPS buffer size B. The degradation scope is pod0, not ToR0, because a k=8 ToR has only 4 uplinks.
Two sub-experiments, one folder each: [`tor_agg/`](tor_agg/README.md) (A: the 16 ToR->agg uplinks of pod0) and [`agg_core/`](agg_core/README.md) (B: the 16 agg->core uplinks of pod0). The label T2 here replaces the earlier T2 scope of the meeting README (now `T2-old`, not started).

## Setup

- **Topology.** `htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_400g.topo` (existing file): 8 pods x (4 ToRs x 4 hosts), 4 aggs per pod, 16 cores, 400G links, 1 us per link, 16 SRv6 paths between pods. Pod0 = hosts 0-15, ToRs 0-3, aggs 0-3. Agg a, uplink l goes to core `a + 4 l`.
- **Traffic.** `connection_matrices/tornado_128n_16mb.cm`: host i sends 16 MiB to host i + 64 (mod 128), so every flow crosses the core (pod p <-> pod p+4). Matched rate `R = 0.5 * S * U / H = 200G` per host, constant-rate sender with no congestion control (`-sender_cc_algo constant -rate_const_gbps 200`), trimming on, `-disable_tor_ecn`, `-q 152 -ecn 38 114` (exp26 BDP formula for 3 tiers, as T3), `-paths 16`. Flags come from `meeting_23_10_26/M4/scripts/run_m4.py` `flags()` by key substitution (`scripts/run_t2.py`).
- **Degradation.** Mean ratio 0.5 on every group of 4 uplinks; the uneven pairs sit inside one switch: 2 uplinks at ratio r and 2 at 1 - r (even position r, odd position 1 - r). A: for each pod0 ToR, aggs 0..3 (even agg r). B: for each pod0 agg, uplinks l = 0..3 (even l r). Shapes: uniform 50/50, 25/75, 10/90, 5/95, plus a healthy matched reference (no degrade file). 1/99 is not run (it entered Freezing Mode in T1). For B "same ToR" was read as "same agg switch" (each agg has exactly 4 core uplinks).
  Uplinks only; the reverse links stay healthy. The ACKs of the pod4->pod0 flows leave through pod0's degraded uplinks, as in T1.
- **New simulator mechanism.** `-degrade_links_file` had no agg->core key. Added `agg_core <agg> <core> <ratio>` (extension `per-link-degrade-agg-core` of `[ADDED: per-link-degrade]` in `../MODIFICATIONS.md`, with its Verification subsection). Sub-experiment A uses only the existing `tor agg ratio` lines.
- **Grid.** B in {1, 2, 4, 8, 16, 32, 64, 128} (B = 5 and 6 added later, see the last section; 450 cells in all), seeds 42-46 (5 seeds, mean and 95% t-CI; first run with 42-44, then 45-46 added because the 3-seed CI at B=8 (up to 4.3 us) could not resolve the step from B=8 to B=16). 9 configs x 8 B x 5 seeds = 360 cells, 0 failures. One pass per cell with `-log_reps_events` for the 16 pod0 hosts and `-log_queue_stats`; gzip'd traces and stdout in `<sub>/traces/` (gitignored; the healthy reference cells are stored in both).
- **Run** (container `m23-dev`, no bind mounts): `scripts/make_configs.py` writes `configs/`; `scripts/setup_container.sh` copies inputs in; `python3 /t2work/run_t2.py --out /t2out --seeds 42 43 44` (then `45 46`); results copied out and split by sub-experiment; `scripts/aggregate_t2.py <sub>` and `../scripts/build_page_t2.py` (one page for both scopes). Checks of the new mechanism: `scripts/validate_agg_core.py`.

## Predictions (written in the plan before any cell ran)

1. A behaves like T1/T3: knee at 6-8, steady-state k p99 6-8.
2. B (the slow resource is shared by all 16 pod0 hosts, two hops from the sender): k tail and overwrites somewhat larger than A at the same shape, knee still 8 or 12. Low confidence.
3. Uniform 50/50: no B dependence beyond B <= 2 in both.
4. Gate (no RTO, no freeze entry): not predictable from T1 alone (2 of 4 uplinks slow per ToR is 50% of the paths, as in T1, but 16 paths instead of 32, 4 hosts per ToR, 3-tier RTT); report per shape.
5. p50 FCT about 700 us in every clear cell (the matched rate sets it).
Seen before the full grid ran: three smoke cells (A 5/95, B 5/95, healthy; B=8, seed 42): max FCT 718.9 / 718.6 / 704.6 us.

## Checks

- **Mechanism** (details in `../MODIFICATIONS.md`): flag-absent and ToR->agg-only runs byte-identical (flow-finish lines) old vs new binary, both clean builds; `agg_core` ratio 1.0 on all 16 links gives the healthy run's flow lines; bad lines (unconnected pair, out-of-range switch, ratio 0 or 5, missing field) exit with an error; T1 r005 B=8 seed 42 reproduces (1024 identical lines).
- **Per cell, all 360** (`config_proof` and `speed_proof` in `<sub>/data/t2_knees.csv`): 16 `Failure:` lines (equal to the degrade file's link lines) with 20/380, 100/300, 40/360 or 200/200 Gbps pairs as per shape, `distinct_paths=16`, 128 flows finished, no `enable on tor downlink 1`, trace not capped (50M rows), 0 reconstruction and add mismatches of k. Speed proof: the achieved Gbps of every scope link (data + header bytes over the run, from `-log_queue_stats`) stays at or below ratio x 400G (+0.5% for the window mismatch: `-log_queue_stats` counts bytes at service completion until the end of the simulation and the rate divides by the last flow's finish time; one cell, A 25/75 B=16 seed 44, reached +0.12%), and no trim occurs on a non-degraded scope link. Every config passes both for all 5 seeds and 8 B.
- **Gate.** 0 RTOs and 0 freeze entries in all 360 cells, including 5/95 in both sub-experiments.
- **Which hosts have the max FCT.** In all 320 degraded cells the slowest flow is a pod0 source (a ToR0..ToR3 host, src 0-15) sending to a host in pod4 (dst 64-79); never a flow into pod0. So `fct_max` (all 128 flows) equals the max over the pod0 sources in every cell, and the knees on the two are identical.
- **Analysis changes during the work.** The first speed-proof tolerance (+0.1%) flagged the 0.12% overshoot of one cell; the tolerance was then set to +0.5%. A pandas attribute clash (`row.shape` is the array shape, not the column) crashed the first aggregation; fixed with `row["shape"]`, no result was affected. The "window effect" reading of the 0.12% overshoot is consistent with the counting rule above, not tested separately.
- **Headlines.** The copied plot headlines name the scope (`-- matched / 3-tier pod0 ToR->agg / non-uniform 5/95`, `... / 3-tier pod0 agg->core / ...`) so pasted headlines from the two pages stay distinguishable.

## Results (5 seeds)

Max FCT over all flows (us, mean +- 95% t-CI). **A (ToR->agg, pod0):**

| shape | B=1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 |
|---|---|---|---|---|---|---|---|---|
| healthy | 704.7 +- 0.1 | 704.7 +- 0.1 | 704.6 +- 0.0 | 704.6 +- 0.0 | 704.6 +- 0.0 | 704.6 +- 0.0 | 704.6 +- 0.0 | 704.6 +- 0.0 |
| uniform 50/50 | 710.4 +- 1.6 | 710.7 +- 1.2 | 708.2 +- 0.5 | 707.5 +- 0.1 | 707.3 +- 0.2 | 707.3 +- 0.2 | 707.3 +- 0.2 | 707.3 +- 0.2 |
| 25/75 | 720.7 +- 1.2 | 714.8 +- 2.1 | 710.2 +- 1.3 | 707.9 +- 0.2 | 707.6 +- 0.4 | 707.7 +- 0.4 | 707.7 +- 0.4 | 707.7 +- 0.4 |
| 10/90 | 816.9 +- 3.3 | 738.1 +- 1.7 | 719.5 +- 2.8 | 714.7 +- 1.0 | 714.6 +- 1.0 | 714.6 +- 1.0 | 714.6 +- 1.0 | 714.6 +- 1.0 |
| 5/95 | 862.5 +- 3.1 | 767.3 +- 3.0 | 727.6 +- 2.0 | 718.3 +- 1.6 | 717.8 +- 1.0 | 717.8 +- 1.0 | 717.8 +- 1.0 | 717.8 +- 1.0 |

**B (agg->core, pod0):**

| shape | B=1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 |
|---|---|---|---|---|---|---|---|---|
| uniform 50/50 | 711.1 +- 0.7 | 710.6 +- 0.7 | 709.1 +- 0.8 | 707.7 +- 0.3 | 707.5 +- 0.2 | 707.5 +- 0.2 | 707.5 +- 0.2 | 707.5 +- 0.2 |
| 25/75 | 723.4 +- 1.1 | 715.2 +- 2.4 | 712.4 +- 1.2 | 708.8 +- 1.1 | 707.6 +- 1.0 | 707.6 +- 0.7 | 707.6 +- 0.7 | 707.6 +- 0.7 |
| 10/90 | 818.6 +- 2.0 | 740.5 +- 0.8 | 721.2 +- 2.1 | 715.3 +- 1.6 | 714.2 +- 0.4 | 714.2 +- 0.4 | 714.2 +- 0.4 | 714.2 +- 0.4 |
| 5/95 | 861.8 +- 2.5 | 767.4 +- 2.3 | 732.0 +- 2.7 | 718.4 +- 1.1 | 717.8 +- 0.8 | 717.8 +- 0.8 | 717.8 +- 0.8 | 717.8 +- 0.8 |

Knees (steady k = uncapped k at B=128 with the first and last 15% of each traced source's span dropped, 16 pod0 hosts; `B_fct` one-sided: smallest B from which every larger B is within the CI or 0.2% of B=128 or better; `B_ow`: smallest B with < 0.1% valid-EV overwrites; `B_ks99`: smallest B at or above the steady k p99). Per-sub tables with all columns: [`tor_agg/README.md`](tor_agg/README.md), [`agg_core/README.md`](agg_core/README.md).

| shape | A: steady k p99 | A: B_ow | A: B_fct | B: steady k p99 | B: B_ow | B: B_fct |
|---|---|---|---|---|---|---|
| uniform 50/50 | 7.0 | 8 | 4 | 8.2 | 16 | 5 (8 on the grid without B=5, 6) |
| 25/75 | 18.4 | 16 | 6 (8) | 17.6 | 16 | 8 |
| 10/90 | 11.2 | 16 | 7 (8) | 10.2 | 16 | 7 (8) |
| 5/95 | 9.6 | 8 | 6 (8) | 8.4 | 16 | 8 |

(`B_fct` on the 11-point grid {1, 2, 4, 5, 6, 7, 8, ...}; bracket = value on the original grid. The steady-k columns did not change; `B_ow` (first B below 0.1% overwrite) changed only for the healthy reference (8 -> 5).)

- **Finer grid (B = 5 and 6 added, 5 seeds; section at the end): the FCT knee is 6 for A 25/75 and 5/95, 7 for A 10/90 and B 10/90, 8 for B 25/75 and 5/95; uniform: 4 for A, 5 for B (B = 7 included; all moves within the CIs).** The rest of this bullet describes the original 8-point grid, where the knee read 8 for every non-uniform shape (uniform: 4 for A, 8 for B; B=4 is within 0.3% of B=128 there). Steps beyond B=8 are within the CI (largest: B 25/75, 708.8 +- 1.1 at B=8 vs 707.6 at B>=16, 0.17%). B=1 and B=2 cost up to +20% and +7% at 5/95, B=4 +1.4% to +2.0%, as in T1 (T1 r005: 848.9 / 755.8 / 723.1 / 712.8 us at B=1, 2, 4, 8). The two scopes give the same curves within about 1 us for B >= 8; at B=4 the agg->core curve is higher by 0.9 to 4.4 us (5/95: 732.0 +- 2.7 vs 727.6 +- 2.0; 25/75: 712.4 vs 710.2).
- **The steady-state k tail is above 8 for all non-uniform shapes** (p99 9.6 to 18.4 over the 16 pod0 hosts) and grows as the shape gets milder from 5/95 to 25/75, then is small at uniform. B_ks99 is 16 or 32, yet FCT does not need it: B_fct is 8. T3 found the same gap between the FCT knee and the k tail; why overwrites beyond B=8 cost so little FCT is not shown here.
- **k tail against T1 and T3 on matched host subsets** (`scripts/steady_k_compare.py`, `data/steady_k_compare.csv`, same steady-k definition, B=128): T2 A hosts 0-3 (ToR0) p99 17.4 / 10.0 / 9.0 at 25/75, 10/90, 5/95 (all 16 pod0 hosts: 18.4 / 11.2 / 9.6, so the host subset moves p99 by at most 1.0); T1 hosts 0-7 of ToR0 (2-tier, 1024 hosts): 12.0 / 9.0 / 6.0; T3 `t3_h128_p16` (same topology, tornado, rate and q/ECN, only ToR0 degraded 5/95), hosts 0-3: 8.0, 9.0, 6.0 in seeds 42-44 (mean 7.7). So the tail is larger than in T1 at 25/75 (+5.4) and 10/90 (+1), and at 5/95 (+3), but the same-topology T3 cell at 5/95 sits within its seed spread of T2 A (9.0, 5 seeds). Which of 3 tiers, 128 hosts with 4 uplinks per ToR, or degrading all four pod0 ToRs instead of one causes the larger tail is not isolated.
- **Overwrites at B=8 are larger in B than in A for every shape** (uniform 0.142 +- 0.059 vs 0.008 +- 0.008; 25/75 0.396 +- 0.074 vs 0.219 +- 0.036; 10/90 0.282 +- 0.032 vs 0.103 +- 0.006; 5/95 0.172 +- 0.079 vs 0.054 +- 0.021 %), and random EV draws too (2.97 vs 2.32% at 5/95). This does not show up in max FCT.
- **Max FCT floor.** At B >= 16 the FCT is 3-4 us above the 2-tier T1 values for the same shapes (717.8 vs 713.9 at 5/95; p50 704.4 vs 700.2): the extra 3-tier RTT, not the buffer.

### Predictions against outcomes

1. **Partly missed.** Knee 8 for the non-uniform shapes (held, 4 for uniform A), but steady k p99 is 9.6, 11.2 and 18.4 (hosts 0-3: 9.0, 10.0, 17.4), not 6-8. It follows the T1 trend (steady k p99 on ToR0 hosts 0-7: 6.0, 9.0, 12.0 for 5/95, 10/90, 25/75) at larger values; the cause of the larger values is not isolated (see above). The knee did not follow the tail.
2. **Held for overwrites and random draws, not for k or the knee.** Overwrites larger in B for all four shapes (CIs above); steady k p99 not systematically larger (B 8.2 / 17.6 / 10.2 / 8.4 vs A 7.0 / 18.4 / 11.2 / 9.6); knee 8 in both.
3. **Held.** Uniform: B=1 and B=2 +0.4% to +0.5%, B=4 +0.1% (A) / +0.2% (B) over B=128.
4. **No gate failure anywhere** (0 RTOs, 0 freeze entries in 360 cells); 5/95 stays clear in both scopes.
5. **Held within 0.7%.** p50 FCT 704.43-704.47 us in every cell (all B, shapes, both scopes), healthy included (the 3-tier RTT adds the 4 us; the rate sets the rest).

## Open and limits

- Why the steady k tail is larger than in T1 (not isolated between tiers, host/uplink counts and pod-wide scope, see above) and why it is largest at 25/75 is open (consistent with, not shown: ECN-marked ACKs are most frequent at 25/75, 1032 (A) and 1229 (B) per run at B=8 against 387 (A) and 627 (B) at 5/95).
- k, overwrites and ACKs per window come from the 16 traced pod0 hosts only; the other 112 hosts are not traced. Max FCT, p99 and counts are over all 128 flows.
- Only 16 flows start in pod0, so max FCT rests on few flows; the CI above is over 5 seeds.
- 1/99 and 3-tier degradation of other links (core->agg, agg->ToR) are not run.

## Status

Runs, aggregation and the interactive page (`plots/interactive.html`, one page for both scopes, T1 layout: gate table, overlays, per-shape panels, ToR->agg left and agg->core right; gitignored) built and checked headless (53 plots, 53 copy buttons, no exceptions). Nothing committed.


## B = 5 and 6 added (predictions, written before the runs)
Added B in {5, 6} to all 9 configs (A: uniform, 25/75, 10/90, 5/95, healthy; B: uniform, 25/75, 10/90, 5/95, healthy) with seeds 42-46: 90 cells, same runner and flags (`run_t2.py --bs 5 6 --seeds 42 43 44 45 46`). `B_fct` is the rule of the knee table above.
Predictions, by interpolation between the stored B=4 and B=8 means (B=128 mean in brackets; the tolerance is max of the two CIs and 0.2% = about 1.4 us):
1. A 5/95: B=4 727.6, B=8 718.3 (717.8). B=5 about 722 (outside), B=6 about 719.5 (edge). Predicted `B_fct` 6 (8 if B=6 lands above 719.4).
2. A 10/90: B=4 719.5, B=8 714.7 (714.6): B=5 about 717 (outside), B=6 about 715.3 (inside). `B_fct` 6.
3. A 25/75: B=4 710.2, B=8 707.9 (707.7): B=5 about 709 (edge), B=6 about 708.3 (inside). `B_fct` 5 or 6.
4. B (agg->core) behaves like A with the B=4 value 1 to 4 us higher: 5/95 B=5 about 724, B=6 about 720; `B_fct` 6 or 8 for 5/95 and 10/90, 6 for 25/75.
5. Uniform 50/50: A stays at 4 (already within tolerance); B (agg->core), whose B=4 value is 709.1 against 707.5, goes from 8 to 5 or 6. Healthy: flat, `B_fct` 1.
6. `pct_random` at B=5 and 6 lies strictly between its B=4 and B=8 means in every degraded config (5/95 A: 7.7% at B=4, 2.3% at B=8, so about 5% at B=5 and 3.5% at B=6).
7. Gate stays clear (0 RTOs, 0 freeze entries), all proofs (config, speed) pass as for the other B.

### Outcome (90 cells ran, 0 failures)
All 90 cells: gate clear (0 RTOs, 0 freeze entries), config_proof and speed_proof pass (16 Failure lines, 16 distinct paths, 128 flows, no `enable on tor downlink 1`, trace not capped, 0 reconstruction mismatches). Max FCT (us, mean +- 95% t-CI over 5 seeds):

| config | B=4 | B=5 | B=6 | B=8 | B=128 | B_fct (old grid -> new) | B_fct (p99) new |
|---|---|---|---|---|---|---|---|
| A uniform | 708.2 +- 0.5 | 707.7 +- 0.2 | 707.5 +- 0.1 | 707.5 +- 0.1 | 707.3 +- 0.2 | 4 -> 4 | 4 |
| A 25/75 | 710.2 +- 1.3 | 710.2 +- 0.9 | 708.3 +- 0.8 | 707.9 +- 0.2 | 707.7 +- 0.4 | 8 -> **6** | 6 |
| A 10/90 | 719.5 +- 2.8 | 717.4 +- 2.4 | 716.2 +- 1.1 | 714.7 +- 1.0 | 714.6 +- 1.0 | 8 -> 8 | 6 |
| A 5/95 | 727.6 +- 2.0 | 723.3 +- 3.3 | 719.0 +- 1.7 | 718.3 +- 1.6 | 717.8 +- 1.0 | 8 -> **6** | 6 |
| B uniform | 709.1 +- 0.8 | 708.5 +- 0.6 | 708.1 +- 0.2 | 707.7 +- 0.3 | 707.5 +- 0.2 | 8 -> **5** | 5 |
| B 25/75 | 712.4 +- 1.2 | 711.1 +- 1.3 | 710.4 +- 0.7 | 708.8 +- 1.1 | 707.6 +- 0.7 | 8 -> 8 | 8 |
| B 10/90 | 721.2 +- 2.1 | 718.3 +- 1.8 | 717.6 +- 1.9 | 715.3 +- 1.6 | 714.2 +- 0.4 | 8 -> 8 | 8 |
| B 5/95 | 732.0 +- 2.7 | 727.3 +- 2.8 | 722.2 +- 2.8 | 718.4 +- 1.1 | 717.8 +- 0.8 | 8 -> 8 | 8 |

Random EV draws (post-warmup draws; mean of 5 seeds; "on degraded" = random draws whose EV maps to a path crossing a slow link, degraded set parsed from the Failure lines, `scripts/add_random_stats.py`; columns `n_random_post_mean`, `n_random_degraded_mean`, `pct_random_degraded_mean` in `<sub>/data/t2_summary.csv`):

| config | % random B=4 / 5 / 6 / 8 | n random B=4 / 5 / 6 / 8 | n random on degraded B=4 / 5 / 6 / 8 |
|---|---|---|---|
| A 5/95 | 7.73 / 5.10 / 3.41 / 2.32 | 5083 / 3341 / 2233 / 1519 | 2534 / 1661 / 1118 / 761 |
| A 10/90 | 7.34 / 4.81 / 3.31 / 2.17 | 4781 / 3130 / 2154 / 1411 | 2389 / 1567 / 1075 / 708 |
| A 25/75 | 6.82 / 4.00 / 2.39 / 2.19 | 4403 / 2583 / 1546 / 1411 | 2227 / 1283 / 768 / 698 |
| B 5/95 | 9.48 / 6.74 / 4.88 / 2.97 | 6262 / 4427 / 3193 / 1943 | 3116 / 2219 / 1595 / 979 |

The random draws land on the degraded set 49.3 to 50.6% of the time in every degraded cell, as expected for uniform draws over 8 of 16 slow paths: the degraded share of random draws is the design value, not a result. That does not isolate why random draws cost FCT: the rate is matched (the load is critical) and unevenness raises the cost per draw (the T1 uniform control r = 0.5 has a knee at 6 although no path is degraded relative to another; T2 uniform 50/50 and healthy also draw randomly, at a smaller or no FCT cost).

Predictions against outcomes:
1. A 5/95: B=5 723.3 (predicted about 722), B=6 719.0 (about 719.5), `B_fct` 6: **held**.
2. A 10/90: B=5 717.4 (about 717), B=6 716.2 (about 715.3, 0.9 above); the tolerance is 1.43 us above B=128, 716.2 is 0.2 us outside it, so `B_fct` stays 8 (6 on the p99 knee): **missed by 0.2 us on the knee, a noise-level miss**.
3. A 25/75: B=5 710.2 (about 709), B=6 708.3, `B_fct` 6: **held** (predicted 5 or 6).
4. B: 5/95 B=5 727.3 (about 724), B=6 722.2 (about 720), both 2 to 3 us higher than predicted; `B_fct` 8 (predicted 6 or 8, held); 10/90 8 (held); 25/75 predicted 6, got 8 (B=6 is 710.4 against 707.6 + 1.4; **missed**).
5. Uniform: A stays 4, B 8 -> 5, healthy 1: **held**.
6. `pct_random` strictly between its B=4 and B=8 means in every degraded config: **held** (A 5/95: 5.1 and 3.4 against 7.7 and 2.3, close to the predicted 5 and 3.5).
7. Gate and proofs: **held**.

Reading: the knee moves from 8 to 6 only for A 25/75 and A 5/95 and from 8 to 5 for B uniform. The steps involved are 0.5 to 1.4 us at B=6 against CIs of 0.8 to 2.8 us at 5 seeds, so the move of the FCT knee is within noise: B=6 (and 5 in 10/90) differ from B=8 by about the width of one CI, and the one-sided rule flips on a few tenths of a us (A 10/90 at 0.2 us). What the finer grid does show, outside noise, is that the cost is a smooth decay from B=4 to B=8 (e.g. A 5/95: 727.6, 723.3, 719.0, 718.3) with no sharp knee: B=5 is still 5.5 us (A) and 9.5 us (B) above B=128 at 5/95, and agg->core sits 1 to 4 us above ToR->agg for B <= 6 (5/95: 4.0 at B=5, 3.2 at B=6, 0.1 at B=8). Overwrites follow (A 5/95: 3.11, 1.56, 0.65, 0.05 % at B=4, 5, 6, 8).

## Page plan: random-EV draws next to max FCT (interactive page)
Question: does the share of random EV draws (overwrites turned into uniform draws) flatten at the same B as max FCT? Primary metric stays max FCT (first plot). Plots: (1) max FCT vs B with knee; (2) random-draw metrics vs B on the same axis (share, count, count on degraded paths, overwrites; max-FCT knees as numbered marks); (3) max-FCT excess over B=128 vs random draws on degraded paths, with Pearson/Spearman (correlational only); then the existing mechanism plots and the table.
Predictions (before the plots): the random-share knee B_rand sits at the max-FCT knee (5 to 8); the correlation is high but driven by B (both fall with B), so it is not read as cause. Built by `scripts/build_page_*.py` with `scripts/page_random.py`.


## B = 7 added (predictions, written before the runs)
Added B = 7 to all 9 configs, seeds 42-46 (45 cells, `run_t2.py --bs 7`). B = 7 lies between the B = 6 and B = 8 means; the knee rule is the one-sided `B_fct` above. Predictions:
1. Max FCT at B = 7 is between B = 6 and B = 8 in every degraded config (A 5/95 about 718.6, A 10/90 about 715.4, A 25/75 about 708.0, B 5/95 about 720, B 10/90 about 716.4, B 25/75 about 709.6), and `pct_random` at B = 7 between its B = 6 and B = 8 values (A 5/95 about 2.8%).
2. Knees: A 10/90 moves from 8 to 7 (its B = 6 is 0.2 us outside the tolerance, B = 7 about 0.7 us above B = 128 is inside) - this is inside the CI and not a finding; A 25/75 and A 5/95 stay at 6, A uniform at 4, B uniform at 5; B 25/75 and B 10/90 stay at 8 (B = 7 about 1.8 to 2.2 us above B = 128, outside the 1.4 to 1.6 tolerance); B 5/95 is borderline, 7 or 8.
3. Gate clear and all proofs pass in the 45 cells.

### Outcome B = 7 (45 cells ran, 0 failures)
Gate clear and all proofs (config, speed) pass in all 45 cells. Max FCT in us (mean +- 95% CI, 5 seeds); `B_fct` on the 11-point grid:

| config | B=4 | B=5 | B=6 | B=7 | B=8 | B=128 | B_fct (before B=7 -> now) |
|---|---|---|---|---|---|---|---|
| A uniform | 708.2 +- 0.5 | 707.7 +- 0.2 | 707.5 +- 0.1 | 707.4 +- 0.2 | 707.5 +- 0.1 | 707.3 +- 0.2 | 4 -> 4 |
| A 25/75 | 710.2 +- 1.3 | 710.2 +- 0.9 | 708.3 +- 0.8 | 707.8 +- 0.8 | 707.9 +- 0.2 | 707.7 +- 0.4 | 6 -> 6 |
| A 10/90 | 719.5 +- 2.8 | 717.4 +- 2.4 | 716.2 +- 1.1 | 716.1 +- 1.8 | 714.7 +- 1.0 | 714.6 +- 1.0 | 8 -> **7** |
| A 5/95 | 727.6 +- 2.0 | 723.3 +- 3.3 | 719.0 +- 1.7 | 719.4 +- 2.5 | 718.3 +- 1.6 | 717.8 +- 1.0 | 6 -> 6 |
| B uniform | 709.1 +- 0.8 | 708.5 +- 0.6 | 708.1 +- 0.2 | 707.8 +- 0.4 | 707.7 +- 0.3 | 707.5 +- 0.2 | 5 -> 5 |
| B 25/75 | 712.4 +- 1.2 | 711.1 +- 1.3 | 710.4 +- 0.7 | 709.5 +- 0.3 | 708.8 +- 1.1 | 707.6 +- 0.7 | 8 -> 8 |
| B 10/90 | 721.2 +- 2.1 | 718.3 +- 1.8 | 717.6 +- 1.9 | 716.1 +- 1.9 | 715.3 +- 1.6 | 714.2 +- 0.4 | 8 -> **7** |
| B 5/95 | 732.0 +- 2.7 | 727.3 +- 2.8 | 722.2 +- 2.8 | 720.8 +- 3.0 | 718.4 +- 1.1 | 717.8 +- 0.8 | 8 -> 8 |

`pct_random` at B = 6 / 7 / 8: A 5/95 3.41 / 2.60 / 2.32, A 10/90 3.31 / 2.45 / 2.17, A 25/75 2.39 / 2.14 / 2.19, B 5/95 4.88 / 3.65 / 2.97, B 10/90 4.92 / 3.45 / 2.49, B 25/75 5.11 / 3.51 / 2.74 (per-config tables with absolute counts and random draws on degraded paths in the sub-READMEs).

Predictions against outcomes: (1) max FCT between B = 6 and B = 8: held in 4 of 6 non-uniform configs (A 10/90 716.1, B 25/75, B 10/90, B 5/95); A 5/95 B = 7 (719.4) is above both B = 6 (719.0) and B = 8 (718.3), and A 25/75 (707.8) is under both, both inside the CIs (noise); levels within 1 us of the predicted values except A 5/95 (0.8 above). `pct_random` between B = 6 and B = 8 held except A 25/75, whose B = 8 value (2.19) is above B = 7 (2.14); the difference is 0.05 points. (2) Knees: A 10/90 -> 7 **held**; A 25/75, A 5/95, uniform A and B unchanged **held**; B 25/75 stays 8 and B 5/95 stays 8 **held**; B 10/90 was predicted 8 and moved to 7 (B = 7 is 1.9 us above B = 128 against a tolerance of 1.9 from its own CI): **missed, inside noise**. (3) Gate and proofs **held**.
Reading: B = 7 changes two `B_fct` values by one step each (8 -> 7 for A 10/90 and B 10/90), both on tolerance edges of 0.2 to 0.4 us; the grid is now too fine for the 5-seed CIs (1 to 3 us) to separate B = 6, 7 and 8 in the 5/95 and 10/90 shapes. The decay from B = 4 to B = 8 stays smooth with the plateau reached around B = 6 to 8.

### Paired knee (`scripts/knee_paired.py` -> `<sub>/data/t2_paired_excess.csv`, `t2_knees_paired.csv`) and B_rand0
Rule as in T1/README.md (per-seed excess over the same seed's B=128; ok if mean <= max(0.2% of B=128, 1.96 SE of the paired differences); smallest B from which all larger B are ok). The unpaired rule is the `B_fct` of the tables above (`plot_common.knee_fct`). B_rand0 = smallest B from which the paired extra random draws over B=128 stay inside their 95% CI of zero.

| config | B_fct unpaired | B_fct paired | B_rand0 (all draws) | B_rand (share within 10%) |
|---|---|---|---|---|
| A healthy | 1 | 1 | 6 | 6 |
| A uniform | 4 | 4 | 7 | 7 |
| A 25/75 | 6 | 6 | 7 | 7 |
| A 10/90 | 7 | 7 | 16 | 8 |
| A 5/95 | 6 | **8** | 8 | 8 |
| B healthy | 1 | 1 | 6 | 6 |
| B uniform | 5 | 5 | 8 | 8 |
| B 25/75 | 8 | 8 | 16 | 8 |
| B 10/90 | 7 | **8** | 16 | 16 |
| B 5/95 | 8 | 8 | 16 | 16 |

The rules disagree for A 5/95 (6 unpaired, 8 paired) and B 10/90 (7 vs 8); all other configs agree. B_rand0 equals the paired B_fct only for A 5/95 (8) and is later for the other five non-uniform configs (7 vs 6, 16 vs 7, 16 vs 8 three times), so "random draws flatten later than max FCT" depends on the tolerance. Wording: random draws cost FCT because the load is critical (matched rate) and unevenness raises the cost per draw; claims that the cost comes from landing on degraded paths are withdrawn.
