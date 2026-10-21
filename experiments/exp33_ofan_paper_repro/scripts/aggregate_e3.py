#!/usr/bin/env python3
"""Aggregate E3 runs: data/e3/runs/<part>__<algo>__N<n>__s<seed>.{out,tsv} -> data/e3/runs_summary.csv, data/e3/summary.csv.
CCT = last 'finished at' (us). LB = CCT of <part>__single__N<n>__s1 (single-flow run, same config/volume per host).
inc_pct = (CCT/LB-1)*100. maxq_* = max over all links of max data-queue bytes (queue stats TSV), per layer and overall; pkts = bytes/4160."""
import csv, glob, os, re, sys, collections, math
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "e3")
runs = os.path.join(D, "runs")
fin = re.compile(r"finished at ([0-9.]+) .*? rtos (\d+) freeze_entries (\d+)")
LAYERS = ["E->A", "A->C", "C->A", "A->E", "E->H"]
PKT = 4160
def load(tag):
    out, tsv = os.path.join(runs, tag + ".out"), os.path.join(runs, tag + ".tsv")
    if not (os.path.exists(out) and os.path.exists(tsv)): return None
    t, rtos = [], 0
    for ln in open(out, errors="replace"):
        m = fin.search(ln)
        if m: t.append(float(m.group(1))); rtos += int(m.group(2))
    mq = collections.defaultdict(int); drops = trims = 0
    for r in csv.DictReader(open(tsv), delimiter="\t"):
        mq[r["layer"]] = max(mq[r["layer"]], int(r["max_q_bytes"])); drops += int(r["drops"]); trims += int(r["trims"])
    r = dict(flows=len(t), cct=max(t) if t else float("nan"), rtos=rtos, drops=drops, trims=trims,
             maxq=max(mq.values()) if mq else 0)
    for L in LAYERS: r["q_" + L] = mq.get(L, 0)
    return r
rows = []; lbs = {}
for f in sorted(glob.glob(os.path.join(runs, "*.tsv"))):
    tag = os.path.basename(f)[:-4]
    m = re.match(r"(\w+?)__(\w+)__N(\d+)__s(\d+)$", tag)
    if not m or not os.path.exists(os.path.join(runs, tag + ".done")): continue
    part, algo, n, seed = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
    r = load(tag)
    if not r: continue
    r.update(part=part, algo=algo, N=n, seed=seed)
    if algo == "single": lbs[(part, n)] = r["cct"]
    rows.append(r)
for r in rows:
    lb = lbs.get((r["part"], r["N"]), float("nan")); r["lb"] = lb
    r["inc_pct"] = (r["cct"] / lb - 1) * 100 if lb == lb else float("nan")
    r["maxq_pkts"] = r["maxq"] / PKT
cols = ["part", "algo", "N", "seed", "flows", "cct", "lb", "inc_pct", "rtos", "drops", "trims", "maxq", "maxq_pkts"] + ["q_" + L for L in LAYERS]
with open(os.path.join(D, "runs_summary.csv"), "w", newline="") as o:
    w = csv.writer(o); w.writerow(cols)
    for r in sorted(rows, key=lambda r: (r["part"], r["N"], r["algo"], r["seed"])): w.writerow([r[c] for c in cols])
def ms(v):
    v = [x for x in v if x == x]; n = len(v)
    if not n: return float("nan"), float("nan"), 0
    mu = sum(v) / n; sd = math.sqrt(sum((x - mu) ** 2 for x in v) / (n - 1)) if n > 1 else 0.0
    return mu, sd / math.sqrt(n), n
g = collections.defaultdict(list)
for r in rows:
    if r["algo"] != "single": g[(r["part"], r["N"], r["algo"])].append(r)
sc = ["part", "N", "algo", "n_seeds", "flows_min", "lb_us", "cct_mean", "cct_sem", "inc_mean", "inc_sem", "maxq_pkts_mean", "maxq_pkts_sem", "maxq_pkts_max", "rtos_mean", "drops_mean", "trims_mean"]
with open(os.path.join(D, "summary.csv"), "w", newline="") as o:
    w = csv.writer(o); w.writerow(sc)
    for k in sorted(g):
        v = g[k]; c = ms([r["cct"] for r in v]); i = ms([r["inc_pct"] for r in v]); q = ms([r["maxq_pkts"] for r in v])
        w.writerow(list(k[:2]) + [k[2], len(v), min(r["flows"] for r in v), "%.3f" % v[0]["lb"], "%.3f" % c[0], "%.3f" % c[1],
                   "%.3f" % i[0], "%.3f" % i[1], "%.2f" % q[0], "%.2f" % q[1], "%.2f" % max(r["maxq_pkts"] for r in v),
                   "%.1f" % (sum(r["rtos"] for r in v) / len(v)), "%.1f" % (sum(r["drops"] for r in v) / len(v)), "%.1f" % (sum(r["trims"] for r in v) / len(v))])
print(open(os.path.join(D, "summary.csv")).read())
