#!/usr/bin/env python3
"""S5 summary: reads <dir>/runs/<strat>__<wl>_<m>mb.{out,tsv}; writes <dir>/summary.tsv and summary.md.
Usage: summarize_s5.py [data/s5 dir]   (default: ../data/s5 relative to this script)
CCT = last 'finished at' (us). LB = CCT of the single-flow run with the same strategy+size.
maxq columns = max over all links of a layer of the data(low)-queue max occupancy, in 4150 B packets (and raw bytes)."""
import csv, glob, os, re, sys, collections
PKT = 4150
LAYERS = ["E->A", "A->C", "C->A", "A->E", "E->H"]
d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "s5")
runs = os.path.join(d, "runs")
fin = re.compile(r"finished at ([0-9.]+) .*? rtos (\d+) freeze_entries (\d+)")

def load(tag):
    out, tsv = os.path.join(runs, tag + ".out"), os.path.join(runs, tag + ".tsv")
    if not (os.path.exists(out) and os.path.exists(tsv)): return None
    times, rtos, fz = [], 0, 0
    for ln in open(out, errors="replace"):
        m = fin.search(ln)
        if m: times.append(float(m.group(1))); rtos += int(m.group(2)); fz += int(m.group(3))
    by = collections.defaultdict(list)
    for r in csv.DictReader(open(tsv), delimiter="\t"): by[r["layer"]].append(r)
    r = dict(flows=len(times), cct=max(times) if times else float("nan"), rtos=rtos, freeze=fz)
    for L in LAYERS:
        rows = by.get(L, [])
        if not rows: continue
        b = [int(x["data_bytes"]) for x in rows]; mean = sum(b) / len(b)
        r[L] = dict(maxq=max(int(x["max_q_bytes"]) for x in rows), maxq_tot=max(int(x["max_q_total_bytes"]) for x in rows),
                    ov=(max(b) / mean - 1) * 100 if mean else float("nan"),
                    trims=sum(int(x["trims"]) for x in rows), drops=sum(int(x["drops"]) for x in rows))
    return r

rows = []
for f in sorted(g for g in glob.glob(os.path.join(runs, "*__*.tsv")) if ".counts." not in g):
    tag = os.path.basename(f)[:-4]
    s, rest = tag.split("__"); w, m = rest.rsplit("_", 1); m = int(m[:-2])
    if w == "single": continue
    r = load(tag); lb = load("%s__single_%dmb" % (s, m))
    if not r: continue
    r.update(strat=s, wl=w, m=m, lb=lb["cct"] if lb else float("nan"))
    r["inc"] = (r["cct"] / r["lb"] - 1) * 100 if lb else float("nan")
    r["trims"] = sum(r[L]["trims"] for L in LAYERS if L in r); r["drops"] = sum(r[L]["drops"] for L in LAYERS if L in r)
    rows.append(r)
order = {"ofan": 0, "ar": 1, "reps": 2, "reps_dl": 3}
rows.sort(key=lambda r: (r["wl"], r["m"], order.get(r["strat"], 9)))
hdr = ["wl", "m_MB", "strat", "flows", "cct_us", "lb_us", "cct_inc_pct", "rtos", "freeze_entries", "trims", "drops"]
for L in LAYERS: hdr += ["maxq_pkts_" + L, "maxq_B_" + L, "ovl_pct_" + L]
with open(os.path.join(d, "summary.tsv"), "w") as o:
    o.write("\t".join(hdr) + "\n")
    for r in rows:
        v = [r["wl"], r["m"], r["strat"], r["flows"], "%.2f" % r["cct"], "%.2f" % r["lb"], "%.2f" % r["inc"], r["rtos"], r["freeze"], r["trims"], r["drops"]]
        for L in LAYERS:
            x = r.get(L); v += ["%.2f" % (x["maxq"] / PKT), x["maxq"], "%.2f" % x["ov"]] if x else ["", "", ""]
        o.write("\t".join(str(t) for t in v) + "\n")
with open(os.path.join(d, "summary.md"), "w") as o:
    for w in sorted({r["wl"] for r in rows}):
        o.write("\n### %s\n\n| m MB | strat | CCT us | +%% over LB | maxq pkts E->A / A->C / C->A / A->E / E->H | ovl %% E->A / A->C / C->A / A->E | rtos | freeze | trims | drops |\n|---|---|---|---|---|---|---|---|---|---|\n" % w)
        for r in rows:
            if r["wl"] != w: continue
            q = " / ".join("%.1f" % (r[L]["maxq"] / PKT) for L in LAYERS)
            ov = " / ".join("%.1f" % r[L]["ov"] for L in LAYERS[:4])
            o.write("| %d | %s | %.1f | %.1f | %s | %s | %d | %d | %d | %d |\n" % (r["m"], r["strat"], r["cct"], r["inc"], q, ov, r["rtos"], r["freeze"], r["trims"], r["drops"]))
    o.write("\n### Gate: ofan E->A max data queue <= (w+1)=7 pkts (29050 B)\n\n")
    for r in rows:
        if r["strat"] == "ofan":
            q = r["E->A"]["maxq"]; o.write("- %s m=%d: E->A maxq %d B = %.2f pkts, total(incl ctrl) %d B -> %s\n" % (r["wl"], r["m"], q, q / PKT, r["E->A"]["maxq_tot"], "PASS" if q <= 7 * PKT else "FAIL"))
print(open(os.path.join(d, "summary.md")).read())
