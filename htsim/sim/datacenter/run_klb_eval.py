#!/usr/bin/env python3
"""
K-LB Evaluation: compare K-LB vs REPS+NSCC and REPS+line-rate
on a k=6 fat-tree (54 hosts, 9 core paths).

Runs each experiment configuration across N_SEEDS distinct random permutation
matrices (and simulator seeds) then aggregates results in parse_klb_fct.py.

Usage:
  python3 run_klb_eval.py            # full run
  python3 run_klb_eval.py --dry-run  # print commands only
"""
import subprocess, os, sys

BINARY = "./htsim_uec"
TOPO   = "topologies/reps/fat_tree_54_1os_3t_400g.topo"
PATHS  = 9        # 9 core switches in k=6 fat-tree (only 9 distinct paths)
QUEUE  = 100      # packets
ECN_LO = 25
ECN_HI = 75
END    = 90000    # 90ms in µs
LINK   = 400000   # Mbps (400G)

# Seeds used for both permutation matrix generation and simulator RNG.
# 5 independent draws gives reasonable variance estimates for 54-flow runs.
SEEDS = [42, 43, 44, 45, 46]

DRY_RUN = "--dry-run" in sys.argv

# Experiments: (label, lb_algo, cc_flags, cwnd, extra_flags)
# -disable_tor_ecn: ECN only on core/agg, not ToR downlinks (Leaf Exception).
# Note: K>9 EVs still work but collapse onto the 9 physical paths; included
# to show the saturation effect.
EXPERIMENTS = [
    ("reps_nscc",    "reps", "-sender_cc_only -disable_tor_ecn",                          140,   ""),
    ("reps_linerate","reps", "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn", 10000, ""),
    ("klb_k1",       "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn", 10000, "-klb_k 1"),
    ("klb_k2",       "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn", 10000, "-klb_k 2"),
    ("klb_k4",       "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn", 10000, "-klb_k 4"),
    ("klb_k8",       "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn", 10000, "-klb_k 8"),
    ("klb_k16",      "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn", 10000, "-klb_k 16"),
    ("klb_k32",      "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn", 10000, "-klb_k 32"),
    # SKLB: deterministic 100% replacement + StatefulECNQueue incumbent advantage
    # idle_timeout=6us ≈ 1 RTT so abandoned EV ghost-entries expire before replacement arrives
    ("sklb_k2",      "sklb", "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn -queue_type stateful_ecn -max_incumbents 6 -idle_timeout_us 6", 10000, "-klb_k 2"),
    ("sklb_k4",      "sklb", "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn -queue_type stateful_ecn -max_incumbents 6 -idle_timeout_us 6", 10000, "-klb_k 4"),
    ("sklb_k8",      "sklb", "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn -queue_type stateful_ecn -max_incumbents 6 -idle_timeout_us 6", 10000, "-klb_k 8"),
]

os.makedirs("connection_matrices", exist_ok=True)
os.makedirs("results/klb", exist_ok=True)

def get_tm(seed):
    path = f"connection_matrices/perm_54n_54c_8MB_s{seed}.cm"
    if not os.path.exists(path):
        result = subprocess.run(
            ["python3", "gen_perm_54.py", "8388608", str(seed)],
            capture_output=True, text=True
        )
        with open(path, "w") as f:
            f.write(result.stdout)
        print(f"  Generated {path}")
    return path

total = len(EXPERIMENTS) * len(SEEDS)
done = 0
for label, lb_algo, cc_flags, cwnd, extra in EXPERIMENTS:
    for seed in SEEDS:
        tm = get_tm(seed)
        out_dir  = f"results/klb/{label}/seed{seed}"
        out_file = f"{out_dir}/stdout.txt"
        os.makedirs(out_dir, exist_ok=True)

        cmd = (
            f"{BINARY} "
            f"-sack_threshold 4000 "
            f"-load_balancing_algo {lb_algo} "
            f"{extra} "
            f"-tm {tm} "
            f"-topo {TOPO} "
            f"-paths {PATHS} "
            f"{cc_flags} "
            f"-enable_qa_gate "
            f"-linkspeed {LINK} "
            f"-ecn {ECN_LO} {ECN_HI} "
            f"-q {QUEUE} "
            f"-cwnd {cwnd} "
            f"-end {END} "
            f"-seed {seed} "
            f"> {out_file} 2>&1"
        )
        done += 1
        print(f"[{done}/{total}] {label} seed={seed}", end=" ", flush=True)
        if DRY_RUN:
            print(f"\n  {cmd}")
            continue
        ret = subprocess.run(cmd, shell=True)
        print("OK" if ret.returncode == 0 else f"EXIT={ret.returncode}")

if not DRY_RUN:
    print("\nAll done. Run: python3 parse_klb_fct.py")
