#!/usr/bin/env python3
"""
plot_fct_raw.py -- exp24: absolute (non-normalized) mean FCT bar chart.

Same data/algorithm set as plot.py's mean_fct.png, but plots raw mean FCT in
microseconds instead of the PATH_STATIC+CONSTANT-normalized ratio, with the
value labeled atop each bar. No rerun -- reuses data/exp24_flows.csv.

Output: plots/mean_fct_raw.png
"""
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
DATA_CSV   = EXP_DIR / "data" / "exp24_flows.csv"
PLOTS_DIR  = EXP_DIR / "plots"

ALGO_ORDER = [
    "path_static",
    "freezing_b1",
    "freezing_b2",
    "freezing_b4",
    "freezing_b8",
    "freezing_b16",
    "freezing_b32",
    "freezing_b64",
    "reps",
    "reps_no_rr",
]
ALGO_LABELS = {
    "path_static":  "PATH_STATIC\n(oracle)",
    "freezing_b1":  "FREEZING\nB=1",
    "freezing_b2":  "FREEZING\nB=2",
    "freezing_b4":  "FREEZING\nB=4",
    "freezing_b8":  "FREEZING\nB=8",
    "freezing_b16": "FREEZING\nB=16",
    "freezing_b32": "FREEZING\nB=32",
    "freezing_b64": "FREEZING\nB=64",
    "reps":         "REPS\n(round-robin,\noriginal)",
    "reps_no_rr":   "REPS\n(no round-robin,\nexp24)",
}
ALGO_COLORS = {
    "path_static":  "#7f7f7f",
    "freezing_b1":  "#f7fbff",
    "freezing_b2":  "#deebf7",
    "freezing_b4":  "#c6dbef",
    "freezing_b8":  "#9ecae1",
    "freezing_b16": "#6baed6",
    "freezing_b32": "#2171b5",
    "freezing_b64": "#08306b",
    "reps":         "#f97f1f",
    "reps_no_rr":   "#2ca02c",
}
CC_ORDER   = ["nscc", "constant"]
CC_LABELS  = {"nscc": "NSCC", "constant": "Constant (linerate)"}
CC_HATCHES = {"nscc": "", "constant": "///"}


def ci95(values: pd.Series) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    se = values.std(ddof=1) / np.sqrt(n)
    return stats.t.ppf(0.975, df=n - 1) * se


def compute_stats(df: pd.DataFrame) -> pd.DataFrame:
    per_seed = df.groupby(["algo", "cc", "seed"])["fct_us"].mean().reset_index(name="value")
    return per_seed.groupby(["algo", "cc"])["value"].agg(mean="mean", ci=ci95).reset_index()


def grouped_bar(ax, stats_df, title, ylabel):
    n_algos = len(ALGO_ORDER)
    n_cc    = len(CC_ORDER)
    bar_w   = 0.35
    group_w = bar_w * n_cc + 0.15
    x       = np.arange(n_algos) * group_w

    for ci_idx, cc in enumerate(CC_ORDER):
        sub = stats_df[stats_df["cc"] == cc].set_index("algo")
        vals = [sub.loc[a, "mean"] if a in sub.index else np.nan for a in ALGO_ORDER]
        errs = [sub.loc[a, "ci"]   if a in sub.index else 0      for a in ALGO_ORDER]
        offsets = x + (ci_idx - (n_cc - 1) / 2) * bar_w
        colors  = [ALGO_COLORS[a] for a in ALGO_ORDER]
        bars = ax.bar(offsets, vals, bar_w,
                       color=colors,
                       hatch=CC_HATCHES[cc],
                       edgecolor="black",
                       linewidth=0.6,
                       label=CC_LABELS[cc],
                       yerr=errs,
                       capsize=3,
                       error_kw={"elinewidth": 0.8, "ecolor": "black"})
        for xi, v, e in zip(offsets, vals, errs):
            if np.isnan(v):
                continue
            ax.text(xi, v + e + 1.5, f"{v:.1f}", ha="center", va="bottom",
                     fontsize=6.5, rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels([ALGO_LABELS[a] for a in ALGO_ORDER], fontsize=8)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8, title="CC mode", title_fontsize=8, loc="upper left")
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)


def main():
    if not DATA_CSV.exists():
        print(f"ERROR: {DATA_CSV} not found - run aggregate.py first", file=sys.stderr)
        sys.exit(1)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_CSV)
    df = df[df["workload"] == "8mb"]
    print(f"Loaded {len(df)} rows (8mb workload)")

    stats_df = compute_stats(df)
    print(stats_df.to_string(index=False))

    fig, ax = plt.subplots(figsize=(12, 5))
    grouped_bar(ax, stats_df,
                "Mean FCT (absolute) - K=16 tornado 8 MB - exp24 round-robin ablation",
                "Mean FCT (us)")
    ax.set_ylim(top=stats_df["mean"].max() * 1.2)
    fig.tight_layout()
    out = PLOTS_DIR / "mean_fct_raw.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
