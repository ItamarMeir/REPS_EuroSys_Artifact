#!/usr/bin/env python3
"""
Binary-threshold ECN sweep on k=10 2-TIER leaf-spine (250 hosts, 25 spine paths).

Same 18 algorithms, K values, seeds, and flow size as run_klb_ecn_sweep_k10.py
(3-tier), but with a 2-tier topology where each EV maps directly to one spine
(no second-level hashing). Used to test whether the FCT gap of K-LB family vs
REPS is amplified by multi-hop hashing in 3-tier.

BDP @ 400 Gbps, 8 us cross-host RTT (4 hops) ~= 400 KB ~= 96 packets.
ECN thresholds: 1 / 5 / 10 packets => 1% / 5% / 10% BDP.

Usage:
  python3 run_klb_ecn_sweep_k10_2t.py             # full run
  python3 run_klb_ecn_sweep_k10_2t.py --sklb-only # only sklb_* / hklb_se_*
  python3 run_klb_ecn_sweep_k10_2t.py --skip-existing
  python3 run_klb_ecn_sweep_k10_2t.py --dry-run
"""
import subprocess, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BINARY = "./htsim_uec"
TOPO   = "topologies/reps/fat_tree_250_1os_2t_400g.topo"
PATHS  = 25
QUEUE  = 100
END    = 90000
LINK   = 400000
FLOW_BYTES = 32 * 1024 * 1024
N_PARALLEL = 8

SEEDS    = [42, 43, 44, 45, 46]
K_VALS   = [4, 8, 16, 32]
# BDP @ 4-hop 8us RTT, 400 Gbps, 4150 B/pkt ~= 96 pkts.
# 1, 5, 10 pkts ~= 1% / 5% / 10% BDP.
ECN_VALS = [1, 5, 10]

DRY_RUN       = "--dry-run"       in sys.argv
SKLB_ONLY     = "--sklb-only"     in sys.argv
SKIP_EXISTING = "--skip-existing" in sys.argv

BASE = "-sender_cc_only -sender_cc_algo constant -disable_tor_ecn"
def SE(k):
    inc = min(k, PATHS)
    return f"{BASE} -queue_type stateful_ecn -max_incumbents {inc} -idle_timeout_us 6"

def experiments():
    if not SKLB_ONLY:
        yield ("reps_nscc",     "reps", "-sender_cc_only -disable_tor_ecn",     140,   "")
        yield ("reps_linerate", "reps", BASE,                                   10000, "")
    for k in K_VALS:
        if not SKLB_ONLY:
            yield (f"klb_k{k}",  "klb",  BASE,   10000, f"-klb_k {k}")
            yield (f"hklb_k{k}", "hklb", BASE,   10000, f"-klb_k {k}")
        yield (f"sklb_k{k}",    "sklb", SE(k),  10000, f"-klb_k {k}")
        yield (f"hklb_se_k{k}", "hklb", SE(k),  10000, f"-klb_k {k}")

OUT_ROOT = "results/ecn_sweep_k10_2t"
os.makedirs(OUT_ROOT, exist_ok=True)
os.makedirs("connection_matrices", exist_ok=True)

def get_tm(seed):
    name = f"perm_250n_250c_32MB_s{seed}.cm"
    path = f"connection_matrices/{name}"
    if not os.path.exists(path):
        result = subprocess.run(
            ["python3", "gen_perm_250.py", str(FLOW_BYTES), str(seed)],
            capture_output=True, text=True
        )
        with open(path, "w") as f:
            f.write(result.stdout)
    return path

for s in SEEDS:
    get_tm(s)

def run_one(task):
    label, lb_algo, flags, cwnd, extra, seed, ecn_k, idx, total = task
    tm = get_tm(seed)
    sub = f"ecn{ecn_k}/{label}/seed{seed}"
    out_dir  = f"{OUT_ROOT}/{sub}"
    out_file = f"{out_dir}/stdout.txt"
    os.makedirs(out_dir, exist_ok=True)
    if SKIP_EXISTING and os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
        print(f"[{idx}/{total}] ecn={ecn_k} {label} seed={seed} SKIP (exists)", flush=True)
        return label, seed, ecn_k, 0

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
print(f"Total experiments: {total} (parallel={N_PARALLEL})  topo=2-tier")

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
    print("\nResults: python3 parse_klb_fct.py --ecn-sweep --dir results/ecn_sweep_k10_2t --ecn-only 1,5,10")
