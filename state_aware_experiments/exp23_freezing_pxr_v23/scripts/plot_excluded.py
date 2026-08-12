#!/usr/bin/env python3
"""
plot_excluded.py — Excluded-set size over time for host 0, seed 42, NSCC.

Reads:
  data/buf_freezing_pxr_b8_nscc_s42.csv  — per-ACK buffer CSV with pxr_excluded_count column

Left y-axis:  pxr_excluded_count (step plot)
Right y-axis: cwnd_pkts (line)
Vertical markers at each exclusion event (transition 0→N or N→N+1 in excluded count).

Output: plots/excluded_size.png
"""
import sys
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

BUF_CSV = DATA_DIR / "buf_freezing_pxr_b8_nscc_s42.csv"


def main():
    if not BUF_CSV.exists():
        print(f"ERROR: {BUF_CSV} not found", file=sys.stderr)
        sys.exit(1)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(BUF_CSV)

    print(f"Loaded {len(df)} rows from {BUF_CSV.name}")
    print(f"Columns: {df.columns.tolist()}")

    if "pxr_excluded_count" not in df.columns:
        print("ERROR: pxr_excluded_count column not found — was the binary rebuilt with FREEZING_PXR support?",
              file=sys.stderr)
        sys.exit(1)

    t = df["time_us"].values
    excl = df["pxr_excluded_count"].values

    # Find rows where excluded count increases (= new exclusion event)
    excl_events = np.where(np.diff(excl, prepend=0) > 0)[0]
    print(f"Exclusion events: {len(excl_events)} at t={t[excl_events].tolist()} µs")

    fig, ax1 = plt.subplots(figsize=(12, 4))

    ax1.step(t, excl, where="post", color="#e6550d", linewidth=1.5,
             label="|excluded EVs|")
    ax1.set_xlabel("Time (µs)", fontsize=9)
    ax1.set_ylabel("|Excluded EV set|", fontsize=9, color="#e6550d")
    ax1.tick_params(axis="y", labelcolor="#e6550d")
    ax1.set_yticks(range(int(excl.max()) + 2))
    ax1.set_ylim(bottom=-0.1)

    # Mark exclusion events
    for idx in excl_events:
        ax1.axvline(t[idx], color="#e6550d", alpha=0.3, linewidth=0.8, linestyle=":")

    if "cwnd_pkts" in df.columns:
        ax2 = ax1.twinx()
        ax2.plot(t, df["cwnd_pkts"].values, color="#3182bd", linewidth=0.8,
                 alpha=0.7, label="cwnd (pkts)")
        ax2.set_ylabel("cwnd (pkts)", fontsize=9, color="#3182bd")
        ax2.tick_params(axis="y", labelcolor="#3182bd")
        lines2, labels2 = ax2.get_legend_handles_labels()
    else:
        lines2, labels2 = [], []

    lines1, labels1 = ax1.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper right")

    ax1.set_title(
        "FREEZING_PXR: Excluded EV set size over time — host 0, seed 42, NSCC\n"
        "K=16 fat tree, 51 failed agg↔core links, tornado 8 MB",
        fontsize=10,
    )
    ax1.grid(linestyle="--", linewidth=0.4, alpha=0.4)
    ax1.set_axisbelow(True)

    fig.tight_layout()
    out = PLOTS_DIR / "excluded_size.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
