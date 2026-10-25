#!/usr/bin/env python3
"""Tornado cells (1024 flows) near line rate, with -log_queue_stats (max queue per switch queue) + event traces for ToR0 srcs 0-7, several seeds.
Run in container m23-dev:  python3 run_tornado_q.py --out /out_q [--workers 4]"""
import argparse, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, "/work")
from run_m4 import flags, DC, TRACE_SRCS
CELLS = [("healthy", 400, s) for s in (42, 43, 44)] + [("healthy", 398, s) for s in (42, 43, 44)] + [("uniform50", 200, 42), ("uniform50", 198, 42)]
def run(c, out):
    fail, R, seed = c; n = f"{fail}_R{R}_s{seed}"
    f = flags("over", fail, 8, seed); f[f.index("-rate_const_gbps") + 1] = str(R)
    tr = f"/tmp/q_{n}.csv"
    cmd = ["./htsim_uec"] + f + ["-log_reps_events", tr, "-log_reps_events_max", "50000000", "-log_queue_stats", str(out / f"{n}.queues.tsv")]
    for s in TRACE_SRCS: cmd += ["-log_reps_events_src", str(s)]
    p = subprocess.run(cmd, cwd=DC, capture_output=True, text=True)
    (out / f"{n}.stdout.txt").write_text(p.stdout)
    if p.returncode: return n + " FAILED " + p.stderr[-200:]
    subprocess.run(f"gzip -9 -c {tr} > {out}/{n}.csv.gz && rm {tr}", shell=True, check=True)
    return n + " ok"
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/out_q"); ap.add_argument("--workers", type=int, default=4); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(lambda c: run(c, out), CELLS): print(r, flush=True)
