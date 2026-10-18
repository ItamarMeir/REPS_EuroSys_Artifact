# C1 results: 16 MiB

Config: `exp30_packet_trimming_en` (trim ON), MPRDMA, freezing LB, tornado 16 MiB (4107 packets/flow),
ToR0 hosts (32), seed 42 only. Healthy = n=0. Degraded = all 32 ToR0 uplinks at 50% speed.
Page: `plots/interactive.html`. Data: `data/c1_split.csv`, `data/c1_split_hosts.csv`, `data/c1_occupancy.csv`,
`data/c1_send_occupancy.csv`, `data/c1_send_checks.csv`.
(4 MiB runs are kept on disk but not presented here.)

## Claim

After each host's first ACK, during backlog (before its last send), the buffer holds at most 2 valid EVs.
B=1 and 2 hold this trivially (the buffer cannot hold more than 2), so only B>=4 tests it.

## Occupancy (event trace, pooled over 32 ToR0 hosts)

Metric: share of trace rows with fresh <= 2, where fresh = valid buffer entries after each event.
"After t0" = rows with time >= the host's first ACK. "Backlog" = after t0 and before the host's last send.

| Scenario | B | after t0 | backlog | max fresh (backlog) | backlog rows fresh>=3 |
|---|---|---|---|---|---|
| healthy | 1 | 1.0000 | 1.0000 | 1 | 0 |
| healthy | 2 | 1.0000 | 1.0000 | 2 | 0 |
| healthy | 4 | 0.8110 | 0.8234 | 4 | 45121 |
| healthy | 8..256 | 0.8309 | 0.8439 | 5 | 39885 |
| degraded | 1 | 1.0000 | 1.0000 | 1 | 0 |
| degraded | 2 | 1.0000 | 1.0000 | 2 | 0 |
| degraded | 4 | 0.9920 | 0.9999 | 3 | 36 |
| degraded | 8..256 | 0.9918 | 0.9998 | 3 | 51 |

Healthy B=8..256 are identical: the valid count never reaches 8, so the buffer size never limits it.
Degraded B=8..256 are identical for the same reason (max valid count is 3).

Drain share (rows after the last send, out of rows after t0): about 1.6% healthy, 0.8% degraded.

## Reading

- **Healthy: the claim does not hold.** During backlog the buffer holds 3–5 valid EVs for about 16% of rows.
  The excess is not a drain tail (drain is 1.6%). This contradicts the earlier conclusion, which came from the
  degraded trace alone.
- **Degraded (all ToR0 uplinks at 50%): the claim holds.** During backlog 99.98% of rows have at most 2 valid
  EVs, and the maximum is 3 (51 rows). The 0.8% drain tail contains the full-buffer states (8 valid).
- Only B>=4 counts as a test. Degraded saturates at B=8 (B=4 is close but not identical: max fresh 3 vs 3,
  but 36 backlog rows with fresh>=3 at B=4 vs 51 at B=8..256, and the send-time table below shows the
  same B=4-vs-B=8 gap: 0.0390 vs 0.0408 at k=2).

## Per-packet split (C1, seed 42)

| Scenario | B | valid | random | stale | RTX |
|---|---|---|---|---|---|
| healthy | 1 | 0.7579 | 0.2421 | 0 | 0 |
| healthy | 2 | 0.9398 | 0.0602 | 0 | 0 |
| healthy | 4..256 | 0.9681..0.9691 | 0.031..0.032 | 0 | 0 |
| degraded | 1 | 0.8744 | 0.1256 | 0 | 1567 |
| degraded | 2..256 | 0.8817..0.8829 | 0.117..0.118 | 0 | 1568..1574 |

Reading: the split is flat from B=4 up. Stale is 0 everywhere (trim on, no RTO, no freeze).
The split includes the warmup: before a host's first ACK every draw is random (about 105 sends per host).

## Send-time k: valid EVs in the buffer just before each draw (post-warmup)

k = valid buffer entries immediately before a SEND/RTX/RTS draw, counted from the host's first ACK
(warmup) onward. Read from the previous row's post-event `fresh` value for that host, not the row's own
`fresh` (which is already post-pop). Columns stop at the largest k observed; a B too small to reach a
k column is blank (impossible, not zero).

| Scenario | B | k=0 | k=1 | k=2 | k=3 | k=4 | k=5 |
|---|---|---|---|---|---|---|---|
| healthy | 1 | 0.2224 | 0.7776 | | | | |
| healthy | 2 | 0.0357 | 0.4061 | 0.5582 | | | |
| healthy | 4 | 0.0057 | 0.1009 | 0.5554 | 0.3238 | 0.0142 | |
| healthy | 8..256 | 0.0067 | 0.1167 | 0.5725 | 0.2969 | 0.0071 | 0.0002 |
| degraded | 1 | 0.1029 | 0.8971 | | | | |
| degraded | 2 | 0.0954 | 0.8644 | 0.0402 | | | |
| degraded | 4 | 0.0952 | 0.8655 | 0.0390 | 0.0003 | | |
| degraded | 8..256 | 0.0942 | 0.8646 | 0.0408 | 0.0004 | | |

