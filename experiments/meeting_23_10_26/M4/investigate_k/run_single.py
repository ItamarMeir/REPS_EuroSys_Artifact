#!/usr/bin/env python3
"""Sanity controls with 1-2 flows (seed 42, B=8, 400G fabric): is the shaper/queue behaviour sound when no other host competes?
Run inside container m23-dev:  python3 run_single.py --out /out_s
 one  = flow 0->512 only; pair = 0->512 and 512->0 (host 0's uplink then carries its data AND the ACKs of the reverse flow).
 Each cell also writes -log_queue_stats (max queue per switch queue) next to the event trace."""
import argparse, subprocess, sys
from pathlib import Path
sys.path.insert(0, "/work")
from run_m4 import flags, DC
CM = {"one": "connection_matrices/one_0to512_s16777216.cm", "pair": "connection_matrices/pair_0_512_s16777216.cm"}
def cells():
    for wl in ("one", "pair"):
        for fail, rates in (("healthy", (400, 398)), ("uniform50", (200, 198))):
            for paths in (32, 1):
                for R in rates:
                    yield wl, fail, paths, R
def name(c): return "{}_{}_p{}_R{}".format(*c)
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/out_s"); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for c in cells():
        wl, fail, paths, R = c; n = name(c)
        f = flags("over", fail, 8, 42)
        f[f.index("-tm") + 1] = CM[wl]; f[f.index("-paths") + 1] = str(paths); f[f.index("-rate_const_gbps") + 1] = str(R)
        tr = f"/tmp/{n}.csv"
        cmd = ["./htsim_uec"] + f + ["-log_reps_events", tr, "-log_reps_events_src", "0", "-log_reps_events_src", "512",
                                    "-log_queue_stats", str(out / f"{n}.queues.tsv")]
        p = subprocess.run(cmd, cwd=DC, capture_output=True, text=True)
        (out / f"{n}.stdout.txt").write_text(p.stdout)
        if p.returncode: print(n, "FAILED", p.stderr[-300:], flush=True); continue
        subprocess.run(f"gzip -9 -c {tr} > {out}/{n}.csv.gz && rm {tr}", shell=True, check=True)
        print(n, "ok", flush=True)
