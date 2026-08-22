#!/usr/bin/env python3
"""
queue_plot_common.py -- exp25: shared queue-occupancy plotting logic used by
both plot.py (NSCC) and plot_queue_constant.py (CONSTANT linerate) so the two
CC modes are plotted "the same way" (same stats, same convergence-gap rule).
"""
import numpy as np
import pandas as pd
from scipy import stats

ALGO_ORDER  = ["freezing_b64", "reps"]
ALGO_LABELS = {"freezing_b64": "FREEZING B=64", "reps": "REPS (round-robin, original)"}
ALGO_COLORS = {"freezing_b64": "#08306b", "reps": "#f97f1f"}

CONV_THRESHOLD_PKTS = 0.01  # queue-drain "converged to ~empty" cutoff


def ci95(values: pd.Series) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    se = values.std(ddof=1) / np.sqrt(n)
    return stats.t.ppf(0.975, df=n - 1) * se


def summarize(df: pd.DataFrame, col: str) -> pd.DataFrame:
    return df.groupby(["algo", "time_us"])[col].agg(mean="mean", ci=ci95).reset_index()


def convergence_time(stats_df: pd.DataFrame, algo: str, threshold=CONV_THRESHOLD_PKTS) -> float:
    """Last time_us at which algo's mean queue is still above threshold --
    i.e. when it has fully drained back to ~empty."""
    sub = stats_df[(stats_df["algo"] == algo) & (stats_df["mean"] > threshold)]
    return sub["time_us"].max()


def line_plot(ax, stats_df, title, ylabel, show_convergence_gap=False):
    for algo in ALGO_ORDER:
        sub = stats_df[stats_df["algo"] == algo].sort_values("time_us")
        ax.plot(sub["time_us"], sub["mean"], color=ALGO_COLORS[algo],
                 label=ALGO_LABELS[algo], linewidth=1.2)
        ax.fill_between(sub["time_us"], sub["mean"] - sub["ci"], sub["mean"] + sub["ci"],
                          color=ALGO_COLORS[algo], alpha=0.25, linewidth=0)

    if show_convergence_gap:
        t_freezing = convergence_time(stats_df, "freezing_b64")
        t_reps = convergence_time(stats_df, "reps")
        gap = t_reps - t_freezing
        y_top = ax.get_ylim()[1]
        # Dedicated margin strip below y=0 so the marker never crosses a
        # still-descending curve (REPS is still ~0.05-0.5 pkt across this
        # x-range, since t_freezing/t_reps are threshold-crossing times, not
        # a shared "both flat" x-range).
        margin = y_top * 0.10
        y_line = -margin * 0.55
        ax.axvline(t_freezing, color=ALGO_COLORS["freezing_b64"], linestyle=":",
                    linewidth=0.9, ymin=0, ymax=1)
        ax.axvline(t_reps, color=ALGO_COLORS["reps"], linestyle=":",
                    linewidth=0.9, ymin=0, ymax=1)
        ax.plot([t_freezing, t_reps], [y_line, y_line], color="black",
                 linewidth=1.2, linestyle="-", marker="|", markersize=10,
                 clip_on=False)
        ax.text((t_freezing + t_reps) / 2, y_line, f"gap = {gap:.1f} us",
                 ha="center", va="bottom", fontsize=8.5, fontweight="bold",
                 clip_on=False)
        ax.set_ylim(-margin, y_top)
        print(f"Convergence (drain to <{CONV_THRESHOLD_PKTS} pkt): "
              f"freezing_b64={t_freezing:.1f} us, reps={t_reps:.1f} us, gap={gap:.2f} us")

    ax.set_xlabel("Time (us)", fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(linestyle="--", linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
