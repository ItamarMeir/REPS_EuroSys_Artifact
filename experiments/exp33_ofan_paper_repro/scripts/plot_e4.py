#!/usr/bin/env python3
"""E4 (Ofan Fig 12) plots -> plots/e4_fig12/<cca>_{cct,util,maxq,fig12}.png, paper style, one set per CCA (dctcp, nscc, mswift).
 cct   : horizontal bars of CCT increase, LINEAR axis, mean +- SEM over 10 seeds (data/e4/e4_summary.csv, 432 hosts, 4 MiB permutation)
 util  : utilisation vs time, ONE seed (data/e4/ts/<cca>_<lb>_s1_series.csv from run_e4_ts.sh + ts_e4.py): mean busy fraction of the 432 ToR uplinks (E->A)
 maxq  : max queue size (KB) vs time, log y, max over all E->A, A->C, C->A, A->E queues (same runs; E->H not logged)
 fig12 : the three panels in a row, like paper Fig 12 (a-c).  If a time-series file is missing the corresponding panel is skipped."""
import csv, os, numpy as np
from paperstyle import *
H = os.path.dirname(os.path.abspath(__file__)); B = os.path.join(H, ".."); P = f"{B}/plots/e4_fig12"; os.makedirs(P, exist_ok=True)
S = {(r["cca"], r["lb"]): r for r in csv.DictReader(open(f"{B}/data/e4/e4_summary.csv")) if r["mode"] == "DTE"}
CC = {"dctcp": "DCTCP", "nscc": "NSCC", "mswift": "MSwift"}; ORDER = ["reps", "ar", "ofan"]; SEED = 1
def bars(ax, cca):
    mu = [float(S[(cca, k)]["inc"]) for k in ORDER]; se = [float(S[(cca, k)]["inc_sem"]) for k in ORDER]; y = np.arange(3)
    ax.barh(y, mu, .8, xerr=se, color=[LB[k][1] for k in ORDER], edgecolor="#555", linewidth=.4, error_kw=dict(elinewidth=.6, capsize=1.5, capthick=.6, ecolor="k"), zorder=3)
    for yi, m, e in zip(y, mu, se): ax.text(m + e + max(mu) * .02, yi, f"{m:.2g}", va="center", ha="left", fontsize=5.5, zorder=4)
    ax.set_yticks(y); ax.set_yticklabels([LB[k][0] for k in ORDER]); ax.invert_yaxis(); ax.set_xlim(0, max(mu) * 1.22); ax.set_ylim(2.5, -.5)
    ax.set_xlabel("CCT Increase (%)"); ax.grid(True, axis="x", zorder=0); ax.tick_params(axis="y", length=0)
def load(cca, k):
    f = f"{B}/data/e4/ts/{cca}_{k}_s{SEED}_series.csv"
    return np.genfromtxt(f, delimiter=",", names=True) if os.path.exists(f) else None
def series(ax, cca, col, kind):
    ok = False
    for k in ORDER:
        d = load(cca, k)
        if d is None: continue
        ok = True; t = d["t_us"]; v = d[col]
        if kind == "q": m = v > 0; t, v = t[m], v[m]
        mk = max(1, len(t) // 7)
        ax.plot(t, v, color=EDGE[k], lw=.8, marker=LB[k][2], mfc=LB[k][1], mec=EDGE[k], ms=3.2, mew=.5, markevery=(ORDER.index(k) * 2, mk), zorder=3)
    ax.set_xlabel("Time (us)"); ax.grid(True, which="major", zorder=0)
    if kind == "u": ax.set_ylabel("Utilization (%)"); ax.set_ylim(-3, 103); ax.set_yticks(range(0, 101, 10)); ax.grid(True, which="major")
    else:
        ax.set_ylabel("Max Queue Size (KB)"); ax.set_yscale("log"); ax.set_ylim(8, 700); ax.set_yticks([10, 20, 50, 100, 200, 500]); ax.set_yticklabels(["10", "20", "50", "100", "200", "500"])
        ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter()); ax.grid(True, which="minor", linewidth=.3)
    ax.set_xlim(-1, {"dctcp": 80, "nscc": 75, "mswift": 75}[cca]); return ok
import matplotlib.ticker
def single(cca, kind, fn, cap, w=2.4, h=1.75):
    f, ax = plt.subplots(figsize=(w, h)); f.subplots_adjust(left=.2 if kind != "cct" else .17, bottom=.3, top=.86, right=.97)
    if kind == "cct": bars(ax, cca)
    elif not series(ax, cca, "util_EA" if kind == "util" else "maxq_all_kb", "u" if kind == "util" else "q"): plt.close(f); return
    caption(ax, cap, -.4); legend_row(f, ORDER, y=1.02); f.savefig(f"{P}/{cca}_{fn}.png"); plt.close(f)
for i, (cca, nm) in enumerate(CC.items()):
    la = "abc" if i == 0 else "def" if i == 1 else "ghi"
    single(cca, "cct", "cct", f"({la[0]}) {nm}: CCT"); single(cca, "util", "util", f"({la[1]}) {nm}: Utilization"); single(cca, "q", "maxq", f"({la[2]}) {nm}: Max Queue Size")
    f, axs = plt.subplots(1, 3, figsize=(7.2, 1.75), gridspec_kw=dict(width_ratios=[1, 1, 1])); f.subplots_adjust(left=.085, right=.99, bottom=.3, top=.86, wspace=.4)
    bars(axs[0], cca); caption(axs[0], f"({la[0]}) {nm}: CCT", -.4)
    if series(axs[1], cca, "util_EA", "u"):
        caption(axs[1], f"({la[1]}) {nm}: Utilization", -.4); series(axs[2], cca, "maxq_all_kb", "q"); caption(axs[2], f"({la[2]}) {nm}: Max Queue Size", -.4)
    legend_row(f, ORDER, y=1.03); f.savefig(f"{P}/{cca}_fig12.png"); plt.close(f)
