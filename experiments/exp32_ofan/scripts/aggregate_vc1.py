#!/usr/bin/env python3
"""Aggregate V-C part 1: overload % per layer per strategy (mean +- SEM over seeds) from data/vc/runs/<strat>_s<seed>.tsv.
Also max queue (packets of 4160 B) per layer. Prints markdown and writes data/vc/vc1_summary.csv"""
import csv, glob, os, re, statistics as st, collections
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "vc")
L = ["E->A", "A->C", "C->A", "A->E"]
res = collections.defaultdict(lambda: collections.defaultdict(list)); mq = collections.defaultdict(lambda: collections.defaultdict(list))
drops = collections.defaultdict(int)
for p in sorted(glob.glob(D + "/runs/*_s[0-9]*.tsv")):
    m = re.match(r"(.+)_s(\d+)\.tsv", os.path.basename(p)); s = m.group(1)
    by = collections.defaultdict(list)
    for r in csv.DictReader(open(p), delimiter="\t"): by[r["layer"]].append(r)
    for l in L:
        b = [int(r["data_bytes"]) for r in by[l]]; mean = sum(b) / len(b)
        res[s][l].append((max(b) / mean - 1) * 100); mq[s][l].append(max(int(r["max_q_bytes"]) for r in by[l]) / 4160)
    drops[s] += sum(int(r["drops"]) for l in by for r in by[l])
def ms(x): return (st.mean(x), st.stdev(x) / len(x) ** .5 if len(x) > 1 else 0.0)
order = ["ofan", "drb", "drb_hash", "drb_src", "rr_fixed", "jsq", "ar", "ar_q193", "rsq", "rps", "reps"]
rows = []
print("| strategy | n | " + " | ".join(L) + " |\n|---|---|" + "---|" * 4)
for s in order:
    if s not in res: continue
    c = [ms(res[s][l]) for l in L]; rows.append([s, len(res[s]["E->A"])] + [x for t in c for x in t])
    print("| %s | %d | " % (s, len(res[s]["E->A"])) + " | ".join("%.1f +- %.1f" % t for t in c) + " |")
print("\nmax queue (pkts, mean over seeds)\n| strategy | " + " | ".join(L) + " | drops |\n|---|" + "---|" * 5)
for s in order:
    if s in mq: print("| %s | " % s + " | ".join("%.1f" % st.mean(mq[s][l]) for l in L) + " | %d |" % drops[s])
with open(D + "/vc1_summary.csv", "w") as f:
    w = csv.writer(f); w.writerow(["strat", "n"] + [a + b for l in L for a, b in ((l + "_mean", ""), (l + "_sem", ""))]); [w.writerow(r) for r in rows]
