#!/usr/bin/env python3
"""
exp26 driver — fig_6_failures_micro conditions (queue/port time-trace).

Original: artifact_scripts/fig_6_failures_micro.py
  topo : topologies/reps/fat_tree_128_1os_3t_400g.topo   (16 distinct inter-pod paths)
  seed : 5
  tm   : connection_matrices/test_symm32.cm  (4 inter-pod flows, 32 MiB each)
  flags: -failed 42 -sack_threshold 4000 -end 90000 -linkspeed 400000
         -ecn 20 80 -q 100 -cwnd 151 -sender_cc_only -sender_cc_algo mprdma
         -log_link -collect_data -save_data_folder <DIR>
  freezing arm additionally: -exit_freeze 100000000
  oblivious (= our `ops`) arm: no -exit_freeze  (matches original)

exp26 change: the original runs exactly {freezing, oblivious}; we run
{ops, reps_b1, reps_b2, reps_b4, reps_b8, reps_b16}, each with its OWN
-save_data_folder so the port/queue traces never overwrite each other
(the original re-used one raw_output/ dir and cp'd between the two runs).
"""
from __future__ import annotations

import argparse

from common import (DC_DIR, PATHS, RUNS_DIR, arm_lb_flags, arms_for, emit,
                    run_one)

TOPO = "topologies/reps/fat_tree_128_1os_3t_400g.topo"
TOPO_KEY = "fat_tree_128_1os_3t_400g"
SEED = 5
N_PATHS = PATHS[TOPO_KEY]
TM = "connection_matrices/test_symm32.cm"
EXIT_FREEZE = "100000000"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="")
    args = ap.parse_args()

    arms = arms_for(N_PATHS)
    if args.arms:
        arms = [a for a in arms if a in args.arms.split(",")]

    total = len(arms)
    print(f"fig6: {total} runs  (topo={TOPO_KEY} n_paths={N_PATHS})", flush=True)

    fails = 0
    for i, arm in enumerate(arms, 1):
        arm_dir = RUNS_DIR / "fig6" / "test_symm32" / "failed42" / arm
        flags = [
            "-failed", "42",
            "-sack_threshold", "4000",
            "-end", "90000",
            "-seed", str(SEED),
            "-sender_cc_only", "-sender_cc_algo", "mprdma",
            "-topo", TOPO,
            "-linkspeed", "400000",
            "-ecn", "20", "80",
            "-q", "100",
            "-cwnd", "151",
            "-log_link",
            "-tm", TM,
            "-collect_data",
            *arm_lb_flags(arm, N_PATHS),
        ]
        if arm.startswith("reps_b"):
            flags += ["-exit_freeze", EXIT_FREEZE]
        res = run_one(flags, arm_dir / "stdout.txt", cwd=DC_DIR,
                      save_data_dest=arm_dir / "raw_output")
        emit(i, total, arm, res)
        if res["status"].startswith("FAIL"):
            fails += 1

    print(f"\nfig6 done: {fails} failures / {total}", flush=True)


if __name__ == "__main__":
    main()
