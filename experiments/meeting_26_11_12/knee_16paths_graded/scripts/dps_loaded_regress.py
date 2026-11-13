#!/usr/bin/env python3
"""Flag-absent regression on LOADED cells (512 hosts, 2048 flows, lat 250, B 8, seed 42): baseline binary vs new binary, REPS cell and god cell.
Compared: the flow-finish lines, the full -log_reps_events trace of the 64 traced flows, and the -log_queue_stats file (all analyses read these). Run in the container."""
import subprocess, sys, tempfile, hashlib
sys.path.insert(0, "/kneework16")
import run_knee16 as rk
r = rk.r; DC = r.m4.DC
OLD, NEW = "/workspace/.baseline/htsim_uec.pre-dps", "/workspace/htsim/sim/datacenter/htsim_uec"
ok = True
def go(binary, name):
    f = r.flags(rk.CFGS[name], 8, 42) + list(rk.CFGS[name].get("extra", []))
    tr = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name; qs = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, dir="/tmp").name
    p = subprocess.run([binary] + f + ["-log_reps_events", tr, "-log_reps_events_max", "50000000", "-log_queue_stats", qs], cwd=DC, capture_output=True, text=True)
    h = lambda path: hashlib.md5(open(path, "rb").read()).hexdigest()
    return [l for l in p.stdout.splitlines() if "finished at" in l], h(tr), h(qs), p.returncode
for name in ("h512_p16g_msgNh_lat250", "h512_p16g_msgNhG_lat250"):
    a, b = go(OLD, name), go(NEW, name)
    same = a == b and len(a[0]) == 2048 and a[3] == 0
    ok &= same
    print(("PASS  " if same else "FAIL  ") + f"{name}: {len(a[0])} flow-finish lines, trace md5 {a[1][:8]}/{b[1][:8]}, queue-stats md5 {a[2][:8]}/{b[2][:8]} (old/new)", flush=True)
print("ALL PASS" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
