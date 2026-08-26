#!/usr/bin/env python3
"""Plot exp19 FCT panels.

Panel A — per-flow avg FCT slowdown (16 flows, baseline vs constrained)
Panel B — aggregate avg and max FCT slowdown with 95% CI

Reads:  data/fcts.csv
Writes: plots/exp19_fct.png
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT  = Path(__file__).resolve().parent
DATA  = ROOT / "data"
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)

FLOW_SIZE   = 268435456
MIN_FCT_US  = FLOW_SIZE * 8 / 400e9 * 1e6   # unloaded FCT at 400 Gbps

COLORS = {"baseline": "#1565C0", "constrained": "#E65100"}
LABELS = {"baseline": "Baseline (4 paths)", "constrained": "Constrained (host 0: 3 paths)"}
CONDITIONS = ["baseline", "constrained"]


def ci95(s):
    n = len(s)
    if n < 2:
        return 0.0
    return float(stats.t.ppf(0.975, df=n - 1) * s.std(ddof=1) / np.sqrt(n))


def main():
    fcts_path = DATA / "fcts.csv"
    if not fcts_path.exists():
        print("ERROR: run aggregate_exp19.py first")
        return

    fcts = pd.read_csv(fcts_path)
    fcts["slowdown"] = fcts["fct_us"] / MIN_FCT_US

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(
        "exp19 — PATH_RR path asymmetry: FCT slowdown\n"
        "256 MiB tornado, PATH_RR src_mod, NSCC, cwnd=155, seeds 42–51 (n=10)",
        fontsize=10)

    # ── Panel A: per-flow avg FCT slowdown ────────────────────────────────────
    flow_ids = sorted(fcts["flow_id"].unique())
    x = np.arange(len(flow_ids))
    width = 0.35

    for i, cond in enumerate(CONDITIONS):
        sub = fcts[fcts["condition"] == cond]
        means, errs = [], []
        for fid in flow_ids:
            s = sub[sub["flow_id"] == fid]["slowdown"]
            means.append(s.mean())
            errs.append(ci95(s))
        offset = (i - 0.5) * width
        ax_a.bar(x + offset, means, width, yerr=errs, capsize=3,
                 color=COLORS[cond], label=LABELS[cond], alpha=0.85)

    ax_a.set_title("A — Per-flow avg FCT slowdown", fontsize=9)
    ax_a.set_xticks(x)
    ax_a.set_xticklabels([str(f) for f in flow_ids], fontsize=7)
    ax_a.set_xlabel("Flow ID (= host index)")
    ax_a.set_ylabel("FCT slowdown (×)")
    ax_a.set_ylim(bottom=1.0)
    # pod boundary markers (hosts 0-3 pod0, 4-7 pod1, 8-11 pod2, 12-15 pod3)
    for boundary in [3.5, 7.5, 11.5]:
        ax_a.axvline(boundary, color="gray", linewidth=0.6, linestyle="--")
    y_top = ax_a.get_ylim()[1]
    for pod, label in enumerate(["pod 0", "pod 1", "pod 2", "pod 3"]):
        ax_a.text(pod * 4 + 1.5, y_top * 0.999, label,
                  fontsize=7, ha="center", va="top", color="gray")
    ax_a.legend(fontsize=8)

    # ── Panel B: aggregate avg / max FCT slowdown ─────────────────────────────
    metrics = {
        "Avg FCT\nslowdown": fcts.groupby(["condition", "seed"])["slowdown"].mean(),
        "Max FCT\nslowdown": fcts.groupby(["condition", "seed"])["slowdown"].max(),
    }
    width2 = 0.3
    group_gap = 1.0
    centers = np.arange(len(metrics)) * group_gap

    for mi, (metric_label, series) in enumerate(metrics.items()):
        for ci, cond in enumerate(CONDITIONS):
            vals = series.xs(cond, level="condition")
            offset = (ci - 0.5) * width2
            ax_b.bar(centers[mi] + offset, vals.mean(), width2,
                     yerr=ci95(vals), capsize=4,
                     color=COLORS[cond], alpha=0.85,
                     label=LABELS[cond] if mi == 0 else "")

    ax_b.set_title("B — Aggregate FCT slowdown (mean across seeds, 95% CI)", fontsize=9)
    ax_b.set_xticks(centers)
    ax_b.set_xticklabels(list(metrics.keys()), fontsize=9)
    ax_b.set_ylabel("FCT slowdown (×)")
    ax_b.set_ylim(bottom=1.0)
    ax_b.legend(fontsize=8)

    plt.tight_layout()
    out = PLOTS / "exp19_fct.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    print("\n=== FCT slowdown summary ===")
    for cond in CONDITIONS:
        sub = fcts[fcts["condition"] == cond]
        avg_s = sub.groupby("seed")["slowdown"].mean()
        max_s = sub.groupby("seed")["slowdown"].max()
        print(f"  {cond:<14} avg={avg_s.mean():.4f}× (±{ci95(avg_s):.4f})"
              f"  max={max_s.mean():.4f}× (±{ci95(max_s):.4f})")

    print("\n=== Per-flow Δ (constrained − baseline, mean across seeds) ===")
    for fid in flow_ids:
        b = fcts[(fcts["condition"] == "baseline")    & (fcts["flow_id"] == fid)]["slowdown"]
        c = fcts[(fcts["condition"] == "constrained") & (fcts["flow_id"] == fid)]["slowdown"]
        delta = c.mean() - b.mean()
        tag = ""
        if fid == 0:          tag = "  <-- CONSTRAINED HOST"
        elif delta > 0.005:   tag = "  <-- VICTIM"
        print(f"  flow {fid:2d}: Δ={delta:+.4f}{tag}")


if __name__ == "__main__":
    main()
