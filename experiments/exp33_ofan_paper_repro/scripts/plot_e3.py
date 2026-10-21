#!/usr/bin/env python3
"""E3 plots (paper style) from data/e3/summary.csv (run aggregate_e3.py first):
 plots/e3_fig4/fig4a_cct.png   horizontal bars, CCT increase per LB algorithm, mean +- SEM (432 hosts, 1 MB permutation, 5 seeds), paper values as red ticks
 plots/e3_fig4/fig4b_maxq.png  per-run max queue (log, 4160 B packets) per algorithm. Only the per-run maximum is available (no time series).
 plots/e3_fig5/fig5{a,b,c}_cct.png, fig5{a,b,c}_maxq.png, fig5_cct.png (3 panels)  vs number of nodes, REPS / AR / Ofan (+AR q=20000 dashed)."""
import csv, os
import numpy as np
from paperstyle import *
H = os.path.dirname(os.path.abspath(__file__)); B = os.path.join(H, "..")
rows = list(csv.DictReader(open(f"{B}/data/e3/summary.csv")))
P4 = f"{B}/plots/e3_fig4"; P5 = f"{B}/plots/e3_fig5"; os.makedirs(P4, exist_ok=True); os.makedirs(P5, exist_ok=True)
fl = lambda r, k: float(r[k])
# ---- Fig 4
ORDER = ["rr", "jsq", "p2c", "rsq", "rps", "reps", "reps_dl", "ar20000", "ar193", "drb", "drb_src", "drb_hash", "drb_rand", "drb_af_rand", "ofan"]
NAME = {"rr": "Simple RR", "jsq": "JSQ", "p2c": "Choice (P2C)", "rsq": "RSQ", "rps": "RPS", "reps": "REPS", "reps_dl": "REPS (+ToR-DL ECN)",
        "ar20000": "AR (q=20000, = RSQ)", "ar193": "AR (q=193)", "drb": "DRB-like, synchronised start", "drb_src": "DRB-like, start = src mod n",
        "drb_hash": "DRB-like, start = hash(src,dst)", "drb_af_rand": "DRB (random phase, Agg-fastest order)", "drb_rand": "DRB-like, random phase, native order", "ofan": "Ofan"}
PAPER = {"rr": 77, "jsq": 43, "p2c": 16, "rsq": 13, "rps": 13, "reps": 14, "ar193": 12, "ar20000": 12, "drb": 3.9, "drb_src": 3.9, "drb_hash": 3.9, "drb_rand": 3.9, "drb_af_rand": 3.9, "ofan": 2.3}
COL = {"rr": "#d98c8c", "jsq": "#d98c8c", "p2c": "#e6c27a", "rsq": "#e6c27a", "rps": "#e6c27a", "reps": "#6fb0b0", "reps_dl": "#6fb0b0", "ar20000": "#8fb86c", "ar193": "#8fb86c"}
d4 = {r["algo"]: r for r in rows if r["part"] == "fig4"}; al = [a for a in ORDER if a in d4]; y = np.arange(len(al))
def bar4(key, fn, xl, cap, log=False, skip=()):
    al = [a for a in ORDER if a in d4 and a not in skip]; y = np.arange(len(al))
    f, ax = plt.subplots(figsize=(4.2, 0.28 * len(al) + 1.2)); f.subplots_adjust(left=.4, bottom=.2, top=.92, right=.95)
    mu = [fl(d4[a], key + "_mean") for a in al]; se = [fl(d4[a], key + "_sem") for a in al]
    ax.barh(y, mu, .75, xerr=se, color=[COL.get(a, "#b394e0") for a in al], edgecolor="#555", linewidth=.4, error_kw=dict(elinewidth=.6, capsize=1.5, ecolor="k"), zorder=3)
    for yi, m, e in zip(y, mu, se): ax.text(m + e + (m * .08 if log else max(mu) * .01), yi, f"{m:.3g}", va="center", fontsize=5.5, zorder=4)
    if key == "inc":
        for yi, a in zip(y, al):
            if a in PAPER: ax.plot([PAPER[a]] * 2, [yi - .4, yi + .4], color="r", lw=1.4, zorder=5)
    ax.set_yticks(y); ax.set_yticklabels([NAME[a] for a in al], fontsize=6); ax.invert_yaxis(); ax.set_xlabel(xl); ax.grid(True, axis="x", zorder=0); ax.tick_params(axis="y", length=0)
    if log: ax.set_xscale("log")
    else: ax.set_xlim(0, max(m + e for m, e in zip(mu, se)) * 1.15)
    ax.set_title(cap, fontsize=7); f.savefig(f"{P4}/{fn}.png"); plt.close(f)
