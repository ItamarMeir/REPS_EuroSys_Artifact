#!/usr/bin/env python3
"""Control runs for why matched/uniform50 k != over/healthy k (seed 42, B=8, one pass with -log_reps_events, traces kept).
Run inside the build container:  python3 run_controls.py --out /out_k
Cells: native200 (200G fabric + 200G NIC, R=200); healthy400 at R = 250/300/350/390 Gbps."""
import argparse, subprocess, sys, shutil
from pathlib import Path
sys.path.insert(0, "/work")
from run_m4 import flags, DC, TRACE_SRCS

CELLS = {
    "native200_R200": dict(topo="fat_tree_1024_1os_2t_200g_native.topo", linkspeed="200000", R="200"),
    "healthy400_R250": dict(R="250"), "healthy400_R300": dict(R="300"),
    "healthy400_R350": dict(R="350"), "healthy400_R390": dict(R="390"),
    "healthy400_R398": dict(R="398"),
    "native200_R198": dict(topo="fat_tree_1024_1os_2t_200g_native.topo", linkspeed="200000", R="198"),
}

def cmd_for(c, out):
    f = flags("over", "healthy", 8, 42)
    def sub(key, val):
        f[f.index(key) + 1] = val
    p = CELLS[c]
    if "topo" in p: sub("-topo", "topologies/reps/" + p["topo"])
    if "linkspeed" in p: sub("-linkspeed", p["linkspeed"])
    sub("-rate_const_gbps", p["R"])
    tr = f"/tmp/{c}.csv"
    cmd = ["./htsim_uec"] + f + ["-log_reps_events", tr, "-log_reps_events_max", "50000000"]
    for s in TRACE_SRCS: cmd += ["-log_reps_events_src", str(s)]
    return cmd, tr

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/out_k"); ap.add_argument("--cells", nargs="*", default=list(CELLS))
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for c in a.cells:
        cmd, tr = cmd_for(c, out)
        p = subprocess.run(cmd, cwd=DC, capture_output=True, text=True)
        (out / f"{c}.stdout.txt").write_text(p.stdout)
        if p.returncode: print(c, "FAILED", p.stderr[-300:]); continue
        subprocess.run(f"gzip -9 -c {tr} > {out}/{c}.csv.gz && rm {tr}", shell=True, check=True)
        fl = [l for l in p.stdout.splitlines() if l.startswith("Flow") and " finished at " in l]
        print(c, "ok flows", len(fl), flush=True)
