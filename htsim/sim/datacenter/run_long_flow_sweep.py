#!/usr/bin/env python3
"""
Long-flow sweep: tests whether KLB/HKLB convergence-tax cost amortizes for large flows.

Algorithms: REPS+NSCC, REPS+linerate, KLB K=4/8, HKLB K=4/8
Flow sizes:  8 MB, 32 MB, 128 MB
Seeds:       5 (42..46)
Topology:    k=8 fat-tree (128 hosts, 16 core paths)

Usage:
  python3 run_long_flow_sweep.py            # full run
  python3 run_long_flow_sweep.py --dry-run  # print commands only
"""
import subprocess, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BINARY = "./htsim_uec"
TOPO   = "topologies/reps/fat_tree_128_1os_3t_400g.topo"
N_PATHS = 16
QUEUE  = 100
ECN_LO = 25
ECN_HI = 75
END    = 90000      # 90 ms covers 128 MB flows (~4 ms each)
LINK   = 400000
N_PARALLEL = 8  # may be overridden via --parallel=N

SEEDS  = list(range(42, 47))                    # 5 seeds
ALL_SIZES = {"8MB": 8388608, "32MB": 33554432, "128MB": 134217728}

DRY = "--dry-run" in sys.argv
TAG = next((a for a in sys.argv if a.startswith("--tag=")), "--tag=baseline").split("=", 1)[1]
SIZES_FILTER = next((a for a in sys.argv if a.startswith("--sizes=")), None)
if SIZES_FILTER:
    wanted = SIZES_FILTER.split("=", 1)[1].split(",")
    SIZES = [ALL_SIZES[s] for s in wanted]
else:
    SIZES = list(ALL_SIZES.values())
SIZE_LABEL = {v: k for k, v in ALL_SIZES.items()}

ENABLE_FIXES = "--enable-fixes" in sys.argv
_parallel_arg = next((a for a in sys.argv if a.startswith("--parallel=")), None)
if _parallel_arg:
    N_PARALLEL = int(_parallel_arg.split("=", 1)[1])

BASE_FLAGS = "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn"

def experiments():
    yield ("reps_nscc",     "reps", "-sender_cc_only -disable_tor_ecn", 140,   "")
    yield ("reps_linerate", "reps", BASE_FLAGS,                          10000, "")
    for k in (4, 8):
        yield (f"klb_k{k}",  "klb",  BASE_FLAGS, 10000, f"-klb_k {k}")
        yield (f"hklb_k{k}", "hklb", BASE_FLAGS, 10000, f"-klb_k {k}")

os.makedirs("connection_matrices", exist_ok=True)
results_root = f"results/long_flow/{TAG}"
os.makedirs(results_root, exist_ok=True)

def get_tm(size_bytes, seed):
    label = SIZE_LABEL[size_bytes]
    path = f"connection_matrices/perm_128n_128c_{label}_s{seed}.cm"
    if not os.path.exists(path):
        result = subprocess.run(
            ["python3", "gen_perm_128.py", str(size_bytes), str(seed)],
            capture_output=True, text=True
        )
        with open(path, "w") as f:
            f.write(result.stdout)
    return path

# Pre-generate TMs serially (fast)
for size in SIZES:
    for seed in SEEDS:
        get_tm(size, seed)

def run_one(task):
    label, lb_algo, flags, cwnd, extra, size, seed, idx, total = task
    size_label = SIZE_LABEL[size]
    tm       = get_tm(size, seed)
    out_dir  = f"{results_root}/{size_label}/{label}/seed{seed}"
    out_file = f"{out_dir}/stdout.txt"
    os.makedirs(out_dir, exist_ok=True)

    fix_flag = " -klb_enable_fixes" if ENABLE_FIXES and lb_algo in ("klb", "sklb", "hklb") else ""
    cmd = (f"{BINARY} -sack_threshold 4000 "
           f"-load_balancing_algo {lb_algo} {extra}{fix_flag} "
           f"-tm {tm} -topo {TOPO} -paths {N_PATHS} "
           f"{flags} -enable_qa_gate "
           f"-linkspeed {LINK} -ecn {ECN_LO} {ECN_HI} "
           f"-q {QUEUE} -cwnd {cwnd} -end {END} -seed {seed} "
           f"> {out_file} 2>&1")

    if DRY:
        print(f"[{idx}/{total}] {label} {size_label} seed={seed}\n  {cmd}")
        return label, size_label, seed, 0

    ret = subprocess.run(cmd, shell=True)
    status = "OK" if ret.returncode == 0 else f"EXIT={ret.returncode}"
    print(f"[{idx}/{total}] {label} {size_label} seed={seed} {status}", flush=True)
    return label, size_label, seed, ret.returncode

all_exps = list(experiments())
tasks = []
total = len(all_exps) * len(SEEDS) * len(SIZES)
idx = 0
# Order: small sizes first (fast) so any early failures are noticed quickly.
for size in SIZES:
    for label, lb_algo, flags, cwnd, extra in all_exps:
        for seed in SEEDS:
            idx += 1
            tasks.append((label, lb_algo, flags, cwnd, extra, size, seed, idx, total))

print(f"Tag: {TAG}  Total runs: {total}  (parallel={N_PARALLEL})")

if DRY:
    for t in tasks:
        run_one(t)
else:
    failures = []
    with ThreadPoolExecutor(max_workers=N_PARALLEL) as pool:
        futs = {pool.submit(run_one, t): t for t in tasks}
        for fut in as_completed(futs):
            label, sz, seed, rc = fut.result()
            if rc != 0:
                failures.append((label, sz, seed, rc))

    print(f"\nDone. {len(failures)} failures." if failures else "\nAll done.")
    for f in failures:
        print(f"  FAILED: {f[0]} {f[1]} seed={f[2]} rc={f[3]}")
    print(f"\nResults: python3 parse_long_flow.py --tag {TAG}")
