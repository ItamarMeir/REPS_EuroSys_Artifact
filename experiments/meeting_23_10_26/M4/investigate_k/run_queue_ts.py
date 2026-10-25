#!/usr/bin/env python3
"""Steady-state queue sampling (-log_tor_queues, ToR->agg uplinks every 1 us) and an 800G-fabric / 400G-NIC causal test.
Tornado, seed 42, B=8, -end 500 us (flows finish ~360 us at R=400). Container m23-dev:  python3 run_queue_ts.py --out /out_t"""
import argparse, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, "/work")
from run_m4 import flags, DC, TRACE_SRCS
CELLS = [("fab400", 400), ("fab400", 398), ("fab800", 400), ("fab800", 398), ("deg", 200), ("deg", 198), ("allt", 200), ("allt", 198), ("alltq", 200), ("alltqe", 200)]
def run(c, out):
    fab, R = c; n = f"{fab}_R{R}_s42"
    f = flags("over", "healthy", 8, 42); f[f.index("-rate_const_gbps") + 1] = str(R); f[f.index("-end") + 1] = "500"
    if fab == "alltqe":  # allt with BOTH queue and ECN thresholds doubled (-q 202 -ecn 50 152): degraded uplinks then hold 101 packets and mark from 25 packets, as native 200G does
        f += ["-degrade_links_file", "/work/degrade_alltor50.txt"]; f[f.index("-end") + 1] = "900"; f[f.index("-q") + 1] = "202"; i = f.index("-ecn"); f[i + 1] = "50"; f[i + 2] = "152"
    if fab == "alltq":   # allt with 2x queue size: degraded uplinks get 101 packets and ECN 25/76 packets like native 200G; ratio-1 queues get 202 (idle at rho 0.5)
        f += ["-degrade_links_file", "/work/degrade_alltor50.txt"]; f[f.index("-end") + 1] = "900"; f[f.index("-q") + 1] = "202"
    if fab == "allt":
        f += ["-degrade_links_file", "/work/degrade_alltor50.txt"]; f[f.index("-end") + 1] = "900"
    if fab == "deg": f += ["-degrade_links_file", "/work/degrade_uniform50.txt"]
    if fab == "fab800": f[f.index("-topo") + 1] = "topologies/reps/fat_tree_1024_1os_2t_fabric800_nic400.topo"
    tr = f"/tmp/t_{n}.csv"
    cmd = ["./htsim_uec"] + f + ["-log_reps_events", tr, "-log_reps_events_max", "50000000", "-log_queue_stats", str(out / f"{n}.queues.tsv"),
                                "-log_tor_queues", str(out / f"{n}.torq.csv")]
    for s in TRACE_SRCS: cmd += ["-log_reps_events_src", str(s)]
    p = subprocess.run(cmd, cwd=DC, capture_output=True, text=True)
    (out / f"{n}.stdout.txt").write_text(p.stdout)
    if p.returncode: return n + " FAILED " + p.stderr[-200:]
    subprocess.run(f"gzip -9 -c {tr} > {out}/{n}.csv.gz && rm {tr}", shell=True, check=True)
    return n + " ok"
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/out_t"); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(2) as ex:
        for r in ex.map(lambda c: run(c, out), CELLS): print(r, flush=True)
