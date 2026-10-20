#!/usr/bin/env python3
"""Per-layer paper metric from a -log_queue_stats TSV.
max link overload % = (max link data_bytes / mean link data_bytes over the layer - 1) * 100.
Links with zero bytes in the layer are INCLUDED in the mean (a dead link is imbalance).
Usage: link_overload.py <queue_stats.tsv> [more.tsv ...]"""
import csv, sys, collections
LAYERS = ["E->A", "A->C", "C->A", "A->E", "E->H"]
for path in sys.argv[1:]:
    by = collections.defaultdict(list)
    for r in csv.DictReader(open(path), delimiter="\t"):
        by[r["layer"]].append(r)
    print("== %s" % path)
    print("%-5s %6s %12s %12s %10s %12s %7s %7s" % ("layer", "links", "mean_bytes", "max_bytes", "overload%", "maxq_bytes", "trims", "drops"))
    for L in LAYERS:
        rows = by.get(L, [])
        if not rows: continue
        b = [int(r["data_bytes"]) for r in rows]
        mean = sum(b) / len(b)
        ov = (max(b) / mean - 1) * 100 if mean > 0 else float("nan")
        print("%-5s %6d %12.0f %12d %10.2f %12d %7d %7d" % (
            L, len(b), mean, max(b), ov, max(int(r["max_q_bytes"]) for r in rows),
            sum(int(r["trims"]) for r in rows), sum(int(r["drops"]) for r in rows)))
