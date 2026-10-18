#!/usr/bin/env python3
"""
exp27 F5 — tornado Max FCT vs flow size under asymmetry.

Twin of plot 5 (plot_small_flows.py). For each fabric emits both forms into
plots/fig4/.  --healthy also overlays the matching plot-5 healthy curves.

  --fabric 2t     : fat_tree_1024_1os_2t_400g -paths 32  -failed 32 (asym32)
  --fabric 2t128  : fat_tree_128_1os_2t_400g  -paths 8   -failed 4  (asym4)
                    exp26 fig4's own micro fabric; 4/8/16 MiB reuse exp26.
  --fabric 3t     : fat_tree_1024_1os_3t_400g -paths 64  -failed 32 (asym32)

All: -q 101/152 -ecn .. per tier, tornado, seed 42, sender-only MPRDMA.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sweep_render import render_sweep

EXP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = EXP_DIR / "data"
OUT_DIR = EXP_DIR / "plots" / "fig4"
EXP26_SUMMARY = EXP_DIR.parent / "exp26_srv6_buffer_sweep" / "data" / "summary.csv"
FIG4_ASYM = DATA_DIR / "fig4_asym" / "summary.csv"
TT128 = DATA_DIR / "twotier128" / "summary.csv"

_ARMS32 = ["ops", "reps_b1", "reps_b2", "reps_b4", "reps_b8", "reps_b16", "reps_b32"]

FABRIC = {
    "2t": dict(
        out="2t_1024host", asym_cond="asym32",
        healthy=[(DATA_DIR / "twotier_flows" / "summary.csv", r"micro::tornado_2t\d+_s\d+$"),
                 (EXP26_SUMMARY, r"micro::tornado_s\d+$")],
        asym=[(FIG4_ASYM, r"micro::tornado_2t\d+_s\d+$")],
        arms=_ARMS32, sizes=[1, 2, 3, 4, 8, 16], bdp_mib=0.41,
        title="1024-host 2-tier (-paths 32), -failed 32 (asym32)",
        cloud=dict(mib=4, csv="fig4_2t_b1_4mib_seeds", seeds=[42, 43, 47, 52]),
    ),
    "2t128": dict(
        out="2t_128host", asym_cond="asym4",
        healthy=[(TT128, r"micro::tornado_2t128\d+_s\d+$")],
        asym=[(TT128, r"micro::tornado_2t128\d+_s\d+$"),
              (EXP26_SUMMARY, r"micro::tornado_s\d+$")],
        arms=["ops", "reps_b1", "reps_b2", "reps_b4", "reps_b8"],
        sizes=[1, 2, 3, 4, 8, 16], bdp_mib=0.41,
        title="128-host 2-tier (-paths 8), -failed 4 (asym4) — exp26 fig4's own fabric",
    ),
    "3t": dict(
        out="3t", asym_cond="asym32",
        healthy=[(DATA_DIR / "small_flows" / "summary.csv", r"micro::tornado_sf\d+_s\d+$"),
                 (DATA_DIR / "k16_3t" / "summary.csv", r"micro::tornado_s\d+$")],
        asym=[(FIG4_ASYM, r"micro::tornado_sf\d+_s\d+$")],
        arms=_ARMS32 + ["reps_b64"], sizes=[1, 2, 3, 4, 8, 16, 32, 64],
        bdp_mib=0.61,
        title="K=16 3-tier (-paths 64), -failed 32 (asym32)",
        cloud=dict(mib=3, csv="fig4_3t_b1_3mib_seeds", seeds=[42, 43, 47, 49]),
    ),
}


def _load(pairs, condition: str) -> pd.DataFrame:
    out = []
    for path, wl_re in pairs:
        if not Path(path).exists():
            continue
        d = pd.read_csv(path)
        d = d[d.workload.str.fullmatch(wl_re) & (d.condition == condition)].copy()
        d["size_mib"] = (d.workload.str.extract(r"_s(\d+)$")[0].astype(int)
                         / 1048576).round().astype(int)
        out.append(d)
    if not out:
        return pd.DataFrame()
    d = pd.concat(out, ignore_index=True).drop_duplicates(["size_mib", "arm"],
                                                          keep="first")
    for c in ("max_fct_us", "speedup_vs_ops_max"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fabric", choices=list(FABRIC), default="2t")
    ap.add_argument("--healthy", action="store_true")
    args = ap.parse_args()
    cfg = FABRIC[args.fabric]
    acond = cfg["asym_cond"]

    raw = {"healthy": _load(cfg["healthy"], "healthy"),
           acond: _load(cfg["asym"], acond)}
    frames = {}
    for lab in (("healthy", acond) if args.healthy else (acond,)):
        d = raw[lab]
        if not d.empty:
            frames[lab] = d[d.size_mib.isin(cfg["sizes"]) & d.arm.isin(cfg["arms"])]
    frames[acond].sort_values(["size_mib", "arm"]).to_csv(
        DATA_DIR / f"fig4_tornado_flows_{cfg['out']}.csv", index=False)

    sizes = [s for s in cfg["sizes"] if s in set(frames[acond].size_mib)]
    sub = (f"thin dashed = healthy, bold = {acond}" if args.healthy
           else f"{acond} (degraded ToR->spine-0 uplinks at 200G)")
    title = (f"exp27 F5 — tornado Max FCT vs flow size under asymmetry\n"
             f"{cfg['title']};  seed 42, single seed;  " + sub)

    # per-seed B=1 speedup at the anomalous flow size — the plotted seed-42 point
    # is a single-flow-tail lottery; overlay a few selected seeds to show it.
    cloud = None
    cc = cfg.get("cloud")
    seed_csv = DATA_DIR / f"{cc['csv']}.csv" if cc else None
    if cc and seed_csv.exists() and cc["mib"] in sizes:
        from plot_micro_bars import arm_style as _as
        col = _as([1, 2, 4, 8, 16, 32, 64])["reps_b1"]["color"]
        sc = pd.read_csv(seed_csv)
        sc = sc[sc.seed.isin(cc["seeds"])]
        cloud = [(cc["mib"], float(sp), col) for sp in sc.speedup]
        title += (f"\n{cc['mib']} MiB B=1: line = seed 42; dots = seeds "
                  f"{cc['seeds']} ({sc.speedup.min():.2f}-{sc.speedup.max():.2f}) "
                  "— single-flow-tail lottery, see README")

    for kind in ("lines", "bars"):
        render_sweep(frames, xcol="size_mib", xvals=sizes,
                     xtick_labels=[f"{s} MiB\n(~{s / cfg['bdp_mib']:.0f} BDP)"
                                   for s in sizes],
                     xlabel="tornado flow size", arms=cfg["arms"],
                     bladder=[1, 2, 4, 8, 16, 32, 64],
                     out=OUT_DIR / f"fig4_tornado_small_flows_{cfg['out']}_{kind}.png",
                     title=title, kind=kind, log_raw=(kind == "lines"),
                     raw_ylabel="Max FCT (μs, log)" if kind == "lines"
                     else "Max FCT (μs)",
                     spd_cloud=cloud if kind == "lines" else None)


if __name__ == "__main__":
    main()
