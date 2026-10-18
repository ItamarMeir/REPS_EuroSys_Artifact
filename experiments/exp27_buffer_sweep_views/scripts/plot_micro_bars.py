#!/usr/bin/env python3
"""
exp27 -- raw-FCT bar charts, the transpose of exp26/plots/fig2_micro.png.

fig2_micro is a horizontal scatter (y = 9 synthetic workloads, x = speedup vs
OPS on max_fct_us). This re-plots the same slice with axes swapped: 2x3 grid,
grouped bars per LB arm, top row = absolute Max FCT (us) with a per-panel
y-scale, bottom row = speedup vs OPS (ops_max / arm_max) with a shared y-scale.

Default (no args) = plot 1: exp26's fig2 micro slice
(fat_tree_1024_1os_2t_400g, -paths 32, B<=32, sizes 4/8/16 MiB), single seed 42.

Plot 2 (K=16 3-tier, run by run_k16_3t.py + exp26 aggregate.py):
  python3 plot_micro_bars.py \
    --summary ../data/k16_3t/summary.csv --sizes 4,8,16,32,64 \
    --bladder 1,2,4,8,16,32,64 --out ../plots/fig2_micro_bars_k16_3t.png \
    --title-suffix "K=16 3-tier, -paths 64"

Both summaries share the exp26 aggregate.py schema (fig, workload=micro::<pat>_s<bytes>,
condition, arm, buf_size, max_fct_us, speedup_vs_ops_max, ...).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
DATA_DIR = EXP_DIR / "data"
PLOTS_DIR = EXP_DIR / "plots"
DEFAULT_SUMMARY = EXP_DIR.parent / "exp26_srv6_buffer_sweep" / "data" / "summary.csv"

# OPS colour copied verbatim from exp26/scripts/plot.py so a given B keeps the
# exact same viridis colour as every exp26 figure.
OPS_COLOR = "#d95f02"
# distinct bar hatch per REPS buffer, so B is legible without colour
HATCH_POOL = ["//", "\\\\", "xx", "..", "oo", "**", "++", "--"]

# workload pattern -> panel, in fig2_micro's own order (I., P., T.)
PANELS = [("incast", "Incast 8:1"), ("perm", "Permutation"), ("tornado", "Tornado")]


def arm_order(df: pd.DataFrame, bladder: list[int]) -> list[str]:
    present = set(pd.to_numeric(
        df.loc[df.arm != "ops", "buf_size"], errors="coerce").dropna().astype(int))
    out = ["ops"] if (df.arm == "ops").any() else []
    return out + [f"reps_b{b}" for b in bladder if b in present]


def arm_style(bladder: list[int]) -> dict[str, dict]:
    cmap = plt.get_cmap("viridis")
    n = max(len(bladder) - 1, 1)
    style = {"ops": dict(color=OPS_COLOR, label="OPS", hatch="")}
    for i, b in enumerate(bladder):
        style[f"reps_b{b}"] = dict(color=cmap(i / n), label=f"REPS  B={b}",
                                   hatch=HATCH_POOL[i % len(HATCH_POOL)])
    return style


def load_slice(summary: Path, sizes_mib: list[int],
               fig: str = "fig2", condition: str = "healthy") -> pd.DataFrame:
    df = pd.read_csv(summary)
    # exact micro-panel workloads only: the 3 base patterns, <pat>_s<bytes>.
    # (a fig4/asym summary also carries tornado_bdp*/2t*/sf* sweep rows.)
    ex = df.workload.str.extract(r"^micro::(incast|perm|tornado)_s(\d+)$")
    df = df[(df.fig == fig) & (df.condition == condition) & ex[0].notna()].copy()
    ex = ex.loc[df.index]
    df["pat"] = ex[0]
    df["size_mib"] = (ex[1].astype(int) / 1048576).round().astype(int)
    df["max_fct_us"] = pd.to_numeric(df.max_fct_us, errors="coerce")
    df["speedup_vs_ops_max"] = pd.to_numeric(df.speedup_vs_ops_max, errors="coerce")
    return df[df.size_mib.isin(sizes_mib)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    ap.add_argument("--sizes", default="4,8,16", help="flow sizes in MiB")
    ap.add_argument("--bladder", default="1,2,4,8,16,32", help="REPS buffer sizes")
    ap.add_argument("--out", default=str(PLOTS_DIR / "fig2" / "fig2_micro_bars.png"))
    ap.add_argument("--title-suffix", default="")
    ap.add_argument("--fig", default="fig2")
    ap.add_argument("--condition", default="healthy")
    args = ap.parse_args()

    summary = Path(args.summary)
    sizes_mib = [int(s) for s in args.sizes.split(",")]
    bladder = [int(b) for b in args.bladder.split(",")]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    df = load_slice(summary, sizes_mib, args.fig, args.condition)
    style = arm_style(bladder)
    arms = arm_order(df, bladder)

    keep = ["fig", "workload", "pat", "size_mib", "condition", "arm", "buf_size",
            "seed", "max_fct_us", "speedup_vs_ops_max"]
    prov = DATA_DIR / (out.stem.replace("micro_bars", "micro_maxfct") + ".csv")
    df[keep].sort_values(["pat", "size_mib", "arm"]).to_csv(prov, index=False)

    x = np.arange(len(sizes_mib))
    bw = 0.8 / len(arms)

    # two rows, same 3 panels: top = raw Max FCT, bottom = speedup vs OPS
    ROWS = [("max_fct_us", "Max FCT (μs)", None),
            ("speedup_vs_ops_max", "Speedup vs OPS\n(Max FCT)", 1.0)]
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), sharey=False)
    for r, (col, ylab, ref) in enumerate(ROWS):
        for ax, (pat, title) in zip(axes[r], PANELS):
            sub = df[df.pat == pat]
            lblfmt = "%.2f" if ref is not None else "%.0f"
            for i, arm in enumerate(arms):
                vals = [
                    (v.iloc[0] if len(v := sub.loc[
                        (sub.size_mib == s) & (sub.arm == arm), col]) else np.nan)
                    for s in sizes_mib
                ]
                cont = ax.bar(x + i * bw, vals, bw, color=style[arm]["color"],
                              hatch=style[arm]["hatch"], edgecolor="black", lw=0.4)
                ax.bar_label(cont, fmt=lblfmt, rotation=90, padding=2, fontsize=6.5)
            if ref is not None:
                ax.axhline(ref, color="grey", ls="--", lw=1.3, zorder=1)
            ax.set_xticks(x + 0.4 - bw / 2)
            ax.set_xticklabels([f"{s} MiB" for s in sizes_mib], fontsize=11)
            ax.set_ylabel(ylab, fontsize=12)
            ax.grid(True, axis="y", ls=":", lw=0.75, alpha=0.75)
            if r == 0:
                ax.set_title(title, fontsize=12)
                heights = [b.get_height() for b in ax.patches
                           if np.isfinite(b.get_height())]
                if heights:
                    ax.set_ylim(0, max(heights) * 1.22)   # headroom for labels
        if ref is not None:   # bottom row: tight common window around ref (1.0)
            heights = [b.get_height() for a in axes[r] for b in a.patches
                       if np.isfinite(b.get_height())]
            lo = min([ref, *heights]) if heights else ref * 0.95
            hi = max([ref, *heights]) if heights else ref * 1.05
            span = hi - lo or ref * 0.1
            for a in axes[r]:
                a.set_ylim(lo - span * 0.15, hi + span * 0.45)  # headroom for labels

    handles = [Patch(facecolor=style[a]["color"], hatch=style[a]["hatch"],
                     edgecolor="black", label=style[a]["label"]) for a in arms]
    fig.legend(handles=handles, loc="lower center", ncol=len(arms), fontsize=10,
               frameon=False, bbox_to_anchor=(0.5, -0.01))
    suffix = f"\n{args.title_suffix}" if args.title_suffix else ""
    fig.suptitle(
        f"exp27 — Max FCT in synthetic benchmarks ({args.fig}, {args.condition})\n"
        "raw-time transpose of the micro panel (top) + speedup vs OPS (bottom); all "
        "arms -use_srv6 + sender-only MPRDMA CC; single seed (42), no error bars"
        + suffix, fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 0.92))
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}\nwrote {prov}")


if __name__ == "__main__":
    main()
