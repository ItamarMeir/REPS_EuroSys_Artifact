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
4. **At R = line rate the in-flight count creeps up, but only weakly and not in every seed.** In-flight slope over 100-600 us (pkts/us),
   3 seeds: R=400 +0.020 / +0.013 / +0.004; R=398 +0.0005 / +0.0015 / +0.0026; native 200G R=200 +0.015 (R=198 +0.003). The k shape is
   the robust signal: R=400 gives mean k 2.13-2.21 and 53-62% of draws at k=2 in all three seeds; R=398 gives 2.78-3.40 and 18-32%.
   The earlier explanation (a queue creeping because the receiver downlink sits at rho = 1.0) is **not supported**: the receiver
   ToR->host queues hold the same ~12 packets (max 14-15) at R=398 and R=400, so they do not distinguish the two. See the queue
   section below.
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

## Status
- Established: the implementation passes the single-flow and pair checks; over/healthy's tight k is robust across 3 seeds and is
  reproduced by a native 200G fabric; every sub-line-rate cell and matched/uniform50 have a wide k; at R=400 the ToR uplink queues
  keep growing while at R=398 they plateau.
- Open: why this makes k tight. ACK burstiness, a creeping receiver downlink, and ECN rate alone were each tested and do not
  explain it. Not run: the 800G-fabric / 400G-NIC test (the topology parser derives the uplink count from the speed ratio, so a
  32 x 800G uplink ToR is rejected; it would need a topology-parser change or oversubscription flags), receiver-downlink degrade
  (`-degrade_links_file` supports ToR uplinks only), more seeds for the steady-state queue sampling.
