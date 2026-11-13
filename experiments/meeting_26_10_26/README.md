# Meeting 2026-10-26: REPS buffer size results and NSCC behavior, repo missions

Source meeting: 2026-10-26 (Itamar Meir, Chen Avin, Gabriel Skalosub), topic "Load Balancing: REPS Buffer Size & NSCC Behavior". Zoom AI summary and full Hebrew transcript: the `.docx` in this directory. This README keeps only what turns into work in this repo (simulations, analysis, simulator mechanisms). Administrative items (next meeting time, who sends which papers, the literature scan) are left out. Previous meeting: [`../meeting_23_10_26/`](../meeting_23_10_26/README.md) (missions M1 to M11); the plots discussed are [`../meeting_23_10_26/M4/plots/interactive.html`](../meeting_23_10_26/M4/plots/interactive.html) (gitignored, published via the thesis repo on request).

Vocabulary (B, k, valid EV, random draw, Freezing Mode) is as defined in the 2026-10-06 and 2026-10-23 READMEs. Mission IDs here use the prefix **T** so they do not clash with M1 to M11.

## What the meeting decided (repo-relevant)

- **B = 8 is enough at the matched rate.** In under and matched, buffer size barely changes FCT; only non-uniform degradation shows a small, monotone effect. Beyond 8 the buffer adds nothing, probably because of path length and RTT (open question T3).
- **NSCC is not part of the current experiments.** The M4 grid runs a constant-rate sender with no congestion control, so NSCC questions are handled separately (T6).
- **Next focus: non-uniform degradation**, to find conditions where B does matter (T1, T2, T4).

## Meeting claims checked against our data

Numbers from `../meeting_23_10_26/M4/data/m4_summary.csv` (3 seeds; overwrites are counted for the 8 traced ToR0 hosts only) unless stated.

