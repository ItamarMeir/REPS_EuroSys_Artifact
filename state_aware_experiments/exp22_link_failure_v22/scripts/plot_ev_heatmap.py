#!/usr/bin/env python3
"""
plot_ev_heatmap.py — Heatmap of EV usage frequency per buffer size.

For each FREEZING buffer size (B=1..64), loads buf_freezing_b{B}_nscc_s42.csv
and counts how often each EV value (0-63) appears in ack_ev (= which path each
ACK traveled). Normalises within each B so columns sum to 1.

Output: plots/ev_heatmap.png
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
DATA_DIR   = EXP_DIR / "data"
PLOTS_DIR  = EXP_DIR / "plots"

BUF_SIZES = [1, 2, 4, 8, 16, 32, 64]
N_EV      = 64   # EV values 0-63 for K=16

# All columns: FREEZING B=1..64 then REPS (unbounded)
COLUMNS = [(f"B={b}", DATA_DIR / f"buf_freezing_b{b}_nscc_s42.csv") for b in BUF_SIZES]
COLUMNS += [("REPS\n(unbounded)", DATA_DIR / "buf_reps_nscc_s42.csv")]


def load_ev_dist(path):
    df = pd.read_csv(path)
    counts = df["ack_ev"].value_counts().reindex(range(N_EV), fill_value=0)
    return counts.values / counts.values.sum()   # normalise to fraction


def main():
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    labels = [label for label, _ in COLUMNS]
    matrix = np.stack([load_ev_dist(path) for _, path in COLUMNS], axis=1)

    uniform = 1.0 / N_EV
    vmax = matrix.max()

    fig, ax = plt.subplots(figsize=(11, 9))

    im = ax.imshow(
        matrix,
        aspect="auto",
        origin="lower",
        cmap="YlOrRd",
        vmin=0,
        vmax=vmax,
    )

    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("Fraction of ACKs using this EV", fontsize=9)
    cb.ax.axhline(y=uniform / vmax, color="blue", linestyle="--", linewidth=1.2)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_xlabel("Algorithm", fontsize=11)

    # draw a separator line before the REPS column
    ax.axvline(x=len(BUF_SIZES) - 0.5, color="white", linewidth=2)

    # Y-axis: show every 8th EV for readability
    yticks = list(range(0, N_EV, 8))
    ax.set_yticks(yticks)
    ax.set_yticklabels(yticks, fontsize=8)
    ax.set_ylabel("EV value (ack_ev — path traveled)", fontsize=11)

    ax.set_title(
        "EV usage distribution — FREEZING B=1..64 and REPS (unbounded)\n"
        "K=16 tornado 8 MB, NSCC, SRv6, 5% link failure, seed=42, host 0 only",
        fontsize=11,
    )

    # overlay dashed uniform reference line on main plot
    ax.axhline(y=-0.5, color="none")  # dummy

    fig.tight_layout()
    out = PLOTS_DIR / "ev_heatmap.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
