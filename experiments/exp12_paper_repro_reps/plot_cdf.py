#!/usr/bin/env python3
"""
plot_cdf.py — FCT CDF plots for Fig 5c (and optionally all figs).

Reads: data/fcts.csv (produced by aggregate.py)
Writes: plots/fig5c_cdf.png  (and others if --fig supplied)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

EXP_DIR   = Path(__file__).parent
DATA_DIR  = EXP_DIR / "data"
PLOTS_DIR = EXP_DIR / "plots"
PLOTS_DIR.mkdir(exist_ok=True)

CCA_COLORS = {
    "swift":  "#f5a623",
    "lswift": "#e06020",
    "mswift": "#27ae60",
    "nscc":   "#2980b9",
    "mnscc":  "#c0392b",
}
CCA_LABELS = {
    "swift":  "Swift",
    "lswift": "LSwift",
    "mswift": "MSwift (P50)",
    "nscc":   "NSCC",
    "mnscc":  "MNSCC",
}

# Fig 5c: same runs as Fig 4 but excludes Swift
FIG5C_CCAS = ["lswift","mswift","nscc","mnscc"]


def plot_cdf(fig_key: str, df_fig: pd.DataFrame, ccas: list, title: str):
    if df_fig.empty:
        print(f"[{fig_key}] No data — skipping CDF.")
        return

    fig, ax = plt.subplots(figsize=(7, 4))

    for cc in ccas:
        vals = df_fig[df_fig["cc"] == cc]["fct_us"].values
        if len(vals) == 0:
            continue
        sorted_v = np.sort(vals)
        cdf = np.arange(1, len(sorted_v)+1) / len(sorted_v)
        ax.plot(sorted_v, cdf,
                label=CCA_LABELS.get(cc, cc),
                color=CCA_COLORS.get(cc, "#888"),
                linewidth=1.8)

    ax.set_xlabel("FCT (µs)", fontsize=11)
    ax.set_ylabel("CDF", fontsize=11)
    ax.set_xscale("log")
    ax.set_title(title, fontsize=10, pad=8)
    ax.legend(fontsize=9, loc="lower right")
    ax.set_ylim(0, 1.05)
    ax.grid(True, which="both", alpha=0.3)
    plt.tight_layout()
    outpath = PLOTS_DIR / f"{fig_key}_cdf.png"
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[plot] Saved {outpath.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fig", nargs="*", type=str, default=["5c"],
                        help="Figure IDs (e.g. 5c 4). Default: 5c.")
    args = parser.parse_args()

    csv_path = DATA_DIR / "fcts.csv"
    if not csv_path.exists():
        print(f"[error] {csv_path} not found. Run aggregate.py first.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path)

    for fig_num in args.fig:
        fig_key = f"fig{fig_num}"

        # Fig 5c reuses Fig 4 data
        src_key = "fig4" if fig_key == "fig5c" else fig_key
        df_fig = df[df["fig"] == src_key]

        if fig_key == "fig5c":
            ccas  = FIG5C_CCAS
            title = "Fig 5c — FCT CDF, Baseline, 128 nodes, 800 Gbps"
        else:
            ccas  = sorted(df_fig["cc"].unique())
            title = f"{fig_key} — FCT CDF"

        plot_cdf(fig_key, df_fig, ccas, title)


if __name__ == "__main__":
    main()
