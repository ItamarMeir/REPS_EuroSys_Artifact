# Why does the k distribution of matched/uniform50 differ from over/healthy?

Question: in M4 matched/uniform50 matches over/healthy in random-EV share (~1% at B=8), retransmits (0) and FCT, but not in k
(valid EVs in the buffer just before a draw): over/healthy has k=2 on 56% of draws and mean 2.2, matched/uniform50 spreads over
k=2..6 with mean 4. This directory holds the controls run to find out why. Nothing here changes the 189-run M4 grid.

**All controls are single runs (B=8, ToR0 sources 0-7; the table values in 'Results' are seed 42 and differ slightly from the 3-seed means in the main README), one pass with `-log_reps_events`; traces kept in `traces/`
(gzip, gitignored; the M4-grid cells are read from `../traces/`).** Windows: k, ACKs-per-window and the RTT/ACK-spacing columns
use the M4 definitions over all post-warmup draws / the 100-300 us steady-state window as labelled; in-flight and trend numbers use
100-600 us. Control runner `run_controls.py` (inside container `m23-dev`).

## Controls
- `native200_R200`, `native200_R198`: `fat_tree_1024_1os_2t_200g_native.topo`, `-linkspeed 200000`, R = 200 (= line rate) and 198.
  The R=200 cell is over/healthy scaled by a factor 2 in time.
- `healthy400_R{250,300,350,390,398}`: the 400G fabric, healthy, R = 250...398 Gbps. Fills the gap between matched/healthy (R=200)
  and over/healthy (R=400).

Scripts: `analyze_rtt.py` (per-packet RTT from SEND/ACK `seqno`, ACK spacing; window 100-300 us), `kdist.py` (k and ACKs per
window, M4 definitions, all post-warmup draws), `winseries.py` (correlation of consecutive window ACK counts), `inflight.py` (k vs
in-flight, 100-600 us), `trend.py` (slope of in-flight and RTT, per-100-us bins, 100-600 us).

## Results
| cell | k mean | k=2 share % | k mode | ACK-spacing CV | mean RTT us | ACKs per window 0 / 1 / 2 % | in-flight slope (pkts/us) |
|---|---|---|---|---|---|---|---|
| over/healthy (R=400 = line rate) | 2.21 | 55.6 | 2 | 0.68 | 10.3 | 22 / 57 / 20 | **+0.020** |
| **native 200G, R=200 (= line rate)** | **2.14** | **57.0** | 2 | 0.66 | 12.5 | 22 / 58 / 19 | **+0.015** |
| healthy R=398 | 3.40 | 18.1 | 3 | - | - | 22 / 57 / 20 | +0.001 |
| native 200G, R=198 | 3.67 | 15.1 | 4 | - | - | 22 / 58 / 19 | +0.003 |
| healthy R=390 | 4.24 | 6.6 | 4-5 | 0.68 | 9.4 | 23 / 56 / 19 | +0.003 |
| healthy R=350 | 5.29 | 0.8 | 5 | 0.73 | 8.7 | 26 / 51 / 20 | -0.001 |
| healthy R=300 | 3.69 | 9.5 | 4 | 0.79 | 8.7 | 33 / 40 / 21 | - |
| healthy R=250 | 3.51 | 8.0 | 4 | 0.73 | 8.6 | 32 / 42 / 21 | - |
| matched/healthy (R=200) | 3.28 | 14.1 | 3 | 0.81 | 8.6 | 32 / 41 / 22 | -0.000 |
| under/healthy (R=100) | 3.21 | 12.1 | 3 | 0.76 | 8.6 | 34 / 36 / 26 | - |
| matched/uniform50 (R=200) | 3.96 | 8.9 | 4 | 0.95 | 10.1 | 36 / 37 / 20 | +0.001 |

1. **Over/healthy is reproduced exactly by a saturated fabric at half the speed**: native 200G with 200G NICs gives the same k
   distribution (mean 2.14 vs 2.21), ACK-window distribution and ACK jitter. The tight k of over/healthy is a property of running
   at line rate, not of the 400G speed or B.
