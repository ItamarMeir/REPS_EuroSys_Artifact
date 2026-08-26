#!/usr/bin/env python3
"""
plot.py -- exp25: mean and p95 core-downlink queue occupancy vs time,
REPS vs FREEZING B=64, NSCC CC mode. Line = mean over 3 seeds, shaded band =
95% CI (t-distribution), same statistical convention as exp21/exp24.
Shared plotting logic lives in queue_plot_common.py (also used by
plot_queue_constant.py for the CONSTANT-linerate variant).

Outputs: plots/mean_queue.png, plots/p95_queue.png
"""
import sys
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from queue_plot_common import summarize, line_plot

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
DATA_CSV   = EXP_DIR / "data" / "exp25_queue_ts.csv"
PLOTS_DIR  = EXP_DIR / "plots"


def main():
    if not DATA_CSV.exists():
        print(f"ERROR: {DATA_CSV} not found - run aggregate.py first", file=sys.stderr)
        sys.exit(1)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_CSV)
    print(f"Loaded {len(df)} rows")

    for col_bytes, col_pkts, title_prefix, fname_prefix in [
        ("mean_queue_bytes", "mean_queue_pkts", "Mean", "mean_queue"),
        ("p95_queue_bytes",  "p95_queue_pkts",  "p95",  "p95_queue"),
    ]:
        stats_pkts = summarize(df, col_pkts)
        print(f"\n--- {col_pkts} ---")
        print(stats_pkts.to_string(index=False))

        fig, ax = plt.subplots(figsize=(9, 4.8))
        line_plot(ax, stats_pkts,
                  f"{title_prefix} core-downlink queue occupancy vs time "
                  "- K=16 tornado, NSCC, exp25",
                  f"{title_prefix} queue depth (packets, first 16 core switches)",
                  show_convergence_gap=(fname_prefix == "mean_queue"))
        fig.tight_layout()
        out = PLOTS_DIR / f"{fname_prefix}.png"
        fig.savefig(out, dpi=150)
        plt.close(fig)
        print(f"Saved {out}")


if __name__ == "__main__":
    main()
