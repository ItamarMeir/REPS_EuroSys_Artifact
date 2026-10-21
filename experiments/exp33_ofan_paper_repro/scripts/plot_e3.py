#!/usr/bin/env python3
"""Plots for E3 from data/e3/summary.csv -> plots/e3_fig4a.png, e3_fig4b.png, e3_fig5{a,b,c}.png (mean +- SEM over seeds)."""
import csv, os, collections
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
rows = list(csv.DictReader(open(os.path.join(H, "data", "e3", "summary.csv"))))
P = os.path.join(H, "plots"); os.makedirs(P, exist_ok=True)
f = lambda r, k: float(r[k])
# ---- Fig 4
order = ["rr", "jsq", "p2c", "rps", "rsq", "reps", "reps_dl", "ar20000", "ar193", "drb", "drb_src", "drb_hash", "ofan"]
label = {"rr": "Simple RR", "jsq": "JSQ", "p2c": "Choice(P2C)", "rps": "RPS", "rsq": "RSQ", "reps": "REPS", "reps_dl": "REPS
+ToR-DL ECN",
         "ar20000": "AR
(q=20000)", "ar193": "AR
(q=193)", "drb": "DRB-like\n(zero start)", "drb_src": "DRB-like\n(src_mod)", "drb_hash": "DRB-like\n(srcdst hash)", "ofan": "Ofan"}
paper = {"rr": 77, "jsq": 43, "p2c": 16, "rps": 13, "rsq": 13, "reps": 14, "ar193": 12, "ar20000": 12, "drb": 3.9, "drb_src": 3.9, "drb_hash": 3.9, "ofan": 2.3}
d4 = {r["algo"]: r for r in rows if r["part"] == "fig4"}
al = [a for a in order if a in d4]
fig, ax = plt.subplots(figsize=(12, 4.5)); x = range(len(al))
ax.bar(x, [f(d4[a], "inc_mean") for a in al], yerr=[f(d4[a], "inc_sem") for a in al], capsize=3, color="#4c78a8", label="this sim (mean +- SEM, 5 seeds)")
ax.plot([i for i, a in enumerate(al) if a in paper], [paper[a] for a in al if a in paper], "r_", ms=22, mew=2.5, ls="none", label="paper Fig 4a")
ax.set_xticks(list(x)); ax.set_xticklabels([label[a] for a in al], fontsize=8); ax.set_ylabel("CCT increase over single-flow bound (%)")
ax.set_title("E3 Fig 4a: 432-host 3-tier, 1 MB permutation, no CCA, 800G"); ax.legend(); ax.grid(axis="y", alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(P, "e3_fig4a.png"), dpi=140); plt.close(fig)
fig, ax = plt.subplots(figsize=(12, 4.5))
ax.bar(x, [f(d4[a], "maxq_pkts_mean") for a in al], yerr=[f(d4[a], "maxq_pkts_sem") for a in al], capsize=3, color="#f58518")
ax.set_yscale("log"); ax.set_xticks(list(x)); ax.set_xticklabels([label[a] for a in al], fontsize=8)
ax.set_ylabel("max data-queue over run and all links (4160 B packets)")
ax.set_title("E3 Fig 4b (per-run maximum only, not a time series): 432 hosts, 1 MB permutation"); ax.grid(axis="y", alpha=.3, which="both")
fig.tight_layout(); fig.savefig(os.path.join(P, "e3_fig4b.png"), dpi=140); plt.close(fig)
# ---- Fig 5
col = {"reps": "#e45756", "ar193": "#4c78a8", "ar20000": "#9ecae9", "ofan": "#54a24b"}
lab5 = {"reps": "REPS", "ar193": "AR (q=193)", "ar20000": "AR (q=20000, ~random)", "ofan": "Ofan"}
ttl = {"fig5a": "(a) permutation, 1 MB", "fig5b": "(b) all-to-all, constant per-flow size (64 KB)", "fig5c": "(c) all-to-all, constant per-host size (16 MB)"}
for part in ["fig5a", "fig5b", "fig5c"]:
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    for ax, key, yl in [(axs[0], "inc", "CCT increase (%)"), (axs[1], "maxq_pkts", "max queue (4160 B pkts)")]:
        for a in ["reps", "ar193", "ar20000", "ofan"]:
            rs = sorted([r for r in rows if r["part"] == part and r["algo"] == a], key=lambda r: int(r["N"]))
            if rs: ax.errorbar([int(r["N"]) for r in rs], [f(r, key + "_mean") for r in rs], [f(r, key + "_sem") for r in rs], marker="o", capsize=3, color=col[a], label=lab5[a])
        ax.set_xscale("log"); ax.set_xticks([16, 54, 128, 250, 432, 1024]); ax.set_xticklabels([16, 54, 128, 250, 432, 1024]); ax.set_xlabel("number of nodes")
        ax.set_ylabel(yl); ax.grid(alpha=.3)
    axs[0].legend(); fig.suptitle("E3 Fig 5 " + ttl[part]); fig.tight_layout(); fig.savefig(os.path.join(P, "e3_%s.png" % part), dpi=140); plt.close(fig)
print("plots written to", P)