2. **The tight shape needs R = line rate.** R=398 (and native R=198) already give a wide k (mean 3.4-3.7, k=2 share 15-18%),
   the same family as every other cell with R below line rate. Over/healthy is the outlier; matched/uniform50 is in the common
   family, with k a little wider than matched/healthy (3.96 vs 3.28).
3. **The ACK-window distribution does not explain k.** At R=390, 398 and native 198 the shares of 0 / 1 / 2 ACK windows
   (22-23 / 56-58 / 19-20) equal those of over/healthy (22 / 57 / 20), yet k is wide. The earlier reading that burstier ACKs make
   matched/uniform50's k wider (README finding 2, commit c12cd32) is therefore not supported and was removed.
4. **At R = line rate the in-flight count keeps rising**; the mechanism section below quantifies it on a window that excludes the flow-end
   drain (the slopes quoted in an earlier version of this item used 100-600 us and were corrupted by it). It rises by +0.004 to +0.020
   pkts/us per source at R=400 (3 seeds), and the ToR uplink queues, not the receiver downlinks, grow with it.
5. **Why matched/uniform50 is wider than matched/healthy**: unsaturated cells have k = C - in-flight (corr(k, in-flight) = -0.85
   to -0.97), so k inherits the in-flight fluctuation. Matched/uniform50 has in-flight std 1.16 vs 0.70 for matched/healthy and k
   std 1.24 vs 0.76: the 200G uplinks at rho ~ 0.985 add queue fluctuation. For the line-rate cells the correlation is -0.07 and
   -0.27, because the drifting in-flight breaks the relation.
6. Lag-1 autocorrelation of the window ACK counts is negative in every cell (-0.2 to -0.46; each ACK answers one send), so it
   does not separate the cells.

## What this means for M4
Matched/uniform50 was never the anomaly. Every sending rate below line rate has a wide k (mean 3.2-5.4 at B=8); over/healthy and
its native-200G twin have a tight k=2 (over/healthy in all 3 seeds), which R=398 mostly loses. The equality that holds between
matched/uniform50 and over/healthy is in random-EV share, retransmits and FCT, not in k. Why R = line rate gives the tight shape is
open (see the sections below); two earlier explanations, ACK burstiness and a creeping receiver-downlink queue, were tested and withdrawn.

Not tested: degrading the receiver downlinks (`-degrade_links_file` only supports ToR uplinks).

## Sanity checks of the implementation (`run_single.py`, `analyze_single.py`, container `m23-dev`)
Load note (corrects an earlier statement): R caps data + ACKs per host NIC, and all tornado traffic crosses ToR links, so at R = line
rate (400G) *every* tier carries exactly 400G per host, and in matched/uniform50 (R=200) the ToR0 uplinks also carry exactly 200G per
uplink (rho = 1.0); the ~394G / ~197G figures are data goodput only. "~3G headroom" in the M4 caveats is wrong for the wire.

1-flow and 2-flow (0->512 and 0<->512, so host 0's uplink carries its data and the reverse flow's ACKs) workloads, 32 paths and 1 path,
healthy R=400/398 and uniform50 R=200/198, seed 42, B=8 (16 cells, `traces/single/`). Every cell passes: RTT flat at the base RTT
(8.3-8.7 us), RTT and in-flight slopes 0.00, 0 ECN-marked ACKs, 0 retransmits, max queue 1-2 packets (the pair at R=400 on one path:
8300 B = 2 packets; the 32-path R=400 receiver downlink 8464 B), and FCT = 4107 packets x 4150 B / R + one RTT to within 0.1 us
(e.g. 349.1 us at R=400, 689.9 us at R=200). So with nothing to merge with, the shaper and the NIC are correct, a single path at
rho = 1.0 with deterministic arrivals does not build a queue, and a queue at rho ~ 1 needs several hosts merging.

Code review (`UecNIC::startSending` / `sendControlPktNow` in `htsim/sim/uec.cpp`, set-up in `main_uec.cpp`): both paths charge
`size*8*timeFromSec(1.0)/egressSpeed()` with the stock integer formula (exact at 400G/200G; 83417 ps at R=398, 0.0001% off); a
packet is charged its full size (data 4150 B, ACK 64 B); `rateGate/rateCharge` are no-ops in shaper mode; one packet is released per
`doNextEvent`, so there is no burst on unblock; ports must be 1. No sim code changed since commit 3c4e585.

