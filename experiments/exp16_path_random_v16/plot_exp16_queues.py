#!/usr/bin/env python3
"""Plot exp16 core-switch queue depths vs time.

Reads: data/qlog_<condition>_64mib_seed42.csv  (6 conditions)
Writes: plots/exp16_queue_depth.png

For each condition: 4 lines (one per core switch).
Y = total bytes across all agg→core[c] queues for that core.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT  = Path(__file__).resolve().parent
DATA  = ROOT / "data"
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)

CONDITIONS = [
    "path_rr_constant",
    "path_rr_nscc",
    "freezing_constant",
    "freezing_nscc",
    "path_random_constant",
    "path_random_nscc",
]
LABELS = {
    "path_rr_constant":     "PATH_RR + constant",
    "path_rr_nscc":         "PATH_RR + NSCC",
    "freezing_constant":    "FREEZING + constant",
    "freezing_nscc":        "FREEZING + NSCC",
    "path_random_constant": "PATH_RANDOM + constant",
    "path_random_nscc":     "PATH_RANDOM + NSCC",
}
CORE_COLORS = ["#1565C0", "#C62828", "#2E7D32", "#6A1B9A"]


def load_all():
    dfs = {}
    for cond in CONDITIONS:
        p = DATA / f"qlog_{cond}_64mib_seed42.csv"
        if not p.exists():
            print(f"WARN: missing {p}")
            continue
        df = pd.read_csv(p)
        # sum bytes across all agg→core[c] uplinks for each (time, core) pair
        per_core = (df.groupby(["time_us", "core"], sort=False)["bytes"]
                    .sum()
                    .reset_index())
        dfs[cond] = per_core
    return dfs


def main():
    dfs = load_all()
    if not dfs:
        print("ERROR: no data found")
        return

    fig, axes = plt.subplots(2, 3, figsize=(18, 9), sharex=True, sharey=True)
    fig.suptitle(
        "exp16: Core-switch queue depth vs time (64 MiB, seed=42)\n"
        "Y = total bytes queued on all agg→core[c] uplinks; one line per core switch\n"
        "tornado workload, 4-ary fat-tree 3-tier, 400 Gbps, cwnd=90",
        fontsize=10,
    )

    cores = sorted(dfs[next(iter(dfs))]["core"].unique()) if dfs else []

    for ax, cond in zip(axes.flat, CONDITIONS):
        df = dfs.get(cond)
        if df is None:
            ax.set_visible(False)
            continue
        for c, color in zip(cores, CORE_COLORS):
            sub = df[df["core"] == c]
            ax.plot(sub["time_us"], sub["bytes"] / 1024,
                    label=f"core {c}", color=color, linewidth=0.7, alpha=0.85)
        ax.set_title(LABELS[cond], fontsize=9)
        ax.set_xlabel("Time (µs)", fontsize=8)
        ax.set_ylabel("Queue depth (KB)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.legend(fontsize=7, ncol=2)
        ax.set_ylim(bottom=0)

    plt.tight_layout()
    out = PLOTS / "exp16_queue_depth.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    print("\nSummary — mean queue depth per core (KB):")
    print(f"{'Condition':<26}  " + "  ".join(f"core{c}" for c in cores))
    for cond in CONDITIONS:
        df = dfs.get(cond)
        if df is None:
            continue
        means = [df[df["core"] == c]["bytes"].mean() / 1024 for c in cores]
        vals = "  ".join(f"{m:>6.1f}" for m in means)
        print(f"{cond:<26}  {vals}")


if __name__ == "__main__":
    main()
