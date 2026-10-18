#!/usr/bin/env python3
"""
exp27 plot 5 — tornado Max FCT vs flow size, healthy fabric.

  --fabric 3t : fat_tree_1024_1os_3t_400g, -paths 64, -q 152 -ecn 38 114 -cwnd 228
                sizes 1/2/3/4 MiB from run_small_flows.py; 8-64 MiB from plots 2/3.
  --fabric 2t : fat_tree_1024_1os_2t_400g, -paths 32, -q 101 -ecn 25 76 -cwnd 151
                sizes 1/2/3 MiB from run_2tier_flows.py; 4/8/16 MiB from exp26.

For each fabric emits both forms into plots/fig2/:
  fig2_tornado_small_flows_<fab>_lines.png   ..._bars.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sweep_render import render_sweep

EXP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = EXP_DIR / "data"
OUT_DIR = EXP_DIR / "plots" / "fig2"
EXP26_SUMMARY = EXP_DIR.parent / "exp26_srv6_buffer_sweep" / "data" / "summary.csv"

_ARMS32 = ["ops", "reps_b1", "reps_b2", "reps_b4", "reps_b8", "reps_b16", "reps_b32"]

FABRIC = {
    "3t": dict(
        out="3t",
        sources=[(DATA_DIR / "small_flows" / "summary.csv", r"micro::tornado_sf\d+_s\d+$"),
                 (DATA_DIR / "k16_3t" / "summary.csv", r"micro::tornado_s\d+$")],
        arms=_ARMS32 + ["reps_b64"],
        sizes=[1, 2, 3, 4, 8, 16, 32, 64],
        bdp_mib=0.61,
        title="K=16 3-tier fat tree (-paths 64, -q 152 -ecn 38 114 -cwnd 228)",
    ),
    "2t": dict(
        out="2t_1024host",
        sources=[(DATA_DIR / "twotier_flows" / "summary.csv", r"micro::tornado_2t\d+_s\d+$"),
                 (EXP26_SUMMARY, r"micro::tornado_s\d+$")],
        arms=_ARMS32,
        sizes=[1, 2, 3, 4, 8, 16],
        bdp_mib=0.41,
        title="1024-host 2-tier fat tree (-paths 32, -q 101 -ecn 25 76 -cwnd 151)",
    ),
    "2t128": dict(
        out="2t_128host",
        sources=[(DATA_DIR / "twotier128" / "summary.csv", r"micro::tornado_2t128\d+_s\d+$")],
        arms=["ops", "reps_b1", "reps_b2", "reps_b4", "reps_b8"],
        sizes=[1, 2, 3, 4, 8, 16],
        bdp_mib=0.41,
        title="128-host 2-tier fat tree (-paths 8, -q 101 -ecn 25 76 -cwnd 151)",
    ),
}


def _load(pairs) -> pd.DataFrame:
    out = []
    for path, wl_re in pairs:
        if not path.exists():
            continue
        d = pd.read_csv(path)
        d = d[d.workload.str.fullmatch(wl_re) & (d.condition == "healthy")].copy()
        d["size_mib"] = (d.workload.str.extract(r"_s(\d+)$")[0].astype(int)
                         / 1048576).round().astype(int)
        out.append(d)
    d = pd.concat(out, ignore_index=True).drop_duplicates(["size_mib", "arm"],
                                                          keep="first")
    for c in ("max_fct_us", "speedup_vs_ops_max"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fabric", choices=list(FABRIC), default="3t")
    args = ap.parse_args()
    cfg = FABRIC[args.fabric]

    df = _load(cfg["sources"])
    df = df[df.size_mib.isin(cfg["sizes"]) & df.arm.isin(cfg["arms"])]
    df.sort_values(["size_mib", "arm"]).to_csv(
        DATA_DIR / f"fig2_tornado_flows_{cfg['out']}.csv", index=False)

    sizes = [s for s in cfg["sizes"] if s in set(df.size_mib)]
    title = (f"exp27 plot 5 — tornado Max FCT vs flow size (healthy)\n"
             f"{cfg['title']};  seed 42, single seed")
    for kind in ("lines", "bars"):
        render_sweep({"healthy": df}, xcol="size_mib", xvals=sizes,
                     xtick_labels=[f"{s} MiB\n(~{s / cfg['bdp_mib']:.0f} BDP)"
                                   for s in sizes],
                     xlabel="tornado flow size", arms=cfg["arms"],
                     bladder=[1, 2, 4, 8, 16, 32, 64],
                     out=OUT_DIR / f"fig2_tornado_small_flows_{cfg['out']}_{kind}.png",
                     title=title, kind=kind, log_raw=(kind == "lines"),
                     raw_ylabel="Max FCT (μs, log)" if kind == "lines"
                     else "Max FCT (μs)")


if __name__ == "__main__":
    main()
