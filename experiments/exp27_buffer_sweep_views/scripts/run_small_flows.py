#!/usr/bin/env python3
"""
exp27 plot 5 driver — short-flow sweep on the K=16 3-tier fat tree.

Tornado, sizes 1/2/3/4 MiB (3-tier BDP ~0.6 MiB, so 1.6-6.4 BDP: short,
transient-dominated flows). Same fabric + thresholds as plots 2/3
(fat_tree_1024_1os_3t_400g, -paths 64, -q 152 -ecn 38 114 -cwnd 228, seed 42,
MPRDMA). Question: does the OPS-vs-REPS Max-FCT gap grow as flows get shorter
and the synchronized-startup transient becomes a larger fraction of FCT?

Generates the 3 missing tornado_n1024 CMs; 4 MiB reuses plot 2/3 data.
Runs in Docker (reps-artifact).
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

from common import DC_DIR, arm_lb_flags, arms_for, get_bdp, run_one  # noqa: E402

RUNS_DIR = EXP_DIR / "runs"
TOPO = "topologies/reps/fat_tree_1024_1os_3t_400g.topo"
N_PATHS = 64
SEED = 42

_BDP = get_bdp(400000, 3, 1000)
Q, ECN, CWND = int(_BDP), (int(_BDP / 4), int(_BDP * 3 / 4)), int(int(_BDP) * 1.5)
assert (Q, ECN, CWND) == (152, (38, 114), 228)

SIZES = [1048576, 2097152, 3145728, 4194304]      # 1/2/3/4 MiB
ARMS = arms_for(N_PATHS)          # ops, reps_b{1,2,4,8,16,32,64}


def cm(size: int) -> str:
    return f"connection_matrices/tornado_n1024_s{size}.cm"


def prep_cms() -> None:
    for size in SIZES:
        p = DC_DIR / cm(size)
        if p.exists():
            print(f"  cm exists: {cm(size)}")
            continue
        c = ["python3", "connection_matrices/gen_tornado.py", cm(size),
             "1024", "1024", str(size), "0", "42"]
        print(f"  gen: {' '.join(c)}", flush=True)
        subprocess.run(c, cwd=str(DC_DIR), check=True)


def flags_for(size: int, arm: str, failed: int = 0, seed: int = SEED) -> list[str]:
    f = [
        "-connections_mapping", "-disable_trim", "-sack_threshold", "4000",
        "-tm", cm(size), "-end", "90000", "-seed", str(seed),
        "-sender_cc_only", "-sender_cc_algo", "mprdma",
        "-topo", TOPO, "-enable_qa_gate", "-linkspeed", "400000",
        "-ecn", str(ECN[0]), str(ECN[1]), "-q", str(Q), "-cwnd", str(CWND),
    ]
    if failed:
        f += ["-failed", str(failed), "-skip_asy"]
    return f + arm_lb_flags(arm, N_PATHS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prep-cms", action="store_true")
    ap.add_argument("--sizes", default=",".join(str(s) for s in SIZES))
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--failed", type=int, default=0,
                    help="degrade N ToR uplinks (-failed N -skip_asy); "
                         "writes fig4/asym<N> instead of fig2/healthy")
    ap.add_argument("--seed", type=int, default=SEED,
                    help="non-42 seeds get a distinct workload key "
                         "(tornado_sf<size>_seed<N>) so they don't overwrite")
    args = ap.parse_args()
    if args.prep_cms:
        prep_cms()

    sizes = [int(s) for s in args.sizes.split(",")]
    arms = [a for a in ARMS if a in args.arms.split(",")]
    figseg, cond = (("fig4", f"asym{args.failed}") if args.failed
                    else ("fig2", "healthy"))
    sfx = "" if args.seed == SEED else f"_seed{args.seed}"
    cells = list(itertools.product(sizes, arms))
    print(f"small_flows: {len(cells)} runs (q={Q} ecn={ECN} cwnd={CWND} "
          f"seed={args.seed}) [{figseg}/{cond}]", flush=True)

    fails = 0
    for i, (size, arm) in enumerate(cells, 1):
        wl = f"tornado_sf{size}{sfx}_s{size}"    # sf-prefixed so it never collides
        out = RUNS_DIR / figseg / "micro" / wl / cond / arm / "stdout.txt"
        res = run_one(flags_for(size, arm, args.failed, args.seed), out, cwd=DC_DIR)
        print(f"[{i}/{len(cells)}] {res['status']:<16} {size}/{arm}  "
              f"{res['nflows']} flows {res['seconds']}s", flush=True)
        if res["status"].startswith("FAIL"):
            fails += 1
    print(f"\nsmall_flows done: {fails} failures / {len(cells)}", flush=True)


if __name__ == "__main__":
    main()
