# REPS-Bank architecture

Gate: `-reps_bank` (+ `-reps_bank_size N`, `-reps_bank_timer_us T`, `-reps_bank_target_rtt_us R`, `-log_reps_bank <file>`).
Requires `-load_balancing_algo freezing`; incompatible with `-reps_soft_replay` and the dual-window sender CCs (hard errors).

## What it does

REPS (`freezing`, non-frozen mode) draws a uniform random EV whenever its 8-slot buffer has no fresh EV. REPS-Bank adds a
second, separate **bank buffer**: a ring of `{ev, insert_time, valid}` slots that receives EVs which came back
**clean (no ECN) and with RTT <= target**. At a send, order is: REPS fresh pop -> **oldest live bank slot** -> random.

* Admission (in `UecSrc::processAck`, before the unchanged `processEv` call): only ACKs with a fresh RTT sample
  (PSN found in the tx bitmap) are considered. ECN-marked: rejected. Clean and `raw_rtt <= target`: admitted.
  Target: `-reps_bank_target_rtt_us` (absolute raw RTT) or, if absent/0, NSCC's own `_base_rtt + _target_Qdelay`.
* Full ring: the slot at `head` (the oldest position) is overwritten, valid or not, exactly like `CircularBufferREPS::add`.
* Expiry: a slot whose age `now - insert_time` is strictly greater than the timer is invalid. Checked lazily at pop time,
  which is observationally identical to a per-slot timer because slots are only read through the pop.
* Start of a connection: no special rule, same as REPS. REPS has no explore burst at start (`explore_counter` is set only at unfreeze); its first
  window is random only because the buffer is empty before the first ACK. The bank is empty then too, so the first window is identical to REPS.
  From the first clean ACK on, the bank serves the draws that REPS would make at random.
* Pop: oldest valid, unexpired slot (scan from `head`); popping invalidates it (single use).
* The bank is per connection, handled exactly like the REPS buffer: `ConnectionInfo` (`CONNECTION_INFO_MAP[src_dst]`) holds
  a `bank` pointer. With `-connections_mapping`, a flow writes its bank into the map when it finishes, and the next flow of
  the same src-dst pair borrows it in `startFlow` (the map owns it; the flow never frees a borrowed bank). Without
  `-connections_mapping` every flow allocates and owns its own bank, which is also what REPS does. Slots and their insert
  times survive from one flow to the next, so the timer is what bounds how stale an inherited EV can be. The bank is not
  consulted in frozen mode or during the post-unfreeze explore burst (freezing is out of scope for v1).
* Trace: `EvSource` `EVSRC_BANK_POP` (`bank_pop` in `-log_reps_events`); own log `-log_reps_bank`
  (`ADD, REJ_ECN, REJ_RTT, NOSAMPLE, POP, EXPIRE, OVERWRITE` rows, last column `conn` = src_dst of the connection);
  `BANK_STATS` line per finished flow (separate from the `finished at` line, which stays byte-identical). BANK_STATS counters
  are per flow (deltas against a snapshot taken in `startFlow`), plus `valid_at_start` (slots inherited from the previous
  flow of the connection), `valid_at_end` and `end_ps` (time of the print). ACKs that reach a flow after it finished carry no
  tx-bitmap sample and can still add `NOSAMPLE`/`REJ_*` rows after `end_ps`; the replay checker excludes them from the
  per-flow counters and fails on any state-changing row after `end_ps`. Conservation per flow:
  `inserted + valid_at_start == popped + expired + overwritten + valid_at_end`.

Code: `htsim/sim/bank_buffer.h` (ring), `uec.h`/`uec.cpp` (statics, admission block in `processAck`, pop in
`nextEntropy_freezing`), `datacenter/main_uec.cpp` (flags, checks, resolved-config line).

## Predictions (written before the smoke runs)

Cell: `fat_tree_128_1os_2t_400g`, `test_symm16.cm` (8 flows of 16 MiB, hosts 0..7 -> 64..71), NSCC + `freezing`,
`-sender_cc_only -disable_tor_ecn`, `-ecn 25 76 -q 100 -cwnd 151`, seed 20.

* P1 conservation (every run): per flow `acks == no_sample + rej_ecn + rej_rtt + inserted` and
  `inserted == popped + expired + overwritten + valid_at_end`; log row counts equal the counters; the independent replay
  (`experiments/tools/bank_log_check.py`) passes.
