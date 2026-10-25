# Why does the k distribution of matched/uniform50 differ from over/healthy?

Question: in M4 matched/uniform50 matches over/healthy in random-EV share (~1% at B=8), retransmits (0) and FCT, but not in k
(valid EVs in the buffer just before a draw): over/healthy has k=2 on 56% of draws and mean 2.2, matched/uniform50 spreads over
k=2..6 with mean 4. This directory holds the controls run to find out why. Nothing here changes the 189-run M4 grid.

**All controls are single runs (seed 42, B=8, ToR0 sources 0-7), one pass with `-log_reps_events`; traces kept in `traces/`
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
   at line rate, not of the 400G speed, the shaper's absolute value or B.
2. **It is a knife edge at R = line rate.** R=398 (and native R=198) already give a wide k (mean 3.4-3.7, k=2 share 15-18%),
   the same family as every other cell with R below line rate. Over/healthy is the outlier; matched/uniform50 is in the common
   family, with k a little wider than matched/healthy (3.96 vs 3.28).
3. **The ACK-window distribution does not explain k.** At R=390, 398 and native 198 the shares of 0 / 1 / 2 ACK windows
   (22-23 / 56-58 / 19-20) equal those of over/healthy (22 / 57 / 20), yet k is wide. The earlier reading that burstier ACKs make
   matched/uniform50's k wider (README finding 2, commit c12cd32) is therefore not supported and was removed.
4. **At R = line rate the queue is not stationary.** In-flight and per-packet RTT rise slowly during 100-600 us (+0.020 pkts/us and
   +1.4 ns/us at over/healthy; +0.015 and +2.2 at native 200G), against +0.000 to +0.003 for every other cell. Random draws are
   0.2-0.4% (over/healthy) and 0.3-1.1% (native 200G, decaying) vs 0.0-0.1% elsewhere. At R=400 the shaper rate equals the link
   rate, so data goodput (~394G) plus the ACKs coming back to the same host (~6G) fill the 400G receiver downlink exactly (rho = 1.0), and
   the queue creeps up; at R=398 it does not. A rising in-flight count keeps pushing k down (each net rise of in-flight is one
   EV that is never banked), which pins k low and tight. This is the proposed mechanism, consistent with the slopes and the random
   draws; it is not directly demonstrated (no per-queue occupancy was logged), and R = line rate is also the point where the shaper
   becomes the stock NIC path, so the two cannot be separated with these cells.
5. **Why matched/uniform50 is wider than matched/healthy**: unsaturated cells have k = C - in-flight (corr(k, in-flight) = -0.85
   to -0.97), so k inherits the in-flight fluctuation. Matched/uniform50 has in-flight std 1.16 vs 0.70 for matched/healthy and k
   std 1.24 vs 0.76: the 200G uplinks at rho ~ 0.985 add queue fluctuation. For the line-rate cells the correlation is -0.07 and
   -0.27, because the drifting in-flight breaks the relation.
6. Lag-1 autocorrelation of the window ACK counts is negative in every cell (-0.2 to -0.46; each ACK answers one send), so it
   does not separate the cells.

## What this means for M4
Matched/uniform50 was never the anomaly. Every sending rate below line rate has a wide k (mean 3.2-5.4 at B=8); over/healthy and
its native-200G twin sit at an operating point (R = line rate, receiver downlink at rho = 1) that is qualitatively different from
"matched to a degraded link". The equality that holds between matched/uniform50 and over/healthy is in random-EV share,
retransmits and FCT, not in k. The tight k=2 of over/healthy is not "better buffering": it comes with a creeping queue.

Not tested: degrading the receiver downlinks (`-degrade_links_file` only supports ToR uplinks), other seeds.
