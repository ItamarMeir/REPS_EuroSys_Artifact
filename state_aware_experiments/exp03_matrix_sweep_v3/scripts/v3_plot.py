#!/usr/bin/env python3
"""
v3 plots from <exp03>/data/v3_data.csv + v3_events.csv.

Generates 4 plots per workload (×4 workloads = 16 plots) into <exp03>/plots/:

  <workload>_p99_vs_sev.png       — per-class p99 FCT vs severity (95% CI, sig markers)
  <workload>_median_vs_sev.png    — per-class median FCT vs severity
  <workload>_events_vs_sev.png    — FREEZING + state-aware events vs severity, bar chart
  <workload>_throughput_recovery.png — cumulative completed-bytes vs time (sev=4 only)

Paths are resolved relative to this script's location.
"""
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_EXP_DIR    = os.path.dirname(_SCRIPT_DIR)
OUT_DIR     = os.path.join(_EXP_DIR, "plots")
DATA_DIR    = os.path.join(_EXP_DIR, "data")
os.makedirs(OUT_DIR, exist_ok=True)

WORKLOADS = ["pureperm", "mice", "elephant", "composite"]
SEVS = [0, 1, 2, 4, 8]
MODES = ["vanilla", "stateaware"]
COLORS = {"vanilla": "tab:blue", "stateaware": "tab:orange"}
CLASS_ORDER = ["mice", "elephant", "incast"]

df = pd.read_csv(os.path.join(DATA_DIR, "v3_data.csv"))
ev = pd.read_csv(os.path.join(DATA_DIR, "v3_events.csv"))
print(f"loaded {len(df)} flow rows, {len(ev)} event rows")

def pct(arr, p):
    arr = np.sort(np.asarray(arr))
    if len(arr) == 0: return float("nan")
    return arr[min(len(arr)-1, int(len(arr)*p))]

def fct_metric_per_seed(sub_df, metric_fn):
    """Per-seed metric value across rows of sub_df. Returns list (one per seed)."""
    if sub_df.empty: return []
    return [metric_fn(g["fct_us"].values) for _, g in sub_df.groupby("seed")]

def ci95(values):
    """Return (lower, upper) for 95% CI of the mean, using t distribution."""
    a = np.asarray(values)
    if len(a) < 2:
        return (a.mean() if len(a) else float("nan"),
                a.mean() if len(a) else float("nan"))
    m = a.mean(); s = a.std(ddof=1)
    h = s * stats.t.ppf((1 + 0.95) / 2, len(a) - 1) / np.sqrt(len(a))
    return (m - h, m + h)

