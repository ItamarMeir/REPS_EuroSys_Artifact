#!/usr/bin/env python3
"""Plots for E2 from data/e2/e2_summary.csv (run aggregate_e2.py first). Writes plots/e2_fig7a.png, e2_fig7b.png, e2_fig8_*.png."""
import math, os, sys
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); EXP = os.path.join(HERE, ".."); d = os.path.join(EXP, "data", "e2"); P = os.path.join(EXP, "plots"); os.makedirs(P, exist_ok=True)
a = pd.read_csv(os.path.join(d, "e2_summary.csv"))
STY = {"ofan": ("tab:green", "o", "-", "Ofan"), "ar_q193": ("tab:blue", "s", "-", "AR (quantized, 800 KB comparator)"),
       "ar_q20000": ("tab:cyan", "s", ":", "AR (quantized, infinite buf: ~random)"), "ar_exact": ("tab:purple", "^", "--", "AR (exact JSQ)"),
       "reps": ("tab:red", "D", "-", "REPS")}
H, ALPHA = 82.0, 10.0
def popt(D): return math.sqrt(H / ALPHA * D) + H          # paper Thm 6: P-H = sqrt(H/alpha * D)
def model(P, D): return (H / (P - H) + ALPHA * P / D) * 100  # increase over a header-free bound (App. G)

def fig7(fig, wl, xs_div, xlabel, out, title):
    s = a[(a.fig == fig) & (a.wl == wl)]
    f, ax = plt.subplots(figsize=(6.4, 4.4))
    for st, (c, mk, ls, lab) in STY.items():
        t = s[s.strat == st].sort_values("size")
        if t.empty: continue
        ax.errorbar(t["size"] / xs_div, t.inc_own.clip(lower=0.01), yerr=t.inc_own_ci.fillna(0), color=c, marker=mk, ls=ls, label=lab, capsize=3)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel(xlabel); ax.set_ylabel("CCT increase over single-flow bound (%)")
    ax.set_title(title, fontsize=10); ax.grid(True, which="both", alpha=.3); ax.legend(fontsize=7); f.tight_layout(); f.savefig(os.path.join(P, out), dpi=130); plt.close(f)
fig7("f7a", "perm", 1048576, "message size (MiB)", "e2_fig7a.png", "Fig 7a repro: permutation, 432 hosts, 800G, no CCA (mean, 95% CI over seeds)")
for wl in sorted(set(a[a.fig == "f7b"].wl)):
    fig7("f7b", wl, 1024, "message size per flow (KiB)", "e2_fig7b.png", "Fig 7b repro: all-to-all, %s hosts, 800G, no CCA" % wl[3:])

for col, tag, lab in (("inc_best", "best", "over P-independent bound (min single-flow CCT over MTUs)"), ("inc_own", "own", "over same-MTU single-flow bound")):
    f, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, D in zip(axs, (524288, 4194304)):
        s = a[(a.fig == "f8") & (a["size"] == D)]
        for st, (c, mk, ls, l) in STY.items():
            t = s[s.strat == st].sort_values("mtu")
            if t.empty: continue
            ax.errorbar(t.mtu, t[col].clip(lower=0.01), yerr=t[col + "_ci"].fillna(0), color=c, marker=mk, ls=ls, label=l, capsize=3)
        if tag == "best":
            xs = [x for x in range(1000, 10001, 100)]
            ax.plot(xs, [model(x, D) for x in xs], "k--", lw=1, label="Ofan model (H=82, alpha=10)")
            po = popt(D); ax.plot([po], [model(po, D)], "ro", ms=8, label="model optimum P=%d B" % round(po)); ax.axvline(po, color="r", lw=.6, alpha=.5)
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("packet size = -mtu (B)"); ax.set_ylabel("CCT increase (%) " + ("" if tag == "best" else "(own-MTU bound)"))
        ax.set_title("%s MiB permutation" % (D / 1048576), fontsize=10); ax.grid(True, which="both", alpha=.3); ax.legend(fontsize=6)
    f.suptitle("Fig 8 repro: " + lab, fontsize=10); f.tight_layout(); f.savefig(os.path.join(P, "e2_fig8_%s.png" % tag), dpi=130); plt.close(f)
print("model optima:", {D: round(popt(D)) for D in (524288, 4194304)})
