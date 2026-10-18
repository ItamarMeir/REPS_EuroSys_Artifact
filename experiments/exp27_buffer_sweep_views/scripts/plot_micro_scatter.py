#!/usr/bin/env python3
"""
exp27 — horizontal speedup-vs-OPS scatter, the exp26/paper "micro panel" form
(exp26/plots/fig{2,4}_micro.png).  Companion to plot_micro_bars.py (the
transpose); same CLI and same data slice.

  y = 9 workload categories (I./P./T. × 4/8/16 MiB), paper order, first on top
  x = speedup vs OPS on Max FCT (ops_max / arm_max), dashed vline at 1.0
  one marker series per arm: OPS orange square, REPS viridis-by-B "X"

Port of exp26/scripts/plot.py::draw_scatter (+ micro_ylab / MICRO_ORDER).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

from plot_micro_bars import DATA_DIR, PLOTS_DIR, OPS_COLOR, arm_order, load_slice
from sweep_render import _SHAPES, _shape

_PFX = {"incast": "I. 8:1", "perm": "P.", "tornado": "T."}
MICRO_ORDER = [f"{_PFX[p]} {s}MiB" for p in ("incast", "perm", "tornado")
               for s in (4, 8, 16)]


def arm_style(bladder: list[int]) -> dict[str, dict]:
    """OPS = filled orange square; each REPS B = its own hollow marker shape
    (same convention as fig2_tornado_bdp_sweep_lines.png)."""
    cmap = plt.get_cmap("viridis")
    n = max(len(bladder) - 1, 1)
    st = {"ops": dict(color=OPS_COLOR, marker="s", filled=True, label="OPS")}
    for i, b in enumerate(bladder):
        st[f"reps_b{b}"] = dict(color=cmap(i / n), marker=_shape(f"reps_b{b}", bladder),
                                filled=False, label=f"REPS  B={b}")
    return st


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True)
    ap.add_argument("--sizes", default="4,8,16")
    ap.add_argument("--bladder", default="1,2,4,8,16,32")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fig", default="fig2")
    ap.add_argument("--condition", default="healthy")
    ap.add_argument("--title-suffix", default="")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",")]
    bladder = [int(b) for b in args.bladder.split(",")]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    df = load_slice(Path(args.summary), sizes, args.fig, args.condition)
    df = df.copy()
    df["ylab"] = df.apply(
        lambda r: f"{_PFX.get(r.pat, r.pat)} {int(r.size_mib)}MiB", axis=1)
    order = [y for y in MICRO_ORDER if y in set(df.ylab)]
    df = df[df.ylab.isin(order)]

    keep = ["fig", "workload", "pat", "size_mib", "condition", "arm", "buf_size",
            "seed", "max_fct_us", "speedup_vs_ops_max", "ylab"]
    prov = DATA_DIR / (out.stem.replace("micro_scatter", "micro_scatter") + ".csv")
    df[keep].sort_values(["ylab", "arm"]).to_csv(prov, index=False)

    style = arm_style(bladder)
    arms = arm_order(df, bladder)
    yc = {lab: i for i, lab in enumerate(order)}

    fig, ax = plt.subplots(figsize=(7.2, 6.6))
    ax.axvline(1.0, color="grey", ls="--", lw=1.5)
    for arm in arms:
        rows = df[df.arm == arm]
        xs = [r.speedup_vs_ops_max for _, r in rows.iterrows()
              if np.isfinite(r.speedup_vs_ops_max)]
        ys = [yc[r.ylab] for _, r in rows.iterrows()
              if np.isfinite(r.speedup_vs_ops_max)]
        if not xs:
            continue
        st = style[arm]
        if st["filled"]:
            ax.scatter(xs, ys, s=150, marker=st["marker"], color=st["color"],
                       edgecolors="none", alpha=0.9, zorder=4)
        else:
            ax.scatter(xs, ys, s=150, marker=st["marker"], facecolors="none",
                       edgecolors=st["color"], linewidths=1.9, alpha=0.95,
                       zorder=3)

    # OPS stalled on flows every REPS arm finished -> its speedup is a lower bound
    if "unfinished_vs_best" in df.columns:
        for _, r in df[(df.arm == "ops")
                       & (df.unfinished_vs_best.fillna(0) > 0)].iterrows():
            ax.text(1.0, yc[r.ylab] + 0.36,
                    f" OPS finished {int(r.n_flows)}/{int(r.n_connections)} flows",
                    va="center", ha="left", fontsize=6, color="crimson")

    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=10)
    ax.set_ylim(len(order) - 0.4, -0.6)
    ax.set_xlabel("Speedup vs OPS (Max FCT)", fontsize=13)
    ax.grid(True, which="both", ls=":", lw=0.75, alpha=0.75)
    suffix = f"\n{args.title_suffix}" if args.title_suffix else ""
    ax.set_title(f"exp27 — synthetic benchmarks ({args.fig}, {args.condition})"
                 f"{suffix}", fontsize=11)

    handles = []
    for a in arms:
        st = style[a]
        if st["filled"]:
            handles.append(Line2D([], [], color=st["color"], marker=st["marker"],
                                  ls="", ms=10, label=st["label"]))
        else:
            handles.append(Line2D([], [], marker=st["marker"], ls="", ms=10,
                                  mfc="none", mec=st["color"], mew=1.9,
                                  label=st["label"]))
    fig.legend(handles=handles, loc="lower center", ncol=min(len(arms), 4),
               fontsize=9, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}\nwrote {prov}")


if __name__ == "__main__":
    main()
