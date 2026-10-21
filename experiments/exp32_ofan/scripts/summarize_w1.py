#!/usr/bin/env python3
"""Summarise W1 runs: CCT (max flow finish), max queue over core layers, trims/drops. Usage: summarize_w1.py <w1 dir>"""
import csv, glob, os, re, sys
d = sys.argv[1]; rows = []
for tsv in sorted(glob.glob(os.path.join(d, "runs", "*.tsv"))):
    tag = os.path.basename(tsv)[:-4]; st, f, sz, rho = tag.split("__")
    out = open(tsv[:-4] + ".out", errors="ignore").read()
    fin = [float(x) for x in re.findall(r"finished at ([0-9.]+)", out)]
    q = {}; tr = dr = 0
    for r in csv.DictReader(open(tsv), delimiter="\t"):
        q[r["layer"]] = max(q.get(r["layer"], 0), int(r["max_q_bytes"])); tr += int(r["trims"]); dr += int(r["drops"])
    rows.append((st, f, int(sz[2:]), float(rho[3:]), max(fin) if fin else float("nan"), len(fin),
                 max(q.get("A->C", 0), q.get("C->A", 0)) / 4160.0, q.get("E->A", 0) / 4160.0, tr, dr))
rows.sort()
print("strat fail size rho CCT_us nfin maxq_core_pkts maxq_EA_pkts trims drops")
for r in rows: print("%s %s %d %.2f %.2f %d %.1f %.1f %d %d" % r)
