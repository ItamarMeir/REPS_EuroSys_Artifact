#!/usr/bin/env python3
"""
v7_plot.py — exp07 plotter.

Reads data/v7_fct.csv, data/v7_events.csv, data/v7_diagnostics.csv
and emits PNG plots to plots/.

Error bars: 95% CI using t-distribution, df = n_seeds - 1 = 2.

Plot catalogue
--------------
fig1_overall_p99_slowdown.png  — p99 FCT slowdown per mode × sev, faceted by workload
fig2_overall_mean_fct.png      — mean FCT (µs) per mode × sev, faceted by workload
fig3_composite_class.png       — composite breakdown: elephant / mice / incast p99 slowdown
fig4_fct_cdf_{workload}.png    — FCT CDF across all flows, 6 modes overlaid (sev=0, sev=4)
fig5_md_event_count.png        — freezing events (proxy for MD aggression) per mode × sev
fig6_diagnostic_timeseries.png — cwnd + exp_avg_ecn + ecn_counter vs time, src=0, sev=4, seed=42
fig7_wtd_block_rate.png        — WTD block rate per workload × sev (mode=wtd only)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
DATA_DIR   = EXP_DIR / "data"
PLOT_DIR   = EXP_DIR / "plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

# ── Design constants ──────────────────────────────────────────────────────────
MODES = ["vanilla", "wtd", "sf_md_gain_ecn", "sf_md_gain_fresh",
         "sf_blend_ecn", "sf_blend_fresh"]
MODE_LABELS = {
    "vanilla":          "Vanilla",
    "wtd":              "WTD",
    "sf_md_gain_ecn":   "Mode A\n(ECN ctr)",
    "sf_md_gain_fresh": "Mode A\n(fresh ctr)",
    "sf_blend_ecn":     "Mode B\n(ECN ctr)",
    "sf_blend_fresh":   "Mode B\n(fresh ctr)",
}
MODE_COLORS = {
    "vanilla":          "#607D8B",   # grey
    "wtd":              "#FF9800",   # orange
    "sf_md_gain_ecn":   "#2196F3",   # blue
    "sf_md_gain_fresh": "#03A9F4",   # light blue
    "sf_blend_ecn":     "#E91E63",   # pink/red
    "sf_blend_fresh":   "#9C27B0",   # purple
}
WORKLOADS  = ["pureperm_8mb", "composite", "perm_32mb", "perm_128mb"]
WL_LABELS  = {
    "pureperm_8mb": "PurePerm 8MB",
    "composite":    "Composite",
    "perm_32mb":    "Perm 32MB",
    "perm_128mb":   "Perm 128MB",
}
SEV_HATCH  = {0: "",     4: "///"}
SEV_ALPHA  = {0: 0.85,   4: 0.7}
SEV_LABEL  = {0: "sev=0 (healthy)", 4: "sev=4 (1 link failed)"}

# ── CI helper ─────────────────────────────────────────────────────────────────
def ci95(values):
    """Return (mean, half-width of 95% CI) using t-distribution (df = n-1)."""
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    n = len(a)
    if n < 2:
        return (float(a[0]) if n == 1 else np.nan), np.nan
    m = a.mean()
    se = stats.sem(a)
    h  = se * stats.t.ppf(0.975, df=n - 1)
    return m, h

def p99_ci95(values):
    """Per-seed p99, then CI across seeds."""
    return ci95(values)

# ── Load data ─────────────────────────────────────────────────────────────────
def load_data():
    fct    = pd.read_csv(DATA_DIR / "v7_fct.csv")
    events = pd.read_csv(DATA_DIR / "v7_events.csv")
    diag   = pd.read_csv(DATA_DIR / "v7_diagnostics.csv")
    return fct, events, diag

# ── Figure 1 — p99 FCT slowdown ───────────────────────────────────────────────
def plot_fig1(fct: pd.DataFrame):
    """6-mode grouped bar per workload, faceted 4-panel rows, sev as hatch."""
    fig, axes = plt.subplots(4, 1, figsize=(12, 14), sharey=False)
    fig.suptitle("p99 FCT Slowdown by Mode", fontsize=13, fontweight="bold")

    bar_width = 0.13
    x = np.arange(len(MODES))

    for ax, wl in zip(axes, WORKLOADS):
        sub = fct[fct["workload"] == wl]
        for si, sev in enumerate([0, 4]):
            ssub = sub[sub["sev"] == sev]
            # Per seed: p99 slowdown
            seed_p99 = ssub.groupby(["mode", "seed"])["slowdown"].quantile(0.99).reset_index()
            seed_p99.columns = ["mode", "seed", "p99_slowdown"]
            # CI across seeds
            stats_ = seed_p99.groupby("mode")["p99_slowdown"].apply(
                lambda v: ci95(v.values)
            )
            for mi, mode in enumerate(MODES):
                if mode not in stats_:
                    continue
                m, h = stats_[mode]
                offset = (si - 0.5) * bar_width
                bar = ax.bar(
                    x[mi] + offset, m,
                    width=bar_width,
                    color=MODE_COLORS[mode],
                    hatch=SEV_HATCH[sev],
                    alpha=SEV_ALPHA[sev],
                    label=f"{MODE_LABELS[mode]} ({SEV_LABEL[sev]})" if ax == axes[0] else "",
                )
                if np.isfinite(h) and h > 0:
                    ax.errorbar(x[mi] + offset, m, yerr=h, fmt="none",
                                color="black", capsize=3, linewidth=1)
        ax.set_title(WL_LABELS[wl], fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels([MODE_LABELS[m] for m in MODES], fontsize=8)
        ax.set_ylabel("p99 slowdown")
        ax.grid(axis="y", alpha=0.3)

    # Legend from first axis
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", fontsize=7, ncol=2)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    out = PLOT_DIR / "fig1_overall_p99_slowdown.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  saved {out.name}")

# ── Figure 2 — mean FCT ───────────────────────────────────────────────────────
def plot_fig2(fct: pd.DataFrame):
    """Mean FCT (µs) per mode × sev, faceted by workload."""
    fig, axes = plt.subplots(4, 1, figsize=(12, 14), sharey=False)
    fig.suptitle("Mean FCT by Mode (µs)", fontsize=13, fontweight="bold")

    bar_width = 0.13
    x = np.arange(len(MODES))

    for ax, wl in zip(axes, WORKLOADS):
        sub = fct[fct["workload"] == wl]
        for si, sev in enumerate([0, 4]):
            ssub = sub[sub["sev"] == sev]
            seed_mean = ssub.groupby(["mode", "seed"])["fct_us"].mean().reset_index()
            seed_mean.columns = ["mode", "seed", "mean_fct"]
            stats_ = seed_mean.groupby("mode")["mean_fct"].apply(
                lambda v: ci95(v.values)
            )
            for mi, mode in enumerate(MODES):
                if mode not in stats_:
                    continue
                m, h = stats_[mode]
                offset = (si - 0.5) * bar_width
                ax.bar(x[mi] + offset, m, width=bar_width,
                       color=MODE_COLORS[mode], hatch=SEV_HATCH[sev],
                       alpha=SEV_ALPHA[sev])
                if np.isfinite(h) and h > 0:
                    ax.errorbar(x[mi] + offset, m, yerr=h, fmt="none",
                                color="black", capsize=3, linewidth=1)
        ax.set_title(WL_LABELS[wl], fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels([MODE_LABELS[m] for m in MODES], fontsize=8)
        ax.set_ylabel("mean FCT (µs)")
        ax.grid(axis="y", alpha=0.3)

    # Shared legend patches
    from matplotlib.patches import Patch
    legend_items = [
        Patch(facecolor="grey", label=SEV_LABEL[0]),
        Patch(facecolor="grey", hatch="///", alpha=0.7, label=SEV_LABEL[4]),
    ]
    fig.legend(handles=legend_items, loc="upper right", fontsize=8)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    out = PLOT_DIR / "fig2_overall_mean_fct.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  saved {out.name}")

# ── Figure 3 — composite class breakdown ──────────────────────────────────────
def plot_fig3(fct: pd.DataFrame):
    """Composite only: elephant / mice / incast p99 slowdown × mode × sev."""
    sub = fct[fct["workload"] == "composite"]
    classes = ["elephant", "mice", "incast"]

    fig, axes = plt.subplots(3, 1, figsize=(12, 11), sharey=False)
    fig.suptitle("Composite Workload: p99 Slowdown by Flow Class", fontsize=13, fontweight="bold")

    bar_width = 0.13
    x = np.arange(len(MODES))

    for ax, fc in zip(axes, classes):
        csub = sub[sub["flow_class"] == fc]
        for si, sev in enumerate([0, 4]):
            ssub = csub[csub["sev"] == sev]
            seed_p99 = ssub.groupby(["mode", "seed"])["slowdown"].quantile(0.99).reset_index()
            seed_p99.columns = ["mode", "seed", "p99"]
            stats_ = seed_p99.groupby("mode")["p99"].apply(lambda v: ci95(v.values))
            for mi, mode in enumerate(MODES):
                if mode not in stats_:
                    continue
                m, h = stats_[mode]
                offset = (si - 0.5) * bar_width
                ax.bar(x[mi] + offset, m, width=bar_width,
                       color=MODE_COLORS[mode], hatch=SEV_HATCH[sev],
                       alpha=SEV_ALPHA[sev])
                if np.isfinite(h) and h > 0:
                    ax.errorbar(x[mi] + offset, m, yerr=h, fmt="none",
                                color="black", capsize=3, linewidth=1)
        ax.set_title(f"{fc} flows", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels([MODE_LABELS[m] for m in MODES], fontsize=8)
        ax.set_ylabel("p99 slowdown")
        ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    out = PLOT_DIR / "fig3_composite_class.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  saved {out.name}")

# ── Figure 4 — FCT CDF per workload ───────────────────────────────────────────
def plot_fig4(fct: pd.DataFrame):
    """One PNG per workload: FCT CDF, 6 modes overlaid, two panels (sev=0, sev=4)."""
    for wl in WORKLOADS:
        sub = fct[fct["workload"] == wl]
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        fig.suptitle(f"FCT CDF — {WL_LABELS[wl]}", fontsize=12, fontweight="bold")

        for ax, sev in zip(axes, [0, 4]):
            ssub = sub[sub["sev"] == sev]
            for mode in MODES:
                vals = ssub[ssub["mode"] == mode]["fct_us"].dropna().values
                if len(vals) == 0:
                    continue
                vals_s = np.sort(vals)
                cdf = np.arange(1, len(vals_s) + 1) / len(vals_s)
                ax.plot(vals_s, cdf, label=MODE_LABELS[mode].replace("\n", " "),
                        color=MODE_COLORS[mode], linewidth=1.5)
            ax.set_title(SEV_LABEL[sev])
            ax.set_xlabel("FCT (µs)")
            ax.set_ylabel("CDF")
            ax.set_xlim(left=0)
            ax.grid(alpha=0.3)
            ax.legend(fontsize=7, loc="lower right")

        plt.tight_layout()
        fname = f"fig4_fct_cdf_{wl}.png"
        out = PLOT_DIR / fname
        fig.savefig(out, dpi=150)
        plt.close(fig)
        print(f"  saved {fname}")

# ── Figure 5 — freezing event count ───────────────────────────────────────────
def plot_fig5(events: pd.DataFrame):
    """Bar chart: fz_starts per run per mode × sev (proxy for freeze aggression)."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Freezing Events per Run (proxy for congestion severity)", fontsize=12)

    bar_width = 0.13
    x = np.arange(len(MODES))

    for ax, sev in zip(axes, [0, 4]):
        sub = events[events["sev"] == sev]
        stats_ = sub.groupby("mode")["fz_starts"].apply(lambda v: ci95(v.values))
        for mi, mode in enumerate(MODES):
            if mode not in stats_:
                continue
            m, h = stats_[mode]
            ax.bar(x[mi], m, width=0.6 * bar_width * len(MODES),
                   color=MODE_COLORS[mode], alpha=0.85)
            if np.isfinite(h) and h > 0:
                ax.errorbar(x[mi], m, yerr=h, fmt="none",
                            color="black", capsize=3, linewidth=1)
        ax.set_title(SEV_LABEL[sev])
        ax.set_xticks(x)
        ax.set_xticklabels([MODE_LABELS[m] for m in MODES], fontsize=8)
        ax.set_ylabel("mean fz_starts per run (±95% CI)")
        ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    out = PLOT_DIR / "fig5_md_event_count.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  saved {out.name}")