## Queue occupancy in the tornado cells
**Whole-run maxima** (`run_tornado_q.py`, `-log_queue_stats`, packets of 4150 B; includes the start-up burst of 1024 flows, so this is
not a steady-state measure):

| cell | ToR0 uplinks: mean of per-queue max | ToR0 host downlinks: mean of max | mean k | % draws at k=2 |
|---|---|---|---|---|
| over/healthy R=400, seeds 42/43/44 | 25 / 26 / 31 | 12.2 / 12.2 / 12.5 | 2.21 / 2.13 / 2.20 | 56 / 62 / 53 |
| healthy R=398, seeds 42/43/44 | 17 / 18 / 26 | 12.1 / 12.1 / 11.8 | 3.40 / 3.38 / 2.78 | 18 / 20 / 32 |
| matched/uniform50 R=200, seed 42 | 16 | 2.8 | 3.96 | 9 |
| uniform50 R=198, seed 42 | 14 | 2.5 | 4.51 | 6 |

Agg->ToR queues peak at 2 packets everywhere; there are no trims or drops. The deepest queues are on the ToR uplinks, not the receiver
downlinks, and the downlink maximum is the same at R=398 and R=400 (so the downlink does not separate them).

**Steady-state uplink queues** (`run_queue_ts.py`, `-log_tor_queues`, all 1024 ToR->agg queues sampled every 1 us, seed 42, run to 500 us):

| window | R=400 fleet-mean queue (pkts) | R=398 fleet-mean queue (pkts) |
|---|---|---|
| 0-30 us | 9.0 | 8.5 |
| 60-100 us | 16.2 | 14.2 |
| 100-160 us | 17.7 | 14.9 |
| 160-220 us | 18.6 | 15.1 |
| 220-280 us | 19.1 | 15.0 |
| 280-340 us | 19.4 | 14.9 |
| slope over 100-330 us | **+0.0100 pkt/us** | +0.0005 pkt/us |

Both start by filling; at R=398 the uplink queue plateaus at ~15 packets, at R=400 (rho = 1.0 on the uplinks) it keeps creeping
(~19 and still rising when the flows end, seed 42 only). This is where the in-flight creep of Result 4 sits: the ToR uplinks, not the
receiver downlink.

**ECN marks and random draws** (srcs 0-7, 100-330 us; steady state):

| cell | ECN-marked ACKs % | random draws % | k mean | k=2 % |
|---|---|---|---|---|
| healthy R=400 s42 / s43 / s44 | 0.10 / 0.18 / 0.39 | 0.28 / 0.34 / 0.50 | 2.21 / 2.13 / 2.20 | 56 / 62 / 53 |
| healthy R=398 s42 / s43 / s44 | 0.00 / 0.01 / 0.16 | 0.05 / 0.05 / 0.25 | 3.40 / 3.38 / 2.78 | 18 / 20 / 32 |
| matched/uniform50 R=200 s42 | 0.18 | 0.28 | 3.96 | 9 |
| uniform50 R=198 s42 | 0.00 | 0.04 | 4.51 | 6 |

Within the healthy cells k gets tighter as ECN marks and random draws increase (R=398 seed 44, with marks, is intermediate). A marked ACK
adds no EV to the buffer, so each mark lowers k by one until a random draw re-anchors it; that is a candidate mechanism. It is not
sufficient on its own: matched/uniform50 R=200 has the same mark and random-draw rates as over/healthy seed 42 yet a wide k.

## Mechanism: k is the drawdown of the in-flight count from its running maximum
(`replay_k.py`, `window_dd.py`, `ramp_win.py`; srcs 0-7, B=8 unless stated. An earlier version of this section used a 100-600 us window,
which for line-rate cells includes the flow-end drain (in-flight collapses after ~356 us), corrupted the fitted trends and wrongly
concluded that the trend does not matter; the scripts producing that were removed and the numbers below replace it.)

