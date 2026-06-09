#!/usr/bin/env python3
"""Plot exp18 — start-slot sweep for PATH_RR: offset 0/1/2 vs PATH_STATIC.

1×2 grid: left=avg FCT slowdown, right=max FCT slowdown. 256 MiB only.
X-axis: off0 (synchronized), off1 (src%np), off2 (src*2%np), path_static (reference).
Two bars per bucket: constant CC (blue) and NSCC (orange).

Reads:  data/fcts.csv
Writes: plots/exp18_startslot_256mib.png
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
MTU_BYTES = 4150
PKT_SERIAL_US = MTU_BYTES * 8 / LINK_RATE_BPS * 1e6
SIZE_BYTES = 268435456  # 256 MiB

# Four conditions: off0, off1, off2, path_static (in order for plot)
CONDITIONS = ["off0", "off1", "off2", "path_static"]
COND_LABELS = {
    "off0": "Off-0",
    "off1": "Off-1",
    "off2": "Off-2",
    "path_static": "PATH_STATIC",
}

CC_VARIANTS = ["constant", "nscc"]
CC_COLORS = {"constant": "#1565C0", "nscc": "#E65100"}
CC_LABELS = {"constant": "constant CC", "nscc": "NSCC"}

def optimal_fct_us(size_bytes):
    t_serial = size_bytes * 8 / LINK_RATE_BPS * 1e6
    data_traversal = NUM_HOPS * (HOP_LATENCY_US + PKT_SERIAL_US)
    ack_return = NUM_HOPS * HOP_LATENCY_US
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
    n_conds = len(CONDITIONS)
    n_cc = len(CC_VARIANTS)
    group_w = 0.6
    bar_w = group_w / n_cc
    x_centers = list(range(n_conds))

    for ci, cc in enumerate(CC_VARIANTS):
        offsets = [(x + (ci - n_cc / 2 + 0.5) * bar_w) for x in x_centers]
        means, errs = [], []
        for cond in CONDITIONS:
            key = f"{cond}_{cc}"
            vals = grouped[key][metric_key]
            m, e = ci95(vals) if vals else (float("nan"), 0.0)
            means.append(m)
            errs.append(e)
        ax.bar(offsets, means, width=bar_w * 0.9,
               yerr=errs, capsize=3,
               color=CC_COLORS[cc], label=CC_LABELS[cc],
               error_kw={"elinewidth": 1.2})

    ax.axhline(1.0, color="black", linewidth=1.0, linestyle="--", label="Optimal (1.0×)")
    ax.set_xticks(x_centers)
    ax.set_xticklabels([COND_LABELS[c] for c in CONDITIONS], fontsize=9)
    ax.set_ylabel("FCT / Optimal FCT")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8)
    ax.set_ylim(bottom=0.99)

def main():
    if not DATA.exists():
        print(f"ERROR: {DATA} not found")
        return

    grouped = load_and_group()
    if not grouped:
        print("ERROR: no data loaded")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(
        "exp18: PATH_RR start-slot sweep — 256 MiB flows\n"
        "(tornado workload, 4-ary fat-tree 3-tier, 400 Gbps, cwnd=155)\n"
        "Off-0=all at slot 0, Off-1=src%np, Off-2=(src*2)%np, PATH_STATIC=reference",
        fontsize=9,
    )

    plot_panel(axes[0], grouped, "avg", "Avg-FCT slowdown")
    plot_panel(axes[1], grouped, "max", "Max-FCT slowdown")

    plt.tight_layout()
    out = PLOTS / "exp18_startslot_256mib.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    print("\nSummary (mean ± 95% CI across seeds):")
    print(f"{'Condition':<26}  {'Avg-slowdown':>13}  {'Max-slowdown':>13}")
    for cond in CONDITIONS:
        for cc in CC_VARIANTS:
            key = f"{cond}_{cc}"
            avgs = grouped[key]["avg"]
            maxs = grouped[key]["max"]
            am, ae = ci95(avgs) if avgs else (float("nan"), 0)
            mm, me = ci95(maxs) if maxs else (float("nan"), 0)
            print(f"{key:<26}  {am:>8.4f}±{ae:.4f}  {mm:>8.4f}±{me:.4f}")

if __name__ == "__main__":
    main()
