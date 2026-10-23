# M1: why NSCC does not restore the healthy valid-EV share under 50% degradation

Verdict: **NSCC is not failing to cut its rate; it holds a standing queue at its delay target, and on the half-speed links that queue sits on the ECN marking ramp.** The ECN-marked ACKs do not recycle EVs, so the REPS buffer drains and 59 to 80% of sends are random draws. Lowering the target monotonically restores the valid share, at an FCT cost.

Data: existing C1 traces (`meeting_06_10_26/C1`) plus new single-seed runs (seed 42, tornado 16 MiB, NSCC, freezing B8, srv6 32 paths, trim on; ToR0 hosts 0 to 31) saved in `data/`. Script: `scripts/analyze_m1.py`, plot `plots/m1_cwnd_and_target.png`, table `data/m1_summary.csv`.

| fabric | NSCC target | % sends random EV | % ACKs ECN | median cwnd (pkts) | max FCT (us) |
|---|---|---|---|---|---|
| healthy 400G | default | 3.2 | 0.1 | 153 (initial, never reduced) | 356 |
| ToR0 uplinks x0.5 | 6 us | 79.5 | 77.1 | 89 | 731 |
| ToR0 uplinks x0.5 | 4.17 us | 58.7 | 56.4 | 81 | 729 |
| ToR0 uplinks x0.5 | 3 us | 45.1 | 42.9 | 74 | 726 |
| ToR0 uplinks x0.5 | 2 us | 33.6 | 30.6 | 67 | 745 |
| ToR0 uplinks x0.5 | 1 us | 17.1 | 7.7 | 59 | 764 |
| ToR0 uplinks x0.5, MPRDMA | n/a | 10.7 | 9.0 | 63 | 767 |
| ALL 1024 ToR uplinks x0.5 | 4.17 us | 57.2 | 54.9 | 81 | 724 |
| ALL 1024 ToR uplinks x0.5 | 6 us | 78.4 | 75.9 | 89 | 719 |
| native 200G (fabric and NICs) | default | 2.1 | 0.1 | 79 (flat) | 706 |

## Findings
1. **Rate is cut, but only to the target-delay equilibrium.** Median cwnd falls from 153 to 81 (4.17 us); the degraded knee is 56 pkts (C1 RESULTS). The 81 vs 56 gap is ~25 packets of queue per host, about 4.1 us at 200 Gbps, i.e. exactly the target. NSCC increases on every unmarked ACK (fair or proportional increase) and decreases only on marked ACKs with delay above target (`_updateCwndOnAck_NSCC_core`, `uec.cpp:2682`), so it settles with delay close to the target.
2. **That queue is inside the ECN ramp.** Degraded links scale buffer and ECN thresholds by 0.5 (12 to 38 pkts at 200 Gbps, 2 to 6 us). A 25-pkt standing queue marks about half the packets; at the 6 us target (about 36 pkts) it marks most. Prediction confirmed by the target sweep: ECN share and random share fall monotonically as the target drops (1 us: 7.7% ECN, 17% random), at the cost of longer FCT (764 us vs 731 us), since a low target underfills the pipe.
3. **Not a ToR0-only artifact.** Degrading every ToR uplink in the tree gives the same numbers as ToR0 alone (57 vs 59% random at 4.17 us).
4. **The "inherently slower network" control must keep the NIC faster than the fabric.** Native 200G (NICs also 200G) looks healthy because the host NIC is the bottleneck, so no network queue forms and the cwnd stays flat at 79 with 0.1% ECN. A 400G-NIC / 200G-fabric tree cannot be built with this topology generator (radix mismatch: 64 uplinks required), so the all-ToR-uplink x0.5 run is the faithful equivalent.
5. **Freezing is not involved**: trim is on, so overload yields NACKs, `rtos` and `freeze_entries` stay 0 in these runs (see the stdout files).
6. MPRDMA (window cut on ECN, no delay target) keeps the marked share at 9% and the valid share at 89%, consistent with the C1 result.

## Implication for the meeting question
The CC does adapt; the metric that moves is "queue the CC is willing to hold", which on degraded links is large relative to the ECN thresholds. For the buffer study this means NSCC results mix two effects (rate and standing-queue ECN pressure). The constant-rate sender (M2) removes both and gives a clean per-rate picture. Open follow-up: NSCC with a target below the ECN kmin delay, or WTD (`-wtd_in_nscc`, exp07, null result on FCT) evaluated on the valid-EV share rather than FCT.
