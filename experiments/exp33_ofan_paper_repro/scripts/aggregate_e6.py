#!/usr/bin/env python3
"""E6 (Ofan Fig 9): aggregate data/e6 -> data/e6/e6_runs.csv, e6_summary.md and plots/e6_fig9/fig9.png.
CCT increase = (max flow finish / LB1 - 1) * 100 with LB1 = healthy single flow at line rate (rho=1).
'ideal' = healthy single flow paced at the instance's rho_max (rate loss only, no queueing).
excess = increase - ideal increase (what the LB itself costs beyond the capacity lost to failures)."""
import csv, glob, json, os, re, statistics, sys
H = os.path.dirname(os.path.abspath(__file__)); B = os.path.join(H, ".."); DN = os.environ.get("E6DIR", "e6"); D = f"{B}/data/{DN}"

def cct(path):
    t = [float(x) for x in re.findall(r"finished at ([0-9.]+)", open(path, errors="ignore").read())]
    return (max(t), len(t)) if t else (float("nan"), 0)

def qstats(tsv):
    mq = 0; dr = 0; tr = 0
    for r in csv.DictReader(open(tsv), delimiter="\t"):
        if r["layer"] in ("E->A", "A->C", "C->A", "A->E"):
            mq = max(mq, int(r["max_q_bytes"])); dr += int(r["drops"]); tr += int(r["trims"])
    return mq / 4160.0, dr, tr

lb1 = cct(f"{D}/runs/lb1.out")[0]
rows = []
for out in sorted(glob.glob(f"{D}/runs/*__p*__s*.out")):
    tag = os.path.basename(out)[:-4]; st, p, s = tag.split("__"); p = p[1:]; s = s[1:]
    if st == "single": continue
    tsv = out[:-4] + ".tsv"
    if not os.path.exists(tsv): continue
    inst = json.load(open(f"{D}/inst/p{p}_s{s}/inst.json"))
    c, n = cct(out); sg = f"{D}/runs/single__p{p}__s{s}.out"
    ideal = cct(sg)[0] if os.path.exists(sg) else float("nan")
    mq, dr, tr = qstats(tsv)
    rows.append(dict(strat=st, p=float(p), seed=int(s), cct=c, nfin=n, nflows=inst["nflows"], rho_max=inst["rho_max"],
                     fluid_ideal_pct=inst["ideal_cct_increase_pct"], inc=(c / lb1 - 1) * 100, ideal_inc=(ideal / lb1 - 1) * 100,
                     excess=(c / ideal - 1) * 100, maxq_pkts=mq, drops=dr, trims=tr, failedE=inst["failed_E"], failedC=inst["failed_C"]))
