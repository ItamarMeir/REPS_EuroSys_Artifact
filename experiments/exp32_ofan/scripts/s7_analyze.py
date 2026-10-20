#!/usr/bin/env python3
"""usage: s7_analyze.py <dir> <agg> <core>. Summarises S7 runs + ofan per-port counts at the Agg switch owning the failed link."""
import csv, re, subprocess, sys, os, collections
D, agg, core = sys.argv[1], sys.argv[2], sys.argv[3]
S = os.path.dirname(os.path.abspath(__file__))
print("config\tfin\tstarted\tCCT_us\tmean_fct\tp99_fct\ttrims\tdrops\textra\tRTS\trtos\tfast_loss\tecn_acks\tabort")
for t in ["ofan_ok","ofan_fail","ecmpar_fail","reps_fail","ecmp_fail"]:
    if os.path.exists("%s/%s.out" % (D,t)):
        print(subprocess.run([sys.executable, S+"/summarize_run.py", t, "%s/%s.out"%(D,t), "%s/%s.tsv"%(D,t), "1027"], capture_output=True, text=True).stdout.strip())
print("\nfailed-link queues (A->C, C->A) in each run [switch idx per queue-stats i,j]; every packet enqueued behind a dead pipe is lost")
for t in ["ofan_ok","ofan_fail","ecmpar_fail","reps_fail","ecmp_fail"]:
    f = "%s/%s.tsv" % (D,t)
    if not os.path.exists(f): continue
    rows = list(csv.DictReader(open(f), delimiter="\t"))
    ac = [r for r in rows if r["layer"]=="A->C" and r["i"]==agg and r["j"]==core]
    ca = [r for r in rows if r["layer"]=="C->A" and r["i"]==core and r["j"]==agg]
    print(t, "A->C", [(r["data_pkts"], r["hdr_bytes"]) for r in ac], "C->A", [(r["data_pkts"], r["hdr_bytes"]) for r in ca])
    ac_all = sorted(int(r["data_pkts"]) for r in rows if r["layer"]=="A->C")
    print("   A->C data_pkts over all links (sorted):", ac_all[:5], "...", ac_all[-3:])
fc = "%s/ofan_fail_counts.tsv" % D
if os.path.exists(fc):
    sw = "Switch_UpperPod_%s" % agg
    rows = [r for r in csv.DictReader(open(fc), delimiter="\t") if r["switch"] == sw]
    pat = r"US%s->CS\d+" % agg
    dead = "US%s->CS%s" % (agg, core)
    print("\nofan_fail at %s (owner of failed first hop %s):" % (sw, dead))
    to_dead = sum(int(r["count"]) for r in rows if dead + "(" in r["port"])
    print("  packets (all classes) steered to the failed port:", to_dead)
    allports = set()
    for r in csv.DictReader(open("%s/ofan_fail.tsv" % D), delimiter="\t"):
        m = re.search(pat, r["queue"])
        if r["layer"] == "A->C" and m and m.group(0) != dead: allports.add(m.group(0))
    per = collections.defaultdict(lambda: collections.defaultdict(int))
    tot = collections.defaultdict(int)
    for r in rows:
        m = re.search(pat, r["port"])
        per[(r["d"], r["t"])][m.group(0)] += int(r["count"]); tot[(r["class"], m.group(0))] += int(r["count"])
    worst = 0; bad = 0
    for k, pc in per.items():
        c = [pc.get(p, 0) for p in allports]
        worst = max(worst, max(c) - min(c)); bad += (max(c) - min(c) > 1)
    print("  live ports:", sorted(allports), "| (dest,type) keys:", len(per), "| max spread over live ports:", worst, "| keys with spread>1:", bad)
    print("  per-port totals by class:", {k: v for k, v in sorted(tot.items())})
