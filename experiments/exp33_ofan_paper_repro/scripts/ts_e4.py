#!/usr/bin/env python3
"""Reduce one -log_link run dir (port/port<switch>_.txt: 't_ns,egress_queue,pktid' per switch-forward event) to a per-1us time series.
usage: ts_e4.py <rundir> <out.csv>.  Reconstruction (no sim change): per egress queue, FIFO departure d_i = max(a_i, d_{i-1}) + 4150 B*8/800 Gb/s (41.5 ns);
busy time per bin -> link utilisation; packets in system (arrived, not yet departed, incl. the one in service) * 4150 B -> queue bytes.
Valid because these runs have 0 trims / 0 drops (all packets > 100 B are full 4150 B data packets) and 1 priority class matters only for headers.
Columns per 1 us bin: t_us, util_<layer> (mean busy fraction over the links of that layer, %; E->H not logged), util_max (max over fabric links, %),
maxq_all_kb / maxq_<layer>_kb (max queue over queues of that layer, KB=1000 B).  Layers by queue name: LS->US ('E>A'), US->LS ('A>E'), US->CS ('A>C'), CS->US ('C>A')."""
import sys, os, re, glob, numpy as np
d, out = sys.argv[1], sys.argv[2]; SVC = 4150 * 8 / 800.0   # ns
ev = {}   # queue -> arrival ns list
for f in glob.glob(f"{d}/port/*.txt"):
    for l in open(f):
        t, rest = l.rstrip("\n").split(",", 1); q = rest.rsplit(",", 1)[0]; ev.setdefault(q, []).append(int(t))
def layer(q):
    m = re.search(r"\)(\w+?)(\d+)->(\w+?)(\d+)\(", q)
    return (m.group(1), m.group(3)) if m else ("?", "?")
LN = {("LS", "US"): "EA", ("US", "LS_"): "AE", ("US", "CS"): "AC", ("CS", "US"): "CA"}
names = sorted(ev); lay = {}
for q in names:
    a, b = layer(q); lay[q] = LN.get((a, b), "other")
tmax = int(max(max(v) for v in ev.values()) / 1000) + 40; NB = tmax
util = {}; qmax = {}
for q in names:
    a = np.sort(np.array(ev[q], dtype=float)); n = len(a); dep = np.empty(n); prev = -1e18
    for i in range(n): prev = max(a[i], prev) + SVC; dep[i] = prev
    st = dep - SVC; bu = np.zeros(NB)   # busy intervals [st, dep)
    for s0, e0 in zip(st, dep):
        b0 = int(s0 // 1000); b1 = int(e0 // 1000)
        if b0 == b1: bu[b0] += e0 - s0
        else:
            bu[b0] += (b0 + 1) * 1000 - s0; bu[b1] += e0 - b1 * 1000
            if b1 - b0 > 1: bu[b0 + 1:b1] += 1000
    util[q] = 100 * bu / 1000
    # queue depth max within each bin: sample at every arrival (depth right after arrival) and bin edges
    k = np.searchsorted(dep, a, side="right")   # departed by arrival time
    depth = (np.arange(n) + 1 - k)              # incl. the arriving packet
    qm = np.zeros(NB); bi = (a // 1000).astype(int)
    np.maximum.at(qm, bi, depth * 4150.0 / 1000)
    qmax[q] = qm
L = ["EH", "EA", "AE", "AC", "CA"]; cols = {}
cols["t_us"] = np.arange(NB) + 0.5
F = [q for q in names if lay[q] in ("EA", "AE", "AC", "CA")]
for l in L[1:]:   # mean busy fraction over all links of the layer (E->H queues are NOT in the -log_link output: single-route last hop bypasses the logger)
    qs = [util[q] for q in names if lay[q] == l]; cols["util_%s" % l] = np.mean(qs, axis=0) if qs else np.zeros(NB)
cols["util_max"] = np.max([util[q] for q in F], axis=0) if F else np.zeros(NB)
cols["maxq_all_kb"] = np.max([qmax[q] for q in names], axis=0)
for l in L:
    qs = [qmax[q] for q in names if lay[q] == l]; cols["maxq_%s_kb" % l] = np.max(qs, axis=0) if qs else np.zeros(NB)
with open(out, "w") as f:
    f.write(",".join(cols) + "\n")
    for i in range(NB): f.write(",".join("%.3f" % cols[c][i] for c in cols) + "\n")
print("ports", len(names), {l: sum(1 for q in names if lay[q] == l) for l in L + ["other"]}, "bins", NB)