Checks (all 18 cells, every check passes):
- **Conservation**: post-warmup send count equals the committed per-host finish-line total minus the
  warmup sends counted in the same pass.
- **Determinism**: P(k=0) equals the random-draw share exactly (k=0 forces a random EV by construction).
- **Reconstruction**: 0 mismatches between the claimed k transitions and the trace's own `fresh` column
  (`fresh_pop` rows: this-row fresh == k-1; `random` rows: k == 0 and this-row fresh == 0).
- **Stale proven 0**: both `freeze_entries` (committed) and `frozen_pop` trace rows are 0 (trim on, no RTO).
- **Capacity**: max(k) <= B in every cell.
- **Sum to 1**: the k-distribution for each cell sums to 1 (float tolerance 1e-9).
- **Cross-check against the independent occupancy trace** (`occupancy.py`'s `max_fresh_backlog`, a
  separate pass over every row, not just sends): max(k) matches it exactly in every cell -- 1,2,4,5,5,5,5,5,5
  for healthy B=1..256 and 1,2,3,3,3,3,3,3,3 for degraded. Send-time sampling and all-row sampling agree
  on the maximum (they are not expected to agree on the distribution -- see the side-by-side check below).

Reading: k saturates at **B=8** in both scenarios (B=4 is still rising towards it: healthy max k is
4 at B=4 vs 5 at B=8..256; degraded k=2 share is 0.0390 at B=4 vs 0.0408 at B=8..256) -- identical to the
occupancy result in the section above, for the same reason (the valid count never reaches higher B's
capacity). Healthy sends see k in {3,4,5} about **30.4%** of the time (0.2969+0.0071+0.0002); degraded
sends see k in {2,3} about 4.1% of the time and never above 3.

Send-time P(k>=3) is roughly double the all-row backlog P(fresh>=3) from the Occupancy section, not
equal to it -- the two are sampled differently (every draw vs every trace row) and should only agree at
the maximum, which they do. Backlog rows split about evenly between post-ACK states (value k, right
before the next draw) and post-send states (value k-1, right after a draw popped one EV), so
0.5*(P(k>=3)+P(k>=4)) should approximate the all-row figure:

| Scenario | 0.5*(P(k>=3)+P(k>=4)) | observed all-row P(fresh>=3), backlog |
|---|---|---|
| healthy (B=8..256) | 0.5*(0.3042+0.0073) = 0.1558 | 0.1561 |
| degraded (B=8..256) | 0.5*(0.0004+0) = 0.0002 | ~0.0002 (51/260395) |

Both match to 3 decimal places, which is the real confirmation that the two independent measurements
(send-time k vs all-row occupancy) describe the same underlying buffer state.

## Checks

- **Trace matches C1:** for every occupancy cell, the trace run's finish lines (1024) match the committed C1
  stdout exactly (`crosscheck_match` = True).
- **Conservation:** SEND rows = 32 x packets per flow, and RTX = NACK = draws - packets (degraded B=8, both sizes).
- **Retransmissions:** 1568 at every B from 8 up, at 16 MiB. Not explained yet.
- **Seed:** every value here is seed 42 only.
- **Binary:** the trace runs use `htsim_uec` rebuilt from HEAD (5d84e80). The C1 split values come from the earlier
  build, which has the same counters.

## SoL (speed-of-light) reference

A real sim arm, not an analytic guess: `-load_balancing_algo path_static -sender_cc_algo constant`
(greedy edge-load picks one disjoint path per flow at setup, `uec.cpp` `path-static`; `constant` CC
freezes cwnd at whatever `-cwnd` sets, `dontUpdateCwndOnAck` -- never reacts). Verified in
`exp16_path_random_v16`/`exp17_cwnd_corrected_v17` to hit ~1.001x the analytic non-blocking optimal on a
tornado workload. No B (no REPS buffer in this arm), so it appears only on the FCT panel, as a floor.

**cwnd smoke test** (fixed window is never adjusted mid-flow under `constant`, so an undersized value
underruns the WHOLE flow, not just ramp-up): swept `-cwnd` on the healthy and degraded cells separately,
holding everything else at C1's own flags. Healthy knee at **cwnd=127** (~1.25x the 32-path `Q=101` BDP);
plateaus at max FCT 354.25 us from there (cwnd=101 still short, at 362.89 us; cwnd>=813 identical to 127's
plateau).

