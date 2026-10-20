#!/usr/bin/env python3
"""S3 gate: per (switch, destination key d, type t) the packet counts over the
PHYSICAL egress queues of that switch must differ by <= 1 (Ofan round robin),
and t=1 (small packets) must be present. Input: -log_ofan_counts CSV."""
import csv, sys, collections
f = sys.argv[1]
tol = int(sys.argv[2]) if len(sys.argv) > 2 else 1
per = collections.defaultdict(lambda: collections.defaultdict(int))
cls = collections.defaultdict(int)
ports_of = collections.defaultdict(set)
for r in csv.DictReader(open(f), delimiter="	"):
    c = int(r["count"])
    per[(r["switch"], r["d"], r["t"])][r["port"]] += c
    ports_of[r["switch"]].add(r["port"])
    cls[(r["t"], r["class"])] += c
bad = 0
for (sw, d, t), pc in sorted(per.items()):
    # include ports of this switch that got zero packets for this key
    counts = [pc.get(p, 0) for p in ports_of[sw]]
    if max(counts) - min(counts) > tol:
        bad += 1
        print("IMBALANCE", sw, "d=%s t=%s" % (d, t), sorted(counts))
print("keys checked:", len(per), "imbalanced:", bad)
print("by (t,class):", dict(cls))
t1 = sum(v for (t, _), v in cls.items() if t == "1")
print("small-packet (t=1) total:", t1)
ok = bad == 0 and t1 > 0
print("S3", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
