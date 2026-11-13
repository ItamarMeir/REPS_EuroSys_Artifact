#!/usr/bin/env python3
"""Run in the container (next to run_t3.py/configs.json): B=128 cell with the existing -log_tor_queues sampler (1 us), filtered on the fly to ToR0 rows
through a FIFO so the 1024-host file stays small. usage: python3 tor0_queues.py <out_dir> <seed> cfg [cfg ...]"""
import os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
import run_t3 as r
out, seed, cfgs = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
os.makedirs(out, exist_ok=True)
def go(name):
    f = r.flags(r.CFGS[name], 128, seed); r.set_flag(f, "-end", 1500)
    fifo = f"/tmp/fifo_{name}_{seed}"; os.path.exists(fifo) and os.unlink(fifo); os.mkfifo(fifo)
    dst = f"{out}/{name}_B128_s{seed}.tor0q.csv"
    aw = subprocess.Popen(["awk", "-F,", "NR==1||$2==0", fifo], stdout=open(dst, "w"))
    t0 = time.time()
    p = subprocess.run(["./htsim_uec"] + f + ["-log_tor_queues", fifo], cwd=r.m4.DC, capture_output=True, text=True)
    aw.wait(); os.unlink(fifo)
    fl = [l for l in p.stdout.splitlines() if "finished at" in l]
    open(f"{out}/{name}_B128_s{seed}.stdout.txt", "w").write(p.stdout)
    print(name, "rc", p.returncode, "secs", int(time.time() - t0), "flows", len(fl), "rows", sum(1 for _ in open(dst)), flush=True)
with ThreadPoolExecutor(6) as ex: list(ex.map(go, cfgs))