def plot_fct_vs_sev(workload, metric, metric_name, outpath):
    """Per-class metric vs severity, vanilla vs state-aware, with 95% CI error bars."""
    classes = [c for c in CLASS_ORDER if c in df[df["workload"] == workload]["flow_class"].unique()]
    n_cls = len(classes)
    fig, axes = plt.subplots(1, n_cls, figsize=(5*n_cls, 4.5), sharey=False, constrained_layout=True)
    if n_cls == 1: axes = [axes]
    metric_fn = (lambda a: pct(a, 0.99)) if metric == "p99" else (lambda a: np.median(a))

    for ax, cls in zip(axes, classes):
        for mode in MODES:
            xs = []; ys = []; lo = []; hi = []; sample_seeds = {}
            for sev in SEVS:
                sub = df[(df["workload"]==workload) & (df["mode"]==mode)
                         & (df["sev"]==sev) & (df["flow_class"]==cls)]
                vals = fct_metric_per_seed(sub, metric_fn)
                vals = [v for v in vals if v == v]  # drop NaN
                if not vals: continue
                m = np.mean(vals); l, h = ci95(vals)
                xs.append(sev); ys.append(m); lo.append(m-l); hi.append(h-m)
                sample_seeds[sev] = sub  # for sig test later
            if not xs: continue
            ax.errorbar(xs, ys, yerr=[lo, hi], marker="o", linewidth=1.5, capsize=4,
                        color=COLORS[mode], label=mode)

        # Significance markers (Mann-Whitney U on per-flow FCTs, between vanilla and SA at each sev)
        if "vanilla" in df[df["workload"]==workload]["mode"].unique() \
           and "stateaware" in df[df["workload"]==workload]["mode"].unique():
            for sev in SEVS:
                v = df[(df["workload"]==workload) & (df["mode"]=="vanilla")
                       & (df["sev"]==sev) & (df["flow_class"]==cls)]["fct_us"].values
                s = df[(df["workload"]==workload) & (df["mode"]=="stateaware")
                       & (df["sev"]==sev) & (df["flow_class"]==cls)]["fct_us"].values
                if len(v) < 5 or len(s) < 5: continue
                try:
                    _, p = stats.mannwhitneyu(v, s, alternative="two-sided")
                except ValueError:
                    continue
                if p < 0.001: tag = "***"
                elif p < 0.01: tag = "**"
                elif p < 0.05: tag = "*"
                else: continue
                # annotate above the higher of the two means at this sev
                v_mean = np.mean(fct_metric_per_seed(df[(df["workload"]==workload) & (df["mode"]=="vanilla") & (df["sev"]==sev) & (df["flow_class"]==cls)], metric_fn) or [0])
                s_mean = np.mean(fct_metric_per_seed(df[(df["workload"]==workload) & (df["mode"]=="stateaware") & (df["sev"]==sev) & (df["flow_class"]==cls)], metric_fn) or [0])
                y_top = max(v_mean, s_mean)
                ax.text(sev, y_top * 1.06, tag, ha="center", fontsize=10, color="black")

        ax.set_xticks(SEVS)
        ax.set_xlabel("# failed Agg-Core links")
        ax.set_ylabel(f"{metric_name} FCT (μs)")
        ax.set_title(f"{cls}", fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8, loc="best")
    fig.suptitle(f"{workload} — {metric_name} FCT vs failure severity   (5 seeds, 95% CI)",
                 fontsize=11)
    plt.savefig(outpath, dpi=120)
    plt.close(fig)
    print(f"  saved {outpath}")

def plot_events_vs_sev(workload, outpath):
    """Bar chart: FREEZING freeze events and state-aware events vs severity."""
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    width = 0.35
    xs = np.arange(len(SEVS))
    vanilla_means = []; vanilla_err = []
    sa_means = []; sa_err = []
    sa_freeze_means = []
    for sev in SEVS:
        v = ev[(ev["workload"]==workload) & (ev["mode"]=="vanilla") & (ev["sev"]==sev)]
        s = ev[(ev["workload"]==workload) & (ev["mode"]=="stateaware") & (ev["sev"]==sev)]
        vanilla_means.append(v["fz_starts"].mean() if len(v) else 0)
        vanilla_err.append(v["fz_starts"].std() if len(v) else 0)
        sa_means.append(s["fz_starts"].mean() if len(s) else 0)
        sa_err.append(s["fz_starts"].std() if len(s) else 0)
        sa_freeze_means.append(s["sa_freezes"].mean() if len(s) else 0)
    ax.bar(xs - width/2, vanilla_means, width, yerr=vanilla_err, capsize=3,
           label="vanilla FREEZING_starts", color="tab:blue", alpha=0.85)
    ax.bar(xs + width/2, sa_means, width, yerr=sa_err, capsize=3,
           label="state-aware FREEZING_starts", color="tab:orange", alpha=0.85)
    ax.plot(xs + width/2, sa_freeze_means, "k*", markersize=10,
            label="state-aware asymmetric-flag flips")
    ax.set_xticks(xs); ax.set_xticklabels(SEVS)
    ax.set_xlabel("# failed Agg-Core links")
    ax.set_ylabel("avg events per run (5 seeds)")
    ax.set_title(f"{workload} — FREEZING + state-aware event counts vs failure severity",
                 fontsize=11)
    ax.grid(True, alpha=0.3, axis="y")
    ax.legend(fontsize=8)
    plt.savefig(outpath, dpi=120)
    plt.close(fig)
    print(f"  saved {outpath}")