# ── Figure 6 — diagnostic time-series ─────────────────────────────────────────
def plot_fig6(diag: pd.DataFrame):
    """
    src=0, composite, sev=4, seed=42: cwnd, exp_avg_ecn, ecn_counter vs time.
    6 modes overlaid.
    """
    sub = diag[(diag["src_id"] == 0) &
               (diag["workload"] == "composite") &
               (diag["sev"] == 4) &
               (diag["seed"] == 42)]

    if sub.empty:
        print("  WARNING: no data for fig6 (composite/sev=4/seed=42/src=0). Skipping.")
        return

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    fig.suptitle("Per-ACK Time-Series: src=0, composite, sev=4, seed=42", fontsize=12)

    panels = [
        ("cwnd_pkts",    "cwnd (packets)"),
        ("exp_avg_ecn",  "exp_avg_ecn (EWMA ECN)"),
        ("ecn_counter",  "ecn_counter (smart-filter B-capped)"),
    ]

    for ax, (col, ylabel) in zip(axes, panels):
        for mode in MODES:
            msub = sub[sub["mode"] == mode].sort_values("time_us")
            if msub.empty or col not in msub.columns:
                continue
            ax.plot(msub["time_us"], msub[col],
                    label=MODE_LABELS[mode].replace("\n", " "),
                    color=MODE_COLORS[mode], linewidth=1.0, alpha=0.85)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(alpha=0.3)

    axes[-1].set_xlabel("time (µs)")
    axes[0].legend(fontsize=7, loc="upper right")
    plt.tight_layout()
    out = PLOT_DIR / "fig6_diagnostic_timeseries.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  saved {out.name}")

