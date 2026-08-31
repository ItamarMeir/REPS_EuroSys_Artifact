#!/usr/bin/env python3
"""
exp26 driver — fig_8_extreme_failures conditions.

Original: artifact_scripts/fig_8_extreme_failures.py
  topo  : topologies/reps/fat_tree_1024_1os_2t_400g.topo      (32 distinct paths)
  seed  : 44
  tm    : connection_matrices/perm_n1024_s33554432.cm         (32 MiB per flow)
  flags : -sack_threshold 4000 -end 90000 -linkspeed 400000
          -ecn 20 80 -q 100 -cwnd 151 -sender_cc_only -sender_cc_algo mprdma
          (NO -connections_mapping, NO -disable_trim  -> trimming stays ON)
  freezing arm additionally: -exit_freeze 10000000000
  conditions: cable-failure levels 0,10,20,30,40,50 %
     0 %  -> no -failures_input
     N %  -> -failures_input ../failures_input/N_percent_failed_cables.txt

exp26 change: LB sweep -> {ops, reps_b1..reps_b32}, every run + -use_srv6 -paths 32.
The `ideal_fct` analytic line from the original is reconstructed in plot.py.
"""
from __future__ import annotations

import argparse
import itertools

from common import (DC_DIR, PATHS, RUNS_DIR, arm_lb_flags, arms_for, emit,
                    run_one)

TOPO = "topologies/reps/fat_tree_1024_1os_2t_400g.topo"
TOPO_KEY = "fat_tree_1024_1os_2t_400g"
SEED = 44
N_PATHS = PATHS[TOPO_KEY]
TM = "connection_matrices/perm_n1024_s33554432.cm"
EXIT_FREEZE = "10000000000"
LEVELS = [0, 10, 20, 30, 40, 50]


def base_flags(level: int) -> list[str]:
    f = ["-sack_threshold", "4000"]
    if level > 0:
        f += ["-failures_input", f"../failures_input/{level}_percent_failed_cables.txt"]
    f += [
        "-end", "90000",
        "-seed", str(SEED),
        "-sender_cc_only", "-sender_cc_algo", "mprdma",
        "-topo", TOPO,
        "-linkspeed", "400000",
        "-ecn", "20", "80",
        "-q", "100",
        "-cwnd", "151",
        "-tm", TM,
    ]
    return f


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="")
    ap.add_argument("--levels", default="", help="comma list, e.g. 0,10,50")
    ap.add_argument("--quick", action="store_true",
                    help="levels 0,50 x {ops,reps_b1,reps_b8,reps_b32}")
    args = ap.parse_args()

    arms = arms_for(N_PATHS)
    levels = list(LEVELS)
    if args.quick:
        arms = ["ops", "reps_b1", "reps_b8", "reps_b32"]
        levels = [0, 50]
    if args.arms:
        arms = [a for a in arms if a in args.arms.split(",")]
    if args.levels:
        want = {int(x) for x in args.levels.split(",")}
        levels = [l for l in levels if l in want]

    cells = list(itertools.product(levels, arms))
    total = len(cells)
    print(f"fig8: {total} runs  (topo={TOPO_KEY} n_paths={N_PATHS})", flush=True)

    fails = 0
    for i, (level, arm) in enumerate(cells, 1):
        cond = f"fail{level:02d}"
        outfile = RUNS_DIR / "fig8" / "perm" / cond / arm / "stdout.txt"
        flags = base_flags(level) + arm_lb_flags(arm, N_PATHS)
        if arm.startswith("reps_b"):
            flags += ["-exit_freeze", EXIT_FREEZE]
        res = run_one(flags, outfile, cwd=DC_DIR)
        emit(i, total, f"{cond}/{arm}", res)
        if res["status"].startswith("FAIL"):
            fails += 1

    print(f"\nfig8 done: {fails} failures / {total}", flush=True)


if __name__ == "__main__":
    main()
