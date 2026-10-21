#!/usr/bin/env python3
"""E1 (Ofan Fig 1) plots from data/e1/e1_summary.csv -> plots/e1_fig1/{fig1.png,fig1a_util.png,fig1b_maxq.png,fig1c_cct.png,extra_*.png}
mean +- SEM over seeds; paper style (scripts/paperstyle.py). Run inside container ofan-dev (pandas+matplotlib)."""
import os, pandas as pd
from paperstyle import *
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.join(H, "..", "plots", "e1_fig1"); os.makedirs(P, exist_ok=True)
s = pd.read_csv(os.path.join(H, "..", "data", "e1", "e1_summary.csv"))
SEL = {"reps": "reps", "ar": "ar_q193", "ofan": "ofan"}   # AR with the 193-pkt (800 KB) buffer, the loss-free configuration
def panel(ax, m, yl, ylim=None, yticks=None, diag=False):
    for k in ("reps", "ar", "ofan"):
        t = s[s.strat == SEL[k]].sort_values("rho"); lab, fc, mk = LB[k]
        ax.errorbar(t.rho, t[m + "_mean"], yerr=t[m + "_sem"], color=EDGE[k], marker=mk, mfc=fc, mec=EDGE[k], ms=4, mew=.6, lw=.9, capsize=1.5, elinewidth=.6)
    if diag: ax.plot([.8, 1], [80, 100], ls=":", color="gray", lw=.7)
    ax.set_xlabel("Load"); ax.set_ylabel(yl); ax.set_xlim(.79, 1.01); ax.set_xticks([.8, .9, 1.0]); ax.set_xticklabels(["0.8", "0.9", "1.0"])
    if ylim: ax.set_ylim(*ylim)
    if yticks: ax.set_yticks(yticks)
    ax.grid(True)
SPEC = [("util_eff_pct", "Max util. (%)", (74, 100), [75, 80, 85, 90, 95, 100], False, "fig1a_util", "(a) Max utilization"),
        ("maxq_kb", "Max queue (KB)", (0, 250), [0, 100, 200], False, "fig1b_maxq", "(b) Max queue size"),
        ("cct_us", "CCT (us)", (17, 20.6), [18, 19, 20], False, "fig1c_cct", "(c) CCT")]
f, axs = plt.subplots(1, 3, figsize=(7.2, 1.75)); f.subplots_adjust(wspace=.42, bottom=.36, top=.84, left=.07, right=.99)
for ax, (m, yl, yl_, yt, dg, fn, cap) in zip(axs, SPEC):
    panel(ax, m, yl, yl_, yt, dg); caption(ax, cap, -.42)
legend_row(f, ["reps", "ar", "ofan"], y=1.02); f.savefig(os.path.join(P, "fig1.png")); plt.close(f)
for m, yl, yl_, yt, dg, fn, cap in SPEC:   # single-panel files
    f, ax = plt.subplots(figsize=(2.5, 1.9)); f.subplots_adjust(left=.22, bottom=.3, top=.85, right=.97); panel(ax, m, yl, yl_, yt, dg); caption(ax, cap, -.38)
    legend_row(f, ["reps", "ar", "ofan"], y=1.02); f.savefig(os.path.join(P, fn + ".png")); plt.close(f)
for m, yl, fn, cap in [("util_pct", "Busiest-link util. (%)", "extra_util_busiest", "Busiest-link utilisation"), ("cct_inc_pct", "CCT increase (%)", "extra_cct_increase", "CCT increase over single-flow bound")]:
    f, ax = plt.subplots(figsize=(2.5, 1.9)); f.subplots_adjust(left=.22, bottom=.3, top=.85, right=.97); panel(ax, m, yl); caption(ax, cap, -.38)
    legend_row(f, ["reps", "ar", "ofan"], y=1.02); f.savefig(os.path.join(P, fn + ".png")); plt.close(f)
