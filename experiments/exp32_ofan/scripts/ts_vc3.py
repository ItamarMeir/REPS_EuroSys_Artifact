#!/usr/bin/env python3
"""Reduce the htsim queue samplers to per-layer AVERAGE queue size (KB) per 1 us bin.
usage: ts_vc3.py <tor.csv> <core.csv> <cdl.csv> <out.csv>
tor.csv  (-log_tor_queues, 1 us)   E->A queues, all of them (time_us,tor,agg,bytes)
core.csv (-log_core_queues, 1 us)  A->C queues, all of them
cdl.csv  (-log_core_downlink_queues, 0.2 us) C->A queues of the FIRST 16 cores only (sim constant), averaged over those
Average = mean over all sampled queues of the layer (idle queues count as 0). KB = 1000 B. A->E and E->H are not sampled by the simulator."""
import sys, csv, collections
def load(p):
    s = collections.defaultdict(lambda: [0, 0])
    for r in csv.DictReader(open(p)):
        b = int(float(r["time_us"])); k = s[b]; k[0] += int(r["bytes"]); k[1] += 1
    return s
tor, core, cdl = load(sys.argv[1]), load(sys.argv[2]), load(sys.argv[3])
ts = sorted(set(tor) | set(core) | set(cdl))
with open(sys.argv[4], "w") as f:
    f.write("t_us,avgq_EA_kb,avgq_AC_kb,avgq_CA_kb\n")
    for t in ts:
        f.write("%d,%.3f,%.3f,%.3f\n" % ((t,) + tuple((d[t][0] / d[t][1] / 1000 if t in d else 0.0) for d in (tor, core, cdl))))
