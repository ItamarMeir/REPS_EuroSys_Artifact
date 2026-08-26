#!/usr/bin/env python3
"""Plot exp15: PATH_RR buffer-order (starting-index mode) effect on FCT.

Reads: data/fcts.csv
Writes: plots/exp15_fct_slowdown.png

Optimal FCT = (flow_size_bytes * 8) / 400e9 * 1e6 + 6 * 0.5  µs
(6 hops cross-pod 3-tier fat-tree; all tornado flows are cross-pod)
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
NUM_HOPS = 6
HOP_LATENCY_US = 0.5

MODES = ["zero", "src_mod", "dst_mod", "srcdst_hash"]
MODE_LABELS = {
    "zero":        "zero\n(sync)",
    "src_mod":     "src_mod\n(src%N)",
    "dst_mod":     "dst_mod\n(dst%N)",
    "srcdst_hash": "srcdst\n(hash)",
}
COLORS = {
    "zero":        "#9E9E9E",
    "src_mod":     "#1565C0",
    "dst_mod":     "#2E7D32",
    "srcdst_hash": "#F57F17",
}
SIZES_BYTES = [4194304, 8388608, 16777216, 67108864, 268435456, 1073741824]
SIZE_LABELS = {
    4194304:    "4 MiB",
    8388608:    "8 MiB",
    16777216:   "16 MiB",
    67108864:   "64 MiB",
    268435456:  "256 MiB",
    1073741824: "1 GiB",
}


def optimal_fct_us(flow_size_bytes):
    return (flow_size_bytes * 8) / LINK_RATE_BPS * 1e6 + NUM_HOPS * HOP_LATENCY_US


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
            key = (row["mode"], int(row["size_bytes"]), int(row["seed"]))
            runs[key].append(float(row["fct_us"]))

    grouped = defaultdict(lambda: defaultdict(lambda: {"avg": [], "max": []}))
    for (mode, size_bytes, seed), fcts in runs.items():
        opt = optimal_fct_us(size_bytes)
        grouped[mode][size_bytes]["avg"].append((sum(fcts) / len(fcts)) / opt)
        grouped[mode][size_bytes]["max"].append(max(fcts) / opt)
    return grouped


def plot_metric(ax, grouped, metric_key, title, ylabel):
    n_modes = len(MODES)
    n_sizes = len(SIZES_BYTES)
    group_width = 0.8
    bar_w = group_width / n_modes
    x_centers = list(range(n_sizes))

    for mi, mode in enumerate(MODES):
        offsets = [(x + (mi - n_modes / 2 + 0.5) * bar_w) for x in x_centers]
        means, errs = [], []
        for size in SIZES_BYTES:
            vals = grouped[mode][size][metric_key]
            m, e = ci95(vals) if vals else (float("nan"), 0.0)
            means.append(m)
            errs.append(e)
        ax.bar(offsets, means, width=bar_w * 0.9,
               yerr=errs, capsize=3,
               color=COLORS[mode], label=MODE_LABELS[mode],
               error_kw={"elinewidth": 1.2})

    ax.axhline(1.0, color="black", linewidth=1.0, linestyle="--", label="Optimal (1.0)")
    ax.set_xticks(x_centers)
    ax.set_xticklabels([SIZE_LABELS[s] for s in SIZES_BYTES])
    ax.set_xlabel("Flow size")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8, ncol=3)
    ax.set_ylim(bottom=0)


def main():
    if not DATA.exists():
        print(f"ERROR: {DATA} not found — run aggregate_exp15.py first")
        return

    grouped = load_and_group()

    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    fig.suptitle(
        "exp15: PATH_RR buffer order — effect of starting-index mode on FCT\n"
        "(PATH_RR + line-rate, tornado workload, 4-ary fat-tree)\n"
        "Slowdown from optimal FCT (lower = better; 1.0 = theoretical minimum)",
        fontsize=10
    )

    plot_metric(axes[0], grouped, "avg", "Avg-FCT slowdown", "Avg FCT / Optimal FCT")
    plot_metric(axes[1], grouped, "max", "Max-FCT slowdown", "Max FCT / Optimal FCT")

    plt.tight_layout()
    out = PLOTS / "exp15_fct_slowdown.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    print("\nSummary (mean ± 95% CI across 3 seeds):")
    print(f"{'Mode':<14}  {'Size':>6}  {'Avg-slowdown':>13}  {'Max-slowdown':>13}")
    for mode in MODES:
        for size in SIZES_BYTES:
            avgs = grouped[mode][size]["avg"]
            maxs = grouped[mode][size]["max"]
            am, ae = ci95(avgs) if avgs else (float("nan"), 0)
            mm, me = ci95(maxs) if maxs else (float("nan"), 0)
            print(f"{mode:<14}  {SIZE_LABELS[size]:>6}  {am:>8.4f}±{ae:.4f}  {mm:>8.4f}±{me:.4f}")


if __name__ == "__main__":
    main()
