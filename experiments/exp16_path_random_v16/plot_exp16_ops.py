#!/usr/bin/env python3
"""Plot exp16 OPS comparison: all 8 conditions at 16 MiB and 64 MiB.

Reads: data/fcts.csv
Writes: plots/exp16_ops_comparison.png

Optimal FCT = (flow_size_bytes * 8) / 400e9 * 1e6 + 6 * 0.5  µs
"""

import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import scipy.stats

ROOT  = Path(__file__).resolve().parent
DATA  = ROOT / "data" / "fcts.csv"
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)

LINK_RATE_BPS  = 400e9
NUM_HOPS       = 6
HOP_LATENCY_US = 0.5
MTU_BYTES      = 4150   # mss=4096 + hdr=54
PKT_SERIAL_US  = MTU_BYTES * 8 / LINK_RATE_BPS * 1e6

SIZES_BYTES = [16777216, 67108864]
SIZE_LABELS = {16777216: "16 MiB", 67108864: "64 MiB"}

CONDITIONS = [
    "path_rr_constant",
    "path_rr_nscc",
    "freezing_constant",
    "freezing_nscc",
    "path_random_constant",
    "path_random_nscc",
    "ops_constant",
    "ops_nscc",
    "path_static_constant",
    "path_static_nscc",
]
LABELS = {
    "path_rr_constant":      "PATH_RR\n+constant",
    "path_rr_nscc":          "PATH_RR\n+NSCC",
    "freezing_constant":     "FREEZING\n+constant",
    "freezing_nscc":         "FREEZING\n+NSCC",
    "path_random_constant":  "PATH_RANDOM\n+constant",
    "path_random_nscc":      "PATH_RANDOM\n+NSCC",
    "ops_constant":          "OPS\n+constant",
    "ops_nscc":              "OPS\n+NSCC",
    "path_static_constant":  "PATH_STATIC\n+constant",
    "path_static_nscc":      "PATH_STATIC\n+NSCC",
}
COLORS = {
    "path_rr_constant":     "#9E9E9E",
    "path_rr_nscc":         "#1565C0",
    "freezing_constant":    "#FF8F00",
    "freezing_nscc":        "#2E7D32",
    "path_random_constant": "#C62828",
    "path_random_nscc":     "#6A1B9A",
    "ops_constant":         "#00838F",
    "ops_nscc":             "#558B2F",
    "path_static_constant": "#B71C1C",
    "path_static_nscc":     "#0D47A1",
}


def optimal_fct_us(flow_size_bytes):
    t_serial       = flow_size_bytes * 8 / LINK_RATE_BPS * 1e6
    data_traversal = NUM_HOPS * (HOP_LATENCY_US + PKT_SERIAL_US)
    ack_return     = NUM_HOPS * HOP_LATENCY_US
    return t_serial + data_traversal + ack_return


def ci95(vals):
    n = len(vals)
    if n < 2:
        return (vals[0] if n == 1 else float("nan")), 0.0
    m = sum(vals) / n
    s = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))
    t = scipy.stats.t.ppf(0.975, df=n - 1)
    return m, t * s / math.sqrt(n)


def load_and_group():
    runs = defaultdict(list)
    with DATA.open() as f:
        for row in csv.DictReader(f):
            size = int(row["size_bytes"])
            if size not in SIZES_BYTES:
                continue
            key = (row["condition"], size, int(row["seed"]))
            runs[key].append(float(row["fct_us"]))

    grouped = defaultdict(lambda: defaultdict(lambda: {"avg": [], "max": []}))
    for (cond, size, seed), fcts in runs.items():
        opt = optimal_fct_us(size)
        grouped[cond][size]["avg"].append((sum(fcts) / len(fcts)) / opt)
        grouped[cond][size]["max"].append(max(fcts) / opt)
    return grouped


def plot_metric(ax, grouped, metric_key, title, ylabel):
    n_conds = len(CONDITIONS)
    n_sizes = len(SIZES_BYTES)
    group_width = 0.85
    bar_w = group_width / n_conds
    x_centers = list(range(n_sizes))

    for ci, cond in enumerate(CONDITIONS):
        offsets = [(x + (ci - n_conds / 2 + 0.5) * bar_w) for x in x_centers]
        means, errs = [], []
        for size in SIZES_BYTES:
            vals = grouped[cond][size][metric_key]
            m, e = ci95(vals) if vals else (float("nan"), 0.0)
            means.append(m)
            errs.append(e)
        ax.bar(offsets, means, width=bar_w * 0.9,
               yerr=errs, capsize=3,
               color=COLORS[cond], label=LABELS[cond].replace("\n", " "),
               error_kw={"elinewidth": 1.2})

    ax.axhline(1.0, color="black", linewidth=1.0, linestyle="--", label="Optimal (1.0)")
    ax.set_xticks(x_centers)
    ax.set_xticklabels([SIZE_LABELS[s] for s in SIZES_BYTES])
    ax.set_xlabel("Flow size")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=7, ncol=2)
    ax.set_ylim(bottom=0)


def main():
    if not DATA.exists():
        print(f"ERROR: {DATA} not found — run aggregate_exp16.py first")
        return

    grouped = load_and_group()

    fig, axes = plt.subplots(1, 2, figsize=(18, 5))
    fig.suptitle(
        "exp16: OPS / PATH_RANDOM / PATH_STATIC vs PATH_RR / FREEZING — 16 MiB and 64 MiB\n"
        "(tornado workload, 4-ary fat-tree 3-tier, 400 Gbps, cwnd=90)\n"
        "PATH_STATIC = collision-free precomputed single path (sanity check; expected ≈1.0×)\n"
        "Slowdown from optimal FCT (lower = better; 1.0 = theoretical minimum)",
        fontsize=9,
    )

    plot_metric(axes[0], grouped, "avg", "Avg-FCT slowdown", "Avg FCT / Optimal FCT")
    plot_metric(axes[1], grouped, "max", "Max-FCT slowdown", "Max FCT / Optimal FCT")

    plt.tight_layout()
    out = PLOTS / "exp16_ops_comparison.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    print("\nSummary (mean ± 95% CI across seeds):")
    print(f"{'Condition':<26}  {'Size':>7}  {'Avg-slowdown':>13}  {'Max-slowdown':>13}")
    for cond in CONDITIONS:
        for size in SIZES_BYTES:
            avgs = grouped[cond][size]["avg"]
            maxs = grouped[cond][size]["max"]
            am, ae = ci95(avgs) if avgs else (float("nan"), 0)
            mm, me = ci95(maxs) if maxs else (float("nan"), 0)
            print(f"{cond:<26}  {SIZE_LABELS[size]:>7}  {am:>8.4f}±{ae:.4f}  {mm:>8.4f}±{me:.4f}")


if __name__ == "__main__":
    main()
