#!/usr/bin/env python3
"""
plot_queue_constant.py -- exp25: mean core-downlink queue occupancy vs time,
REPS vs FREEZING B=64, CONSTANT-linerate CC mode. Same stats/convergence-gap
rule as plot.py's NSCC version (shared logic in queue_plot_common.py) --
separate output so the NSCC plot is unaffected.

Output: plots/mean_queue_constant.png
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
DATA_CSV   = EXP_DIR / "data" / "exp25_queue_ts_constant.csv"
PLOTS_DIR  = EXP_DIR / "plots"


def main():
    if not DATA_CSV.exists():
        print(f"ERROR: {DATA_CSV} not found - run aggregate_constant.py first", file=sys.stderr)
        sys.exit(1)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_CSV)
    print(f"Loaded {len(df)} rows")

    stats_pkts = summarize(df, "mean_queue_pkts")
    print("\n--- mean_queue_pkts (constant) ---")
    print(stats_pkts.to_string(index=False))

    fig, ax = plt.subplots(figsize=(9, 4.8))
    line_plot(ax, stats_pkts,
              "Mean core-downlink queue occupancy vs time "
              "- K=16 tornado, CONSTANT linerate, exp25",
              "Mean queue depth (packets, first 16 core switches)",
              show_convergence_gap=True)
    fig.tight_layout()
    out = PLOTS_DIR / "mean_queue_constant.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
