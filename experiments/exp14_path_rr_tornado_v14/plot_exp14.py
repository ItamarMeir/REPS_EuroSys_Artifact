#!/usr/bin/env python3
"""Plot exp14: FCT slowdown from optimal for PATH_RR vs REPS on tornado workload.

Reads: data/fcts.csv
Writes: plots/exp14_fct_slowdown.png

Optimal FCT = transmission + propagation:
  optimal_us = (flow_size_bytes * 8) / 400e9 * 1e6 + 6 * 0.5
  (6 hops for cross-pod 3-tier fat-tree at 0.5 µs/hop; all tornado flows are cross-pod)

Slowdown = actual_fct / optimal_fct (1.0 = perfect; lower is better)
"""

import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import scipy.stats

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "fcts.csv"
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)

LINK_RATE_BPS = 400e9
HOP_LATENCY_US = 0.5
NUM_HOPS = 6  # cross-pod 3-tier: host-ToR-Agg-Core-Agg-ToR-host

CONDITIONS = ["path_rr+constant", "path_rr+nscc", "freezing+nscc", "freezing+constant"]
COND_LABELS = {
    "path_rr+constant": "PATH_RR\n+Linerate",
    "path_rr+nscc":     "PATH_RR\n+NSCC",
    "freezing+nscc":    "REPS\n+NSCC",
    "freezing+constant":"REPS\n+Linerate",
}
COLORS = {
    "path_rr+constant": "#2196F3",
    "path_rr+nscc":     "#1565C0",
    "freezing+nscc":    "#E53935",
    "freezing+constant":"#B71C1C",
}
SIZES_BYTES = [4194304, 8388608, 16777216]
SIZE_LABELS = {4194304: "4 MiB", 8388608: "8 MiB", 16777216: "16 MiB"}


def optimal_fct_us(flow_size_bytes: int) -> float:
    tx = (flow_size_bytes * 8) / LINK_RATE_BPS * 1e6
    prop = NUM_HOPS * HOP_LATENCY_US
    return tx + prop


def ci95(vals):
    n = len(vals)
    if n < 2:
        return (vals[0] if n == 1 else float("nan")), 0.0
    m = sum(vals) / n
    s = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))
    t = scipy.stats.t.ppf(0.975, df=n - 1)
    return m, t * s / math.sqrt(n)


def load_data():
    # grouped[condition][size_bytes] -> list of per-run max/avg slowdown
    # We want per-seed (across all flows in that run) max and avg
    # Key: (condition, size_bytes, seed) -> list of fct_us values
    runs = defaultdict(list)
    with DATA.open() as f:
        for row in csv.DictReader(f):
            cond = row["condition"]
            size_bytes = int(row["size_bytes"])
            seed = int(row["seed"])
            fct_us = float(row["fct_us"])
            runs[(cond, size_bytes, seed)].append(fct_us)
    return runs


def compute_slowdowns(runs):
    # For each (cond, size), collect per-seed {avg_slowdown, max_slowdown}
    # grouped[cond][size] -> {"avg": [...], "max": [...]}
    grouped = defaultdict(lambda: defaultdict(lambda: {"avg": [], "max": []}))
    for (cond, size_bytes, seed), fcts in runs.items():
        opt = optimal_fct_us(size_bytes)
        avg_sd = (sum(fcts) / len(fcts)) / opt
        max_sd = max(fcts) / opt
        grouped[cond][size_bytes]["avg"].append(avg_sd)
        grouped[cond][size_bytes]["max"].append(max_sd)
    return grouped


def plot_metric(ax, grouped, metric_key, title, ylabel):
    n_conds = len(CONDITIONS)
    n_sizes = len(SIZES_BYTES)
    group_width = 0.8
    bar_w = group_width / n_conds
    x_centers = list(range(n_sizes))

    for ci, cond in enumerate(CONDITIONS):
        offsets = [(x + (ci - n_conds / 2 + 0.5) * bar_w) for x in x_centers]
        means, errs = [], []
        for size in SIZES_BYTES:
            vals = grouped[cond][size][metric_key]
            if vals:
                m, e = ci95(vals)
            else:
                m, e = float("nan"), 0.0
            means.append(m)
            errs.append(e)
        ax.bar(offsets, means, width=bar_w * 0.9,
               yerr=errs, capsize=3,
               color=COLORS[cond], label=COND_LABELS[cond],
               error_kw={"elinewidth": 1.2})

    ax.axhline(1.0, color="black", linewidth=1.0, linestyle="--", label="Optimal (1.0)")
    ax.set_xticks(x_centers)
    ax.set_xticklabels([SIZE_LABELS[s] for s in SIZES_BYTES])
    ax.set_xlabel("Flow size")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8, ncol=2)
    ax.set_ylim(bottom=0)


def main():
    if not DATA.exists():
        print(f"ERROR: {DATA} not found — run aggregate_exp14.py first")
        return

    runs = load_data()
    grouped = compute_slowdowns(runs)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("exp14: PATH_RR vs REPS — Tornado workload, 4-ary fat-tree\n"
                 "Slowdown from optimal FCT (lower = better; 1.0 = theoretical minimum)",
                 fontsize=11)

    plot_metric(axes[0], grouped, "avg", "Avg-FCT slowdown", "Avg FCT / Optimal FCT")
    plot_metric(axes[1], grouped, "max", "Max-FCT slowdown", "Max FCT / Optimal FCT")

    plt.tight_layout()
    out = PLOTS / "exp14_fct_slowdown.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    # Print summary table
    print("\nSummary (mean slowdown across seeds):")
    print(f"{'Condition':<22}  {'Size':>6}  {'Avg-slowdown':>13}  {'Max-slowdown':>13}")
    for cond in CONDITIONS:
        for size in SIZES_BYTES:
            avgs = grouped[cond][size]["avg"]
            maxs = grouped[cond][size]["max"]
            am, ae = ci95(avgs) if avgs else (float("nan"), 0)
            mm, me = ci95(maxs) if maxs else (float("nan"), 0)
            print(f"{cond:<22}  {SIZE_LABELS[size]:>6}  {am:>8.3f}±{ae:.3f}  {mm:>8.3f}±{me:.3f}")


if __name__ == "__main__":
    main()
