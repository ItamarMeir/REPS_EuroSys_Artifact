# C1: claim 1 - under backlog, B>2 does not matter

**Claim** (meeting summary l.7; Gabriel 36:00-40:57; pending l.36): with the sender always backlogged, at most 1-2 valid EVs sit in the REPS buffer at any moment, so buffer size beyond 2 has no effect.

**Why it matters**: if true, B only changes behaviour when the buffer is not backlogged or in Freezing Mode. Motivates C2-C4.

**Scenario**: healthy fabric and degraded fabric (exp30 a2 links), always backlogged (long flows, sender never idle). Fabric `fat_tree_1024_1os_2t_400g`, `-use_srv6 -paths 32`, MPRDMA, `-load_balancing_algo freezing`, `-reps_buffer_size` in {1,2,4,8,16,32}.

**Measurement** (decided, task l.44-45):
1. Valid count = `fresh` column of `-log_reps_events` (= `getNumberFreshEntropies()`; `isValid` set on clean ACK, cleared on pop, `buffer_reps.cpp:35-69`). Filter `src_id`; sample every ~1000 rows across the run (millions of packets). Report the distribution (histogram per B), not only the mean.
2. Slow-motion: one ~500-packet window in steady state, viewed in `experiments/tools/reps_event_viewer.py` (Play, speed slider) to see which slots turn valid and when.
3. One ToR0 host and one non-ToR0 host (hosts are uniform within each group).

**Trace setup**: `-log_reps_events` with `-log_reps_events_src <id>` and `-log_reps_events_window <t0> <t1>` (ns) around steady state. Full-run logging overflows the 200000-row default (`uec.cpp:354`).

**Pass / fail**: claim holds if, for B>=2, the valid-count distribution is concentrated at 0-2 for >95% of samples and does not shift with B. Report the distribution per B on one Y axis.

**Open risk**: `fresh` counts clean ACKs still in the buffer. Confirm with a 50-row trace of one flow before trusting the series (general plan work item 1).