| Claim in the meeting | What our data shows |
|---|---|
| Matched: max FCT nearly identical across B (702 to 709 us); B = 8 absorbs the worst case | matched/non-uniform max FCT: 715.8 us (B=1), 709.1 (B=2), 703.4 (B=8), 702.9 (B=64). matched/uniform50: 707.1, 709.0, 702.5, 702.3. Consistent. |
| Overwrites of valid EVs (a clean ACK arriving at a full buffer) are about a tenth of a percent (Chen's rough estimate: 8,000 of 10 million packets, about 0.08%) | At B=8: 0.13% (non-uniform), 0.012% (uniform50), 0 (healthy). The same order for non-uniform, lower elsewhere. At B=1 and B=2 it is 10 to 29%, so the proxy only becomes small at B=8. |
| Over (twice the capacity): almost no ACK carries a valid EV, nearly all draws are random | over/uniform50 and over/non-uniform: 99.3 to 99.7% random draws at every B; over/healthy: 0.8% at B=8. Consistent. |
| High k (4 to 7) comes from ACK bursts: 2 ACKs in a window between two sends, twice in a row, raise k to 4, and it only falls in a window with 0 ACKs | Consistent with [`../meeting_23_10_26/M4/investigate_k/README.md`](../meeting_23_10_26/M4/investigate_k/README.md): k is the running sum of (clean ACKs - 1) per send window. In matched, 2 data arrivals land in one send window in about 28% of windows (replay with the return delay held constant; real ACK counts: 2 ACKs in 20%, 0 ACKs in 36%) because the receiver's last link is idle; over/healthy has almost none. See the sections "Per-packet attribution" and "Anatomy of a 4-to-6-ACK send window". |
| Non-uniform: more valid EVs discarded goes with higher max FCT; uniform: no such link (Itamar). Chen: it is only a proxy, show it in FCT | Open: at B=8 the effect is within noise (max FCT 703.4 vs 702.9 at B=64). T1 looks for cells where overwrites at B=8 are far above 0.13% and FCT follows. |
| NSCC "should just adapt to 200G; 50% is not the relevant number" (Chen); Itamar asked for time | Already measured in `../meeting_06_10_26/C1` (seed 42, `-target_q_delay 4.17`): degraded NSCC holds cwnd at a median 81 packets against the 153 cap (about 53%, so it does adapt to roughly half capacity), with 56% of ACKs ECN-marked against 0.1% healthy. The "50%" is the marking rate at NSCC's operating point, not the capacity. The 56% vs the paper's about 50% is not explained; one untested hypothesis is that 4.17 us corresponds to about 104 KB, which equals `ecn_low` on a 200G uplink. |

## Missions

| ID | Type | Mission | Depends on |
|---|---|---|---|
| T1 | Experiment (main) | Extreme non-uniform degradation without entering Freezing Mode; does B keep mattering? | none |
| T2 | Experiment | 3-tier fat tree k=8 (16 paths): T1 shapes with the degradation on pod0 uplinks, A = ToR->agg, B = agg->core | T1; new `agg_core` degrade key for B |
| T2-old | Experiment / build | (earlier scope of the label T2, not started) Other failure shapes: static 0/1, dynamic per-link 50%, and a screening grid of about 10 distortion directions | T1 (screening metric), new mechanism for dynamic |
| T3 | Experiment | Where does "8" come from: RTT, path length, path count, ACK-arrival variance? | none |
| T4 | Experiment / analysis | Adversarial scenario where very large B helps; analytic bound on useful B | T2-old (dynamic), investigate_k results |
| T5 | Experiment | Does Freezing Mode change the buffer-size picture? | none |
| T6 | Diagnose | Where does NSCC's ECN marking come from, and why about 56%? | none |
| T7 | Exploratory (build) | ToR-side immediate rate cap for senders to the same destination ToR | add-mechanism |

Suggested order: T1 first (Chen: clear the buffer table before new ideas), T3 and T5 in parallel, T2 and T4 after T1 shows or fails to show an effect, T6 then T7 last.

Rules for every mission (from the root and `experiments/CLAUDE.md`): build and run only via Docker (container `m23-dev`); `-disable_tor_ecn` whenever `-sender_cc_only` is set; derive flags from `../meeting_23_10_26/M4/scripts/run_m4.py` `flags()`, never retype them; one pass per run with `-log_reps_events` and the other logs, keep gzip'd traces, never delete; write predictions before looking at results and report misses; at least 3 seeds; check theoretical twins and prove the configuration from the output; any change under `htsim/sim/` goes through the `add-mechanism` and `validate-mechanism` skills (banner, `MODIFICATIONS.md` row, architecture doc, flag-absent output byte-identical).

## T1. Extreme non-uniform degradation without Freezing Mode

Meeting: Itamar proposed near 0% and 100% degradation without entering Freezing Mode, to see whether B keeps mattering; Chen: start from the same configuration and go as low as possible (10% or 1%) without Freezing Mode, and check whether the knee at 8 grows.

- **Config.** Pairs (r, 1 - r) keep total ToR0 uplink capacity at 50%, as the current 25/75 model does: r in {0.25 (current), 0.1, 0.05, 0.01} on half of the uplinks, 1 - r on the other half. Use `-degrade_links_file` (lines `tor agg ratio`, ratio in (0, 4], ToR uplinks only, 2-tier fat tree; see `../MODIFICATIONS.md` section per-link-degrade). Matched rate 200G, B in {1, 2, 4, 8, 16, 32, 64} plus at least one larger value. Reuse `run_m4.py` and add the failure files next to `degrade_nonuniform_25_75.txt`.
- **Gate (Freezing Mode).** Freezing Mode is entered when a retransmission timer expires (`rtxTimerExpired` in `htsim/sim/uec.cpp`). Reject, or report separately, any cell with a FREEZE event in `-log_reps_events` or a nonzero RTO count. Record the lowest r that stays clear of it.
- **Metrics.** Max and p99 FCT per B, `pct_random`, `pct_overwrite` and `ev_overwrites` at B=8 (0.13% now), k distribution. The meeting's point: overwrites are only a proxy, so look for cells where overwrites at B=8 are far above 0.13% and see whether FCT follows.
- **Result.** Done: see [`T3/README.md`](T3/README.md). The knee stays at 8 across radix, hosts, paths and tiers; it moved to 12 only with 4x link latency and queue/ECN thresholds scaled to the BDP.
- **Prediction (to fill before running).** Suggested starting guess: the smaller r, the larger the FCT gap between small and large B, and the B at which FCT flattens moves above 8; the grid shows where, if anywhere.
- **Done when.** A table of FCT and overwrites against (r, B), with the Freezing Mode gate result per cell, 3 or more seeds.
- **Status (done, 3 seeds):** [`T1/README.md`](T1/README.md). Gate-clear r = 0.25, 0.10, 0.05: knee at B = 8 on the original grid, 5 to 6 with B = 5, 6 added (within the 3-seed CIs), overwrites at B=8 stay at or below 0.13%, but the cost of B = 1 or 2 grows as r falls (B=1 minus B=8 max FCT 12, 97, 136 us). r = 0.01 enters Freezing Mode (RTOs). Lowest clear r: 0.05.

## T2. 3-tier fat tree k=8, pod0 degradation (ToR->agg and agg->core)

See [`T2/README.md`](T2/README.md) (sub-experiments in `T2/tor_agg/` and `T2/agg_core/`). **Result.** Done (5 seeds, 450 cells incl. B = 5, 6, gate clear everywhere): the FCT knee is at B=8 on the original grid for every non-uniform shape (25/75, 10/90, 5/95) and reads 6 for ToR->agg 25/75 and 5/95 once B = 5, 6 are added (still 8 elsewhere, within noise), when the degradation is on the pod0 ToR->agg uplinks and when it is on the pod0 agg->core uplinks (uniform: 4 and 8); the steady-state k p99 is above 8 (9.6 to 18.4, larger than T1's 6 to 12 on matched hosts; cause not isolated) but FCT does not follow it. Overwrites at B=8 are larger for agg->core. The slowest flow is always a pod0 source sending to pod4. New simulator key `agg_core` in `-degrade_links_file`.

## T2-old. Other failure shapes, and a screening grid

(Earlier scope of the label T2; the label T2 is now the 3-tier pod0 experiment above. Not started. T4 refers to the dynamic model of this section.)

- **Static 0 or 1 (Chen's static model).** Links either full or dead. Itamar's objection: dead links trigger an RTO and Freezing Mode, which is a different mechanism. Use it as a Freezing Mode control that feeds T5, not as a degradation model.
- **Dynamic model.** Each link, at each time scale, is degraded or full with probability 50%, changing during the run, so that the ACKs must be used in time. Existing hooks only cover one fail-and-recover event (`-timed_window` with `-timed_fail_tor_uplinks` / `-timed_fail_tor_downlinks`). A periodic per-link flip is a new mechanism: first check whether a queue's service rate can change at runtime (`FatTreeTopology::alloc_queue` sets it at construction), then follow `add-mechanism` and `validate-mechanism`. Validation idea: with a flip probability of 0 or 1 it must reproduce the static per-link-degrade run byte for byte.
- **Screening grid (Itamar).** Define about 10 distortion directions of the uniformity (shape of the ratio distribution, which links, time scale), keep only those that show a difference. Screening metric: the gap in max or p99 FCT between B=2 and B=64, plus `pct_overwrite` at B=8. Screen with one seed, confirm the kept directions with 3 to 5 seeds.

## T3. Origin of "8"

Meeting: Chen thinks 8 comes from path length and RTT, through the variance of the ACK arrival rate (longer paths mean more congestion and more variance), not from the radix; Itamar suggests the variance of arrivals or the distribution of the degradation. Expansion test: Chen proposed a network twice the size (a longer path, a larger variance), perhaps one more tier.

- **(a) Tiers.** Run the same cells on a 3-tier fat tree (`-tiers 3`, `htsim/sim/datacenter/topologies/reps/fat_tree_1024_1os_3t_400g.topo`) against the 2-tier topology used now. Check that the degradation file and the rate carry over (the per-link degrade works on 2-tier; for 3-tier, check how to degrade first).
- **(b) Split path length from path count.** Vary `-paths` (16, 32, 64) and `-hop_latency` separately.
- **(c) Larger network.** Only if a topology file and a tornado matrix for it exist; none for 2048 hosts exists now (`connection_matrices/gen_tornado.py` makes the matrix; the topology file would be new).
- **Analysis.** For each variant: the knee of B (smallest B where FCT is flat and overwrites about 0) against the spread of ACKs per send window. Reuse `../meeting_23_10_26/M4/scripts/reaggregate_ack_windows.py` and the `investigate_k` scripts (`burst_trace.py`, `replay_pkt_cf.py`).
- **Prediction (to fill before running).** If Chen is right, a longer path moves the knee above 8; if the degradation distribution drives it, changing tiers alone will not.

## T4. Adversarial scenario and analytic bound

Meeting: show a scenario where FCT keeps falling even up to B = 2048 (it need not be realistic), and above all an upper bound of the form "networks with properties a to d need no B larger than X".

- **Scenario search.** The overwrite counts at B=8 are near 0 in every current cell, so the scenario needs ACK bursts far larger than the current ones: for example a link recovering after a long degradation (needs the dynamic model from T2), or a step in the send rate. Run B up to 2048 on such a scenario.
- **Bound.** In `investigate_k` the k replay is exact (0 mismatches), and k equals the capped drawdown of the in-flight count from its running maximum. So the useful B is the tail of the in-flight drawdown over one RTT. From the measured drawdown distribution, derive the smallest B with a given overwrite probability and compare it with the observed knee of 8. State the properties it depends on (send window, ACK spread, RTT).

## T5. Does Freezing Mode change the picture?

Meeting (pending): whether Freezing Mode matters depends on how many valid ACKs die. In the simulation one fully dead path (RTO) is enough to enter Freezing Mode. Chen: with one dead path of about 100, the stale EVs clear out and nothing changes; many paths must die for an effect. Possible motivation for small B: it drains stale EVs faster in Freezing Mode (Itamar is not sure that is the conclusion).

- **Config.** Number of dead ToR0 uplinks in {1, 2, 4, 8, 16} of 32 (our `-paths 32`; the meeting said about 100 paths), via `-timed_fail_tor_uplinks <tor> <count>` with `-timed_window`, or `-fail_pipes_file` (3-tier only). `-exit_freeze 200000000` (no thaw during the run), B in {1 to 64}.
- **Metrics.** FCT, time spent in frozen mode, number of FREEZE and UNFREEZE events, share of stale EVs among draws (from `-log_reps_events`).
- **Prediction (to fill before running).** Chen's: one dead path of 32 has little effect; Itamar's: a small B recovers faster.

## T6. Where does NSCC's ECN marking come from?

Meeting (open question): why does NSCC not settle at 50% of capacity? Chen: if ECN were marked at the tail of the degraded link, the marking rate would be much higher than 50%; perhaps it is marked in another layer (the spine). The meeting also stated that the marks come from the ToR downlinks queues, on all ports; this is not yet checked.

- **Existing evidence.** C1 measured 56.4% marked ACKs, per host 51 to 58%, with the same share at B=256 (seed 42).
- **Where the marks are.** `-log_queue_stats` reports trims, drops and max queue per queue but no ECN mark counter; the ACK-level `ecn` from `-log_reps_events` says only that a mark happened, not where. First use the queue occupancy time series next to the thresholds (`-ecn 25 76` on `-q 101`); if that is not enough, add a small per-queue mark counter (add-mechanism; flag-absent output byte-identical).
- **Target-delay hypothesis.** Sweep `-target_q_delay` around 4.17 us and check whether the marked share follows the point where the target equals `ecn_low` on a 200G uplink (about 104 KB).
- **Done when.** A per-layer table of mark counts, and the marked share against `-target_q_delay`.

## T7. Exploratory: ToR-side immediate rate cap

Meeting: Ofan's switch-side load balancer (per-destination-ToR round-robin pointers, separate for ACKs and data) gave Itamar a new idea. A ToR that sees two senders to the same destination ToR caps their send rate at once (for example half the capacity, or a formula by flow size, mice vs elephants) instead of waiting an RTT for feedback. It is an upper bound only; congestion control keeps acting below it. It could extend to the aggregation layer. Chen: simple and nice, unclear whether it was done before.

- **Already in the repo.** The Ofan pointer scheme is implemented (`-strat ofan`, [`../OFAN_ARCHITECTURE.md`](../OFAN_ARCHITECTURE.md), `../exp32_ofan/`). The rate cap is new.
- **Possible hook.** The per-NIC egress shaper from the constant-rate sender (`UecNIC::_egress_bps`, `-rate_const_gbps`; [`../RATE_CONST_ARCHITECTURE.md`](../RATE_CONST_ARCHITECTURE.md)) could be driven by a ToR-side count of active senders per destination ToR. Design and validation would follow `add-mechanism` and `validate-mechanism`.
- **Status.** Lower priority than T1 to T5 (Chen: finish the buffer checks first); Itamar's literature check on whether switch-level proactive rate control already exists comes first.
