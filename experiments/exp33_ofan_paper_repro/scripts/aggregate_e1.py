#!/usr/bin/env python3
"""E1 aggregator. Reads <dir>/runs/<strat>__rho<r>__s<seed>.{out,tsv} (+ single__rho<r>) -> <dir>/e1_runs.csv (tidy, per run)
and <dir>/e1_summary.csv (mean, SEM per strat x rho). Usage: aggregate_e1.py [data/e1 dir]
Definitions (per run):
 cct_us      = last 'finished at'.   D_us = single-flow CCT(rho) - size/(rho*C)  (fixed path latency, ~6.4us)
 fabric links = layers E->A, A->C, C->A, A->E (E->H = host downlink, excluded; every host receives 1 flow).
 ref_bytes   = mean data_bytes over E->H links (= bytes of one flow incl. headers).
 util_pct    = 100 * (max fabric-link data_bytes / ref_bytes) * (size/C) / (cct - D).  An unloaded run with a perfectly
               balanced fabric gives util = rho*100 (that is the 'ideal' line).  Busiest link's wire-busy fraction over the
               busy period [D, cct].
 util_eff_pct = 100 * (size/C)/(cct - D): completion-rate efficiency (all links, = rho*100 when ideal; saturates below load when CCT lags).
 bal_pct     = 100 * rho * mean fabric link bytes / max fabric link bytes (per layer, min over layers) : balance-only efficiency.
 maxq_kb     = max over ALL switch egress queues (all 5 layers) of max data-queue occupancy, KB=1000 B."""
import csv, glob, os, re, sys, collections, math
d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "e1")
runs = os.path.join(d, "runs"); SIZE = 1048576; C = 800e9 / 8  # bytes/s
FAB = ["E->A", "A->C", "C->A", "A->E"]; ALL = FAB + ["E->H"]
fin = re.compile(r"finished at ([0-9.]+) .*? rtos (\d+) freeze_entries (\d+)")
def parse(tag):
    out, tsv = os.path.join(runs, tag + ".out"), os.path.join(runs, tag + ".tsv")
    if not (os.path.exists(out) and os.path.exists(tsv)): return None
    t, rto = [], 0
    for ln in open(out, errors="replace"):
        m = fin.search(ln)
        if m: t.append(float(m.group(1))); rto += int(m.group(2))
    by = collections.defaultdict(list)
    for r in csv.DictReader(open(tsv), delimiter="\t"): by[r["layer"]].append(r)
    return dict(t=t, rto=rto, by=by)
single = {}
for f in glob.glob(os.path.join(runs, "single__rho*.tsv")):
    tag = os.path.basename(f)[:-4]; p = parse(tag)
    if p and p["t"]: single[tag.split("rho")[1]] = max(p["t"])
rows = []
for f in sorted(glob.glob(os.path.join(runs, "*__rho*__s*.tsv"))):
    tag = os.path.basename(f)[:-4]; st, rs, ss = tag.split("__"); rho = float(rs[3:]); seed = int(ss[1:])
    p = parse(tag)
    if not p or not p["t"]: continue
    cct = max(p["t"]); sl = single.get(rs[3:], float("nan"))
    D = sl - SIZE / (rho * C) * 1e6
    by = p["by"]
    ref = sum(int(r["data_bytes"]) for r in by["E->H"]) / len(by["E->H"])
    fb = [int(r["data_bytes"]) for L in FAB for r in by[L]]
    util = 100 * (max(fb) / ref) * (SIZE / C * 1e6) / (cct - D)
    util_eff = 100 * (SIZE / C * 1e6) / (cct - D)
    bal = 100 * rho * min((sum(int(r["data_bytes"]) for r in by[L]) / len(by[L])) / max(int(r["data_bytes"]) for r in by[L]) for L in FAB)
    row = dict(strat=st, rho=rho, seed=seed, flows=len(p["t"]), cct_us=cct, single_us=sl, D_us=D,
               cct_inc_pct=(cct / sl - 1) * 100, util_pct=util, util_eff_pct=util_eff, bal_pct=bal,
               maxq_kb=max(int(r["max_q_bytes"]) for L in ALL for r in by[L]) / 1000,
               rtos=p["rto"], trims=sum(int(r["trims"]) for L in ALL for r in by[L]),
               drops=sum(int(r["drops"]) for L in ALL for r in by[L]))
    for L in ALL: row["maxq_kb_" + L] = max(int(r["max_q_bytes"]) for r in by[L]) / 1000
    rows.append(row)
if not rows: sys.exit("no runs")
cols = list(rows[0].keys())
with open(os.path.join(d, "e1_runs.csv"), "w", newline="") as o:
    w = csv.DictWriter(o, cols); w.writeheader(); w.writerows(rows)
# t 97.5% quantile, df=n-1 (small table) for reference; SEM reported
g = collections.defaultdict(list)
for r in rows: g[(r["strat"], r["rho"])].append(r)
metrics = ["cct_us", "cct_inc_pct", "util_pct", "util_eff_pct", "bal_pct", "maxq_kb", "rtos", "trims", "drops"] + ["maxq_kb_" + L for L in ALL]
with open(os.path.join(d, "e1_summary.csv"), "w", newline="") as o:
    w = csv.writer(o); w.writerow(["strat", "rho", "n"] + [m + s for m in metrics for s in ("_mean", "_sem")])
    for (st, rho), rs in sorted(g.items()):
        v = [st, rho, len(rs)]
        for m in metrics:
            x = [r[m] for r in rs]; mu = sum(x) / len(x)
            sem = (sum((a - mu) ** 2 for a in x) / (len(x) - 1)) ** 0.5 / math.sqrt(len(x)) if len(x) > 1 else 0.0
            v += ["%.4f" % mu, "%.4f" % sem]
        w.writerow(v)
print("wrote", len(rows), "runs;", len(g), "cells")
