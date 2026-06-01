#!/usr/bin/env python3
"""
Algorithm sweep: KLB / HKLB / SKLB × K={4,8,16,32,64,128} × 10 seeds
on k=8 fat-tree (128 hosts, 16 core paths).

Runs experiments in parallel (up to N_PARALLEL at once).

Usage:
  python3 run_algo_sweep_k8.py            # full run
  python3 run_algo_sweep_k8.py --dry-run  # print commands only
"""
import subprocess, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BINARY   = "./htsim_uec"
TOPO     = "topologies/reps/fat_tree_128_1os_3t_400g.topo"
N_PATHS  = 16       # (k/2)^2 = 16 core switches
QUEUE    = 100      # packets
ECN_LO   = 25
ECN_HI   = 75
END      = 90000    # 90 ms in µs
LINK     = 400000   # Mbps (400 G)
N_PARALLEL = 8      # parallel workers (match nproc)

SEEDS  = list(range(42, 52))   # 10 seeds: 42..51
K_VALS = [4, 8, 16, 32, 64, 128]

DRY_RUN = "--dry-run" in sys.argv

# For SKLB: max_incumbents = min(K, N_PATHS) to cover expected sub-flow load per link.
# With permutation TM, per-link load ≈ K sub-flows (capped at N_PATHS distinct EVs).
def max_inc(k):
    return min(k, N_PATHS)

BASE_FLAGS = "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn"
SE_FLAGS   = lambda k: (f"{BASE_FLAGS} -queue_type stateful_ecn "
                        f"-max_incumbents {max_inc(k)} -idle_timeout_us 6")

# (label, lb_algo, flags, cwnd_pkts, extra)
def experiments():
    # Baselines
    yield ("reps_nscc",     "reps", "-sender_cc_only -disable_tor_ecn",  140,   "")
    yield ("reps_linerate", "reps", BASE_FLAGS,                          10000, "")
    # Sweep
    for k in K_VALS:
        yield (f"klb_k{k}",  "klb",  BASE_FLAGS,  10000, f"-klb_k {k}")
        yield (f"hklb_k{k}", "hklb", BASE_FLAGS,  10000, f"-klb_k {k}")
        yield (f"sklb_k{k}", "sklb", SE_FLAGS(k), 10000, f"-klb_k {k}")

os.makedirs("connection_matrices", exist_ok=True)
os.makedirs("results/sweep_k8", exist_ok=True)

def get_tm(seed):
    path = f"connection_matrices/perm_128n_128c_8MB_s{seed}.cm"
    if not os.path.exists(path):
        result = subprocess.run(
            ["python3", "gen_perm_128.py", "8388608", str(seed)],
            capture_output=True, text=True
        )
        with open(path, "w") as f:
            f.write(result.stdout)
    return path

# Pre-generate all traffic matrices (serial, fast)
for seed in SEEDS:
    get_tm(seed)

def run_one(task):
    label, lb_algo, flags, cwnd, extra, seed, idx, total = task
    tm       = get_tm(seed)
    out_dir  = f"results/sweep_k8/{label}/seed{seed}"
    out_file = f"{out_dir}/stdout.txt"
    os.makedirs(out_dir, exist_ok=True)

    cmd = (f"{BINARY} -sack_threshold 4000 "
           f"-load_balancing_algo {lb_algo} {extra} "
           f"-tm {tm} -topo {TOPO} -paths {N_PATHS} "
           f"{flags} -enable_qa_gate "
           f"-linkspeed {LINK} -ecn {ECN_LO} {ECN_HI} "
           f"-q {QUEUE} -cwnd {cwnd} -end {END} -seed {seed} "
           f"> {out_file} 2>&1")

    if DRY_RUN:
        print(f"[{idx}/{total}] {label} seed={seed}\n  {cmd}")
        return label, seed, 0

    ret = subprocess.run(cmd, shell=True)
    status = "OK" if ret.returncode == 0 else f"EXIT={ret.returncode}"
    print(f"[{idx}/{total}] {label} seed={seed} {status}", flush=True)
    return label, seed, ret.returncode

# Build task list
tasks = []
all_exps = list(experiments())
total = len(all_exps) * len(SEEDS)
idx = 0
for label, lb_algo, flags, cwnd, extra in all_exps:
    for seed in SEEDS:
        idx += 1
        tasks.append((label, lb_algo, flags, cwnd, extra, seed, idx, total))

print(f"Total experiments: {total}  (parallel={N_PARALLEL})")

if DRY_RUN:
    for t in tasks:
        run_one(t)
else:
    failures = []
    with ThreadPoolExecutor(max_workers=N_PARALLEL) as pool:
        futs = {pool.submit(run_one, t): t for t in tasks}
        for fut in as_completed(futs):
            label, seed, rc = fut.result()
            if rc != 0:
                failures.append((label, seed, rc))

    print(f"\nDone. {len(failures)} failures." if failures else "\nAll done.")
    if failures:
        for f in failures:
            print(f"  FAILED: {f[0]} seed={f[1]} rc={f[2]}")

    print("\nResults: python3 parse_sweep_k8.py")
