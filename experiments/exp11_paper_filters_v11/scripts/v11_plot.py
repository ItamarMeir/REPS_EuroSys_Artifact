#!/usr/bin/env python3
"""
v11_plot.py — exp11 paper-workload filter comparison plotter.

Reads data/v11_fct.csv, data/v11_events.csv, data/v11_diagnostics.csv and emits
8 PNG figures to plots/.

  fig1_p99_baseline.png      — p99 FCT slowdown × mode × sev (baseline, class-split)
  fig2_p99_perm.png          — p99 FCT slowdown × mode × sev (perm)
  fig3_p99_hsdp.png          — p99 FCT slowdown × mode × sev (hsdp)
  fig4_p99_incast.png        — p99 FCT slowdown × mode × sev (incast32)
  fig5_ecn_counter_dist.png  — ECN-counter distribution at ecn=1 ACKs (vanilla, per workload)
  fig6_high_counter_rate.png — P(counter≥4|ecn=1) per workload × sev (vanilla)
  fig7_wtd_block_rate.png    — WTD block rate per workload × sev (wtd mode)
  fig8_mode_summary.png      — All 4 workloads × 8 modes mean slowdown grid (sev=0)

95 % CI across 3 seeds via t-distribution.
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats as scipy_stats

warnings.filterwarnings("ignore")

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
DATA_DIR   = EXP_DIR / "data"
PLOT_DIR   = EXP_DIR / "plots"
PLOT_DIR.mkdir(exist_ok=True)

MODES = [
    "vanilla", "wtd",
    "sf_md_gain_ecn", "sf_md_gain_fresh", "sf_md_gain_evhealth",
    "sf_blend_ecn",   "sf_blend_fresh",   "sf_blend_evhealth",
]
MODE_LABEL = {
    "vanilla":             "Vanilla",
    "wtd":                 "WTD",
    "sf_md_gain_ecn":      "SF-A/ECN",
    "sf_md_gain_fresh":    "SF-A/Fresh",
    "sf_md_gain_evhealth": "SF-A/EvH",
    "sf_blend_ecn":        "SF-B/ECN",
    "sf_blend_fresh":      "SF-B/Fresh",
    "sf_blend_evhealth":   "SF-B/EvH",
}
MODE_COLORS = plt.cm.tab10(np.linspace(0, 1, len(MODES)))
MODE_COLOR  = dict(zip(MODES, MODE_COLORS))

WORKLOADS = ["baseline", "perm", "hsdp", "incast32"]
WL_LABEL  = {
    "baseline": "Baseline (perm + 4 ECMP)",
    "perm":     "Pure permutation",
    "hsdp":     "HSDP (Llama-70B)",
    "incast32": "Incast 32→1",
}

SEV_LABEL = {0: "Healthy (sev=0)", 4: "Failure (sev=4)"}
SEV_COLOR = {0: plt.cm.Dark2(0), 4: plt.cm.Dark2(0.5)}

CLASS_LABEL = {
    "ecmp_elephant": "ECMP elephants (ids 1-4)",
    "sprayed_perm":  "Sprayed permutation (ids 5-128)",
}

plt.rcParams.update({
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 8,
    "figure.dpi": 150,
})


def ci95(vals):
    arr = np.asarray(vals, dtype=float)
    n = len(arr)
    if n < 2:
        return 0.0
    return scipy_stats.t.ppf(0.975, df=n - 1) * arr.std(ddof=1) / np.sqrt(n)


def p99_per_seed(group):
    return group.groupby("seed")["slowdown"].quantile(0.99)


def load_data():
    fct  = pd.read_csv(DATA_DIR / "v11_fct.csv")
    ev   = pd.read_csv(DATA_DIR / "v11_events.csv")
    try:
        diag = pd.read_csv(DATA_DIR / "v11_diagnostics.csv")
    except FileNotFoundError:
        diag = pd.DataFrame()
    return fct, ev, diag


# ── fig1: baseline class-split p99 × mode × sev ──────────────────────────────
def fig1_baseline(fct):
    df = fct[fct["workload"] == "baseline"]
    if df.empty:
        print("  fig1: no data"); return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=False)
    for ax, cls in zip(axes, ("ecmp_elephant", "sprayed_perm")):
        sub_c = df[df["flow_class"] == cls]
        x = np.arange(len(MODES))
        width = 0.4
        for j, sev in enumerate((0, 4)):
            ys, errs = [], []
            for mode in MODES:
                g = sub_c[(sub_c["mode"] == mode) & (sub_c["sev"] == sev)]
                per_seed = p99_per_seed(g)
                ys.append(per_seed.mean()); errs.append(ci95(per_seed.values))
            offset = (j - 0.5) * width
            ax.bar(x + offset, ys, width, yerr=errs, capsize=2,
                   label=SEV_LABEL[sev], color=SEV_COLOR[sev], edgecolor='black', linewidth=0.4)
        ax.set_xticks(x); ax.set_xticklabels([MODE_LABEL[m] for m in MODES],
                                              rotation=30, ha="right")
        ax.set_ylabel("p99 FCT Slowdown")
        ax.set_title(CLASS_LABEL[cls])
        ax.legend(loc="best")
        ax.grid(True, axis="y", alpha=0.3)
    fig.suptitle("Baseline workload — p99 slowdown × mode × sev (paper config, 800 G)")
    fig.tight_layout()
    out = PLOT_DIR / "fig1_p99_baseline.png"
    fig.savefig(out, dpi=150); plt.close(fig)
    print(f"  → {out}")


def _fig_single_workload(fct, workload, fig_path, title):
    df = fct[fct["workload"] == workload]
    if df.empty:
        print(f"  {fig_path.name}: no data"); return
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(MODES))
    width = 0.4
    for j, sev in enumerate((0, 4)):
        ys, errs = [], []
        for mode in MODES:
            g = df[(df["mode"] == mode) & (df["sev"] == sev)]
            per_seed = p99_per_seed(g)
            ys.append(per_seed.mean()); errs.append(ci95(per_seed.values))
        offset = (j - 0.5) * width
        ax.bar(x + offset, ys, width, yerr=errs, capsize=2,
               label=SEV_LABEL[sev], color=SEV_COLOR[sev], edgecolor='black', linewidth=0.4)
    ax.set_xticks(x); ax.set_xticklabels([MODE_LABEL[m] for m in MODES],
                                          rotation=30, ha="right")
    ax.set_ylabel("p99 FCT Slowdown")
    ax.set_title(title)
    ax.legend(loc="best")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_path, dpi=150); plt.close(fig)
    print(f"  → {fig_path}")


def fig2_perm(fct):
    _fig_single_workload(fct, "perm", PLOT_DIR / "fig2_p99_perm.png",
        f"{WL_LABEL['perm']} — p99 slowdown × mode (paper config, 800 G)")


def fig3_hsdp(fct):
    _fig_single_workload(fct, "hsdp", PLOT_DIR / "fig3_p99_hsdp.png",
        f"{WL_LABEL['hsdp']} — p99 slowdown × mode (paper config, 800 G)")


def fig4_incast(fct):
    _fig_single_workload(fct, "incast32", PLOT_DIR / "fig4_p99_incast.png",
        f"{WL_LABEL['incast32']} — p99 slowdown × mode (paper config, 800 G)")


# ── fig5: ECN counter distribution ───────────────────────────────────────────
def fig5_ecn_counter_dist(diag):
    if diag.empty or "ecn_counter" not in diag.columns:
        print("  fig5: no diagnostics"); return
    df = diag[(diag["mode"] == "vanilla") & (diag["ecn"] == 1)]
    if df.empty:
        print("  fig5: no ECN ACKs in vanilla — skipping"); return
    fig, axes = plt.subplots(1, 4, figsize=(14, 4), sharey=True)
    for ax, wl in zip(axes, WORKLOADS):
        sub = df[df["workload"] == wl]
        if sub.empty:
            ax.set_title(f"{WL_LABEL[wl]}\n(no ECN)")
            ax.set_xlabel("ecn_counter")
            continue
        ax.hist(sub["ecn_counter"], bins=range(0, 10), edgecolor="black",
                color=plt.cm.Dark2(0.2))
        ax.set_xlabel("ecn_counter at ecn=1 ACKs")
        ax.set_title(f"{WL_LABEL[wl]}\n(n={len(sub):,})")
        ax.set_xticks(range(0, 9))
        ax.grid(True, axis="y", alpha=0.3)
    axes[0].set_ylabel("ECN-ACK count")
    fig.suptitle("ECN-counter distribution (vanilla mode, all sev/seeds pooled)")
    fig.tight_layout()
    out = PLOT_DIR / "fig5_ecn_counter_dist.png"
    fig.savefig(out, dpi=150); plt.close(fig)
    print(f"  → {out}")


# ── fig6: high counter rate per workload × sev ──────────────────────────────
def fig6_high_counter_rate(ev):
    df = ev[ev["mode"] == "vanilla"]
    if df.empty:
        print("  fig6: no data"); return
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(WORKLOADS))
    width = 0.4
    for j, sev in enumerate((0, 4)):
        ys, errs = [], []
        for wl in WORKLOADS:
            g = df[(df["workload"] == wl) & (df["sev"] == sev)]
            vals = g["high_counter_rate"].values
            ys.append(vals.mean() if len(vals) > 0 else 0)
            errs.append(ci95(vals))
        offset = (j - 0.5) * width
        ax.bar(x + offset, ys, width, yerr=errs, capsize=3,
               label=SEV_LABEL[sev], color=SEV_COLOR[sev], edgecolor='black', linewidth=0.4)
    ax.set_xticks(x); ax.set_xticklabels([WL_LABEL[w] for w in WORKLOADS],
                                          rotation=20, ha="right")
    ax.set_ylabel("P(ecn_counter ≥ 4 | ecn = 1)")
    ax.set_title("Vanilla mode: ECN concentration per workload (higher = more diffuse)")
    ax.legend(); ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out = PLOT_DIR / "fig6_high_counter_rate.png"
    fig.savefig(out, dpi=150); plt.close(fig)
    print(f"  → {out}")


# ── fig7: WTD block rate ─────────────────────────────────────────────────────
def fig7_wtd_block_rate(ev):
    df = ev[ev["mode"] == "wtd"]
    if df.empty:
        print("  fig7: no data"); return
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(WORKLOADS))
    width = 0.4
    for j, sev in enumerate((0, 4)):
        ys, errs = [], []
        for wl in WORKLOADS:
            g = df[(df["workload"] == wl) & (df["sev"] == sev)]
            vals = g["wtd_block_rate"].values
            ys.append(vals.mean() if len(vals) > 0 else 0)
            errs.append(ci95(vals))
        offset = (j - 0.5) * width
        ax.bar(x + offset, ys, width, yerr=errs, capsize=3,
               label=SEV_LABEL[sev], color=SEV_COLOR[sev], edgecolor='black', linewidth=0.4)
    ax.set_xticks(x); ax.set_xticklabels([WL_LABEL[w] for w in WORKLOADS],
                                          rotation=20, ha="right")
    ax.set_ylabel("WTD MD-block rate")
    ax.set_title("WTD mode: fraction of ECN ACKs blocked from MD")
    ax.legend(); ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out = PLOT_DIR / "fig7_wtd_block_rate.png"
    fig.savefig(out, dpi=150); plt.close(fig)
    print(f"  → {out}")


# ── fig8: mode × workload grid summary ───────────────────────────────────────
def fig8_mode_summary(fct):
    df = fct[fct["sev"] == 0]
    if df.empty:
        print("  fig8: no data"); return
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), sharey=False)
    for ax, wl in zip(axes.ravel(), WORKLOADS):
        sub = df[df["workload"] == wl]
        ys, errs = [], []
        for mode in MODES:
            g = sub[sub["mode"] == mode]
            per_seed = p99_per_seed(g)
            ys.append(per_seed.mean()); errs.append(ci95(per_seed.values))
        x = np.arange(len(MODES))
        ax.bar(x, ys, yerr=errs, capsize=2,
               color=[MODE_COLOR[m] for m in MODES], edgecolor='black', linewidth=0.4)
        ax.set_xticks(x); ax.set_xticklabels([MODE_LABEL[m] for m in MODES],
                                              rotation=30, ha="right")
        ax.set_ylabel("p99 FCT Slowdown")
        ax.set_title(WL_LABEL[wl])
        ax.grid(True, axis="y", alpha=0.3)
    fig.suptitle("Mode comparison summary — all 4 paper workloads (sev=0, paper config, 800 G)",
                 fontsize=12)
    fig.tight_layout()
    out = PLOT_DIR / "fig8_mode_summary.png"
    fig.savefig(out, dpi=150); plt.close(fig)
    print(f"  → {out}")


def main():
    print("Loading data ...")
    fct, ev, diag = load_data()
    print(f"  FCT rows: {len(fct):,}  Event rows: {len(ev)}  Diag rows: {len(diag):,}")

    print("\nGenerating figures ...")
    fig1_baseline(fct)
    fig2_perm(fct)
    fig3_hsdp(fct)
    fig4_incast(fct)
    fig5_ecn_counter_dist(diag)
    fig6_high_counter_rate(ev)
    fig7_wtd_block_rate(ev)
    fig8_mode_summary(fct)
    print(f"\nAll figures written to {PLOT_DIR}/")


if __name__ == "__main__":
    main()