# ── Figure 7 — WTD block rate ─────────────────────────────────────────────────
def plot_fig7(events: pd.DataFrame):
    """
    For mode=wtd only: wtd_block_rate per workload × sev.
    Sanity check that WTD is actually suppressing MD events.
    """
    sub = events[events["mode"] == "wtd"]
    if sub.empty:
        print("  WARNING: no WTD events data. Skipping fig7.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    fig.suptitle("WTD Block Rate (fraction of ECN ACKs where MD was suppressed)",
                 fontsize=11)

    x = np.arange(len(WORKLOADS))
    bar_width = 0.35

    for ax, sev in zip(axes, [0, 4]):
        ssub = sub[sub["sev"] == sev]
        stats_ = ssub.groupby("workload")["wtd_block_rate"].apply(
            lambda v: ci95(v.values)
        )
        for wi, wl in enumerate(WORKLOADS):
            if wl not in stats_:
                continue
            m, h = stats_[wl]
            ax.bar(wi, m, width=bar_width, color=MODE_COLORS["wtd"], alpha=0.85)
            if np.isfinite(h) and h > 0:
                ax.errorbar(wi, m, yerr=h, fmt="none",
                            color="black", capsize=3, linewidth=1)
        ax.set_title(SEV_LABEL[sev])
        ax.set_xticks(x)
        ax.set_xticklabels([WL_LABELS[w] for w in WORKLOADS], fontsize=8,
                           rotation=15, ha="right")
        ax.set_ylabel("WTD block rate (±95% CI)")
        ax.set_ylim(0, 1.05)
        ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    out = PLOT_DIR / "fig7_wtd_block_rate.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  saved {out.name}")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("Loading data ...")
    try:
        fct, events, diag = load_data()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("Run v7_aggregate.py first.")
        return

    if fct.empty:
        print("ERROR: v7_fct.csv is empty — no runs have completed yet.")
        return

    print(f"  fct: {len(fct)} rows, events: {len(events)} rows, diag: {len(diag)} rows")
    print("Generating plots ...")

    plot_fig1(fct)
    plot_fig2(fct)
    plot_fig3(fct)
    plot_fig4(fct)
    plot_fig5(events)
    plot_fig6(diag)
    plot_fig7(events)

    print(f"\nAll plots saved to: {PLOT_DIR}")

if __name__ == "__main__":
    main()
