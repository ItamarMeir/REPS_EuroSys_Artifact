#!/usr/bin/env python3
"""Per-layer max link overload over LIVE links + the dead links' own bytes (static Agg<->Core failure).
usage: link_overload_valid.py <agg> <core> <label=queue_stats.tsv> ...
overload% = (max live-link data_bytes / mean live-link data_bytes - 1)*100; dead links (A->C agg->core, C->A core->agg) are excluded
from the mean and reported separately (data_bytes, data_pkts, drops that landed on them)."""
import csv, sys, collections
agg, core = sys.argv[1], sys.argv[2]
LAY = ["E->A", "A->C", "C->A", "A->E", "E->H"]
for a in sys.argv[3:]:
    lab, path = a.split("=", 1)
    by = collections.defaultdict(list); dead = []
    for r in csv.DictReader(open(path), delimiter="\t"):
        isd = (r["layer"] == "A->C" and r["i"] == agg and r["j"] == core) or (r["layer"] == "C->A" and r["i"] == core and r["j"] == agg)
        (dead if isd else by[r["layer"]]).append(r)
    print("== %s" % lab)
    for L in LAY:
        rows = by.get(L, [])
        if not rows: continue
        b = [int(x["data_bytes"]) for x in rows]; m = sum(b) / len(b)
        print("  %-5s live_links=%3d mean=%10.0f max=%9d overload=%7.2f%% maxq=%6d trims=%d drops=%d" % (L, len(b), m, max(b), (max(b) / m - 1) * 100 if m else float("nan"),
              max(int(x["max_q_bytes"]) for x in rows), sum(int(x["trims"]) for x in rows), sum(int(x["drops"]) for x in rows)))
    for x in dead:
        print("  DEAD %s %s,%s: data_bytes=%s data_pkts=%s hdr_bytes=%s drops=%s trims=%s" % (x["layer"], x["i"], x["j"], x["data_bytes"], x["data_pkts"], x["hdr_bytes"], x["drops"], x["trims"]))
