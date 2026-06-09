#!/usr/bin/env python3
"""Standalone plot of ToR→Agg queue integrals for exp20.

Wide figure, no CI bars, pod separators for readability.
Reads:  data/tor_queue_integral.csv
Writes: plots/exp20_tor_queues.png
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT  = Path(__file__).resolve().parent
DATA  = ROOT / "data"
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)

COLORS = {"baseline": "#1565C0", "constrained": "#E65100"}
LABELS = {"baseline": "Baseline (16 paths)", "constrained": "Constrained (host 0: 15 paths)"}
CONDITIONS = ["baseline", "constrained"]

# k=8 fat-tree: 8 pods, 4 ToRs per pod (ToRs 0-3 → pod 0, 4-7 → pod 1, etc.)
TORS_PER_POD = 4
AGGS_PER_TOR = 4


def main():
    tqi_path = DATA / "tor_queue_integral.csv"
    if not tqi_path.exists():
        print("ERROR: run aggregate_exp20.py first")
        return

    tqi = pd.read_csv(tqi_path)
    tor_agg_pairs = sorted(tqi[["tor", "agg"]].drop_duplicates().itertuples(index=False))
    n_pairs = len(tor_agg_pairs)

    # Mean across seeds (no CI bars)
    means = {}
    for cond in CONDITIONS:
        means[cond] = []
        for pair in tor_agg_pairs:
            tor, agg = pair
            vals = tqi.query("condition == @cond and tor == @tor and agg == @agg") \
                      .groupby("seed")["queue_byte_us"].sum()
            means[cond].append(vals.mean())

    x = np.arange(n_pairs)
    width = 0.4

    fig, ax = plt.subplots(figsize=(40, 6))
    fig.suptitle(
        "exp20 — ToR→Agg queue integral per uplink (bytes·µs)\n"
        "k=8 fat-tree, 128 hosts, 256 MiB tornado, PATH_RR src_mod, NSCC, seeds 42–46 (n=5, mean only)",
        fontsize=10)

    for ci, cond in enumerate(CONDITIONS):
        offset = (ci - 0.5) * width
        ax.bar(x + offset, means[cond], width,
               color=COLORS[cond], label=LABELS[cond], alpha=0.85)

    # Pod separator lines and labels
    n_tors = max(p.tor for p in tor_agg_pairs) + 1
    n_pods = n_tors // TORS_PER_POD
    pod_size = TORS_PER_POD * AGGS_PER_TOR  # pairs per pod = 16
    for pod in range(n_pods):
        start = pod * pod_size
        end = start + pod_size - 1
        if pod > 0:
            ax.axvline(start - 0.5, color="black", linewidth=0.8, linestyle="-", alpha=0.4)
        # Shade alternating pods
        if pod % 2 == 1:
            ax.axvspan(start - 0.5, end + 0.5, alpha=0.04, color="gray")
        ax.text((start + end) / 2, ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 1,
                f"pod {pod}", fontsize=7, ha="center", va="bottom", color="dimgray")

    # Highlight ToR 0 uplinks
    tor0_xs = [i for i, p in enumerate(tor_agg_pairs) if p.tor == 0]
    if tor0_xs:
        ax.axvspan(min(tor0_xs) - 0.5, max(tor0_xs) + 0.5,
                   alpha=0.12, color="red")
        ax.text((min(tor0_xs) + max(tor0_xs)) / 2, 0,
                "ToR 0\n(hosts 0–3)", fontsize=7, ha="center", va="bottom",
                color="darkred", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([f"T{p.tor}→A{p.agg}" for p in tor_agg_pairs],
                       fontsize=5.5, rotation=70, ha="right")
    ax.set_xlabel("ToR→Agg uplink", fontsize=10)
    ax.set_ylabel("Σ queue integral (bytes·µs)", fontsize=10)
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=9, loc="upper right")

    # Re-draw pod labels after ylim is set
    ymax = ax.get_ylim()[1]
    for pod in range(n_pods):
        start = pod * pod_size
        end = start + pod_size - 1
        ax.text((start + end) / 2, ymax * 0.98,
                f"pod {pod}", fontsize=7, ha="center", va="top", color="dimgray")

    plt.tight_layout()
    out = PLOTS / "exp20_tor_queues.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
