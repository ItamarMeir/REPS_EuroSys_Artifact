#!/usr/bin/env python3
"""E2 plots (Ofan Figs 7, 8), paper style -> plots/e2_fig7/*.png, plots/e2_fig8/*.png. Needs data/e2/e2_summary.csv (+ optional data/e2_k8, data/e2_k10 summaries from
aggregate_e2.py <dir> <N>). Mean +- 95% CI (t) over seeds; AR = quantized comparator with 800 KB-scale buffer (ar_q193) plus dotted AR with infinite buffer."""
import math, os, pandas as pd
from paperstyle import *
H = os.path.dirname(os.path.abspath(__file__)); B = os.path.join(H, ".."); P7 = f"{B}/plots/e2_fig7"; P8 = f"{B}/plots/e2_fig8"; os.makedirs(P7, exist_ok=True); os.makedirs(P8, exist_ok=True)
def ld(n):
    f = f"{B}/data/{n}/e2_summary.csv"; return pd.read_csv(f) if os.path.exists(f) else None
A, K8, K10 = ld("e2"), ld("e2_k8"), ld("e2_k10")
SEL = {"reps": "reps", "ar": "ar_q193", "ofan": "ofan"}
HH, ALPHA = 82.0, 10.0
popt = lambda D: math.sqrt(HH / ALPHA * D) + HH
model = lambda P, D: (HH / (P - HH) + ALPHA * P / D) * 100
def line(ax, t, x, col, k, ls="-", ci="ci"):
    lab, fc, mk = LB[k]; t = t.sort_values(x)
    ax.errorbar(t[x], t[col].clip(lower=.05), yerr=t[col + "_ci"].fillna(0) if ci else None, color=EDGE[k], marker=mk, mfc=fc, mec=EDGE[k], ms=4, mew=.6, lw=.9, ls=ls, capsize=1.5, elinewidth=.6)
def fig7(ax, df, fig, wl, div, xl, xt):
    s = df[(df.fig == fig) & (df.wl == wl)]
    for k in ("reps", "ar", "ofan"): line(ax, s[s.strat == SEL[k]].assign(x=lambda d: d["size"] / div), "x", "inc_own", k)
    t = s[s.strat == "ar_q20000"].assign(x=lambda d: d["size"] / div).sort_values("x")
    if len(t): ax.plot(t.x, t.inc_own, ls=":", color="gray", lw=.8, marker="s", ms=2.5, mfc="none", mec="gray")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xticks(xt); ax.set_xticklabels([("%g" % v) for v in xt]); ax.minorticks_off()
    ax.set_xlabel(xl); ax.set_ylabel("CCT Increase (%)"); ax.grid(True, which="major")
def sing(fn, cap, df, fig, wl, div, xl, xt, size=(2.6, 1.9)):
    f, ax = plt.subplots(figsize=size); f.subplots_adjust(left=.2, bottom=.3, top=.85, right=.97); fig7(ax, df, fig, wl, div, xl, xt); caption(ax, cap, -.38)
    legend_row(f, ["reps", "ar", "ofan"], y=1.02); f.savefig(f"{P7}/{fn}.png"); plt.close(f)
XA = [.5, 2, 8, 64]; XB = [128, 256, 512]
sing("fig7a", "(a) Permutation", A, "f7a", "perm", 1048576, "Message size (MB)", XA)
sing("fig7b", "(b) All-to-All", A, "f7b", "ata128", 1024, "Message size (KB)", XB)
f, axs = plt.subplots(1, 2, figsize=(5.2, 1.9)); f.subplots_adjust(wspace=.35, bottom=.3, top=.85, left=.1, right=.99)
fig7(axs[0], A, "f7a", "perm", 1048576, "Message size (MB)", XA); caption(axs[0], "(a) Permutation", -.38)
fig7(axs[1], A, "f7b", "ata128", 1024, "Message size (KB)", XB); caption(axs[1], "(b) All-to-All (128 hosts)", -.38)
legend_row(f, ["reps", "ar", "ofan"], y=1.02); f.savefig(f"{P7}/fig7.png"); plt.close(f)
if K8 is not None: sing("fig7a_k8_128hosts", "(a') Permutation, 128 hosts", K8, "f7a", "perm", 1048576, "Message size (MB)", XA)
if A is not None:  # AR variants, all-to-all and permutation, extra
    f, axs = plt.subplots(1, 2, figsize=(5.4, 1.9)); f.subplots_adjust(wspace=.35, bottom=.3, top=.85, left=.1, right=.99)
    for ax, fig, wl, div, xl in ((axs[0], "f7a", "perm", 1048576, "Message size (MB)"), (axs[1], "f7b", "ata128", 1024, "Message size (KB)")):
        s = A[(A.fig == fig) & (A.wl == wl)]
        for st, c, mk in (("ar_q193", "tab:blue", "s"), ("ar_q20000", "gray", "s"), ("ar_exact", "tab:purple", "^"), ("ofan", EDGE["ofan"], "D"), ("reps", EDGE["reps"], "v")):
            t = s[s.strat == st].sort_values("size"); ax.errorbar(t["size"] / div, t.inc_own.clip(lower=.05), yerr=t.inc_own_ci.fillna(0), color=c, marker=mk, ms=3, lw=.8, capsize=1.5, label=st)
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel(xl); ax.set_ylabel("CCT Increase (%)"); ax.grid(True)
    axs[0].legend(fontsize=5.5); f.savefig(f"{P7}/extra_ar_variants.png"); plt.close(f)

def fig8(ax, df, D, col, model_on):
    s = df[(df.fig == "f8") & (df["size"] == D)]
    for k in ("reps", "ar", "ofan"): line(ax, s[s.strat == SEL[k]], "mtu", col, k)
    if model_on:
        xs = list(range(1000, 10001, 100)); ax.plot(xs, [model(x, D) for x in xs], "k--", lw=.8)
        po = popt(D); ax.plot([po], [model(po, D)], "o", color="red", ms=4.5, zorder=5); ax.axvline(po, color="red", lw=.4, alpha=.5)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xticks([1000, 2000, 4000, 10000]); ax.set_xticklabels(["1K", "2K", "4K", "10K"]); ax.minorticks_off()
    ax.set_xlabel("Packet size (B)"); ax.set_ylabel("CCT Increase (%)"); ax.grid(True, which="major")
def f8set(df, suffix, tag):
    for col, name, mo in (("inc_best", "fig8", True), ("inc_own", "fig8_ownlb", False)):
        f, axs = plt.subplots(1, 2, figsize=(5.2, 1.9)); f.subplots_adjust(wspace=.35, bottom=.3, top=.85, left=.1, right=.99)
        for ax, D, c in zip(axs, (524288, 4194304), ("(a) 0.5 MB message", "(b) 4 MB message")): fig8(ax, df, D, col, mo); caption(ax, c, -.38)
        legend_row(f, ["reps", "ar", "ofan"], y=1.02); f.savefig(f"{P8}/{name}{suffix}.png"); plt.close(f)
f8set(A, "", "432")
if K10 is not None: f8set(K10, "_k10_250hosts", "250")
print("model optima P*:", {D: round(popt(D)) for D in (524288, 4194304)})