bar4("inc", "fig4a_cct_main", "CCT Increase (%)   [red tick = paper Fig 4a]", "Fig 4a: 432 hosts, 1 MB permutation, no CCA", skip=("drb", "drb_src", "drb_hash", "drb_rand", "reps_dl"))
bar4("inc", "fig4a_cct", "CCT Increase (%)   [red tick = paper Fig 4a]", "Fig 4a: 432 hosts, 1 MB permutation, no CCA")
bar4("maxq_pkts", "fig4b_maxq", "Max queue over run (4160 B packets)", "Fig 4b (per-run maximum only)", log=True)
# ---- Fig 5
LB2 = dict(LB, drb=("DRB", "#f0b27a", "^")); EDGE2 = dict(EDGE, drb="#c0762f")
SER = [("reps", "reps", "REPS", {}), ("ar193", "ar", "AR (q=193)", {}), ("ar20000", "ar", "AR (q=20000)", dict(ls="--", alpha=.7)), ("drb_af_rand", "drb", "DRB (random phase, Agg-fast)", {}), ("ofan", "ofan", "Ofan", {})]
TT = {"fig5a": "(a) Permutation (1 MB)", "fig5b": "(b) ATA, const. per-flow (64 KB)", "fig5c": "(c) ATA, const. per-host (32 MB)"}
def panel(ax, part, key, yl):
    for algo, lk, lab, kw in SER:
        rs = sorted([r for r in rows if r["part"] == part and r["algo"] == algo], key=lambda r: int(r["N"]))
        if not rs: continue
        ax.errorbar([int(r["N"]) for r in rs], [fl(r, key + "_mean") for r in rs], [fl(r, key + "_sem") for r in rs], color=EDGE2[lk], marker=LB2[lk][2], mfc=LB2[lk][1],
                    mec=EDGE2[lk], ms=3.5, lw=.9, elinewidth=.6, capsize=1.5, label=lab, **kw)
    ax.set_xscale("log"); ax.set_xticks([16, 54, 128, 250, 432, 1024]); ax.set_xticklabels(["16", "54", "128", "250", "432", "1024"], fontsize=5.5)
    ax.set_xlim(12, 1300 if part == "fig5a" else 330); ax.minorticks_off(); ax.set_xlabel("Number of Nodes"); ax.set_ylabel(yl); ax.grid(True)
    if key == "maxq_pkts": ax.set_yscale("log")
for key, tag, yl in [("inc", "cct", "CCT Increase (%)"), ("maxq_pkts", "maxq", "Max queue (pkts)")]:
    f, axs = plt.subplots(1, 3, figsize=(7.2, 1.9)); f.subplots_adjust(left=.07, right=.99, bottom=.3, top=.82, wspace=.32)
    for ax, part in zip(axs, ["fig5a", "fig5b", "fig5c"]):
        panel(ax, part, key, yl); caption(ax, TT[part], -.42)
        f2, a2 = plt.subplots(figsize=(2.6, 1.9)); f2.subplots_adjust(left=.2, bottom=.3, top=.86, right=.97); panel(a2, part, key, yl); caption(a2, TT[part], -.42)
        a2.legend(frameon=False, fontsize=5.5, loc="upper left"); f2.savefig(f"{P5}/{part}_{tag}.png"); plt.close(f2)
    axs[0].legend(frameon=False, fontsize=5.5, loc="upper left"); f.savefig(f"{P5}/fig5_{tag}.png"); plt.close(f)
print("plots written")
