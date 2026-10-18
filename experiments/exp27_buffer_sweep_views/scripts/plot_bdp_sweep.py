#!/usr/bin/env python3
"""
exp27 plot 4 — REPS-vs-OPS Max-FCT gap vs the BDP the thresholds derive from.

exp26 2-tier fabric fixed (fat_tree_1024_1os_2t_400g, -paths 32, -use_srv6),
tornado 4 MiB, seed 42, MPRDMA; synthetic BDP B -> -q B -ecn B/4 3B/4 -cwnd 1.5B.
Shows the healthy REPS-vs-OPS gap is a resonance peaking at B=101 (exp26's own
config), not a topology effect.

Emits both forms into plots/fig2/:
  fig2_tornado_bdp_sweep_lines.png   fig2_tornado_bdp_sweep_bars.png
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from sweep_render import render_sweep

EXP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = EXP_DIR / "data"
OUT_DIR = EXP_DIR / "plots" / "fig2"
LADDER = [1, 2, 4, 8, 16, 32]
ARMS = ["ops"] + [f"reps_b{b}" for b in LADDER]


def main() -> None:
    df = pd.read_csv(DATA_DIR / "bdp_sweep" / "summary.csv")
    df = df[df.workload.str.match(r"micro::tornado_bdp\d+_s4194304")
            & (df.condition == "healthy")].copy()
    df["bdp"] = df.workload.str.extract(r"bdp(\d+)_").astype(int)
    for c in ("max_fct_us", "speedup_vs_ops_max"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values(["bdp", "arm"])
    df.to_csv(DATA_DIR / "fig2_tornado_bdpSweep.csv", index=False)

    bdps = sorted(df.bdp.unique())
    title = ("exp27 plot 4 — REPS vs OPS gap is set by BDP-provisioning, not "
             "topology\nexp26 2-tier fabric (-paths 32), tornado 4 MiB, seed 42, "
             "healthy")
    for kind in ("lines", "bars"):
        render_sweep({"healthy": df}, xcol="bdp", xvals=bdps,
                     xtick_labels=[str(b) for b in bdps],
                     xlabel="BDP the thresholds derive from  "
                            "(-q B, -ecn B/4 3B/4, -cwnd 1.5B)",
                     arms=ARMS, bladder=[1, 2, 4, 8, 16, 32, 64],
                     out=OUT_DIR / f"fig2_tornado_bdp_sweep_{kind}.png",
                     title=title, kind=kind,
                     vlines=[(101, "#444"), (152, "#888")])


if __name__ == "__main__":
    main()
