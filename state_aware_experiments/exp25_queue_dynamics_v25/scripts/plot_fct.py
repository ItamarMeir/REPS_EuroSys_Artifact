#!/usr/bin/env python3
"""
plot_fct.py -- exp25: real (non-normalized) mean FCT bar chart, REPS vs
FREEZING B=64, both NSCC and CONSTANT-linerate CC modes combined into one
grouped-bar plot (same grouping style as exp24's plot.py: hatched bars for
CONSTANT). Value labeled atop each bar.

No rerun -- reuses exp24's already-aggregated data/exp24_flows.csv.

Output: plots/mean_fct.png
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
EXP24_CSV  = EXP_DIR.parent / "exp24_reps_no_rr_v24" / "data" / "exp24_flows.csv"
PLOTS_DIR  = EXP_DIR / "plots"

ALGO_ORDER  = ["freezing_b64", "reps"]
ALGO_LABELS = {"freezing_b64": "FREEZING\nB=64", "reps": "REPS\n(round-robin,\noriginal)"}
ALGO_COLORS = {"freezing_b64": "#08306b", "reps": "#f97f1f"}
CC_ORDER    = ["nscc", "constant"]
CC_LABELS   = {"nscc": "NSCC", "constant": "Constant (linerate)"}
CC_HATCHES  = {"nscc": "", "constant": "///"}


def ci95(values: pd.Series) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    se = values.std(ddof=1) / np.sqrt(n)
    return stats.t.ppf(0.975, df=n - 1) * se


def main():
    if not EXP24_CSV.exists():
        print(f"ERROR: {EXP24_CSV} not found", file=sys.stderr)
        sys.exit(1)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(EXP24_CSV)
    df = df[df["algo"].isin(ALGO_ORDER)]
    print(f"Loaded {len(df)} rows (freezing_b64/reps, both cc modes)")

    per_seed = df.groupby(["algo", "cc", "seed"])["fct_us"].mean().reset_index(name="value")
    stats_df = per_seed.groupby(["algo", "cc"])["value"].agg(mean="mean", ci=ci95).reset_index()
    print(stats_df.to_string(index=False))

    n_algos = len(ALGO_ORDER)
    n_cc    = len(CC_ORDER)
    bar_w   = 0.35
    group_w = bar_w * n_cc + 0.15
    x       = np.arange(n_algos) * group_w

    fig, ax = plt.subplots(figsize=(6.5, 5))
    for ci_idx, cc in enumerate(CC_ORDER):
        sub = stats_df[stats_df["cc"] == cc].set_index("algo")
        vals = [sub.loc[a, "mean"] for a in ALGO_ORDER]
        errs = [sub.loc[a, "ci"] for a in ALGO_ORDER]
        offsets = x + (ci_idx - (n_cc - 1) / 2) * bar_w
        colors = [ALGO_COLORS[a] for a in ALGO_ORDER]
        ax.bar(offsets, vals, bar_w, color=colors, hatch=CC_HATCHES[cc],
               edgecolor="black", linewidth=0.6, label=CC_LABELS[cc],
               yerr=errs, capsize=4, error_kw={"elinewidth": 0.8, "ecolor": "black"})
        for xi, v, e in zip(offsets, vals, errs):
            ax.text(xi, v + e + 1.5, f"{v:.1f} us", ha="center", va="bottom",
                     fontsize=8.5, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([ALGO_LABELS[a] for a in ALGO_ORDER], fontsize=9)
    ax.set_ylabel("Mean FCT (us)", fontsize=9)
    ax.set_title("Mean FCT (absolute) - K=16 tornado - exp25", fontsize=10)
    ax.set_ylim(0, stats_df["mean"].max() * 1.2)
    ax.legend(fontsize=8, title="CC mode", title_fontsize=8)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    fig.tight_layout()

    out = PLOTS_DIR / "mean_fct.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved {out}")

    for cc in CC_ORDER:
        sub = stats_df[stats_df["cc"] == cc].set_index("algo")
        gap = sub.loc["reps", "mean"] - sub.loc["freezing_b64", "mean"]
        print(f"FCT gap ({cc}, reps - freezing_b64): {gap:.2f} us")


if __name__ == "__main__":
    main()
