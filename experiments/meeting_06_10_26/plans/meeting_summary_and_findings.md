# 2026-10-06 meeting: buffer size analysis — plan

Source: meeting transcript (Itamar Meir, Gabriel Skalosub, Chen Avin). Next meeting: Monday 2026-10-12, 10:00.

## Blocker: freeze under partial degradation depends on the trim setting and the RTT gate

Meeting item (line 46): run without trim so freezing fires under partial degradation.

- **Trim off, congested path (degradation, no dead link): freeze does fire, but gated and sparse.**
  Freeze-on-RTO runs only when `_last_rto_max_rtt < _base_rtt * 1.65` (`htsim/sim/uec.cpp:5066`).
  Counted `started freezing mode1` lines in exp30 Part A stdout (trim off, 24 seeds per cell, `runs/a1`, `runs/a2`):
  4 MiB, n=4: 15/24 runs freeze, 53 events; n=8: 8/24 runs, 34 events; n=32: 3/24 runs, 4 events.
  16 MiB, n=32: 6/24 runs, 85 events. Heavy degradation (a2, 90-95% slowdown on ToR0 links): 23-24/24 runs freeze.
  Per-host mean diagnostics (`freeze_entries_per_host`, max 0.073) hide this. Use run-level counts.
  Mode2 (ungated) never fired in trim-off runs (total 0), as expected.
- **Trim on, congested path: no freeze.** Congestion trims rather than drops, so no RTO
  (`exp30_packet_trimming_en`, `rto_per_host = 0` at every n).
- **Trim on, dead path: freeze fires.** Part B / `-timed_window` kill links through `LinkFailureEvent` → `Pipe::_failed`
  (`htsim/sim/pipe.cpp:67`), which calls `pkt.free()` with no trim. The sender recovers only by RTO → freeze.
  The `simCableFailures` path (`pipe.cpp:53-61`) is the one that trims, and it is not used by Part B.
- So the real question for the meeting is not "does freeze fire" but "which trigger and which trim setting gives
  the regime Gabriel wants (buffer-only operation under degradation, no dead links)". Only trim off produces it,
  and only where the RTT gate happens to open. A bypass flag would make it deterministic and needs the
  ADDED-banner / MODIFICATIONS / ARCHITECTURE process.

## Action items mapped to the repo

1. **Per-packet split: valid / stale-in-freezing / random.**
   - Source enums already exist: `EVSRC_FRESH_POP` (valid, non-frozen), `EVSRC_FROZEN_POP` (frozen, unsplit),
     `EVSRC_FROZEN_POP_VALID` / `_STALE` (dual algos only), `EVSRC_RANDOM`, `EVSRC_EXPLORE`
     (`uec.cpp` ~4010-4075).
   - Counters already exist for `ev_random` and `ev_explore` (`metrics-counters`).
   - Plan: use `-log_reps_events` and aggregate by source. For non-dual algos, call `is_valid_frozen()` in the logger only
     (read-only) to split frozen pops. Confirm the buckets sum to 1 (4 buckets: fresh, frozen-valid, frozen-stale, random+explore).
   - Merge into Gabriel's three categories for presentation. Explore is a fourth bucket to report separately.
2. **Valid-EV count over time, plus ~500-packet slow-motion view.**
   - `-log_reps_events` snapshots the buffer per row. `experiments/tools/reps_event_viewer.py` gives the slow-motion view.
   - Sample every ~1000 rows of a run (Gabriel: millions of packets). Use one ToR0 host and one non-ToR0 host.
   - Verify the snapshot marks validity per slot before relying on it.
3. **B up to 256.**
   - `-reps_buffer_size` parses any integer (`datacenter/main_uec.cpp:926`). The circular buffer has no hard cap in
     `buffer_reps.h`, so runs will work. Verify the `_no_of_paths` mapping.
   - With `-use_srv6 -paths 32` there are 32 distinct EVs. B > 32 means duplicate entries. Report this as a caveat, not a result.
4. **Speed-of-Flight oracle (baseline).**
   - Use `path_rr` plus a liveness mask from the same failure schedule (fixed for static kill, switching for `-timed_window`).
   - Confirm which SRv6 path indices map to ToR0's failed uplinks (`path_rr_npaths_override` may keep only the dead ones).
   - Use the same CC as the B arms (MPRDMA). Itamar said "NSCC" for the oracle idea (transcript ~38:59); mixing CCs would confound normalization.
5. **Sanity check: FCT proportional to lost bandwidth.**
   - Largely answered by exp30 A1 (n=32, r=0.5): p50 97 -> 180 us at 4 MiB, p99 356 -> 738 us at 16 MiB (~1.9-2.1x).
   - Pull Part B F=16 from exp30 data to show the halving case. Rerun only if numbers do not line up.
6. **Same Y axis across B.** Check uncommitted `build_interactive.py` diffs in exp29/exp30 before editing.
7. **Bursty traffic.** Check `experiments/workloads/` generators and `.cm` start times. Low priority.
8. **SLRU / replacement policy.** Deferred until oracle shows headroom (Chen: "first find the workplace").

Not on the list but raised:
- Interaction of NSCC with B was never tested (transcript ~24:39, "need to check whether buffer size changes with NSCC").
- B=32 variance larger than B=16 unexplained.
- Max-FCT-only focus: in exp30 Part B, B=1 strands flows past `-end` (90 ms censor). Report the stuck-flow count separately.

## Order

1. Classification counters and valid-count trace (cheap, tests both hypotheses).
2. Speed-of-Flight oracle (normalization and SLRU depend on it).
3. B=256 after cap check.
4. RTT-gate bypass flag (only if the earlier results say it is needed).
5. Bursty traffic.

## Needs the user

- Shared research repo: hosting, and Gabriel/Chen handles. Gabriel wants text, refs and figures, no code, no heavy data.
  Chen suggested a second repo for code. Do not create or invite anyone without confirmation.
- Whether to start on item 1.
