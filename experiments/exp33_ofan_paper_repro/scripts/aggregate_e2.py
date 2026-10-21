#!/usr/bin/env python3
"""Aggregate E2 runs -> data/e2/e2_runs.csv (one row per run) and data/e2/e2_summary.csv (mean, 95% CI over seeds).
Usage: aggregate_e2.py [data/e2 dir]  (default: ../data/e2 relative to this script).
Tags: <fig>__<strat>__<wl>_<size>_<mtu>_s<seed>   and   single__<fam>_<wl>_<size>_<mtu>
CCT = last 'finished at' (us). LB (own) = single-flow CCT of the same family+size+mtu (ATA: single flow of (N-1)*size bytes).
LB (best) = min over mtu of the own LB for the same size/family (P-independent bound used for Fig 8's sweet spot)."""
import csv, glob, math, os, re, sys, collections
import pandas as pd
try:
    from scipy import stats as sps
    tcrit = lambda n: sps.t.ppf(0.975, n - 1)
except Exception:
    T = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36}
    tcrit = lambda n: T.get(n - 1, 1.96)
d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "e2")
runs = os.path.join(d, "runs")
fin = re.compile(r"finished at ([0-9.]+) .*? rtos (\d+) freeze_entries (\d+)")
LAYERS = ["E->A", "A->C", "C->A", "A->E", "E->H"]

def load(tag):
    out, tsv = os.path.join(runs, tag + ".out"), os.path.join(runs, tag + ".tsv")
    if not os.path.exists(os.path.join(runs, tag + ".done")) or not os.path.exists(out): return None
    t, rt, fz = [], 0, 0
    for ln in open(out, errors="replace"):
        m = fin.search(ln)
        if m: t.append(float(m.group(1))); rt += int(m.group(2)); fz += int(m.group(3))
    r = dict(flows=len(t), cct=max(t) if t else float("nan"), rtos=rt, freeze=fz, trims=0, drops=0)
    for L in LAYERS: r["maxq_" + L] = float("nan")
    if os.path.exists(tsv):
        by = collections.defaultdict(list)
        for x in csv.DictReader(open(tsv), delimiter="\t"): by[x["layer"]].append(x)
        for L, rows in by.items():
            r["trims"] += sum(int(x["trims"]) for x in rows); r["drops"] += sum(int(x["drops"]) for x in rows)
            if L in LAYERS: r["maxq_" + L] = max(int(x["max_q_bytes"]) for x in rows)
    return r

single = {}
rows = []
for f in sorted(glob.glob(os.path.join(runs, "*.done"))):
    tag = os.path.basename(f)[:-5]
    r = load(tag)
    if not r: continue
    if tag.startswith("single__"):
        fam, wl, size, mtu = re.match(r"single__(.+?)_(perm|ata\d+)_(\d+)_(\d+)$", tag).groups()
        single[(fam, wl, int(size), int(mtu))] = r["cct"]; continue
    m = re.match(r"(f7a|f7b|f8|trim)__(.+?)__(perm|ata\d+)_(\d+)_(\d+)_s(\d+)$", tag)
    if not m: continue
    fig, st, wl, size, mtu, seed = m.groups(); size, mtu, seed = int(size), int(mtu), int(seed)
    n = int(re.sub(r"\D", "", wl)) if wl.startswith("ata") else 432
    r.update(fig=fig, strat=st, wl=wl, size=size, mtu=mtu, seed=seed, expected=(n * (n - 1) if wl.startswith("ata") else n), tag=tag)
    rows.append(r)
def fam(st): return "ofan" if st.startswith("ofan") else ("reps" if st.startswith("reps") else "ar_q20000")
for r in rows:
    mult = (int(re.sub(r"\D", "", r["wl"])) - 1) if r["wl"].startswith("ata") else 1
    r["lb_own"] = single.get((fam(r["strat"]), r["wl"], r["size"] * mult, r["mtu"]), float("nan"))
    r["inc_own"] = (r["cct"] / r["lb_own"] - 1) * 100
    best = [v for (f, w, s, m_), v in single.items() if f == fam(r["strat"]) and w == r["wl"] and s == r["size"] * mult]
    r["lb_best"] = min(best) if best else float("nan")
    r["inc_best"] = (r["cct"] / r["lb_best"] - 1) * 100
    r["complete"] = r["flows"] == r["expected"]
df = pd.DataFrame(rows)
df.to_csv(os.path.join(d, "e2_runs.csv"), index=False)
def ci(x):
    x = x.dropna(); n = len(x)
    return pd.Series(dict(mean=x.mean(), ci=(tcrit(n) * x.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan"), n=n))
g = df.groupby(["fig", "wl", "strat", "size", "mtu"])
agg = g.apply(lambda s: pd.Series(dict(
    n=len(s), complete=int(s.complete.sum()), inc_own=s.inc_own.mean(), inc_own_ci=ci(s.inc_own)["ci"],
    inc_best=s.inc_best.mean(), inc_best_ci=ci(s.inc_best)["ci"], cct=s.cct.mean(), lb_own=s.lb_own.mean(),
    rtos=s.rtos.mean(), freeze=s.freeze.mean(), trims=s.trims.mean(), drops=s.drops.mean(), maxq_EA=s["maxq_E->A"].mean(),
    maxq_CA=s["maxq_C->A"].mean()))).reset_index()
agg.to_csv(os.path.join(d, "e2_summary.csv"), index=False)
print(agg.to_string(float_format=lambda x: "%.2f" % x))
