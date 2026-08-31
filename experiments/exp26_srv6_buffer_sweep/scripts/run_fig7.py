#!/usr/bin/env python3
"""
exp26 driver — fig_7_failures conditions.

Original: artifact_scripts/fig_7_failures.py -> run_all_failure.py -> run_failures.py
  topo   : topologies/reps/fat_tree_32_1os_2t_400g.topo          (4 distinct paths)
  seed   : 42
  cc     : -sender_cc_only -sender_cc_algo mprdma
  flags  : -connections_mapping -disable_trim -sack_threshold 4000
           -end 90000 -linkspeed 400000 -ecn 25 76 -q 101 -other_location -cwnd 151
  bdp    : getBDP(400000, 2, 1000) = 101.66  -> q=101, ecn=25/76, cwnd=151
  workloads (run_all_failure.py:22,39,56):
     permutation -> connection_matrices/permutation_size8388608B.cm
     dc          -> connection_matrices/100load_32.cm
     ai          -> connection_matrices/allreduce.cm
  failure scenarios (run_failures.py:28): 8 files, all via -failures_input.

exp26 change: LB sweep -> {ops, reps_b1, reps_b2, reps_b4}, every run + -use_srv6
              -paths 4.
"""
from __future__ import annotations

import argparse
import itertools

from common import (DC_DIR, PATHS, RUNS_DIR, arm_lb_flags, arms_for, emit,
                    get_bdp, run_one)

TOPO = "topologies/reps/fat_tree_32_1os_2t_400g.topo"
TOPO_KEY = "fat_tree_32_1os_2t_400g"
SEED = 42
N_PATHS = PATHS[TOPO_KEY]

WORKLOADS = {
    "permutation": "connection_matrices/permutation_size8388608B.cm",
    "dc": "connection_matrices/100load_32.cm",
    "ai": "connection_matrices/allreduce.cm",
}

SCENARIOS = [
    "5_percent_failed_switches_and_cables",
    "5_percent_failed_switches",
    "5_percent_failed_cables",
    "fail_one_switch_one_cable",
    "fail_one_cable",
    "fail_one_switch",
    "ber_cable_one_percent",
    "ber_switch_one_percent",
]

# run_failures.py getRunScript(): queue_size=int(bdp); ecn_min=int(bdp/4);
# ecn_max=int(bdp*3/4); cwnd=int(queue_size*1.5)   -> q=101, ecn=25/76, cwnd=151
_bdp = get_bdp(400000, 2, 1000)          # 101.656
Q = int(_bdp)                            # 101
ECN_MIN = int(_bdp / 4)                  # 25
ECN_MAX = int(_bdp * 3 / 4)              # 76
CWND = int(Q * 1.5)                      # 151


def base_flags(tm: str, scenario: str) -> list[str]:
    return [
        "-connections_mapping",
        "-disable_trim",
        "-sack_threshold", "4000",
        "-failures_input", f"../failures_input/{scenario}.txt",
        "-tm", tm,
        "-end", "90000",
        "-seed", str(SEED),
        "-sender_cc_only", "-sender_cc_algo", "mprdma",
        "-topo", TOPO,
        "-linkspeed", "400000",
        "-ecn", str(ECN_MIN), str(ECN_MAX),
        "-q", str(Q),
        "-other_location",
        "-cwnd", str(CWND),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="", help="comma list to restrict arms")
    ap.add_argument("--workloads", default="", help="comma list to restrict workloads")
    ap.add_argument("--scenarios", default="", help="comma list to restrict scenarios")
    ap.add_argument("--quick", action="store_true",
                    help="permutation + fail_one_cable + {ops,reps_b1,reps_b4} only")
    args = ap.parse_args()

    arms = arms_for(N_PATHS)
    workloads = list(WORKLOADS)
    scenarios = list(SCENARIOS)
    if args.quick:
        arms = ["ops", "reps_b1", "reps_b4"]
        workloads = ["permutation"]
        scenarios = ["fail_one_cable"]
    if args.arms:
        arms = [a for a in arms if a in args.arms.split(",")]
    if args.workloads:
        workloads = [w for w in workloads if w in args.workloads.split(",")]
    if args.scenarios:
        scenarios = [s for s in scenarios if s in args.scenarios.split(",")]

    cells = list(itertools.product(workloads, scenarios, arms))
    total = len(cells)
    print(f"fig7: {total} runs  (topo={TOPO_KEY} n_paths={N_PATHS} "
          f"q={Q} ecn={ECN_MIN}/{ECN_MAX} cwnd={CWND})", flush=True)

    fails = 0
    for i, (wl, scen, arm) in enumerate(cells, 1):
        tm = WORKLOADS[wl]
        outfile = RUNS_DIR / "fig7" / wl / scen / arm / "stdout.txt"
        flags = base_flags(tm, scen) + arm_lb_flags(arm, N_PATHS)
        res = run_one(flags, outfile, cwd=DC_DIR)
        emit(i, total, f"{wl}/{scen}/{arm}", res)
        if res["status"].startswith("FAIL"):
            fails += 1

    print(f"\nfig7 done: {fails} failures / {total}", flush=True)


if __name__ == "__main__":
    main()
