#!/usr/bin/env python3
"""Plot exp17: 2×2 grid — row=flow size (16/64 MiB), col=avg/max FCT slowdown.

X-axis per subplot: algorithm buckets (PATH_RR, FREEZING, PATH_RANDOM, OPS, PATH_STATIC).
Two bars per bucket: constant CC (blue) and NSCC (orange).

Reads:  data/fcts.csv
Writes: plots/exp17_fct_slowdown.png
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

# Algorithm buckets — x-axis order
ALGOS = ["path_rr", "freezing", "path_random", "ops", "path_static"]
ALGO_LABELS = {
    "path_rr":      "PATH_RR",
    "freezing":     "FREEZING",
    "path_random":  "PATH_RANDOM",
    "ops":          "OPS",
    "path_static":  "PATH_STATIC",
}

# Two CC variants per bucket
CC_VARIANTS = ["constant", "nscc"]
CC_COLORS   = {"constant": "#1565C0", "nscc": "#E65100"}
CC_LABELS   = {"constant": "constant CC", "nscc": "NSCC"}


def optimal_fct_us(size_bytes):
    t_serial       = size_bytes * 8 / LINK_RATE_BPS * 1e6
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
    """Returns grouped[condition][size_bytes] = {"avg": [per-seed], "max": [per-seed]}"""
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


def plot_subplot(ax, grouped, size_bytes, metric_key, title):
    n_algos = len(ALGOS)
    n_cc    = len(CC_VARIANTS)
    group_w = 0.6
    bar_w   = group_w / n_cc
    x_centers = list(range(n_algos))

    for ci, cc in enumerate(CC_VARIANTS):
        offsets = [(x + (ci - n_cc / 2 + 0.5) * bar_w) for x in x_centers]
        means, errs = [], []
        for algo in ALGOS:
            cond = f"{algo}_{cc}"
            vals = grouped[cond][size_bytes][metric_key]
            m, e = ci95(vals) if vals else (float("nan"), 0.0)
            means.append(m)
            errs.append(e)
        ax.bar(offsets, means, width=bar_w * 0.9,
               yerr=errs, capsize=3,
               color=CC_COLORS[cc], label=CC_LABELS[cc],
               error_kw={"elinewidth": 1.2})

    ax.axhline(1.0, color="black", linewidth=1.0, linestyle="--", label="Optimal (1.0×)")
    ax.set_xticks(x_centers)
    ax.set_xticklabels([ALGO_LABELS[a] for a in ALGOS], fontsize=8)
    ax.set_ylabel("FCT / Optimal FCT")
    ax.set_title(title, fontsize=9)
    ax.legend(fontsize=7)
    ax.set_ylim(bottom=0.95)


def main():
    if not DATA.exists():
        print(f"ERROR: {DATA} not found — run aggregate_exp17.py first")
        return

    grouped = load_and_group()

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle(
        "exp17: All LB algorithms at cwnd=155 (= BDP knee)\n"
        "(tornado workload, 4-ary fat-tree 3-tier, 400 Gbps)\n"
        "Optimal = T_serial + 6×(0.5+0.083) µs + 6×0.5 µs   (lower = better; 1.0× = formula floor)",
        fontsize=10,
    )

    metrics = [("avg", "Avg-FCT slowdown"), ("max", "Max-FCT slowdown")]
    for ri, size in enumerate(SIZES_BYTES):
        for ci, (metric_key, metric_label) in enumerate(metrics):
            ax = axes[ri][ci]
            plot_subplot(
                ax, grouped, size, metric_key,
                f"{SIZE_LABELS[size]} — {metric_label}",
            )

    plt.tight_layout()
    out = PLOTS / "exp17_fct_slowdown.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    print("\nSummary (mean ± 95% CI across seeds):")
    print(f"{'Condition':<26}  {'Size':>7}  {'Avg-slowdown':>13}  {'Max-slowdown':>13}")
    for algo in ALGOS:
        for cc in CC_VARIANTS:
            cond = f"{algo}_{cc}"
            for size in SIZES_BYTES:
                avgs = grouped[cond][size]["avg"]
                maxs = grouped[cond][size]["max"]
                am, ae = ci95(avgs) if avgs else (float("nan"), 0)
                mm, me = ci95(maxs) if maxs else (float("nan"), 0)
                print(f"{cond:<26}  {SIZE_LABELS[size]:>7}  {am:>8.4f}±{ae:.4f}  {mm:>8.4f}±{me:.4f}")


if __name__ == "__main__":
    main()
