#!/usr/bin/env python3
"""
plot_ev_diversity.py — EV diversity across FREEZING buffer sizes.

Two panels:
  Left:  Sorted EV frequency rank plot — 64 EVs sorted descending by usage share,
         overlaid for each B. Deviations above/below the uniform reference line
         reveal which buffer sizes concentrate on fewer paths.
  Right: Concentration metrics bar chart — max path ratio and CV per algorithm.

Output: plots/ev_diversity.png
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR   = SCRIPT_DIR.parent / "data"
PLOTS_DIR  = SCRIPT_DIR.parent / "plots"

N_EV = 64
UNIFORM = 100.0 / N_EV   # 1.5625 %

CONFIGS = [
    ("B=1",  "buf_freezing_b1_nscc_s42.csv",  "#f03b20"),
    ("B=2",  "buf_freezing_b2_nscc_s42.csv",  "#fd8d3c"),
    ("B=4",  "buf_freezing_b4_nscc_s42.csv",  "#fecc5c"),
    ("B=8",  "buf_freezing_b8_nscc_s42.csv",  "#78c679"),
    ("B=16", "buf_freezing_b16_nscc_s42.csv", "#41b6c4"),
    ("B=32", "buf_freezing_b32_nscc_s42.csv", "#2c7fb8"),
    ("B=64", "buf_freezing_b64_nscc_s42.csv", "#253494"),
    ("REPS", "buf_reps_nscc_s42.csv",          "#984ea3"),
]


def ev_freq_pct(fname):
    df = pd.read_csv(DATA_DIR / fname)
    counts = df["ack_ev"].value_counts().reindex(range(N_EV), fill_value=0)
    return counts.values / counts.values.sum() * 100


def main():
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    data = [(label, color, ev_freq_pct(fname)) for label, fname, color in CONFIGS]

    fig, axes = plt.subplots(1, 2, figsize=(13, 7))
    fig.subplots_adjust(bottom=0.28, top=0.91)

    # ── Left: sorted rank plot ──────────────────────────────────────────────
    ax = axes[0]
    ranks = np.arange(1, N_EV + 1)
    line_handles = []
    for label, color, freq in data:
        sorted_freq = np.sort(freq)[::-1]
        ln, = ax.plot(ranks, sorted_freq, label=label, color=color, linewidth=1.5)
        line_handles.append(ln)

    ax.axhline(UNIFORM, color="black", linestyle="--", linewidth=1.0,
               label=f"Uniform (1/64 = {UNIFORM:.2f}%)")
    ax.set_xlabel("EV rank (sorted by usage, most → least)", fontsize=10)
    ax.set_ylabel("Usage share (%)", fontsize=10)
    ax.yaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f%%"))
    ax.set_title("Sorted EV frequency profile", fontsize=10)
    ax.set_xlim(1, N_EV)
    ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.7)
    ax.legend(loc="upper right", fontsize=7, framealpha=0.9)

    # ── Right: concentration metrics bar chart ─────────────────────────────
    ax2 = axes[1]
    labels = [label for label, _, _ in data]
    colors = [color for _, color, _ in data]

    cvs = [(freq.std() / freq.mean() * 100) for _, _, freq in data]

    x     = np.arange(len(labels))
    bar_w = 0.55

    ax2.bar(x, cvs, bar_w, color=colors, edgecolor="black", linewidth=0.7)

    ax2.axhline(0.0, color="black", linestyle="--", linewidth=1.0)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, fontsize=9)
    ax2.set_ylabel("CV = std ÷ mean × 100%", fontsize=10)
    ax2.set_title("EV path usage — Coefficient of Variation", fontsize=10)
    ax2.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.7)
    ax2.set_ylim(bottom=0)

    fig.suptitle(
        "EV usage diversity per algorithm — K=16 tornado 8 MB, NSCC, SRv6, seed=42, host 0",
        fontsize=11,
    )

    # ── Explanatory text below plots ───────────────────────────────────────
    left_text = (
        "LEFT: Each colored line = one algorithm. X-axis: 64 EVs (paths) sorted from most-used (rank 1) to least-used (rank 64).\n"
        "Y-axis: fraction of ACKs that traveled that path. A perfectly flat line at 1.56% means all 64 paths are used equally\n"
        "(perfect load spreading). Lines that peak above or dip below the dashed reference show unequal path usage."
    )
    right_text = (
        "RIGHT — CV = std ÷ mean × 100% of per-EV usage frequencies. CV = 0% means all 64 paths are used equally.\n"
        "Higher CV = more imbalance: traffic is concentrated on fewer paths. Each bar color matches the algorithm\n"
        "color in the left plot."
    )

    fig.text(0.02, 0.135, left_text, fontsize=7.5, va="top", ha="left",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#f0f0f0", alpha=0.9, edgecolor="grey"))
    fig.text(0.52, 0.135, right_text, fontsize=7.5, va="top", ha="left",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#f0f0f0", alpha=0.9, edgecolor="grey"))

    out = PLOTS_DIR / "ev_diversity.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