1. **Identity.** The constant-rate sender's timing does not depend on k, so k can be replayed from the event stream alone: clean ACK
   +1 (cap B), ECN-marked ACK +0, draw -1 (floor 0). The replay reproduces the traced `fresh` on every row (0 mismatches). So k is a
   reflected walk driven by in-flight changes; without the cap it is exactly the drawdown of M(t) = in-flight + marked ACKs from its
   running maximum since the source's first ACK.
2. **Same-window comparison** (100-330 us, inside every cell's flow; `window_dd.py`). `dd_first` = B=inf drawdown with the running max
   from the first ACK; `dd_win` = running max restarted at 100 us (forgets the start-up); `dd_win_dt` = `dd_win` after removing the linear
   trend of M fitted inside the window; hf = std of M with its 10 us moving average removed.

| cell | k observed | dd_first | dd_win | dd_win detrended | slope of M (pkts/us) | hf |
|---|---|---|---|---|---|---|
| over/healthy R=400 s42 / s43 / s44 | 2.31 / 2.19 / 2.29 | 1.35 / 1.40 / 1.83 | 1.34 / 1.39 / 1.82 | 2.28 / 2.44 / 3.62 | +0.033 / +0.039 / +0.042 | 0.57 / 0.58 / 0.72 |
| native 200G R=200 | 2.07 | 1.10 | 1.08 | 2.42 | +0.046 | 0.59 |
| healthy R=398 s42 / s43 / s44 | 3.66 / 3.71 / 2.96 | 2.68 / 2.73 / 2.02 | 2.50 / 2.48 / 2.01 | 2.55 / 2.63 / 2.79 | +0.001 / +0.004 / +0.021 | 0.67 / 0.66 / 0.67 |
| native 200G R=198 | 3.51 | 2.60 | 2.58 | 2.58 | -0.000 | 0.84 |
| healthy R=390 / 350 / 300 / 250 | 4.57 / 5.42 / 3.71 / 3.52 | 3.69 / 4.59 / 2.77 / 2.62 | 3.12 / 2.37 / 2.48 / 2.44 | 3.28 / 2.36 / 2.48 / 2.45 | +0.003 / -0.001 / -0.000 / +0.000 | 0.88 / 0.78 / 0.84 / 1.05 |
| matched/healthy R=200, under/healthy R=100 | 3.19, 3.17 | 2.23, 2.17 | 2.09, 1.94 | 2.09, 1.93 | -0.000, -0.000 | 0.73, 0.66 |
| **matched/uniform50 R=200** | **4.07** | **3.96** | **3.90** | **4.78** | **+0.016** | **1.20** |
| uniform50 R=198 | 4.73 | 5.84 | 3.90 | 3.81 | -0.001 | 1.31 |

   (k observed is windowed too, so it differs slightly from the whole-run means elsewhere. The slope of M includes the marked ACKs. The B=8 cap binds in the degraded cells, so there k observed is not dd_first + 1: matched/uniform50 4.07 vs 3.96, uniform50 R=198 4.73 vs 5.84; in the healthy cells k is dd_first + about 1.)
3. **Why over/healthy is tight: its in-flight count keeps rising, and ECN marks add to it.** The drawdown of the in-flight count alone (marks
   excluded, running max from the first ACK, window 100-330 us) falls monotonically with its slope:

| cell | in-flight slope (pkts/us) | marked-ACK slope (pkts/us) | drawdown of in-flight alone | k observed | k with marks treated as clean |
|---|---|---|---|---|---|
| over/healthy R=400 s42 | +0.0199 | +0.0127 | 1.37 | 2.31 | 2.33 |
| over/healthy R=400 s43 | +0.0146 | +0.0246 | 1.53 | 2.19 | 2.33 |
| over/healthy R=400 s44 | +0.0039 | +0.0384 | 2.05 | 2.29 | 2.50 |
| healthy R=398 s44 | +0.0033 | +0.0180 | 2.25 | 2.96 | 3.18 |
| healthy R=398 s42 / s43 | +0.001 / +0.004 | ~0 / ~0.002 | 2.68 / 2.73 (M, from first ACK) | 3.66 / 3.71 | - |
| matched/uniform50 R=200 | +0.0025 | +0.0130 | 4.51 | 4.07 | 4.43 |

   The replay with marks treated as clean agrees with the in-flight-only drawdown (k = drawdown + 0 to 1, the pre-draw convention), so the two
   tools are consistent. Marks are a secondary contributor (they lower k by 0.0-0.2 at R=400, 0.2 at R=398 s44, 0.4 at matched/uniform50);
   seed 44 has the weakest in-flight rise of the three and is the least tight. Counterfactuals on M = in-flight + marks (`ramp_win.py`, same
   window; these keep the in-flight series fixed while changing the buffer, and path choice does depend on the buffer, so read them as
   *consistent with*, not a causal proof): removing the fitted trend raises over/healthy's drawdown from 1.3 / 1.8 to 2.3 / 3.6 and native
   200G's from 1.1 to 2.4, the values of the sub-line-rate stationary cells (2.1-2.6); adding a +0.035 pkts/us ramp to those cells lowers them to
   1.4-1.85 (R=398 2.5 -> 1.6, native 198 2.6 -> 1.7, R=300 2.5 -> 1.85, matched/healthy 2.1 -> 1.5), the range of over/healthy. A simulation
   that changes the queue growth itself is the causal test (point 7).
4. **Why matched/uniform50 is wide: its in-flight count fluctuates about twice as much and does not creep as much.** hf is 1.2 (R=198: 1.3)
   against 0.57-0.84 in the healthy cells, and even with the start-up forgotten its drawdown is 3.9 against 1.3-2.6. A +0.035 ramp lowers it
   only to 3.1, so the larger fluctuation, not only the missing trend, keeps it high. The 400G fabric at the same R=200 (matched/healthy) has
   hf 0.73, so the extra fluctuation comes with the degraded 200G ToR0 uplinks. Its uplink queue also creeps about 7x slower than
   over/healthy's (ToR0 mean queue slope +0.0027 vs +0.0198 pkt/us at rho = 1.0 on both; R=198: -0.0006).
5. **Start-up memory** matters in the intermediate cells: restarting the running max at 100 us lowers R=350 from 4.6 to 2.4, R=390 from 3.7 to
   3.1 and R=198 (degraded) from 5.8 to 3.9, so part of their wide k is the in-flight peak of the first ~30 us, which a stationary queue never exceeds again.
6. **Not the main cause** (each tested): ECN marks alone (secondary, point 3; the extra-EV-loss counterfactual moves R=398 from 3.4 to
   2.5-2.8 but not to 2.2), ACK-window counts, receiver-downlink occupancy, the time-converted spread of queue
   lengths across the 32 sprayed uplinks (R=400: 6.6 packets x 83 ns = 0.55 us; matched/uniform50: 2.8 x 166 ns = 0.46 us).

7. **Degraded-uplink controls** (`run_queue_ts.py`, seed 42, window 100-330 us; the `deg_*` cells ran with `-end 500`, so no flow finishes in them and only
   their window numbers are valid). The all-ToR degrade file is `t a 0.5` for t, a in 0..31 (`*.txt` is gitignored, so it is not committed).
   `allt` = every ToR uplink at 50% and R=200, which puts every uplink at rho = 1.0 as in over/healthy, with host links and downlinks at rho = 0.5.
   `allt -q 202` doubles the queue size only; `allt -q 202 -ecn 50 152` doubles the queue size and the ECN thresholds, so the degraded uplinks hold
   101 packets and mark from 25 packets, as the 200G uplinks of the native-200G fabric do (`per-link-degrade` scales both with the link ratio, and
   the ECN thresholds are absolute, so `-q` alone does not move them).

| cell | k mean (whole run) | k=2 % | window: k obs / dd_first | slope of M: in-flight + marks (pkts/us) | hf | uplink queue: fleet mean, slope (pkt/us) | ECN-marked ACKs (run) |
|---|---|---|---|---|---|---|---|
| allt R=200 | 3.44 | 16.9 | 3.40 / 3.27 | -0.0001 + 0.0821 | 1.44 | 11.0, +0.0020 | 133,693 |
| allt R=200, -q 202 | 3.45 | 16.5 | 3.40 / 3.27 | same to 4 digits (the queue never exceeds 50 packets by 330 us) | 1.44 | 11.0, +0.0020 | 135,420 |
| allt R=200, -q 202 -ecn 50 152 | 4.24 | 10.4 | 4.28 / 3.85 | +0.037 (total) | 1.69 | 15.7, **+0.0198** | 8,224 |
| allt R=198 | 4.46 | 6.7 | 4.76 / 4.41 | -0.002 (total) | 1.34 | 7.2, -0.0041 | - |
| matched/uniform50 R=200 (only ToR0) | 3.96 | 8.9 | 4.07 / 3.96 | +0.0025 + 0.0130 | 1.20 | ToR0 9.6, +0.0027 | 286 (whole run, 1024 flows) |
| over/healthy R=400 | 2.21 | 55.6 | 2.31 / 1.35 | +0.020 + 0.013 (s42) | 0.57 | 18.2, +0.0198 | 8,588 |

   - Degrading only ToR0 is not the cause: with every uplink at rho = 1.0 the k stays wide.
   - The slow uplink-queue creep of the degraded cells comes from the scaled ECN thresholds: marking from ~12 packets makes the degraded queue stop
     near 11 packets (16x more marks than over/healthy, the in-flight count flat), while with the thresholds doubled the uplink queue creeps at
     +0.0198 pkt/us, the same as over/healthy's, and marks fall 16x. Queue capacity alone has no effect.
   - **But k stays wide even when the queue creeps** (4.24, k=2 10%), because the local in-flight fluctuation of the degraded-uplink cells is 2.3-3x that of
     over/healthy (hf 1.2-1.7 vs 0.57). A steep M rise does not tighten k when the fluctuation is that large (allt: slope +0.082 in M, mostly marks, but
     hf 1.44: drawdown 3.3, and 4.75 for in-flight alone). The drawdown depends on the rise **relative to** the local fluctuation.
   - Why the degraded 200G-uplink cells fluctuate more is not established. The native 200G fabric (200G uplinks at the same load, hf 0.59) differs
     from them in that its host links and downlinks are also at rho = 1.0; that is the remaining candidate, from single runs and not tested.

8. **Which hop matters: interventions on the all-ToR-uplinks-at-50% fabric** (`allt`: every uplink at rho = 1.0, host links, agg->ToR and ToR->host at
   rho = 0.5; R=200; seeds 42 / 43; window 100-330 us; `run_queue_ts.py` cells `ph_*`). The `per-link-degrade-speedup` and `per-hop-degrade` extensions
   (see `experiments/MODIFICATIONS.md`) let the degrade file speed up uplinks and scale every agg->ToR / ToR->host link.

| cell (all uplinks at 50%, R=200 unless stated) | k mean s42 / s43 | k=2 % | hf | note |
|---|---|---|---|---|
| allt (nothing else changed) | 3.44 / 3.16 | 16.9 / 21.4 | 1.44 / 1.52 | wide |
| + every agg->ToR link at 50% | 3.55 / 3.90 | 15.1 / 9.7 | 1.40 / 1.29 | still wide |
| **+ every ToR->host link at 50%** | **2.23 / 2.16** | **58.3 / 65.3** | **0.55 / 0.65** | **tight** |
| + agg->ToR and ToR->host at 50% | 2.34 / 2.12 | 50.1 / 62.8 | 0.56 / 0.58 | tight (host->ToR links stay 400G, so not identical to native 200G) |
| + ToR->host at 50%, R=198 | 4.86 / 5.46 | 4.8 / 5.3 | 0.68 / 0.67 | wide, M falling (-0.006 / -0.015 pkts/us) |
| native 200G with the uplinks sped up to 400G, R=200 | 2.28 / 2.18 | 51.5 / 59.6 | 0.61 / 0.60 | tight (uplink queue 0.7 packets) |
| matched/healthy R=200 (400G everywhere) | 3.28 | 14.1 | 0.73 | wide, M flat |

   - **The last hop, the ToR->host links at rho = 1, is what makes the fluctuation small and k tight** (2 seeds, an intervention that changes only those
     links). Every host is both sender and receiver, so each such link carries the incoming data and the returning ACKs; the two directions were not separated.
     It is the stage where the 32 sprayed paths reconverge into one FIFO, which agg->ToR (still a sprayed parallel stage) is not. The agg->ToR links do not. A rho = 1 uplink without it gives the large fluctuation (hf 1.4-1.5), and an uplink at rho = 0.5 (queue
     0.7 packets) is not needed. The host->ToR link could not be varied: `-linkspeed 200000` left the results identical to the digit (`ph_h` = `ph_none`,
     `ph_had` = `ph_ad`), so that arm is untested.
   - **Loss, marks and trims are not the explanation.** In every cell above the ToR->host queues have 0 trims and 0 drops (peak 21-24 packets of 50 with them
     at 50%), the traced sources have 0 RTX / NACK / RTS and the whole-run RTS count is 0. The cells with the ToR->host links at 50% do trim some packets on the
     200G uplinks (1,187-2,752 trims, ECN-marked ACKs 149-222k, vs allt 227-484 and 118-134k), so I repeated the cell with queue size and ECN thresholds doubled
     (`ph2_dqe`: 0 trims, 2-4k marked ACKs, 50x fewer): k stays tight (2.09 / 2.17, k=2 on 61 / 62%, hf 0.59 / 0.55). The tightening does not come from marks or trims.
   - **Third seed (44):** allt is wide (k 3.64, k=2 13%, hf 1.20) and allt + ToR->host at 50% is tight (2.25, 52%, hf 0.55), so both cells now hold in 3 seeds.
   - **Which side of the last hop** (`hdown_tor`: only some ToRs' ToR->host links at 50%; tornado sends from ToR0's hosts to ToR16's hosts, and the traced sources are on ToR0):
     only ToR16's links (the *receivers* of the traced flows' data) already give a tight k (2.33 / 2.38, k=2 on 43 / 42%, hf 0.62 / 0.60, 2 seeds), while only ToR0's links
     (where ToR0's ACKs and ToR16's data arrive) do not smooth (hf 1.67 / 1.35; k 2.24 in seed 42 only because M rises very steeply there, +0.42 pkts/us, and 3.43 in seed 43).
     So it is the stage where the data packets of a flow reconverge before the receiver, not the ACK-return link, that evens the arrivals.
   - **The two factors act separately.** The no/no cell (matched/healthy) is wide because nothing rises (M flat), not because of large fluctuation
     (hf 0.73). The cells with a rho = 1 uplink but no rho = 1 ToR->host link are wide because of large fluctuation. Tight needs both: smoothing from the
     ToR->host link at rho = 1 and a rising in-flight count, which only a queue at exactly rho = 1 provides.
   - **The rho = 0.99 tension is resolved:** with the ToR->host link at 50% and R=198 the smoothing survives (hf 0.67-0.68 vs 0.55-0.65 at R=200)
     but the rise is gone (M falls, the queue drains from the start-up peak), so the drawdown is large (dd_first 4.9-6.3) and k is wide. Native 200G
     R=198 (hf 0.84) and healthy R=398 (hf 0.67 vs 0.57-0.72 at R=400) fit the same reading: the rise needs rho >= 1 exactly.
   - **Measured per packet at the receivers, in the same runs as k** (`-log_sink_arrivals`, a new diagnostic added for this check, see `experiments/MODIFICATIONS.md`;
     `samerun.py`; the 8 flows from ToR0's hosts, window 100-330 us, **3 seeds 42 / 43 / 44** for every cell below; each run also writes the event trace, so a flow's
     arrival spacing, in-flight fluctuation, drawdown and k come from one simulation; flag-absent finish lines byte-identical):

| cell | CV of data-arrival spacing at the receiver | in-flight fluctuation hf | drawdown | k |
|---|---|---|---|---|
| over/healthy R=400 | 0.04 / 0.03 / 0.03 | 0.57 / 0.58 / 0.72 | 1.35 / 1.40 / 1.83 | 2.31 / 2.19 / 2.29 |
| healthy R=398 | 0.07 / 0.07 / 0.07 | 0.67 / 0.66 / 0.67 | 2.68 / 2.73 / 2.02 | 3.66 / 3.71 / 2.96 |
| native 200G R=200 | 0.06 / 0.06 / 0.05 | 0.59 / 0.58 / 0.58 | 1.10 / 1.26 / 1.28 | 2.07 / 2.25 / 2.26 |
| allt + every ToR->host link at 50% | 0.01 / 0.01 / 0.01 | 0.55 / 0.65 / 0.55 | 1.24 / 1.19 / 1.11 | 2.22 / 2.18 / 2.09 |
| allt + only the receivers' (ToR16) ToR->host at 50% | 0.02 / 0.02 / 0.02 | 0.62 / 0.60 / 0.79 | 1.29 / 1.35 / 1.46 | 2.27 / 2.33 / 2.41 |
| matched/uniform50 | 0.74 / 0.73 / 0.72 | 1.20 / 1.41 / 1.19 | 3.96 / 3.24 / 3.84 | 4.07 / 3.33 / 3.79 |
| allt (all uplinks at 50%) | 0.73 / 0.76 / 0.71 | 1.44 / 1.52 / 1.20 | 3.27 / 2.91 / 3.88 | 3.40 / 3.09 / 3.83 |
| allt + only ToR0's (senders') ToR->host at 50% | 0.77 / 0.72 / 0.73 | 1.67 / 1.35 / 1.14 | 1.89 / 3.37 / 4.11 | 2.58 / 3.57 / 4.10 |

     The data stream at the receiver is almost perfectly evenly spaced (CV 0.01-0.07) where the receiver's ToR->host link is busy, including R=398, and clumped
     (CV 0.71-0.77) where it is not, in all three seeds; the receivers' links alone switch it on, the senders' links do not. Across the 192 flows of the 24 runs the
     per-flow Spearman correlations are +0.81 (arrival CV vs in-flight fluctuation), +0.76 (fluctuation vs drawdown) and +0.70 (arrival CV vs k). The one cell that
     breaks the k pattern, "only ToR0" seed 42 (k 2.58 with hf 1.67), is the steep-rise case noted above (the drawdown is small because M rises very steeply); the
     other two seeds are wide. The R=398 cell has the smoothing (CV 0.07) but no rise, hence its larger drawdown, as in the R=198 test.
     (A "jitter about a straight line" statistic was also computed; it does not separate the cells because ~40% of packets are reordered in all of them, so it is not used.)
   - Mechanism: a rho = 1 uplink queue is a random walk that adds per-path delay jitter; the busy ToR->host FIFO of the receiver releases packets
     back-to-back, which evens the arrival spacing the receiver sees and therefore the ACK stream and the in-flight count.

## Status
- **Established.** The implementation passes the single-flow and pair checks and the byte-identity check after both sim extensions. Over/healthy's tight k
  holds in 3 seeds and is reproduced by a native 200G fabric. k is exactly the (capped) drawdown of the in-flight count (plus marked ACKs) from its
  running maximum. A tight k needs (a) small local in-flight fluctuation, which the busy last-hop ToR->host links provide (intervention, 2 seeds;
  the agg->ToR links do not), and (b) a rising in-flight count, which needs a queue at exactly rho = 1 (the uplinks in over/healthy; downstream in the
  sped-up-uplink fabric). Degraded cells fail (a): a rho = 1 uplink with the downlinks at rho = 0.5 gives 2-3x the fluctuation. Their slower uplink-queue
  creep (scaled ECN thresholds) is a second-order difference: doubling the thresholds restores it without making k tight.
- **Open / caveats.** The host->ToR link arm (cannot be varied with the current flags); the receiver-side smoothing is measured per packet in the same runs as k (3 seeds); all cells in the arrival table have 3 seeds, the other per-hop cells 2,
  the queue-sampling controls and the ramp counterfactuals (consistent-with only) are single seed 42; staggered flow starts untested.