* P2 huge target + huge timer (1e6 us each): `rej_rtt == 0`, `expired == 0`, `no_sample == 0`,
  `rej_ecn == ecn_acks` of the same flow's `finished at` line (every ECN ACK has a sample), so
  `inserted == acks - ecn_acks`.
* P3 sends identity (trace of hosts 0..7): `SEND+RTX+RTS = fresh_pop + bank_pop + random + explore` per host, and
  `bank_pop` count == `popped` counter. Random draws fall relative to baseline (bank absorbs REPS-buffer misses); the
  remaining random draws are at least the first-window draws (bank empty before the first clean ACK).
* P4 boundary sweep of the RTT target (threshold derived from data): the never-admit run (target 1 ps) is dynamics-identical
  to baseline and its `REJ_RTT` rows list every clean ACK's RTT; let `R_min` be their minimum. Then
  target `R_min - 1 ps` -> `inserted == 0` and flow-finish lines byte-identical to baseline;
  target `R_min` -> `inserted >= 1` (`<=` admits at the boundary) and the first `ADD` row coincides with a baseline
  `REJ_RTT` row of RTT `R_min`; inserted is non-decreasing in the target over {R_min-1ps, R_min, auto, huge}.
* P5 default-target redundancy: with `target = base_rtt + 6 us` and ECN `kmin` onset (~2 us of queueing, scaled with the
  link) below it, clean ACKs with RTT above target are rare: `rej_rtt` is small relative to `rej_ecn` in healthy and
  degraded cells. (If this misses it is reported, not explained away.)
* P6 timer sweep: timer 1 ps never serves (identical to baseline); expiries grow as the timer shrinks.

* P7 per-connection sharing (`-connections_mapping`, K=3 sequential 0.5 MiB messages per src-dst pair, 128 pairs, 8-slot bank,
  timer 100 us): (a) without `-connections_mapping`, or with one flow per pair, the per-connection binary is
  byte-identical (stdout apart from the new `valid_at_start`/`end_ps` tokens) to the previous per-flow binary; (b) messages
  2 and 3 start with `valid_at_start` equal to the bank size (a message ends with its ring full of clean EVs: 8 x 128 = 1024
  per message index); (c) when the gap between messages is above the timer (period 300 us) all inherited slots expire on the
  first pop of the next message, `expired == valid_at_start` per message index, and when it is below the timer (period 80 us,
  gap about 60 us) nothing expires and the inherited slots are served (`popped` rises, fewer random draws in the first
  window); (d) the control (REPS only) shows the REPS buffer carried over (`fresh` > 0 at the first send of messages 2 and 3).

* P8 stale entries after a failure (written before running). Cell: 3-tier `fat_tree_128_1os_3t_400g`, `test_symm16.cm`, NSCC +
  freezing, `-fail_link_time 50 200 -fail_link_target 0 0`, seeds 20-22, all 8 hosts traced, bank timer in {1, 10, 100, 1000} us.
  Metric: among SEND rows in the failure window [50, 200) us, the fraction of seqnos that were later retransmitted (RTX) is the
  loss fraction, split by `ev_src`. Prediction: bank_pop loss fraction exceeds fresh_pop loss fraction (a bank EV may have been
  banked before the link died and is never re-validated, a fresh EV was validated by a recent ACK); random sits near the
  fraction of paths crossing the failed link; the bank_pop excess shrinks as the timer shrinks and is absent at 1 us (no bank
  pops at all). A confirmed excess is reported as a finding (it would motivate invalidating the bank on RTO/NACK), not patched.

* P9 interactions (written before running; freezing mode is out of scope, so no failure cells). Code reading: the bank is reachable
  only with `-load_balancing_algo freezing` (hard error otherwise), so DPS, PATH_RR, PXR, OPS and the other LB algos cannot combine with it.
  Left: sender-side mechanisms that keep the freezing LB (`-state_aware_ecn`, `-smart_filter_mode`, `-wtd_in_nscc`) and `-reps_draw_weights`.
  The first three change only what the CC sees; the bank reads the real `pkt.ecn_echo()` and the real RTT, so prediction: on the degraded
  cell (`-failed 4 -skip_asy`, symm16, seeds 20-22) with each of them plus `-reps_bank`, the checker passes, conservation holds on every flow,
  and the trace join has 0 mismatches. `-reps_draw_weights capacity` biases only the random fallback; a bank pop returns before the
  bias branch, so prediction: bank_pop EVs are unbiased by construction (they are echoed EVs), random draws keep the bias, checker and
  join pass, bank_pop count > 0. No new hard error is expected to be needed. A miss (checker/join failure or crash) is reported.

