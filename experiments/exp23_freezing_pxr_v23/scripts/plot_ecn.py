#!/usr/bin/env python3
"""
plot_ecn.py — Exact ECN counts per flow, NSCC only, FREEZING_PXR buffer sweep.

Reads runs/freezing_pxr_b{B}_nscc_s{seed}.out directly.

Output: plots/ecn_exposure.png
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
RUNS_DIR   = EXP_DIR / "runs"
PLOTS_DIR  = EXP_DIR / "plots"

FINISH_RE = re.compile(
    r"finished at\s+[\d.]+.*?\becn_acks\s+(\d+)", re.IGNORECASE
)

BUF_SIZES   = [1, 2, 4, 8, 16, 32, 64]
ALGO_ORDER  = [f"freezing_pxr_b{b}" for b in BUF_SIZES]
ALGO_LABELS = {f"freezing_pxr_b{b}": f"B={b}" for b in BUF_SIZES}
ALGO_COLORS = {
    "freezing_pxr_b1":  "#f7fbff",
    "freezing_pxr_b2":  "#deebf7",
    "freezing_pxr_b4":  "#c6dbef",
    "freezing_pxr_b8":  "#9ecae1",
    "freezing_pxr_b16": "#6baed6",
    "freezing_pxr_b32": "#2171b5",
    "freezing_pxr_b64": "#08306b",
}


def ci95(values):
    n = len(values)
    if n < 2:
        return 0.0
    se = np.std(values, ddof=1) / np.sqrt(n)
    return float(stats.t.ppf(0.975, df=n - 1) * se)


def load_ecn_counts():
    rows = []
    for algo in ALGO_ORDER:
        for seed in [42, 43, 44]:
            path = RUNS_DIR / f"{algo}_nscc_s{seed}.out"
            if not path.exists():
                print(f"  WARNING: {path.name} not found — skipping", file=sys.stderr)
                continue
            counts = [int(m.group(1)) for line in path.read_text().splitlines()
                      if (m := FINISH_RE.search(line))]
            if not counts:
                print(f"  WARNING: no ecn_acks found in {path.name}", file=sys.stderr)
                continue
            rows.append({
                "algo":       algo,
                "seed":       seed,
                "mean_ecn":   np.mean(counts),
                "median_ecn": np.median(counts),
                "p99_ecn":    np.percentile(counts, 99),
                "n_flows":    len(counts),
            })
    return pd.DataFrame(rows)


def main():
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = load_ecn_counts()
    if df.empty:
        print("ERROR: no data found", file=sys.stderr)
        sys.exit(1)

    print(df[["algo", "seed", "n_flows", "mean_ecn", "median_ecn"]].to_string(index=False))

    agg = []
    for algo in ALGO_ORDER:
        sub = df[df["algo"] == algo]
        if sub.empty:
            continue
        agg.append({
            "algo":   algo,
            "mean":   sub["mean_ecn"].mean(),
            "ci":     ci95(sub["mean_ecn"].values),
            "median": sub["median_ecn"].mean(),
            "p99":    sub["p99_ecn"].mean(),
        })
    agg_df = pd.DataFrame(agg)

    present = [a for a in ALGO_ORDER if a in agg_df["algo"].values]
    x      = np.arange(len(present))
    bar_w  = 0.55
    colors = [ALGO_COLORS[a] for a in present]
    labels = [ALGO_LABELS[a] for a in present]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    for ax, metric, ylabel, title_sfx in [
        (axes[0], "mean", "Mean ECN-marked ACKs per flow", "mean"),
        (axes[1], "p99",  "p99  ECN-marked ACKs per flow", "p99"),
    ]:
        vals = [agg_df.loc[agg_df["algo"] == a, metric].values[0] for a in present]
        cis  = [agg_df.loc[agg_df["algo"] == a, "ci"].values[0]   for a in present]

        ax.bar(x, vals, bar_w, color=colors, edgecolor="black", linewidth=0.7,
               yerr=cis if metric == "mean" else None,
               capsize=3, error_kw={"elinewidth": 0.8, "ecolor": "black"})
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(
            f"ECN count ({title_sfx}) — K=16 tornado 8 MB, NSCC, 51 failed links, seeds 42-44",
            fontsize=9)
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.5)
        ax.set_axisbelow(True)

    fig.suptitle("FREEZING_PXR — ECN exposure per buffer size", fontsize=11)
    fig.tight_layout()
    out = PLOTS_DIR / "ecn_exposure.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