def plot_throughput_recovery(workload, sev, outpath):
    """Cumulative completed-bytes over time, vanilla vs state-aware, at fixed severity."""
    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    for mode in MODES:
        sub = df[(df["workload"]==workload) & (df["mode"]==mode) & (df["sev"]==sev)]
        if sub.empty: continue
        # Aggregate across seeds: bin time, sum sizes, average across seeds
        bins = np.linspace(0, sub["fct_us"].max() + 1, 100)
        per_seed_cum = []
        for seed, g in sub.groupby("seed"):
            order = g.sort_values("fct_us")
            cum_t = order["fct_us"].values
            cum_b = np.cumsum(order["size"].values)
            cum_at_bin = np.interp(bins, cum_t, cum_b, left=0)
            per_seed_cum.append(cum_at_bin)
        if not per_seed_cum: continue
        M = np.array(per_seed_cum)
        ax.plot(bins, M.mean(axis=0)/1e6, linewidth=1.8,
                color=COLORS[mode], label=f"{mode} (sev={sev})")
        ax.fill_between(bins, M.min(axis=0)/1e6, M.max(axis=0)/1e6,
                        color=COLORS[mode], alpha=0.15)
    # Add sev=0 reference
    for mode in MODES:
        sub = df[(df["workload"]==workload) & (df["mode"]==mode) & (df["sev"]==0)]
        if sub.empty: continue
        bins = np.linspace(0, sub["fct_us"].max() + 1, 100)
        per_seed_cum = []
        for seed, g in sub.groupby("seed"):
            order = g.sort_values("fct_us")
            cum_at_bin = np.interp(bins, order["fct_us"].values, np.cumsum(order["size"].values), left=0)
            per_seed_cum.append(cum_at_bin)
        if not per_seed_cum: continue
        M = np.array(per_seed_cum)
        ax.plot(bins, M.mean(axis=0)/1e6, linewidth=1.2, linestyle="--", alpha=0.6,
                color=COLORS[mode], label=f"{mode} (no fail, ref)")
    ax.axvspan(50, 200, color="red", alpha=0.08, label="failure window (sev>0)")
    ax.set_xlabel("time (μs)")
    ax.set_ylabel("cumulative completed bytes (MB)")
    ax.set_title(f"{workload} — failure-recovery cumulative throughput (sev={sev})", fontsize=11)
    ax.grid(True, alpha=0.3); ax.legend(fontsize=8, loc="lower right")
    plt.savefig(outpath, dpi=120)
    plt.close(fig)
    print(f"  saved {outpath}")

def main():
    for w in WORKLOADS:
        wdf = df[df["workload"] == w]
        if wdf.empty:
            print(f"skip {w} (no data)"); continue
        plot_fct_vs_sev(w, "p99",    "p99",    f"{OUT_DIR}/{w}_p99_vs_sev.png")
        plot_fct_vs_sev(w, "median", "median", f"{OUT_DIR}/{w}_median_vs_sev.png")
        plot_events_vs_sev(w,                  f"{OUT_DIR}/{w}_events_vs_sev.png")
        # Throughput-recovery: use sev=4 if available, else max sev present
        avail = sorted(wdf["sev"].unique())
        sev_choice = 4 if 4 in avail else (avail[-1] if avail else 0)
        plot_throughput_recovery(w, sev_choice,
                                 f"{OUT_DIR}/{w}_throughput_recovery_sev{sev_choice}.png")
    print(f"\nAll plots in {OUT_DIR}/")

if __name__ == "__main__":
    main()
