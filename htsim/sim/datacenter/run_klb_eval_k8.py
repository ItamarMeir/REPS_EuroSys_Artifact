#!/usr/bin/env python3
"""
K-LB Evaluation on k=8 fat-tree (128 hosts, 16 core paths).

Larger topology than k=6 (9 paths) provides:
  - More meaningful K range (K up to 16 before saturation)
  - Lower EV collision probability pre-dedup
  - Better statistical coverage across paths

Usage:
  python3 run_klb_eval_k8.py            # full run
  python3 run_klb_eval_k8.py --dry-run  # print commands only
"""
import subprocess, os, sys

BINARY = "./htsim_uec"
TOPO   = "topologies/reps/fat_tree_128_1os_3t_400g.topo"
PATHS  = 16       # (k/2)^2 = 16 core switches → 16 distinct paths for k=8
QUEUE  = 100      # packets
ECN_LO = 25
ECN_HI = 75
END    = 90000    # 90ms in µs
LINK   = 400000   # Mbps (400G)

# Per-link sub-flow load estimate for k=8 with permutation TM:
#   ToR uplink: 4 hosts × K EVs / 4 uplinks = K sub-flows
#   Agg uplink: same reasoning = K sub-flows
#   Core link:  128 flows × K EVs / 16 paths / 2 (two core links per path) ≈ 4K sub-flows...
# Conservative max_incumbents = 2×K or 8, whichever larger.
MAX_INC = 8       # safe for K up to 8; covers 2× expected ToR sub-flow load

SEEDS = [42, 43, 44, 45, 46]

DRY_RUN = "--dry-run" in sys.argv

EXPERIMENTS = [
    ("reps_nscc",     "reps", "-sender_cc_only -disable_tor_ecn",                           140,   ""),
    ("reps_linerate", "reps", "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn",  10000, ""),
    ("klb_k1",        "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn",  10000, "-klb_k 1"),
    ("klb_k2",        "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn",  10000, "-klb_k 2"),
    ("klb_k4",        "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn",  10000, "-klb_k 4"),
    ("klb_k8",        "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn",  10000, "-klb_k 8"),
    ("klb_k16",       "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn",  10000, "-klb_k 16"),
    ("klb_k32",       "klb",  "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn",  10000, "-klb_k 32"),
    # SKLB: deterministic replacement + StatefulECNQueue incumbent advantage
    # idle_timeout_us=6 ≈ 1 RTT (6µs one-way × 2 paths to core = 6µs) so ghost entries expire
    # before replacement EV arrives at switch.
    (f"sklb_k2",      "sklb", f"-sender_cc_only -sender_cc_algo constant -disable_tor_ecn -queue_type stateful_ecn -max_incumbents {MAX_INC} -idle_timeout_us 6", 10000, "-klb_k 2"),
    (f"sklb_k4",      "sklb", f"-sender_cc_only -sender_cc_algo constant -disable_tor_ecn -queue_type stateful_ecn -max_incumbents {MAX_INC} -idle_timeout_us 6", 10000, "-klb_k 4"),
    (f"sklb_k8",      "sklb", f"-sender_cc_only -sender_cc_algo constant -disable_tor_ecn -queue_type stateful_ecn -max_incumbents {MAX_INC} -idle_timeout_us 6", 10000, "-klb_k 8"),
    # Hybrid-KLB: discovery (oblivious) until K clean ACKs received, then round-robin + KLB replacement
    ("hklb_k2",       "hklb", "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn", 10000, "-klb_k 2"),
    ("hklb_k4",       "hklb", "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn", 10000, "-klb_k 4"),
    ("hklb_k8",       "hklb", "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn", 10000, "-klb_k 8"),
    # Hybrid-KLB + StatefulECN: switch definitively rejects non-incumbents during discovery
    (f"hklb_se_k4",   "hklb", f"-sender_cc_only -sender_cc_algo constant -disable_tor_ecn -queue_type stateful_ecn -max_incumbents {MAX_INC} -idle_timeout_us 6", 10000, "-klb_k 4"),
    (f"hklb_se_k8",   "hklb", f"-sender_cc_only -sender_cc_algo constant -disable_tor_ecn -queue_type stateful_ecn -max_incumbents {MAX_INC} -idle_timeout_us 6", 10000, "-klb_k 8"),
]

os.makedirs("connection_matrices", exist_ok=True)
os.makedirs("results/klb_k8", exist_ok=True)

def get_tm(seed):
    path = f"connection_matrices/perm_128n_128c_8MB_s{seed}.cm"
    if not os.path.exists(path):
        result = subprocess.run(
            ["python3", "gen_perm_128.py", "8388608", str(seed)],
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
        out_dir  = f"results/klb_k8/{label}/seed{seed}"
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
    print("\nAll done. Run: python3 parse_klb_fct.py --dir results/klb_k8")