* P10 FCT rise / trims (written before the sweep, after seeing 5 seeds of trims at the ToR0 uplinks: baseline about 300, bank about 2200, and
  mean FCT 375 -> 412 us; degraded-uplink share of packets is 6.7% in both, equal to its capacity share 0.5/7.5). Working hypothesis (not yet
  tested): bank pops are echoed EVs that are older than REPS-buffer EVs (up to the timer), so they point at paths that were clean when the ACK
  came back but whose queues have since filled; trims (and the retransmits they cause) follow. Dose-response prediction (degraded cell, seeds
  20-22): at fixed size 8, trims and mean FCT rise monotonically with the timer over {2, 10, 30, 100, 1000} us and the 2 us point is closest to
  baseline; at fixed timer 100 us, trims and FCT rise monotonically with size over {1, 8, 64}. Non-monotonic means the stale-EV account is wrong.

## Verification

Full list of checks and results: `experiments/MODIFICATIONS.md`, section `[ADDED: reps-bank]`, Verification subsection.
Summary against the predictions above (final binary):

* P1, P2, P3, P4, P6 held. P4 boundary: target `R_min - 1 ps` admitted 0 and matched baseline; target `R_min` admitted 39 and
  its first `ADD` equals the baseline `REJ_RTT` row of that ACK. Target 0 is literal (admits nothing) and is byte-identical
  to plain REPS.
* **P5 missed.** Predicted `rej_rtt` small relative to `rej_ecn` in the degraded cell. Measured `rej_rtt` about 3.4-3.6k vs
  `rej_ecn` about 13.8k (about 25%) over 4 seeds; healthy cell `rej_rtt` 0. Round 2 ruled out the first explanation; cause unexplained.
* Negative controls: 5 corrupted logs detected by `bank_log_check.py`; a simulator built with `>` changed to `>=` in the expiry
  test fails the checker; 5 broken `BankBuffer` variants caught by `bank_buffer_test.cpp`.

* P9 held (interactions): bank + `-state_aware_ecn` / `-smart_filter_mode` / `-wtd_in_nscc` / `-reps_draw_weights <list>` all pass the checker and the trace join (3 seeds, degraded cell); smart-filter and WTD are inert in that cell (see the final-binary bullet below for a cell where they act). Bank-reachable only with `freezing`, so other LB algos are hard-excluded.

* Round 2 (final per-connection binary): A1-A3, B (trace join, 0 mismatches), C1, C3 (P9 held), D, E and F are recorded in MODIFICATIONS.
  Missed predictions: P5 (rej_rtt not small; its cause, H1 "queueing below kmin on the slow uplink", is ruled out in that form: the rejected ACKs
  sit at about 8.2 us of total path queueing, the drain time of one full queue but equally the sum of several partial queues), the C1 loss-fraction and 1 us timer predictions, E1 (degraded-uplink share does not fall: baseline
  REPS already sits at capacity share) and P10 (timer does not matter above 2 us; size 64 is not above size 8). Finding: with the bank on, 58% of
  sends repeat an EV sent by the same host within 8 us (baseline 0.3%), because a clean ACK feeds both the REPS buffer and the bank; ToR0 uplink trims
  rise about 7x and mean FCT in the degraded cell about 9.6% (5/5 seeds). P5 follow-up: ToR-downlink ECN on changes nothing, which rules out only queueing above kmin on the ToR-to-host queues; sub-kmin ToR-to-host queueing, the ACK return path, and dequeue-time marking from the backlog left behind (`compositequeue.cpp:116-143`) all remain candidates. The cause is open. This is consistent with, not shown to be caused by, the double use of
  one EV; a possible design change (do not bank an EV that is also kept fresh in the REPS buffer) is not implemented.

* Warm-up gate tried and removed: a gate that kept the bank off for the first BDP/MTU draws was built on the belief that REPS has a BDP random burst at connection start. It does not (only after unfreeze), so the gate was removed; the bank is identical to REPS before the first clean ACK because it is empty.

* Final binary reruns (A1, A2, A3, unit test, all checker/join negative controls, hard errors) match the earlier results; `-reps_draw_weights capacity -use_srv6` passes checker and join; smart filter and WTD are inert in the symm16, perm128 and incast cells but change the run in exp07's 3-tier perm cell, where bank + each of them passes checker and trace join (one seed).

Not covered: frozen-mode behaviour (out of scope), stale entries after a failure (C1 froze at the first RTO), and the causal test of the repeated-EV finding.
