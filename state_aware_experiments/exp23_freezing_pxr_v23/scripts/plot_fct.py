#!/usr/bin/env python3
"""
plot_fct.py — FCT plots for exp23 FREEZING_PXR buffer sweep.

Normalised to PATH_STATIC+constant from exp22 (same denominator as exp22/plot.py
so plots are directly comparable side by side).

Outputs (matching exp22 filenames):
  plots/mean_fct.png   — mean FCT ratio
  plots/p99_fct.png    — p99  FCT ratio
  plots/slowdown.png   — mean slowdown ratio
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

SCRIPT_DIR  = Path(__file__).resolve().parent
EXP_DIR     = SCRIPT_DIR.parent
DATA_CSV    = EXP_DIR / "data" / "exp23_flows.csv"
EXP22_CSV   = EXP_DIR.parent / "exp22_link_failure_v22" / "data" / "exp22_flows.csv"
PLOTS_DIR   = EXP_DIR / "plots"

BUF_SIZES  = [1, 2, 4, 8, 16, 32, 64]
ALGO_ORDER  = [f"freezing_pxr_b{b}" for b in BUF_SIZES]
ALGO_LABELS = {f"freezing_pxr_b{b}": f"FREEZING_PXR\nB={b}" for b in BUF_SIZES}
ALGO_COLORS = {
    "freezing_pxr_b1":  "#f7fbff",
    "freezing_pxr_b2":  "#deebf7",
    "freezing_pxr_b4":  "#c6dbef",
    "freezing_pxr_b8":  "#9ecae1",
    "freezing_pxr_b16": "#6baed6",
    "freezing_pxr_b32": "#2171b5",
    "freezing_pxr_b64": "#08306b",
}

CC_ORDER  = ["nscc", "constant"]
CC_LABELS = {"nscc": "NSCC", "constant": "Constant (linerate)"}
CC_HATCHES = {"nscc": "", "constant": "///"}


def ci95(values: pd.Series) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    se = values.std(ddof=1) / np.sqrt(n)
    return float(stats.t.ppf(0.975, df=n - 1) * se)


def reference_fct(exp22_df: pd.DataFrame) -> float:
    """Mean FCT of PATH_STATIC+constant from exp22, averaged across seeds."""
    ref = exp22_df[(exp22_df["algo"] == "path_static") & (exp22_df["cc"] == "constant")]
    if ref.empty:
        raise ValueError("No path_static+constant rows in exp22 CSV.")
    return ref.groupby("seed")["fct_us"].mean().mean()


def reference_slowdown(exp22_df: pd.DataFrame) -> float:
    ref = exp22_df[(exp22_df["algo"] == "path_static") & (exp22_df["cc"] == "constant")]
    return ref.groupby("seed")["slowdown"].mean().mean()


def compute_stats(df, metric, ref_fct, ref_slow):
    if metric == "mean_fct":
        per_seed = df.groupby(["algo", "cc", "seed"])["fct_us"].mean() / ref_fct
    elif metric == "p99_fct":
        per_seed = df.groupby(["algo", "cc", "seed"])["fct_us"].quantile(0.99) / ref_fct
    elif metric == "slowdown":
        per_seed = df.groupby(["algo", "cc", "seed"])["slowdown"].mean() / ref_slow
    else:
        raise ValueError(metric)

    per_seed = per_seed.reset_index(name="value")
    return per_seed.groupby(["algo", "cc"])["value"].agg(mean="mean", ci=ci95).reset_index()


def grouped_bar(ax, stats_df, title, ylabel):
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

    ax.axhline(1.0, color="grey", linewidth=1.0, linestyle="--",
               label="PATH_STATIC+constant (exp22 ref)")
    ax.set_xticks(x)
    ax.set_xticklabels([ALGO_LABELS[a] for a in ALGO_ORDER], fontsize=8)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8, title="CC mode", title_fontsize=8)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(bottom=0)


def main():
    if not DATA_CSV.exists():
        print(f"ERROR: {DATA_CSV} not found — run aggregate.py first", file=sys.stderr)
        sys.exit(1)
    if not EXP22_CSV.exists():
        print(f"ERROR: {EXP22_CSV} not found — needed for PATH_STATIC reference", file=sys.stderr)
        sys.exit(1)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df     = pd.read_csv(DATA_CSV)
    df22   = pd.read_csv(EXP22_CSV)

    ref_fct  = reference_fct(df22)
    ref_slow = reference_slowdown(df22)
    print(f"Reference FCT  (PATH_STATIC+constant, exp22): {ref_fct:.3f} µs")
    print(f"Reference slow (PATH_STATIC+constant, exp22): {ref_slow:.4f}")
    print(f"Loaded {len(df)} rows from {DATA_CSV}")

    for metric, title, ylabel, fname in [
        ("mean_fct",
         "Mean FCT / PATH_STATIC-constant (exp22) — K=16 tornado 8 MB, SRv6, 5% link failure",
         "Mean FCT  /  PATH_STATIC-constant FCT",
         "mean_fct.png"),
        ("p99_fct",
         "p99 FCT / PATH_STATIC-constant (exp22) — K=16 tornado 8 MB, SRv6, 5% link failure",
         "p99 FCT  /  PATH_STATIC-constant FCT",
         "p99_fct.png"),
        ("slowdown",
         "Mean slowdown / PATH_STATIC-constant (exp22) — K=16 tornado 8 MB, SRv6, 5% link failure",
         "Mean slowdown  /  PATH_STATIC-constant slowdown",
         "slowdown.png"),
    ]:
        stats_df = compute_stats(df, metric, ref_fct, ref_slow)
        fig, ax  = plt.subplots(figsize=(9, 4.5))
        grouped_bar(ax, stats_df, title, ylabel)
        fig.tight_layout()
        out = PLOTS_DIR / fname
        fig.savefig(out, dpi=150)
        plt.close(fig)
        print(f"  Saved {out}")

    print("\nDone.")


if __name__ == "__main__":
    main()
