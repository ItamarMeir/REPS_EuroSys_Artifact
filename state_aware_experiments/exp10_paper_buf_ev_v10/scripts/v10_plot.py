#!/usr/bin/env python3
"""
v10_plot.py — exp10 (paper workloads) plotter.

Reads data/v10_fct.csv and data/v10_events.csv, emits 8 figures to plots/.

Part A figures (buffer size sweep, fixed -paths 65535):
  fig1_buf_baseline.png  — p99 slowdown × buf_size × class (baseline)
  fig2_buf_hsdp.png      — p99 slowdown × buf_size × sev   (hsdp)
  fig3_buf_incast.png    — p99 slowdown × buf_size × sev   (incast32)

Part B figures (EV domain sweep, fixed buf=8):
  fig4_ev_baseline.png   — p99 slowdown × paths × class    (baseline)
  fig5_ev_hsdp.png       — p99 slowdown × paths × sev      (hsdp)
  fig6_ev_incast.png     — p99 slowdown × paths × sev      (incast32)

Summary figures (all 4 workloads, sev=0):
  fig7_buf_summary.png   — mean slowdown × buf_size × workload
  fig8_ev_summary.png    — mean slowdown × paths    × workload

95% CI across seeds via t-distribution.
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

DARK2 = plt.cm.Dark2(np.linspace(0, 1, 8))

BUF_VALUES = [1, 2, 4, 8, 1024]
EV_VALUES  = [32, 256, 65535]
BUF_TICKS  = ["1", "2", "4", "8", "∞"]
EV_TICKS   = ["32", "256", "64K"]

WL_LABEL = {
    "baseline": "Baseline (perm + 4 ECMP)",
    "perm":     "Pure permutation",
    "hsdp":     "HSDP (Llama-70B)",
    "incast32": "Incast 32→1",
}
WL_COLOR = {
    "baseline": DARK2[0],
    "perm":     DARK2[1],
    "hsdp":     DARK2[2],
    "incast32": DARK2[3],
}
WL_MARKER = {
    "baseline": "o",
    "perm":     "s",
    "hsdp":     "^",
    "incast32": "D",
}

SEV_LABEL = {0: "Healthy (sev=0)", 4: "Failure (sev=4)"}
SEV_COLOR = {0: DARK2[0], 4: DARK2[4]}

CLASS_LABEL = {
    "ecmp_elephant": "ECMP elephants (ids 1-4, 64 MB)",
    "sprayed_perm":  "Sprayed permutation (ids 5-128, 8 MB)",
}
CLASS_COLOR = {"ecmp_elephant": DARK2[5], "sprayed_perm": DARK2[6]}

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


def p99_slowdown_per_seed(group):
    return group.groupby("seed")["slowdown"].quantile(0.99)


def mean_slowdown_per_seed(group):
    return group.groupby("seed")["slowdown"].mean()


def load_data():
    fct = pd.read_csv(DATA_DIR / "v10_fct.csv")
    ev  = pd.read_csv(DATA_DIR / "v10_events.csv")
    return fct, ev


# ── Part A: baseline (2 classes, sev=0) ──────────────────────────────────────
def fig1_buf_baseline(fct):
    df = fct[(fct["part"] == "buf") & (fct["workload"] == "baseline") & (fct["sev"] == 0)]
    if df.empty:
        print("  fig1: no data"); return
    fig, ax = plt.subplots(figsize=(6, 4))
    for cls in ("ecmp_elephant", "sprayed_perm"):
        sub = df[df["flow_class"] == cls]
        ys, errs = [], []
        for bv in BUF_VALUES:
            g = sub[sub["axis_val"] == bv]
            per_seed = p99_slowdown_per_seed(g)
            ys.append(per_seed.mean()); errs.append(ci95(per_seed.values))
        ax.errorbar(range(len(BUF_VALUES)), ys, yerr=errs,
                    label=CLASS_LABEL[cls], color=CLASS_COLOR[cls],
                    marker="o", linewidth=1.5, capsize=3)
    ax.set_xticks(range(len(BUF_VALUES))); ax.set_xticklabels(BUF_TICKS)
    ax.set_xlabel("REPS Buffer Size (slots)")
    ax.set_ylabel("p99 FCT Slowdown")
    ax.set_title("Part A: p99 Slowdown × Buffer Size — Baseline (4 ECMP + 124 sprayed perm)\n"
                 "sev=0, 800 Gbps")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = PLOT_DIR / "fig1_buf_baseline.png"
    fig.savefig(out, dpi=150); plt.close(fig)
    print(f"  → {out}")


def _fig_per_workload_axis(fct, *, part_letter, workload, fig_path, axis_values, axis_ticks,
                           axis_label, title_prefix):
    df = fct[(fct["part"] == part_letter) & (fct["workload"] == workload)]
    if df.empty:
        print(f"  {fig_path.name}: no data"); return
    fig, ax = plt.subplots(figsize=(6, 4))
    for sev in (0, 4):
        sub = df[df["sev"] == sev]
        ys, errs = [], []
        for av in axis_values:
            g = sub[sub["axis_val"] == av]
            per_seed = p99_slowdown_per_seed(g)
            ys.append(per_seed.mean()); errs.append(ci95(per_seed.values))
        ax.errorbar(range(len(axis_values)), ys, yerr=errs,
                    label=SEV_LABEL[sev], color=SEV_COLOR[sev],
                    marker="o", linewidth=1.5, capsize=3)
    ax.set_xticks(range(len(axis_values))); ax.set_xticklabels(axis_ticks)
    ax.set_xlabel(axis_label)
    ax.set_ylabel("p99 FCT Slowdown")
    ax.set_title(f"{title_prefix} — {WL_LABEL[workload]}\n800 Gbps")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_path, dpi=150); plt.close(fig)
    print(f"  → {fig_path}")


def fig2_buf_hsdp(fct):
    _fig_per_workload_axis(fct, part_letter="buf", workload="hsdp",
        fig_path=PLOT_DIR / "fig2_buf_hsdp.png",
        axis_values=BUF_VALUES, axis_ticks=BUF_TICKS,
        axis_label="REPS Buffer Size (slots)",
        title_prefix="Part A: p99 Slowdown × Buffer Size")


def fig3_buf_incast(fct):
    _fig_per_workload_axis(fct, part_letter="buf", workload="incast32",
        fig_path=PLOT_DIR / "fig3_buf_incast.png",
        axis_values=BUF_VALUES, axis_ticks=BUF_TICKS,
        axis_label="REPS Buffer Size (slots)",
        title_prefix="Part A: p99 Slowdown × Buffer Size")


def fig4_ev_baseline(fct):
    df = fct[(fct["part"] == "ev") & (fct["workload"] == "baseline") & (fct["sev"] == 0)]
    if df.empty:
        print("  fig4: no data"); return
    fig, ax = plt.subplots(figsize=(6, 4))
    for cls in ("ecmp_elephant", "sprayed_perm"):
        sub = df[df["flow_class"] == cls]
        ys, errs = [], []
        for av in EV_VALUES:
            g = sub[sub["axis_val"] == av]
            per_seed = p99_slowdown_per_seed(g)
            ys.append(per_seed.mean()); errs.append(ci95(per_seed.values))
        ax.errorbar(range(len(EV_VALUES)), ys, yerr=errs,
                    label=CLASS_LABEL[cls], color=CLASS_COLOR[cls],
                    marker="s", linewidth=1.5, capsize=3)
    ax.set_xticks(range(len(EV_VALUES))); ax.set_xticklabels(EV_TICKS)
    ax.set_xlabel("EV Domain (-paths)")
    ax.set_ylabel("p99 FCT Slowdown")
    ax.set_title("Part B: p99 Slowdown × EV Domain — Baseline (4 ECMP + 124 sprayed perm)\n"
                 "sev=0, buf=8, 800 Gbps")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = PLOT_DIR / "fig4_ev_baseline.png"
    fig.savefig(out, dpi=150); plt.close(fig)
    print(f"  → {out}")


def fig5_ev_hsdp(fct):
    _fig_per_workload_axis(fct, part_letter="ev", workload="hsdp",
        fig_path=PLOT_DIR / "fig5_ev_hsdp.png",
        axis_values=EV_VALUES, axis_ticks=EV_TICKS,
        axis_label="EV Domain (-paths)",
        title_prefix="Part B: p99 Slowdown × EV Domain")


def fig6_ev_incast(fct):
    _fig_per_workload_axis(fct, part_letter="ev", workload="incast32",
        fig_path=PLOT_DIR / "fig6_ev_incast.png",
        axis_values=EV_VALUES, axis_ticks=EV_TICKS,
        axis_label="EV Domain (-paths)",
        title_prefix="Part B: p99 Slowdown × EV Domain")


# ── Summary plots ─────────────────────────────────────────────────────────────
def _fig_summary(fct, *, part_letter, axis_values, axis_ticks, axis_label, fig_path, title):
    df = fct[(fct["part"] == part_letter) & (fct["sev"] == 0)]
    if df.empty:
        print(f"  {fig_path.name}: no data"); return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for wl in ("baseline", "perm", "hsdp", "incast32"):
        sub = df[df["workload"] == wl]
        ys, errs = [], []
        for av in axis_values:
            g = sub[sub["axis_val"] == av]
            per_seed = mean_slowdown_per_seed(g)
            ys.append(per_seed.mean()); errs.append(ci95(per_seed.values))
        ax.errorbar(range(len(axis_values)), ys, yerr=errs,
                    label=WL_LABEL[wl], color=WL_COLOR[wl],
                    marker=WL_MARKER[wl], linewidth=1.5, capsize=3)
    ax.set_xticks(range(len(axis_values))); ax.set_xticklabels(axis_ticks)
    ax.set_xlabel(axis_label)
    ax.set_ylabel("Mean FCT Slowdown")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_path, dpi=150); plt.close(fig)
    print(f"  → {fig_path}")


def fig7_buf_summary(fct):
    _fig_summary(fct, part_letter="buf",
        axis_values=BUF_VALUES, axis_ticks=BUF_TICKS,
        axis_label="REPS Buffer Size (slots)",
        fig_path=PLOT_DIR / "fig7_buf_summary.png",
        title="Summary: Mean Slowdown × Buffer Size — all paper workloads (sev=0)")


def fig8_ev_summary(fct):
    _fig_summary(fct, part_letter="ev",
        axis_values=EV_VALUES, axis_ticks=EV_TICKS,
        axis_label="EV Domain (-paths)",
        fig_path=PLOT_DIR / "fig8_ev_summary.png",
        title="Summary: Mean Slowdown × EV Domain — all paper workloads (sev=0, buf=8)")


def main():
    print("Loading data ...")
    fct, ev = load_data()
    print(f"  FCT rows: {len(fct):,}  Event rows: {len(ev)}")
    print(f"  Workloads present: {sorted(fct['workload'].unique())}")

    print("\nGenerating figures ...")
    fig1_buf_baseline(fct)
    fig2_buf_hsdp(fct)
    fig3_buf_incast(fct)
    fig4_ev_baseline(fct)
    fig5_ev_hsdp(fct)
    fig6_ev_incast(fct)
    fig7_buf_summary(fct)
    fig8_ev_summary(fct)
    print(f"\nAll figures written to {PLOT_DIR}/")


if __name__ == "__main__":
    main()
