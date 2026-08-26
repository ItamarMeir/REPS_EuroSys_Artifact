#!/usr/bin/env python3
"""
plot.py — Plot exp21 results normalised to PATH_STATIC + CONSTANT linerate.

All FCTs are expressed as multiples of the PATH_STATIC+CONSTANT mean FCT
(the best achievable baseline with a static oracle + no CC overhead).
PATH_STATIC is excluded from the comparison plots since it is the reference.

Outputs
-------
  plots/mean_fct.png    — mean FCT ratio, 8 MB tornado
  plots/p99_fct.png     — p99  FCT ratio, 8 MB tornado
  plots/slowdown.png    — mean slowdown (= FCT / ideal single-flow FCT), 8 MB tornado
  plots/128mib_probe.png — B=8 vs B=16 normalised mean FCT, 128 MiB tornado (if data exists)
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
DATA_CSV   = EXP_DIR / "data" / "exp22_flows.csv"
PLOTS_DIR  = EXP_DIR / "plots"

# ── algo ordering and display ──────────────────────────────────────────────
# PATH_STATIC is excluded from comparison plots (it is the reference = 1.0).
ALGO_ORDER = [
    "oblivious64",
    "freezing_b1",
    "freezing_b2",
    "freezing_b4",
    "freezing_b8",
    "freezing_b16",
    "freezing_b32",
    "freezing_b64",
    "reps",
]
ALGO_LABELS = {
    "freezing_b1":  "FREEZING\nB=1",
    "freezing_b2":  "FREEZING\nB=2",
    "freezing_b4":  "FREEZING\nB=4",
    "freezing_b8":  "FREEZING\nB=8",
    "freezing_b16": "FREEZING\nB=16",
    "freezing_b32": "FREEZING\nB=32",
    "freezing_b64": "FREEZING\nB=64",
    "reps":         "REPS\n(unbounded)",
    "oblivious64":  "Random EV\n(64, stateless)",
}
CC_ORDER  = ["nscc", "constant"]
CC_LABELS = {"nscc": "NSCC", "constant": "Constant (linerate)"}

ALGO_COLORS = {
    "freezing_b1":  "#f7fbff",   # near-white blue
    "freezing_b2":  "#deebf7",   # very light blue
    "freezing_b4":  "#c6dbef",
    "freezing_b8":  "#9ecae1",
    "freezing_b16": "#6baed6",
    "freezing_b32": "#2171b5",
    "freezing_b64": "#08306b",   # darkest blue
    "reps":         "#f97f1f",   # orange
    "oblivious64":  "#2ca02c",   # green
}
CC_HATCHES = {"nscc": "", "constant": "///"}


def ci95(values: pd.Series) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    se = values.std(ddof=1) / np.sqrt(n)
    return stats.t.ppf(0.975, df=n - 1) * se


def reference_fct(df: pd.DataFrame) -> float:
    """Mean FCT of PATH_STATIC + CONSTANT, averaged across seeds."""
    ref = df[(df["algo"] == "path_static") & (df["cc"] == "constant")]
    if ref.empty:
        raise ValueError("No path_static+constant rows found — cannot compute reference FCT.")
    return ref.groupby("seed")["fct_us"].mean().mean()


def compute_stats(df: pd.DataFrame, metric: str, ref: float):
    """Per-(algo,cc) mean ± 95% CI normalised to `ref`.

    metric: 'mean_fct' | 'p99_fct' | 'slowdown'
    """
    if metric == "mean_fct":
        per_seed = df.groupby(["algo", "cc", "seed"])["fct_us"].mean() / ref
    elif metric == "p99_fct":
        per_seed = df.groupby(["algo", "cc", "seed"])["fct_us"].quantile(0.99) / ref
    elif metric == "slowdown":
        per_seed = df.groupby(["algo", "cc", "seed"])["slowdown"].mean()
        # normalise slowdown by PATH_STATIC+constant mean slowdown
        ref_slow = df[(df["algo"] == "path_static") & (df["cc"] == "constant")] \
                     .groupby("seed")["slowdown"].mean().mean()
        per_seed = per_seed / ref_slow
    else:
        raise ValueError(metric)

    per_seed = per_seed.reset_index(name="value")
    result = per_seed.groupby(["algo", "cc"])["value"].agg(
        mean="mean", ci=ci95
    ).reset_index()
    return result


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

    # Reference line at 1.0 (= PATH_STATIC + CONSTANT)
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


def plot_8mb(df: pd.DataFrame):
    sub = df[df["workload"] == "8mb"]
    ref = reference_fct(sub)
    print(f"  Reference FCT (PATH_STATIC+constant, 8 MB): {ref:.3f} µs")

    for metric, title, ylabel, fname in [
        ("mean_fct",
         f"Mean FCT / PATH_STATIC-constant — K=16 tornado 8 MB, SRv6 buffer sweep, 5% link failure",
         "Mean FCT  /  PATH_STATIC-constant FCT",
         "mean_fct.png"),
        ("p99_fct",
         f"p99 FCT / PATH_STATIC-constant — K=16 tornado 8 MB, SRv6 buffer sweep, 5% link failure",
         "p99 FCT  /  PATH_STATIC-constant FCT",
         "p99_fct.png"),
        ("slowdown",
         f"Mean slowdown / PATH_STATIC-constant — K=16 tornado 8 MB, SRv6 buffer sweep, 5% link failure",
         "Mean slowdown  /  PATH_STATIC-constant slowdown",
         "slowdown.png"),
    ]:
        stats_df = compute_stats(sub, metric, ref)
        fig, ax = plt.subplots(figsize=(9, 4.5))
        grouped_bar(ax, stats_df, title, ylabel)
        fig.tight_layout()
        out = PLOTS_DIR / fname
        fig.savefig(out, dpi=150)
        plt.close(fig)
        print(f"  Saved {out}")


def plot_128mib(df: pd.DataFrame):
    sub = df[df["workload"] == "128mib"]
    if sub.empty:
        print("  No 128 MiB data yet — skipping 128mib_probe.png")
        return

    # Reference: use path_static+constant from 8 MB scaled by flow-size ratio,
    # Raw FCT (µs) — no normalisation.
    all_128_algos = ["freezing_b1", "freezing_b2", "freezing_b4",
                     "freezing_b8", "freezing_b16", "freezing_b32", "freezing_b64"]
    nscc_sub      = sub[sub["cc"] == "nscc"]
    present_algos = [a for a in all_128_algos if a in nscc_sub["algo"].values]

    if not present_algos:
        print("  No 128 MiB NSCC data yet — skipping 128mib_probe.png")
        return

    EXTRA_COLORS = {"freezing_b1": "#f7fbff", "freezing_b2": "#deebf7"}
    colors_128   = {**EXTRA_COLORS, **ALGO_COLORS}

    fig, ax = plt.subplots(figsize=(8, 4.5))
    x     = np.arange(len(present_algos))
    bar_w = 0.55
    vals  = []
    for algo in present_algos:
        mean_fct = nscc_sub[nscc_sub["algo"] == algo].groupby("seed")["fct_us"].mean().mean()
        vals.append(mean_fct)

    colors = [colors_128.get(a, "#aec7e8") for a in present_algos]
    labels = [a.replace("freezing_b", "B=") for a in present_algos]

    ax.bar(x, vals, bar_w, color=colors, edgecolor="black", linewidth=0.6)

    # Annotate each bar with exact FCT value
    for xi, v in enumerate(vals):
        ax.text(xi, v + 5, f"{v:.0f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Mean FCT (µs)", fontsize=9)
    ax.set_title("128 MiB tornado, NSCC — buffer sweep (seed=42, 1 seed)", fontsize=10)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)

    print(f"  128 MiB NSCC raw FCTs: " +
          ", ".join(f"B={a.split('b')[1]}={v:.0f}µs" for a, v in zip(present_algos, vals)))

    fig.tight_layout()
    out = PLOTS_DIR / "128mib_probe.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Saved {out}")


def main():
    if not DATA_CSV.exists():
        print(f"ERROR: {DATA_CSV} not found — run aggregate.py first", file=sys.stderr)
        sys.exit(1)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_CSV)
    # Handle CSVs written before the 'workload' column was added
    if "workload" not in df.columns:
        df["workload"] = "8mb"
    print(f"Loaded {len(df)} rows from {DATA_CSV}")

    print("\n--- 8 MB plots ---")
    plot_8mb(df)

    print("\n--- 128 MiB probe plot ---")
    plot_128mib(df)

    print("\nDone.")


if __name__ == "__main__":
    main()
