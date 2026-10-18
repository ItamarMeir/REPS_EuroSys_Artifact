#!/usr/bin/env python3
"""
exp27 plot 3 -- tornado 4 MiB, SRv6, vs fat-tree radix K of the 3-tier fabric.

x = K in {4, 8, 16}  ->  SRv6 path count (K/2)^2 in {4, 16, 64}.
Grouped bars per K; the arms present in a group are ops + reps_b{1..(K/2)^2},
so K=4 shows 4 bars, K=8 shows 6, K=16 shows 8 (not every B is relevant at
every K -- missing bars are simply absent).

Two stacked panels:
  top    raw Max FCT (us)
  bottom speedup vs OPS on Max FCT  (ops_max / arm_max), zoomed near 1.0

Colour + hatch per B kept identical to plots 1-2. Vertical value label on
every bar.

Data:
  K=4,8  -> data/k_sweep/summary.csv   (run_k_sweep.py + exp26 aggregate.py)
  K=16   -> data/k16_3t/summary.csv    (reused from plot 2, tornado_s4194304)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from plot_micro_bars import arm_order, arm_style

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
DATA_DIR = EXP_DIR / "data"
PLOTS_DIR = EXP_DIR / "plots"

FULL_LADDER = [1, 2, 4, 8, 16, 32, 64]
K_PATHS = {4: 4, 8: 16, 16: 64}
K_HOSTS = {4: 16, 8: 128, 16: 1024}


def load() -> pd.DataFrame:
    frames = []
    k48 = DATA_DIR / "k_sweep" / "summary.csv"
    if k48.exists():
        d = pd.read_csv(k48)
        d = d[d.workload.str.match(r"micro::tornado_K\d+_s4194304")].copy()
        d["K"] = d.workload.str.extract(r"_K(\d+)_").astype(int)
        frames.append(d)
    k16 = pd.read_csv(DATA_DIR / "k16_3t" / "summary.csv")
    k16 = k16[k16.workload == "micro::tornado_s4194304"].copy()
    k16["K"] = 16
    frames.append(k16)

    df = pd.concat(frames, ignore_index=True)
    for c in ("max_fct_us", "speedup_vs_ops_max"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def main() -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = load().sort_values(["K", "arm"])
    df.to_csv(DATA_DIR / "fig2_tornado_kSweep.csv", index=False)

    style = arm_style(FULL_LADDER)
    all_arms = ["ops"] + [f"reps_b{b}" for b in FULL_LADDER]
    ks = sorted(df.K.unique())
    x = np.arange(len(ks))
    bw = 0.85 / len(all_arms)

    ROWS = [("max_fct_us", "Max FCT (μs)", None, "%.0f"),
            ("speedup_vs_ops_max", "Speedup vs OPS\n(Max FCT)", 1.0, "%.3f")]
    fig, axes = plt.subplots(2, 1, figsize=(9, 9), sharex=True)
    for ax, (col, ylab, ref, fmt) in zip(axes, ROWS):
        for i, arm in enumerate(all_arms):
            vals, xs = [], []
            for j, k in enumerate(ks):
                row = df[(df.K == k) & (df.arm == arm)]
                if len(row):
                    vals.append(row[col].iloc[0])
                    xs.append(x[j] + i * bw)
            if not xs:
                continue
            cont = ax.bar(xs, vals, bw, color=style[arm]["color"],
                          hatch=style[arm]["hatch"], edgecolor="black", lw=0.4)
            ax.bar_label(cont, fmt=fmt, rotation=90, padding=2, fontsize=6.5)
        if ref is not None:
            ax.axhline(ref, color="grey", ls="--", lw=1.2, zorder=1)
        ax.set_ylabel(ylab, fontsize=12)
        ax.grid(True, axis="y", ls=":", lw=0.7, alpha=0.75)

    # top: linear from 0 with label headroom
    h = [b.get_height() for b in axes[0].patches if np.isfinite(b.get_height())]
    axes[0].set_ylim(0, max(h) * 1.18)
    # bottom: tight window around 1.0
    sp = df.speedup_vs_ops_max.dropna()
    pad = max((sp.max() - sp.min()) * 0.15, 0.01)
    axes[1].set_ylim(min(1.0, sp.min()) - pad, max(1.0, sp.max()) + pad * 3)

    axes[1].set_xticks(x + 0.85 / 2 - bw / 2)
    axes[1].set_xticklabels(
        [f"K={k}\n{K_HOSTS[k]} hosts · {K_PATHS[k]} paths" for k in ks],
        fontsize=10)
    axes[1].set_xlabel("fat-tree radix K (3-tier)", fontsize=12)
    axes[0].set_title(
        "exp27 plot 3 — Tornado 4 MiB, SRv6, sender-only MPRDMA CC\n"
        "vs 3-tier fat-tree radix K; seed 42, single seed → no error bars",
        fontsize=11)

    present = arm_order(df, FULL_LADDER)
    handles = [Patch(facecolor=style[a]["color"], hatch=style[a]["hatch"],
                     edgecolor="black", label=style[a]["label"]) for a in present]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles),
               fontsize=9, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    out = PLOTS_DIR / "fig2" / "fig2_tornado_k_sweep.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
