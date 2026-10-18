# C2: Freezing-Mode buffer drain speed vs B

**Claim** (2026-10-06 meeting): once Freezing Mode is entered, a larger buffer takes longer to
drain its stale entries than a small one.

**Scenario**: `exp30_packet_trimming_en` base, trim ON, NSCC, freezing LB, tornado 16 MiB, seed 42.
B in {1,2,4,8,16,32,64,128,256}. Two cells: F=0 (healthy anchor) vs F=16 (transient kill of 16 of
ToR0's 32 uplinks, `-timed_window 10 110 -timed_fail_tor_uplinks 0 16` -- kill at t=10us, past the
~8.8us warmup end measured from C1; recover at t=110us, 100us down). Trim ON because trim-off's
freeze gate (recent-max-RTT > 1.65*base_rtt) never fires at this kind of uniform degradation --
checked directly against `exp30_concentrated_path_loss`'s existing 16 MiB/x=32/r=0.5 runs: 0 freeze
events at every B, despite thousands of RTOs per cell. Trim-on freezes unconditionally on any RTO,
and a real dead path guarantees RTOs on it.

`-exit_freeze 200` (us) is a hard, timer-only unfreeze (`processEv_freezing`, `uec.cpp`, has no
other exit condition) -- a freeze entered during the 100us-down window is still frozen when the
link recovers at t=110us, and only exits at its own 200us-from-FREEZE mark.

**Measurements**:
1. Per-packet split (valid/random/stale/explore), same as C1, over all ToR0 hosts. Unlike C1
   (trim on, no RTO -> stale always 0), C2 enters Freezing Mode, so stale is expected nonzero.
   `frozen_pop` is classified valid/stale by looking up the slot at `(frozen_head-1) % buf_size`
   (count modulus) in the previous same-src row (pre-pop state) -- verified to match the committed
   `ev_valid`/`ev_stale` finish-line counters exactly.
2. Send-time k-histogram, split by `frozen_mode` at draw time (a frozen-mode pop follows a
   different slot-selection rule than a normal earliest-fresh pop).
3. Drain metric, per freeze epoch (FREEZE to next UNFREEZE, same src): of the frozen-mode draws,
   how many are stale, and where the LAST stale draw falls (draws after it got a valid EV even
   though the epoch hadn't unfrozen yet). Stale draws split by during-kill (t<110us, dead paths
   genuinely exist) vs after-recovery (t>=110us, a stale draw there is a leftover).
4. FCT: p50/p95/p99/max across the 32 ToR0 hosts, per B.
5. Diagnostics kept, same fields as exp30's own `aggregate30.py` (`rtos`, `ecn_acks`, `freeze_us`,
   `fast_loss`, `RTS`).

**Buffer-view pages**: pick a src with `freeze_entries > 0` (not always src 0), windowed from
just before the kill (t~9us) through ~260us past the first FREEZE (covers the 200us exit_freeze
timer), not a first-5000-events cut (would miss the freeze on a 16 MiB trace).

**Correctness gates** (all checked on a seeded smoke cell, F=16/B=8, before the full sweep):
- Phase-timing: FREEZE lands inside [10,110]us for every host; UNFREEZE comes before that host's
  last SEND (so a healthy finish phase exists after recovery) -- confirmed.
- `reps_event_viewer.py --verify` per src, all 32 hosts pass (first real test of the frozen-mode
  invariants -- pop-order modulus, ECN-marked-ACK-doesn't-write, UNFREEZE-all-invalid -- against
  real frozen data; C1 never froze).
- Trace-derived valid+stale == committed finish-line `ev_valid`+`ev_stale` exactly -- confirmed.
- F=0's flags are byte-identical to C1-NSCC's x=0 cell (`base_flags(part="b", f_uplinks=0)` ==
  `base_flags(part="a1", n=0)`) -- confirmed before running, so F=0 doubles as a determinism check
  against already-committed data.
- Known, unrelated to this plan: `-disable_tor_ecn` is missing from `common30.py`'s `base_flags`
  whenever `-sender_cc_only` is used (confirmed via the `enable on tor downlink 1` stdout line on
  the smoke cell) -- pre-existing in the shared trim-on config, also affects C1-NSCC. Not fixed
  mid-series; recorded in RESULTS.md.

**Pass/fail**: claim holds if sends-to-last-stale-draw increases with B. A null result is
acceptable and must be reported as such.