with open(f"{D}/e6_runs.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

def ms(v):
    v = [x for x in v if x == x]
    return (statistics.mean(v), statistics.stdev(v) / len(v) ** .5 if len(v) > 1 else 0.0, len(v)) if v else (float("nan"), 0, 0)
ORDER = ["reps", "ar193", "jsq", "ofan", "ofan_weighted"]
NAME = {"reps": "REPS", "ar193": "AR (q=193)", "jsq": "JSQ", "ofan": "Ofan (plain)", "ofan_weighted": "Ofan weighted"}
ps = sorted({r["p"] for r in rows}); lines = []
lines.append(f"LB1 (healthy single flow, rho=1) = {lb1:.3f} us\n")
lines.append("| p (%) | " + " | ".join(NAME[k] for k in ORDER) + " | ideal (rate loss only) |")
lines.append("|---|" + "---|" * (len(ORDER) + 1))
summ = {}
for p in ps:
    cells = []
    for k in ORDER:
        v = [r["inc"] for r in rows if r["strat"] == k and r["p"] == p]
        m, e, n = ms(v); summ[(k, p)] = (m, e, n); cells.append(f"{m:.1f} +- {e:.1f} (n={n})" if n else "-")
    idl = ms([r["ideal_inc"] for r in rows if r["strat"] == "ofan" and r["p"] == p])
    lines.append(f"| {p:g} | " + " | ".join(cells) + f" | {idl[0]:.1f} +- {idl[1]:.1f} |")
lines.append("\nExcess over each instance's own ideal (CCT / ideal CCT - 1, %), mean +- SEM:\n")
lines.append("| p (%) | " + " | ".join(NAME[k] for k in ORDER) + " |"); lines.append("|---|" + "---|" * len(ORDER))
for p in ps:
    cells = []
    for k in ORDER:
        m, e, n = ms([r["excess"] for r in rows if r["strat"] == k and r["p"] == p]); cells.append(f"{m:.1f} +- {e:.1f}" if n else "-")
    lines.append(f"| {p:g} | " + " | ".join(cells) + " |")
lines.append("\nMax queue (4160 B packets, max over fabric layers), mean over seeds; drops/trims summed:\n")
lines.append("| p (%) | " + " | ".join(NAME[k] for k in ORDER) + " |"); lines.append("|---|" + "---|" * len(ORDER))
for p in ps:
    cells = []
    for k in ORDER:
        rr = [r for r in rows if r["strat"] == k and r["p"] == p]
        cells.append(f"{statistics.mean(r['maxq_pkts'] for r in rr):.0f} / drops {sum(r['drops'] for r in rr)}" if rr else "-")
    lines.append(f"| {p:g} | " + " | ".join(cells) + " |")
inc = [r for r in rows if r["nfin"] != r["nflows"]]
lines.append(f"\nRuns where not all flows finished: {len(inc)} of {len(rows)}")
open(f"{D}/e6_summary.md", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))

# ---- plot (paper style): paper values read by eye from Fig 9 (approximate)
from paperstyle import *
import numpy as np
PD = "e6_fig9" if DN == "e6" else f"{DN}_fig9"; os.makedirs(f"{B}/plots/{PD}", exist_ok=True)
paper = {"reps": [13, 21, 24.5, 28, 30.5], "ar193": [12.5, 21, 24.5, 27.5, 31], "ofan": [3.5, 15, 19.5, 23, 28]}
px = [0, 0.5, 1, 1.5, 2]
fig, axs = plt.subplots(1, 2, figsize=(6.4, 2.3))
for ax, (title, sel) in zip(axs, [("this repo (432 hosts)", True), ("paper Fig 9 (read by eye)", False)]):
    if sel:
        for k, st, col in [("reps", "reps", "reps"), ("ar193", "ar", "ar"), ("ofan", "ofan", "ofan")]:
            y = [summ[(k, p)][0] for p in ps]; e = [summ[(k, p)][1] for p in ps]
            ax.errorbar(ps, y, yerr=e, color=EDGE[col], marker=LB[col][2], mfc=LB[col][1], mec=EDGE[col], ms=3.5, lw=.9, capsize=1.5,
                        label=NAME[k])
        y = [summ[("ofan_weighted", p)][0] if ("ofan_weighted", p) in summ and summ[("ofan_weighted", p)][2] else summ[("ofan", p)][0] for p in ps]
        ax.plot(ps, y, color="#d62728", marker="o", ms=3, lw=.9, ls="--", label="Ofan weighted (ext.)")
        idl = [ms([r["ideal_inc"] for r in rows if r["strat"] == "ofan" and r["p"] == p])[0] for p in ps]
        ax.plot(ps, idl, color="k", lw=.8, ls=":", label="ideal (rate loss)")
    else:
        for k, col in [("reps", "reps"), ("ar193", "ar"), ("ofan", "ofan")]:
            ax.plot(px, paper[k], color=EDGE[col], marker=LB[col][2], mfc=LB[col][1], mec=EDGE[col], ms=3.5, lw=.9, label=NAME[k] if k != "ofan" else "Ofan")
    ax.set_xlabel("Link Failure Probability (%)"); ax.set_ylabel("CCT Increase (%)"); ax.grid(True, zorder=0); ax.set_title(title, fontsize=7)
    ax.legend(fontsize=5.5, frameon=False)
axs[1].set_ylim(axs[0].get_ylim())
fig.tight_layout(); fig.savefig(f"{B}/plots/{PD}/fig9.png"); print("plot written")
