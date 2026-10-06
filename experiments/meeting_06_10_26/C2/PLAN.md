# C2: claim 2 - in Freezing Mode, larger B drains slower

**Claim** (open question l.26; Gabriel 55:16-56:14, 90:05; pending l.36; Gabriel 72:18 "force the system to rely only on its buffers and measure valid/stale/random"): once frozen, a larger buffer takes longer to clear its stale entries, so small B recovers faster.

**Known, not re-tested**: freeze fires with trim off under congested degradation. Established by exp30 Part A run counts (trim off: 4 MiB n=4 15/24 runs; a2 90-95% 23-24/24 runs). Those runs are the baseline here.

**Scenario**: exp30 a2 (90/95% slowdown on ToR0 links), 4 MiB, trim off. B in {1,2,4,8,16,32}. Dead-path contrast (exp30 Part B, F=16) is a second scenario inside this row, reused from existing data unless missing.

**Measurements**:
1. Per-packet split of SEND/RTX/RTS (task l.40): valid / stale-in-freezing / random, plus explore as a fourth bucket. DUAL algos carry `ev_src` natively. FREEZING does not (byte-identical trace rule): derive offline from the previous row of the same `src_id`, reading slot `frozen_head`; valid if `isValid`, else stale. Validate against one dual-window arm (native labels; 100% match required). Add the check to `experiments/tools/test_reps_event_viewer.py`.
2. Drain metric: after each FREEZE row, track stale fraction among occupied slots vs sends since freeze. Report sends until stale fraction = 0 or UNFREEZE, per B.
3. FCT: ToR0 max plus p50/p95/p99 and stuck-past-`-end` count.

**Trace windows**: `-log_reps_events_window` around the first freeze per host (bounds from the `started freezing` stdout lines).

**Pass / fail**: claim holds if drain sends increase monotonically with B. A null result is acceptable and must be reported as such.

**Note**: Gabriel's remark that the effect may only show at large B is tested in C3.
