#!/usr/bin/env python3
"""Steady-state queue sampling (-log_tor_queues, ToR->agg uplinks every 1 us) and an 800G-fabric / 400G-NIC causal test.
Tornado, seed 42, B=8, -end 500 us (flows finish ~360 us at R=400). Container m23-dev:  python3 run_queue_ts.py --out /out_t"""
import argparse, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, "/work")
from run_m4 import flags, DC, TRACE_SRCS
CELLS_OLD = [("fab400", 400), ("fab400", 398), ("fab800", 400), ("fab800", 398), ("deg", 200), ("deg", 198), ("allt", 200), ("allt", 198), ("alltq", 200), ("alltqe", 200), ("f200", 200), ("f200", 198)]
ARRIVALS = False
def run(c, out):
    fab, R = c[0], c[1]; seed = c[2] if len(c) > 2 else 42; n = f"{fab}_R{R}_s{seed}"
    f = flags("over", "healthy", 8, seed); f[f.index("-rate_const_gbps") + 1] = str(R); f[f.index("-end") + 1] = "500"
    if fab.startswith("ph2_"):   # per-ToR last-hop: d16 = only ToR16's ToR->host links at 50% (the receivers of ToR0's flows), d0 = only ToR0's (where ToR0's ACKs and ToR16's data
        # arrive), dqe = all ToR->host links at 50% with queue and ECN thresholds doubled (fewer marks/trims on the degraded uplinks)
        o = fab[4:]; df = {"d16": "ph2_d16", "d0": "ph2_d0", "dqe": "ph_d"}[o]
        f += ["-degrade_links_file", f"/work/degrade_{df}.txt"]; f[f.index("-end") + 1] = "900"
        if o == "dqe": f[f.index("-q") + 1] = "202"; i = f.index("-ecn"); f[i + 1] = "50"; f[i + 2] = "152"
    if fab.startswith("ph_"):   # per-hop intervention on top of 'allt' (all ToR uplinks at 50%, R=200): h = host links at 200G (-linkspeed 200000),
        # a = all agg->ToR links at 50%, d = all ToR->host links at 50% (per-hop-degrade); 'none' = allt itself
        o = fab[3:]; df = {"none": "alltor50", "h": "alltor50", "a": "ph_a", "d": "ph_d", "ad": "ph_ad", "had": "ph_ad"}[o]
        f += ["-degrade_links_file", f"/work/degrade_{df}.txt"]; f[f.index("-end") + 1] = "900"
        if "h" in o: f[f.index("-linkspeed") + 1] = "200000"
    if fab == "nat":   # native 200G fabric (all links and NICs 200G)
        f[f.index("-topo") + 1] = "topologies/reps/fat_tree_1024_1os_2t_200g_native.topo"; f[f.index("-linkspeed") + 1] = "200000"; f[f.index("-end") + 1] = "900"
    if fab == "n200up2":   # native 200G fabric (all links 200G, NIC 200G) but every ToR uplink sped up to 400G (ratio 2.0): uplinks at rho 0.5, host links / agg->ToR / ToR->host at rho 1
        f[f.index("-topo") + 1] = "topologies/reps/fat_tree_1024_1os_2t_200g_native.topo"; f[f.index("-linkspeed") + 1] = "200000"
        f += ["-degrade_links_file", "/work/degrade_alltor200pct.txt"]; f[f.index("-end") + 1] = "900"
    if fab == "f200":   # fabric 200G in BOTH directions (ToR<->agg), host links 400G, R=200: uplinks and agg->ToR downlinks at rho 1, host links/downlinks at 0.5
        f[f.index("-topo") + 1] = "topologies/reps/fat_tree_1024_1os_2t_fabric200_nic400.topo"; f[f.index("-end") + 1] = "900"
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
    if ARRIVALS:   # data arrivals at the receivers of ToR0's flows (flow id = source host + 1)
        cmd += ["-log_sink_arrivals", str(out / f"{n}.arr.csv")]
        for fid in range(1, 9): cmd += ["-log_sink_arrivals_flow", str(fid)]
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
