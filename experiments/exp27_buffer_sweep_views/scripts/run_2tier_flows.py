#!/usr/bin/env python3
"""
exp27 plot 5b — tornado flow-size sweep on a 2-tier fabric (twin of plot 5).

  --nhosts 1024 (default): fat_tree_1024_1os_2t_400g, -paths 32
  --nhosts 128            : fat_tree_128_1os_2t_400g,  -paths 8   (exp26 fig4's
                            own micro fabric — pair with -failed 4)

exp26's exact 2-tier thresholds -q 101 -ecn 25 76 -cwnd 151 (paper's q = 1*BDP
at the 2-tier BDP; tier-based so identical for 128 and 1024 hosts), tornado,
seed 42, sender-only MPRDMA.

Default sizes are the ones NOT already in exp26: 1/2/3 MiB (4/8/16 MiB come from
exp26's own summary.csv via the plotters). Pass --prep-cms to generate any
missing tornado_n<hosts>_s<size>.cm. Runs in Docker (reps-artifact).
"""
from __future__ import annotations

import argparse
import itertools
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(EXP_DIR.parent / "exp26_srv6_buffer_sweep" / "scripts"))

from common import DC_DIR, arm_lb_flags, arms_for, run_one  # noqa: E402

RUNS_DIR = EXP_DIR / "runs"
DEFAULT_SEED = 42
Q, ECN, CWND = 101, (25, 76), 151
SIZES = [1048576, 2097152, 3145728]              # 1/2/3 MiB (4/8/16 reused)

NHOSTS = {1024: ("fat_tree_1024_1os_2t_400g", 32),
          128: ("fat_tree_128_1os_2t_400g", 8)}


def cm(nhosts: int, size: int) -> str:
    return f"connection_matrices/tornado_n{nhosts}_s{size}.cm"


def prep_cms(nhosts: int, sizes: list[int]) -> None:
    for size in sizes:
        p = DC_DIR / cm(nhosts, size)
        if p.exists():
            print(f"  cm exists: {cm(nhosts, size)}")
            continue
        c = ["python3", "connection_matrices/gen_tornado.py", cm(nhosts, size),
             str(nhosts), str(nhosts), str(size), "0", "42"]
        print(f"  gen: {' '.join(c)}", flush=True)
        subprocess.run(c, cwd=str(DC_DIR), check=True)


def flags_for(topo: str, npaths: int, size: int, arm: str,
              failed: int, nhosts: int, seed: int) -> list[str]:
    f = [
        "-connections_mapping", "-disable_trim", "-sack_threshold", "4000",
        "-tm", cm(nhosts, size), "-end", "90000", "-seed", str(seed),
        "-sender_cc_only", "-sender_cc_algo", "mprdma",
        "-topo", f"topologies/reps/{topo}.topo", "-enable_qa_gate",
        "-linkspeed", "400000",
        "-ecn", str(ECN[0]), str(ECN[1]), "-q", str(Q), "-cwnd", str(CWND),
    ]
    if failed:
        f += ["-failed", str(failed), "-skip_asy"]
    return f + arm_lb_flags(arm, npaths)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nhosts", type=int, default=1024, choices=list(NHOSTS))
    ap.add_argument("--sizes", default=",".join(str(s) for s in SIZES))
    ap.add_argument("--arms", default="")
    ap.add_argument("--failed", type=int, default=0,
                    help="degrade N ToR uplinks (-failed N -skip_asy); "
                         "writes fig4/asym<N> instead of fig2/healthy")
    ap.add_argument("--prep-cms", action="store_true")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help="non-42 seeds get a distinct workload key so they "
                         "don't overwrite the canonical run")
    args = ap.parse_args()

    topo, npaths = NHOSTS[args.nhosts]
    all_arms = arms_for(npaths)
    arms = [a for a in all_arms if not args.arms or a in args.arms.split(",")]
    sizes = [int(s) for s in args.sizes.split(",")]
    if args.prep_cms:
        prep_cms(args.nhosts, sizes)
    figseg, cond = (("fig4", f"asym{args.failed}") if args.failed
                    else ("fig2", "healthy"))
    tag = "" if args.nhosts == 1024 else f"{args.nhosts}"
    ssfx = "" if args.seed == DEFAULT_SEED else f"_seed{args.seed}"

    cells = list(itertools.product(sizes, arms))
    print(f"2tier_flows: {len(cells)} runs on {topo} (-paths {npaths}, "
          f"q={Q} ecn={ECN} cwnd={CWND} seed={args.seed}) [{figseg}/{cond}]",
          flush=True)
    fails = 0
    for i, (size, arm) in enumerate(cells, 1):
        wl = f"tornado_2t{tag}{size}{ssfx}_s{size}"
        out = RUNS_DIR / figseg / "micro" / wl / cond / arm / "stdout.txt"
        res = run_one(flags_for(topo, npaths, size, arm, args.failed,
                                args.nhosts, args.seed), out, cwd=DC_DIR)
        print(f"[{i}/{len(cells)}] {res['status']:<16} {size}/{arm}  "
              f"{res['nflows']} flows {res['seconds']}s", flush=True)
        if res["status"].startswith("FAIL"):
            fails += 1
    print(f"\n2tier_flows done: {fails} failures / {len(cells)}", flush=True)


if __name__ == "__main__":
    main()
