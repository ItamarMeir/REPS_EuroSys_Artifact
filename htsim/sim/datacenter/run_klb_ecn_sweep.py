#!/usr/bin/env python3
"""
Binary-threshold ECN sweep on k=8 fat-tree (128 hosts, 16 core paths).

Sweeps the ECN marking threshold K_ECN (binary: Kmin=Kmax) across multiple
values to expose how sensitive each LB algorithm is to the marking aggressiveness.

Uses 32MB flows so the system has time to reach steady state before flows finish,
which is required for convergence-time measurement.

Each run logs per-tier ECN counts in 100us bins (`-log_ecn_timeseries`),
parsed by parse_klb_fct.py to compute the time at which the aggregate ECN
rate stabilizes near zero.

Usage:
  python3 run_klb_ecn_sweep.py            # full run
  python3 run_klb_ecn_sweep.py --dry-run  # print commands only
"""
import subprocess, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BINARY = "./htsim_uec"
TOPO   = "topologies/reps/fat_tree_128_1os_3t_400g.topo"
PATHS  = 16        # (k/2)^2 = 16 core paths for k=8
QUEUE  = 100       # packets
END    = 90000     # 90 ms in us
LINK   = 400000    # Mbps (400 G)
FLOW_BYTES = 32 * 1024 * 1024   # 32MB - long enough to observe convergence
N_PARALLEL = 8

SEEDS = [42, 43, 44]
# Binary ECN thresholds (Kmin=Kmax). 5 ~= 5% BDP, 15 ~= 15% BDP, 25 ~= 25% BDP.
# Setting Kmin==Kmax makes CompositeQueue use only the strict-> Kmax branch,
# producing hard step-function marking with no probabilistic RED zone.
ECN_VALS = [5, 15, 25]

DRY_RUN = "--dry-run" in sys.argv

BASE = "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn"
def SE(k):
    inc = min(k, PATHS)
    return f"{BASE} -queue_type stateful_ecn -max_incumbents {inc} -idle_timeout_us 6"

# (label, lb_algo, flags, cwnd_pkts, extra)
def experiments():
    # Baselines - REPS at NSCC and REPS at line-rate (no CC)
    yield ("reps_nscc",     "reps", "-sender_cc_only -disable_tor_ecn",     140,   "")
    yield ("reps_linerate", "reps", BASE,                                   10000, "")
    # KLB at K=4 and K=N (=16)
    yield ("klb_k4",   "klb",  BASE,    10000, "-klb_k 4")
    yield ("klb_k16",  "klb",  BASE,    10000, "-klb_k 16")
    # HKLB at K=4 and K=N (=16)
    yield ("hklb_k4",  "hklb", BASE,    10000, "-klb_k 4")
    yield ("hklb_k16", "hklb", BASE,    10000, "-klb_k 16")
    # SKLB at K=4 and K=N (=16)
    yield ("sklb_k4",  "sklb", SE(4),   10000, "-klb_k 4")
    yield ("sklb_k16", "sklb", SE(16),  10000, "-klb_k 16")

OUT_ROOT = "results/ecn_sweep"
os.makedirs(OUT_ROOT, exist_ok=True)
os.makedirs("connection_matrices", exist_ok=True)

def get_tm(seed):
    name = f"perm_128n_128c_32MB_s{seed}.cm"
    path = f"connection_matrices/{name}"
    if not os.path.exists(path):
        result = subprocess.run(
            ["python3", "gen_perm_128.py", str(FLOW_BYTES), str(seed)],
            capture_output=True, text=True
        )
        with open(path, "w") as f:
            f.write(result.stdout)
    return path

# Pre-generate TMs serially (fast)
for s in SEEDS:
    get_tm(s)

def run_one(task):
    label, lb_algo, flags, cwnd, extra, seed, ecn_k, idx, total = task
    tm = get_tm(seed)
    sub = f"ecn{ecn_k}/{label}/seed{seed}"
    out_dir  = f"{OUT_ROOT}/{sub}"
    out_file = f"{out_dir}/stdout.txt"
    os.makedirs(out_dir, exist_ok=True)

    cmd = (f"{BINARY} -sack_threshold 4000 "
           f"-load_balancing_algo {lb_algo} {extra} "
           f"-tm {tm} -topo {TOPO} -paths {PATHS} "
           f"{flags} -enable_qa_gate "
           f"-linkspeed {LINK} -ecn {ecn_k} {ecn_k} "
           f"-q {QUEUE} -cwnd {cwnd} -end {END} -seed {seed} "
           f"-log_ecn_timeseries -ecn_bin_us 100 "
           f"> {out_file} 2>&1")

    if DRY_RUN:
        print(f"[{idx}/{total}] ecn={ecn_k} {label} seed={seed}\n  {cmd}")
        return label, seed, ecn_k, 0

    ret = subprocess.run(cmd, shell=True)
    status = "OK" if ret.returncode == 0 else f"EXIT={ret.returncode}"
    print(f"[{idx}/{total}] ecn={ecn_k} {label} seed={seed} {status}", flush=True)
    return label, seed, ecn_k, ret.returncode

all_exps = list(experiments())
total = len(all_exps) * len(SEEDS) * len(ECN_VALS)
print(f"Total experiments: {total} (parallel={N_PARALLEL})")

tasks = []
idx = 0
for ecn_k in ECN_VALS:
    for label, lb_algo, flags, cwnd, extra in all_exps:
        for seed in SEEDS:
            idx += 1
            tasks.append((label, lb_algo, flags, cwnd, extra, seed, ecn_k, idx, total))

if DRY_RUN:
    for t in tasks:
        run_one(t)
else:
    failures = []
    with ThreadPoolExecutor(max_workers=N_PARALLEL) as pool:
        futs = {pool.submit(run_one, t): t for t in tasks}
        for fut in as_completed(futs):
            label, seed, ecn_k, rc = fut.result()
            if rc != 0:
                failures.append((label, seed, ecn_k, rc))
    if failures:
        print(f"\n{len(failures)} failures:")
        for f in failures:
            print(f"  FAILED: ecn={f[2]} {f[0]} seed={f[1]} rc={f[3]}")
    else:
        print("\nAll done.")
    print("\nResults: python3 parse_klb_fct.py --ecn-sweep")
