#!/usr/bin/env python3
"""
exp27 plot 2 driver — re-run exp26's fig2 "micro" panel on the K=16 3-tier fat
tree (fat_tree_1024_1os_3t_400g, 1024 hosts, 64 distinct cross-pod paths).

Same command template as exp26 run_sym.py `micro_flags` (healthy only), with:
  * -topo swapped to the 3-tier 1024-host topology
  * -q / -ecn / -cwnd recomputed from the 3-tier BDP (getBDP tiers 2 -> 3)
  * -paths 64, buffer sweep B in {1,2,4,8,16,32,64}
  * flow sizes {4,8,16,32,64} MiB

Runs are written in the exp26 layout
  runs/fig2/micro/<pat>_s<bytes>/healthy/<arm>/stdout.txt
so exp26/scripts/aggregate.py can aggregate them unchanged:
  EXP26_RUNS=<exp27>/runs EXP26_DATA=<exp27>/data/k16_3t python3 aggregate.py

Must run where the Linux htsim_uec binary executes (Docker image
reps-artifact, per CLAUDE.md). `--prep-cms` generates the 5 missing connection
matrices in DC_DIR first (seed 42, deterministic).
"""
from __future__ import annotations

import argparse
import itertools
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
EXP26_SCRIPTS = EXP_DIR.parent / "exp26_srv6_buffer_sweep" / "scripts"
sys.path.insert(0, str(EXP26_SCRIPTS))

from common import (  # noqa: E402  (path insert above)
    DC_DIR, arm_lb_flags, arms_for, b_ladder, get_bdp, run_one)

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"

TOPO = "topologies/reps/fat_tree_1024_1os_3t_400g.topo"
N_PATHS = 64
SEED = 42

# 3-tier BDP -> queue / ECN / cwnd, exactly as run_symmetric.py:64-66,88 derives
# them (verified: the tiers=2 form reproduces exp26's live 101 / 25 76 / 151).
_BDP = get_bdp(400000, 3, 1000)
Q = int(_BDP)                                   # 152
ECN = (int(_BDP / 4), int(_BDP * 3 / 4))        # (38, 114)
CWND = int(Q * 1.5)                             # 228
assert (Q, ECN, CWND) == (152, (38, 114), 228), (Q, ECN, CWND)

PATTERNS = ["perm", "tornado", "incast"]
SIZES = [4194304, 8388608, 16777216, 33554432, 67108864]   # 4/8/16/32/64 MiB


def cm_path(pat: str, size: int) -> str:
    if pat == "incast":
        return f"connection_matrices/incast_n1024_s{size}_d8.cm"
    return f"connection_matrices/{pat}_n1024_s{size}.cm"


def gen_missing_cms() -> None:
    """Create the 5 connection matrices not already in DC_DIR, using the same
    generator invocations as run_symmetric.py:124 `create_tm_files`."""
    specs = [
        ("gen_permutation.py", "perm", [67108864]),
        ("gen_tornado.py", "tornado", [33554432, 67108864]),
        ("gen_incast.py", "incast", [33554432, 67108864]),
    ]
    for gen, pat, sizes in specs:
        for size in sizes:
            out = cm_path(pat, size)
            if (DC_DIR / out).exists():
                print(f"  cm exists: {out}")
                continue
            if pat == "incast":
                cmd = ["python3", f"connection_matrices/{gen}", out,
                       "1024", "8", str(size), "0", "42", "1"]
            else:
                cmd = ["python3", f"connection_matrices/{gen}", out,
                       "1024", "1024", str(size), "0", "42"]
            print(f"  gen: {' '.join(cmd)}", flush=True)
            subprocess.run(cmd, cwd=str(DC_DIR), check=True)


def base_flags(pat: str, size: int) -> list[str]:
    return [
        "-connections_mapping", "-disable_trim",
        "-sack_threshold", "4000",
        "-tm", cm_path(pat, size),
        "-end", "90000",
        "-seed", str(SEED),
        "-sender_cc_only", "-sender_cc_algo", "mprdma",
        "-topo", TOPO,
        "-enable_qa_gate",
        "-linkspeed", "400000",
        "-ecn", str(ECN[0]), str(ECN[1]),
        "-q", str(Q),
        "-cwnd", str(CWND),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prep-cms", action="store_true")
    ap.add_argument("--patterns", default=",".join(PATTERNS))
    ap.add_argument("--sizes", default=",".join(str(s) for s in SIZES),
                    help="comma list of flow sizes in BYTES")
    ap.add_argument("--arms", default="", help="comma list to restrict arms")
    args = ap.parse_args()

    if args.prep_cms:
        gen_missing_cms()

    pats = [p for p in PATTERNS if p in args.patterns.split(",")]
    sizes = [int(s) for s in args.sizes.split(",")]
    arms = arms_for(N_PATHS)                      # ops + reps_b{1,2,4,8,16,32,64}
    assert b_ladder(N_PATHS) == [1, 2, 4, 8, 16, 32, 64], b_ladder(N_PATHS)
    if args.arms:
        arms = [a for a in arms if a in args.arms.split(",")]

    cells = list(itertools.product(pats, sizes, arms))
    total = len(cells)
    print(f"k16_3t: {total} runs  (q={Q} ecn={ECN} cwnd={CWND} paths={N_PATHS})",
          flush=True)

    fails = warns = 0
    for i, (pat, size, arm) in enumerate(cells, 1):
        wl = f"{pat}_s{size}"
        outfile = RUNS_DIR / "fig2" / "micro" / wl / "healthy" / arm / "stdout.txt"
        flags = base_flags(pat, size) + arm_lb_flags(arm, N_PATHS)
        res = run_one(flags, outfile, cwd=DC_DIR)
        tag = res["status"]
        extra = f"  {res['nflows']} flows, {res['seconds']}s"
        if res["tor_ecn_reenabled"]:
            extra += "  [TOR-ECN-REENABLED]"
        if res.get("cm_warn"):
            extra += f"  *** {res['cm_warn']} ***"
            warns += 1
        print(f"[{i}/{total}] {tag:<20} {pat}/{size}/{arm}{extra}", flush=True)
        if tag.startswith("FAIL"):
            fails += 1

    print(f"\nk16_3t done: {fails} failures / {total}"
          f"{f', {warns} CM WARNINGS' if warns else ''}", flush=True)


if __name__ == "__main__":
    main()