Degraded is the opposite shape -- FCT *falls* as cwnd drops, then plateaus, instead of rising then
plateauing like healthy. First swept 127-1024 and got a monotonically *rising* tail (152 -> 710.915 us,
203+ -> 710.997 us), which looked like a plateau but was actually still above the true floor, caught only
by sweeping *below* 127 too. BDP = rate x RTT: halving the uplink's rate halves its BDP, so the degraded
knee is correctly *below* 127, not above it -- the earlier "152, coincidentally close to C1's shared
`-cwnd 151`" framing was the bug, not a real knee. True knee at **cwnd=56** (packets); plateaus at max FCT
700.367 us from cwnd=56 up through at least 90 (56/64/76/90 all identical to 3 decimals), then rises again
above the plateau at cwnd>=101 as the oversized window re-overshoots the halved-rate path. Below 56 it
drops off fast (40 -> 885.1 us, 32 -> 1098.6 us) -- genuinely under-provisioned.

Swept **isolated to the 32 ToR0 hosts** via the new `-host_cwnd_overrides` flag (mirrors
`-host_lb_overrides`'s per-host map; `experiments/MODIFICATIONS.md` row `per-host-cwnd`): ToR0 hosts get
the swept cwnd, every other host keeps a non-bottlenecking cwnd (1024 pkts), so the sweep isn't also
under/over-provisioning the 992 background flows sharing the same run. Re-ran the full ladder (32-127)
isolated and got numbers identical to the earlier global-cwnd sweep at every matching value (e.g. 700.367
at 56/64/76/90 either way) -- on this topology the 32 dedicated ToR0 paths don't share capacity with the
background flows, so isolation changes nothing numerically, but it is the methodologically honest way to
run it and is what the committed `sol`/x32 run now uses.

**Mechanism, confirmed directly from the trace**: at cwnd=152, ToR0 host 0's `ecn_acks` = 4053 of 4107
packets (99%) -- the oversized frozen window keeps the halved-rate queue deep for almost the entire flow.
At the true knee cwnd=56, `ecn_acks` = 8 of 4107 (0.2%) -- the window matches the path's own halved BDP, so
the queue almost never builds. This is exactly the oversized-window-on-a-slower-path effect the BDP-halving
argument predicts.

| Scenario | SoL p50 (us) | SoL max (us) | hosts |
|---|---|---|---|
| healthy | 354.250 | 354.250 | 32 |
| degraded | 700.367 | 700.367 | 32 |

(SoL's p50 and max coincide: all 32 hosts get an identical dedicated path and an identical fixed
window, so every flow's FCT lands on the same float value up to rounding.)

**Slowdown from SoL, using max/makespan (not p50) as the comparison metric** -- SoL models every flow
finishing at the same instant; a real B-sweep's p50 CAN legitimately beat that single value (early
finishers borrow bandwidth ahead of stragglers without violating total-bit conservation), but the
slowest flow (max) cannot finish before the aggregate floor -- that is what SoL actually pins down:

| Scenario | REPS max FCT (B>=8, saturated) | SoL max FCT | slowdown |
|---|---|---|---|
| healthy, MPRDMA | 356.407 us | 354.250 us | 1.006x |
| healthy, NSCC | 356.407 us | 354.250 us | 1.006x |
| degraded, MPRDMA | 766.574 us | 700.367 us | 1.094x |
| degraded, NSCC | 730.768 us | 700.367 us | 1.043x |

Reading: healthy REPS is essentially at the speed-of-light floor regardless of B or CC (0.6% off).
Degraded REPS pays a real, CC-dependent tax on top of the (now corrected, lower) floor -- NSCC (4.3%
slowdown) tracks SoL noticeably closer than MPRDMA (9.4% slowdown) once all 32 ToR0 uplinks are halved,
even though neither CC's own median FCT (687-690 us) is far from the other's.

**"Could smart-spraying across ToR0's links lower max FCT further?"** No, not in this cell: all 32 of
ToR0's uplinks are degraded uniformly (not a few of them), and `path_static` already assigns each of the
32 flows its own distinct uplink 1:1 -- confirmed by SoL's own numbers above (p50 == max exactly, zero
variance already). There are no non-victim hosts left to redistribute load to, and the floor is already
total-bytes / total-aggregate-uplink-capacity, evenly split. This is also already tested empirically: C1's
real `freezing` (REPS-spray) arms at x=32 ARE the "spray across ToR0 uplinks" case, and they are *slower*
than pinned `path_static` (766.6/730.8 us spray vs 700.4 us pinned), not faster -- dynamic spraying adds
its own overhead (ECN reaction, retransmits, cwnd churn) on top of a floor it cannot beat. The idea would
be real for *partial* degradation (some ToR0 uplinks healthy, some not) where non-victims exist to donate
slack to -- out of scope here, C1's degraded cell is all-32-uniform by construction.
