#!/usr/bin/env python3
"""
exp27 F4 — is the asymmetric-regime REPS win also a BDP-provisioning resonance?

Twin of plot 4 (plot_bdp_sweep.py) under the asym32 condition (-failed 32).
Emits both forms into plots/fig4/:
  fig4_tornado_bdp_sweep_lines.png   fig4_tornado_bdp_sweep_bars.png

--healthy also overlays the plot-4 healthy curves (data/bdp_sweep/summary.csv).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sweep_render import render_sweep

EXP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = EXP_DIR / "data"
OUT_DIR = EXP_DIR / "plots" / "fig4"

LADDER = [1, 2, 4, 8, 16, 32]
ARMS = ["ops"] + [f"reps_b{b}" for b in LADDER]
COND = [  # (label, summary, condition)
    ("healthy", DATA_DIR / "bdp_sweep" / "summary.csv", "healthy"),
    ("asym32", DATA_DIR / "fig4_asym" / "summary.csv", "asym32"),
]


def load(path: Path, condition: str) -> pd.DataFrame:
    d = pd.read_csv(path)
    d = d[d.workload.str.match(r"micro::tornado_bdp\d+_s4194304")
          & (d.condition == condition)].copy()
    d["bdp"] = d.workload.str.extract(r"bdp(\d+)_").astype(int)
    for c in ("max_fct_us", "speedup_vs_ops_max"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.sort_values(["bdp", "arm"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--healthy", action="store_true")
    args = ap.parse_args()
    conds = COND if args.healthy else [c for c in COND if c[0] == "asym32"]
    frames = {lab: load(p, cnd) for lab, p, cnd in conds if p.exists()}
    frames["asym32"].to_csv(DATA_DIR / "fig4_tornado_bdpSweep.csv", index=False)

    bdps = sorted(frames["asym32"].bdp.unique())
    sub = ("thin dashed = healthy, bold = asym32 (-failed 32)" if args.healthy
           else "asym32 (-failed 32, 32 degraded ToR uplinks)")
    title = ("exp27 F4 — is the asymmetry-regime REPS win also a "
             "BDP-provisioning resonance?\n"
             "exp26 2-tier fabric (-paths 32), tornado 4 MiB, seed 42;  " + sub)
    for kind in ("lines", "bars"):
        render_sweep(frames, xcol="bdp", xvals=bdps,
                     xtick_labels=[str(b) for b in bdps],
                     xlabel="BDP the thresholds derive from  "
                            "(-q B, -ecn B/4 3B/4, -cwnd 1.5B)",
                     arms=ARMS, bladder=[1, 2, 4, 8, 16, 32, 64],
                     out=OUT_DIR / f"fig4_tornado_bdp_sweep_{kind}.png",
                     title=title, kind=kind,
                     vlines=[(101, "#444"), (152, "#888")])


if __name__ == "__main__":
    main()
