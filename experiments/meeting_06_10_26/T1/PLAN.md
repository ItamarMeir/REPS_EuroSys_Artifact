# T1: sanity check - FCT proportional to lost bandwidth

**Source**: pending l.33-34 (verify the sanity experiment shows FCT proportional to the fraction of links that fell; start with all links healthy and half healthy; FCT should about double when bandwidth halves, up to CC effects); Chen 87:19 ("if twice as many links fall, FCT should be twice as long"); Gabriel 87:41 (check this first).

**Scenario**: two arms, same fabric and workload, B=8, MPRDMA, trim off:
- arm A: all links healthy
- arm B: bandwidth halved on the affected links (exp28 degradation knob: `-failed` with `-down_ratio`, see exp28 README; exp30 A1 n=32 r=0.5 is already near this)

**Existing data**: exp30 A1 n=32, r=0.5: p50 97 -> 180 us (4 MiB), p99 356 -> 738 us (16 MiB), about 1.9-2.1x. Check whether this already satisfies the check before any new run.

**Measurements**: FCT ratio arm B / arm A with CI over seeds (>=3).

**Pass / fail**: ratio within about 1.8-2.2x (CC effects allowed). Outside that, debug before any B conclusion.
