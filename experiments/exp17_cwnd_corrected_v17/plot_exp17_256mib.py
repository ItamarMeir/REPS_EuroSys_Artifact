#!/usr/bin/env python3
"""Plot exp17 — 256 MiB only: 1×2 grid (avg | max), algorithm buckets on x-axis.

Reads:  data/fcts.csv
Writes: plots/exp17_fct_slowdown_256mib.png
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
MTU_BYTES      = 4150
PKT_SERIAL_US  = MTU_BYTES * 8 / LINK_RATE_BPS * 1e6

SIZE_BYTES = 268435456  # 256 MiB

ALGOS = ["path_rr", "freezing", "path_random", "ops", "path_static"]
ALGO_LABELS = {
    "path_rr":      "PATH_RR",
    "freezing":     "FREEZING",
    "path_random":  "PATH_RANDOM",
    "ops":          "OPS",
    "path_static":  "PATH_STATIC",
}

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
    runs = defaultdict(list)
    with DATA.open() as f:
        for row in csv.DictReader(f):
            if int(row["size_bytes"]) != SIZE_BYTES:
                continue
            key = (row["condition"], int(row["seed"]))
            runs[key].append(float(row["fct_us"]))

    grouped = defaultdict(lambda: {"avg": [], "max": []})
    opt = optimal_fct_us(SIZE_BYTES)
    for (cond, seed), fcts in runs.items():
        grouped[cond]["avg"].append((sum(fcts) / len(fcts)) / opt)
        grouped[cond]["max"].append(max(fcts) / opt)
    return grouped


def plot_panel(ax, grouped, metric_key, title):
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
            vals = grouped[cond][metric_key]
            m, e = ci95(vals) if vals else (float("nan"), 0.0)
            means.append(m)
            errs.append(e)
        ax.bar(offsets, means, width=bar_w * 0.9,
               yerr=errs, capsize=3,
               color=CC_COLORS[cc], label=CC_LABELS[cc],
               error_kw={"elinewidth": 1.2})

    ax.axhline(1.0, color="black", linewidth=1.0, linestyle="--", label="Optimal (1.0×)")
    ax.set_xticks(x_centers)
    ax.set_xticklabels([ALGO_LABELS[a] for a in ALGOS], fontsize=9)
    ax.set_ylabel("FCT / Optimal FCT")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8)
    ax.set_ylim(bottom=0.95)


def main():
    if not DATA.exists():
        print(f"ERROR: {DATA} not found — run aggregate_exp17.py first")
        return

    grouped = load_and_group()
    if not grouped:
        print("ERROR: no 256 MiB data — run scripts/02_run_exp17_256mib.sh first")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "exp17: All LB algorithms at cwnd=155 — 256 MiB flows\n"
        "(tornado workload, 4-ary fat-tree 3-tier, 400 Gbps)\n"
        "Optimal = T_serial + 6×(0.5+0.083) µs + 6×0.5 µs   (lower = better; 1.0× = formula floor)",
        fontsize=10,
    )

    plot_panel(axes[0], grouped, "avg", "Avg-FCT slowdown")
    plot_panel(axes[1], grouped, "max", "Max-FCT slowdown")

    plt.tight_layout()
    out = PLOTS / "exp17_fct_slowdown_256mib.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    print("\nSummary (mean ± 95% CI across seeds):")
    print(f"{'Condition':<26}  {'Avg-slowdown':>13}  {'Max-slowdown':>13}")
    for algo in ALGOS:
        for cc in CC_VARIANTS:
            cond = f"{algo}_{cc}"
            avgs = grouped[cond]["avg"]
            maxs = grouped[cond]["max"]
            am, ae = ci95(avgs) if avgs else (float("nan"), 0)
            mm, me = ci95(maxs) if maxs else (float("nan"), 0)
            print(f"{cond:<26}  {am:>8.4f}±{ae:.4f}  {mm:>8.4f}±{me:.4f}")


if __name__ == "__main__":
    main()
