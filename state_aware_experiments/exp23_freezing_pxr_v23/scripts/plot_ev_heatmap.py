#!/usr/bin/env python3
"""
plot_ev_heatmap.py — Heatmap of EV usage frequency per FREEZING_PXR buffer size.

For each B in {1,2,4,8,16,32,64}, loads buf_freezing_pxr_b{B}_nscc_s42.csv and
counts how often each EV (0-63) appears in ack_ev. Normalises within each column.

Cyan dashes mark EVs that were ever added to the excluded set for that buffer size
(read from pxr_excluded_evs column).

Output: plots/ev_heatmap.png
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR   = SCRIPT_DIR.parent / "data"
PLOTS_DIR  = SCRIPT_DIR.parent / "plots"

BUF_SIZES = [1, 2, 4, 8, 16, 32, 64]
N_EV      = 64

COLUMNS = [(f"B={b}", DATA_DIR / f"buf_freezing_pxr_b{b}_nscc_s42.csv")
           for b in BUF_SIZES]


def load_ev_dist(path: Path):
    df = pd.read_csv(path)
    counts = df["ack_ev"].value_counts().reindex(range(N_EV), fill_value=0)
    return counts.values / counts.values.sum()


def load_excluded_evs(path: Path):
    df = pd.read_csv(path)
    if "pxr_excluded_evs" not in df.columns:
        return set()
    excluded = set()
    for val in df["pxr_excluded_evs"].dropna():
        for ev in str(val).split("|"):
            ev = ev.strip()
            if ev.isdigit():
                excluded.add(int(ev))
    return excluded


def main():
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    present = [(label, path) for label, path in COLUMNS if path.exists()]
    missing = [label for label, path in COLUMNS if not path.exists()]
    if missing:
        print(f"WARNING: missing buffer CSVs for: {missing}")
    if not present:
        print("ERROR: no buffer CSVs found")
        return

    labels  = [label for label, _ in present]
    matrix  = np.stack([load_ev_dist(path) for _, path in present], axis=1)
    uniform = 1.0 / N_EV
    vmax    = matrix.max()

    # Excluded EVs per column
    excluded_per_col = [load_excluded_evs(path) for _, path in present]
    for i, (label, evs) in enumerate(zip(labels, excluded_per_col)):
        if evs:
            print(f"  {label}: excluded EVs = {sorted(evs)}")

    fig, ax = plt.subplots(figsize=(10, 9))

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

    # Overlay cyan dashes for excluded EVs per column
    for col_idx, evs in enumerate(excluded_per_col):
        for ev in sorted(evs):
            ax.plot([col_idx - 0.45, col_idx + 0.45], [ev, ev],
                    color="cyan", linewidth=1.2, linestyle="--", alpha=0.8)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_xlabel("Buffer size (B)", fontsize=11)

    yticks = list(range(0, N_EV, 4))
    ax.set_yticks(yticks)
    ax.set_yticklabels(yticks, fontsize=8)
    ax.set_ylabel("EV value (path traveled)", fontsize=11)

    ax.set_title(
        "EV usage distribution — FREEZING_PXR B=1..64\n"
        "K=16 tornado 8 MB, NSCC, SRv6, 51 failed links, seed=42, host 0\n"
        "(cyan dashes = EVs ever excluded by PXR for that buffer size)",
        fontsize=10,
    )

    fig.tight_layout()
    out = PLOTS_DIR / "ev_heatmap.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
