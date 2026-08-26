#!/usr/bin/env python3
"""
plot.py — exp24: does disabling REPS's deterministic first-window round-robin
(reps_no_rr) close the FCT gap to FREEZING seen in exp21?

Same normalization style as exp21/plot.py: all FCTs expressed as multiples of
the PATH_STATIC+CONSTANT mean FCT. Includes every FREEZING buffer size from
exp21 (B=1..64), plus original reps and this exp's reps_no_rr, for direct
comparison on the same axis exp21 used.

Outputs: plots/mean_fct.png, plots/p99_fct.png, plots/slowdown.png
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
CC_ORDER  = ["nscc", "constant"]
CC_LABELS = {"nscc": "NSCC", "constant": "Constant (linerate)"}
CC_HATCHES = {"nscc": "", "constant": "///"}


def ci95(values: pd.Series) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    se = values.std(ddof=1) / np.sqrt(n)
    return stats.t.ppf(0.975, df=n - 1) * se


def reference_fct(df: pd.DataFrame) -> float:
    """Mean FCT of PATH_STATIC + CONSTANT, averaged across seeds — same
    reference exp21 used, so the two are directly comparable."""
    ref = df[(df["algo"] == "path_static") & (df["cc"] == "constant")]
    if ref.empty:
        raise ValueError("No path_static+constant rows found - cannot compute reference FCT.")
    return ref.groupby("seed")["fct_us"].mean().mean()


def compute_stats(df: pd.DataFrame, metric: str, ref: float):
    if metric == "mean_fct":
        per_seed = df.groupby(["algo", "cc", "seed"])["fct_us"].mean() / ref
    elif metric == "p99_fct":
        per_seed = df.groupby(["algo", "cc", "seed"])["fct_us"].quantile(0.99) / ref
    elif metric == "slowdown":
        per_seed = df.groupby(["algo", "cc", "seed"])["slowdown"].mean()
        ref_slow = df[(df["algo"] == "path_static") & (df["cc"] == "constant")] \
                     .groupby("seed")["slowdown"].mean().mean()
        per_seed = per_seed / ref_slow
    else:
        raise ValueError(metric)

    per_seed = per_seed.reset_index(name="value")
    return per_seed.groupby(["algo", "cc"])["value"].agg(mean="mean", ci=ci95).reset_index()


def grouped_bar(ax, stats_df, title, ylabel, ref_line=1.0):
    n_algos = len(ALGO_ORDER)
    n_cc    = len(CC_ORDER)
    bar_w   = 0.35
    group_w = bar_w * n_cc + 0.1
    x       = np.arange(n_algos) * group_w

    for ci_idx, cc in enumerate(CC_ORDER):
        sub = stats_df[stats_df["cc"] == cc].set_index("algo")
        vals = [sub.loc[a, "mean"] if a in sub.index else np.nan for a in ALGO_ORDER]
        errs = [sub.loc[a, "ci"]   if a in sub.index else 0      for a in ALGO_ORDER]
        offsets = x + (ci_idx - (n_cc - 1) / 2) * bar_w
        colors  = [ALGO_COLORS[a] for a in ALGO_ORDER]
        ax.bar(offsets, vals, bar_w,
               color=colors,
               hatch=CC_HATCHES[cc],
               edgecolor="black",
               linewidth=0.6,
               label=CC_LABELS[cc],
               yerr=errs,
               capsize=3,
               error_kw={"elinewidth": 0.8, "ecolor": "black"})

    ax.axhline(ref_line, color="grey", linewidth=1.0, linestyle="--",
               label="PATH_STATIC+constant (ref)")

    ax.set_xticks(x)
    ax.set_xticklabels([ALGO_LABELS[a] for a in ALGO_ORDER], fontsize=8)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8, title="CC mode", title_fontsize=8)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(bottom=1.0)


def main():
    if not DATA_CSV.exists():
        print(f"ERROR: {DATA_CSV} not found - run aggregate.py first", file=sys.stderr)
        sys.exit(1)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_CSV)
    df = df[df["workload"] == "8mb"]
    print(f"Loaded {len(df)} rows (8mb workload)")

    ref = reference_fct(df)
    print(f"Reference FCT (PATH_STATIC+constant): {ref:.3f} us")

    for metric, title, ylabel, fname in [
        ("mean_fct",
         "Mean FCT / PATH_STATIC-constant - K=16 tornado 8 MB - exp24 round-robin ablation",
         "Mean FCT  /  PATH_STATIC-constant FCT",
         "mean_fct.png"),
        ("p99_fct",
         "p99 FCT / PATH_STATIC-constant - K=16 tornado 8 MB - exp24 round-robin ablation",
         "p99 FCT  /  PATH_STATIC-constant FCT",
         "p99_fct.png"),
        ("slowdown",
         "Mean slowdown / PATH_STATIC-constant - K=16 tornado 8 MB - exp24 round-robin ablation",
         "Mean slowdown  /  PATH_STATIC-constant slowdown",
         "slowdown.png"),
    ]:
        stats_df = compute_stats(df, metric, ref)
        print(f"\n--- {metric} ---")
        print(stats_df.to_string(index=False))
        fig, ax = plt.subplots(figsize=(11, 4.8))
        grouped_bar(ax, stats_df, title, ylabel)
        fig.tight_layout()
        out = PLOTS_DIR / fname
        fig.savefig(out, dpi=150)
        plt.close(fig)
        print(f"Saved {out}")


if __name__ == "__main__":
    main()
