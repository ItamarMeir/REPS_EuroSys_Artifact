# C2 - does a larger buffer drain more slowly in Freezing Mode?

## Claim under test
From the 2026-10-06 meeting: once a sender enters Freezing Mode, the REPS buffer is replayed instead of refilled, so a larger buffer holds more stale entries (EVs already drawn once, possibly from dead paths) and should take longer to stop drawing stale EVs. If true, bigger B costs recovery time. Pass criterion in `PLAN.md`: the number of sends until the last stale draw increases with B; a null result is acceptable.

Freezing Mode in this code: a retransmission timeout (RTO) puts the sender in frozen mode. While frozen it stops sampling new EVs and replays the buffer's entries (valid or stale) until a timer (`-exit_freeze`) fires, which wipes the buffer and returns to normal.

## Setup
- Base `exp30_packet_trimming_en`: fabric `fat_tree_1024_1os_2t_400g`, tornado 16 MiB, **NSCC**, packet trimming ON, `-load_balancing_algo freezing -use_srv6 -paths 32`, seed 42, `-exit_freeze 200` (microseconds, a timer-only exit).
- Two cells per B: **F = 0** (healthy anchor; never freezes) and **F = 16**: a transient kill of 16 of ToR0's 32 uplinks (EVs 0 to 15 die; 16 to 31 survive) with `-timed_window 10 110 -timed_fail_tor_uplinks 0 16`, i.e. down from t = 10 us to t = 110 us (after the roughly 8.8 us warmup).
- B in {1, 2, 4, 8, 16, 32, 64, 128, 256}, 18 cells, 32 ToR0 hosts each, full event trace per cell.
- Trim ON because with trim OFF Freezing Mode does not fire at this kind of uniform degradation (the RTO freeze gate `_last_rto_max_rtt < 1.65 x base_rtt` stays closed); with trim ON any RTO freezes, and a dead path guarantees RTOs.
- Known gap, inherited from the exp30 trim-on config: `-disable_tor_ecn` is not passed with `-sender_cc_only`, so ToR-downlink ECN is on (it also applies to C1-NSCC).

## What is measured
Per host and per freeze epoch (FREEZE to the next UNFREEZE):
1. **Per-packet split** of frozen draws into valid / stale (a frozen pop is classified by the slot content in the previous row) / random.
2. **Drain metric** (`drain.py`): of the frozen-mode draws, how many are stale and where the *last* stale draw falls (sends since the freeze). Stale draws are split into during the kill (dead paths really exist) and after recovery (leftover).
3. **Failed-EV content** (`failed_ev_buffer.py`): how many written slots still cache a dead EV (0 to 15) and how fast ACK overwrites clear them, with the clock starting at kill onset. Also the load imbalance over the 16 good EVs while frozen.
4. **FCT**: p50 / p95 / p99 / max over the 32 ToR0 hosts.
Correctness gates (smoke cell F = 16, B = 8): FREEZE lands inside [10, 110] us for every host, the event viewer's `--verify` passes for all 32 hosts, and trace-derived valid + stale equals the committed finish-line counters exactly.

## Results (seed 42, 32 hosts per cell)
| B | median sends to last stale draw | stale share of frozen draws | hosts whose dead EVs cleared before recovery | F = 16 p50 / max FCT (us) |
|---|---|---|---|---|
| 1 | 1221 | 55% | 32 / 32 | 486 / 518 |
| 8 | 1198 | 52% | 32 / 32 | 491 / 515 |
| 16 | 1194 | 52% | 32 / 32 | 491 / 508 |
| 64 | 1200 | 54% | 32 / 32 | 490 / 510 |
| 128 | 1192 | 59% | 32 / 32 | 494 / 508 |
| 256 | 1076 | 60% | 27 / 32 | 500 / 537 |
Healthy (F = 0) FCT is 356 us at every B.

- **The claim is not supported.** Sends to the last stale draw do not grow with B (about 1180 to 1220 for B <= 128, and lower, 1076, at B = 256). Per epoch the outcome is about two thirds "stale until unfreeze" and one third "cleared before unfreeze" at every B.
- **The median host enters Freezing Mode 39.7 us after the kill** (RTO-driven, the same for every B). By then ACK overwrites have usually cleaned the dead EVs from the buffer (median 0 dead entries at freeze for B <= 128; B = 256 holds a median 49 and 5 of 32 hosts still have dead EVs at recovery).
- More than half of frozen draws are stale at every B (0.52 to 0.60); there are no random draws while frozen. The stale share is lowest at B = 8 to 16 (0.52) and highest at B = 128 to 256 (0.59 to 0.60), so it rises only at the large end.
- FCT under the kill is about 490 us (p50) for B = 2 to 128; B = 1 is slightly faster at the median but has a higher max; **B = 256 is the worst** (p50 500 us, max 537 us). With one seed these differences are not resolved.
- Net: C2 is a null result for "bigger B drains slower"; the only visible cost of a very large buffer is at B = 256.

## Caveats
- One seed (42); no confidence intervals. Differences of a few microseconds are within what other experiments (exp28 to exp31) found to be noise.
- Only one failure shape (16 of 32 uplinks down for 100 us) and one exit timer (200 us).
- No `RESULTS.md`; the numbers above were read from `data/c2_drain.csv`, `c2_failed_ev_epochs.csv`, `c2_freezing_split.csv` and `c2_fct.csv`. `plots/interactive.html` has the full time-series and per-B panels.

## Reproduce
```bash
cd /workspace/experiments/meeting_06_10_26/C2/scripts
python3 run_c2.py --workers 2          # 18 cells + SoL arm; writes ../runs and ../traces (gzipped)
python3 send_occupancy.py              # send-time k, split by frozen_mode -> c2_send_occupancy.csv
python3 drain.py                       # -> c2_drain.csv
python3 failed_ev_buffer.py            # -> c2_failed_ev_*.csv, c2_good_ev_*.csv
python3 freezing_mode.py               # -> c2_freezing_split.csv, c2_freezing_acks.csv
python3 view_traces.py                 # per-B buffer view pages -> ../plots/buffer_view_*.html
python3 build_c2.py                    # -> ../plots/interactive.html
```
The order is inferred from each script's docstring and inputs; check a script's header before running it standalone.

## Files
`PLAN.md`; `scripts/` (`run_c2.py`, `send_occupancy.py`, `drain.py`, `failed_ev_buffer.py`, `freezing_mode.py`, `view_traces.py`, `build_c2.py`); `data/` (13 CSVs); `plots/interactive.html` plus nine `buffer_view_16MiB_F16_B<B>_src0.html` replays of one freezing host per B (local only; traces in `traces/` also local).
