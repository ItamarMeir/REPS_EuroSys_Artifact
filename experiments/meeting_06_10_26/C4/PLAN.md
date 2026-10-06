# C4: does claim 1 hold without constant backlog? (bursty sender)

**Source**: pending l.35 (test whether bursty traffic changes the effect of buffer size); open question l.30 (does the 1-2 valid EVs claim hold when send rate is not always above ACK rate); Chen 57:44 ("maybe we need a bursty process, not always backlogged"), 64:22; Chen 61:09 (randomly pause between packets).

**Why**: C1 and C2 are all backlogged. Chen's point: a non-backlogged sender may let good EVs accumulate, changing what B does.

**Scenario**: on/off source (random bursts and gaps) on healthy fabric, B in {2,8}. Start with 2 and 8; widen only if an effect appears.

**Implementation**: no bursty generator found yet in the repo. Check `experiments/workloads/` first (work item). If absent, prefer a generator producing on/off `.cm` (connection-matrix) start times or sizes, which needs no C++ change. If a C++ change is needed, it gets an ADDED banner and a `MODIFICATIONS.md` row.

**Measurements**: valid-count distribution (C1 method) during bursts and gaps separately; FCT.

**Pass / fail**: if valid count rises above 2 during gaps and B>2 then changes FCT, claim 1 is limited to backlog. Otherwise claim 1 extends to bursty traffic.
