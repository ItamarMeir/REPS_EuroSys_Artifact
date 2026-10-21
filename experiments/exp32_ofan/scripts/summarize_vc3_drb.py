#!/usr/bin/env python3
"""Part-3 summary: plateau (mean over t in [10,40) us) of per-layer avg queue (KB) and per-layer max queue (pkts of 4160 B). usage: summarize_vc3_drb.py <ts_dir>"""
import csv, sys, glob, os, re, collections
D = sys.argv[1]; V = ["ofan", "drb", "drb_hash", "drb_rand", "drb_af", "drb_af_rand"]
print("| variant | seed | E->A KB | A->C KB | C->A KB | max q E->A/A->C/C->A/A->E/E->H (pkts) |\n|---|---|---|---|---|---|")
for v in V:
    for s in (1, 2):
        p = "%s/%s_n1024_s%d_series.csv" % (D, v, s)
        if not os.path.exists(p): continue
        rows = [r for r in csv.DictReader(open(p)) if 10 <= int(r["t_us"]) < 40]
        pl = [sum(float(r[k]) for r in rows) / len(rows) for k in ("avgq_EA_kb", "avgq_AC_kb", "avgq_CA_kb")]
        mq = collections.OrderedDict((l, 0) for l in ("E->A", "A->C", "C->A", "A->E", "E->H"))
        for r in csv.DictReader(open("%s/%s_n1024_s%d_qs.tsv" % (D, v, s)), delimiter="\t"): mq[r["layer"]] = max(mq[r["layer"]], int(r["max_q_bytes"]))
        print("| %s | %d | %.1f | %.1f | %.1f | %s |" % (v, s, *pl, " / ".join(str(round(x / 4160)) for x in mq.values())))
