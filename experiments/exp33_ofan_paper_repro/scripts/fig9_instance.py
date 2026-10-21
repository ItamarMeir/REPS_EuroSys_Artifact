#!/usr/bin/env python3
"""Fig 9 instance generator: random link failures + permutation workload + rho_max.

Ofan paper (arXiv 2610.07230) §6.2: each edge-aggregation and aggregation-core link is dropped with
probability p; every host then paces at rho_max, "the highest rate at which all flows could send if traffic
were balanced perfectly across all valid shortest paths". We take "balanced perfectly" as the fluid split in
which every valid shortest path of a flow carries an equal share (the split that path-count-weighted Ofan
realises), so rho_max = min(1, 1 / max directed-link load) with load measured in units of host line rate.

Topology: 3-tier fat-tree (k=12 default: 12 pods, 6 ToR + 6 Agg per pod, 6 hosts per ToR, 36 cores; Agg of
position a uplinks to cores l*A+a, core c reaches the Agg of position c%A of every pod -- the same indexing as
fat_tree_topology.cpp / fat_tree_switch.cpp rc_agg_reaches).

Usage: fig9_instance.py <outdir> <p_percent> <seed> [--size BYTES] [--pods 12] [--apod 6] [--hpt 6]
Writes <outdir>/fail.txt ("C agg core" / "E tor agg" per cut cable), <outdir>/wl.cm, <outdir>/inst.json
(rho_max, ideal CCT increase, failed-link counts, predicted per-link loads). Instances in which some flow has no
valid shortest path are rejected and re-drawn (seed advances); the json records the attempt count.
"""
import argparse, json, os, random, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument("outdir"); ap.add_argument("p_percent", type=float); ap.add_argument("seed", type=int)
ap.add_argument("--size", type=int, default=1048576)
ap.add_argument("--pods", type=int, default=12); ap.add_argument("--apod", type=int, default=6)
ap.add_argument("--hpt", type=int, default=6)
a = ap.parse_args()
P, A, HPT = a.pods, a.apod, a.hpt
TPP = A                      # ToRs per pod = Aggs per pod (k/2)
UPL = A                      # core uplinks per Agg
NTOR = P * TPP; NAGG = P * A; NCORE = A * UPL; NH = NTOR * HPT; HPP = TPP * HPT
here = os.path.dirname(os.path.abspath(__file__))
gen = os.path.join(here, "..", "..", "exp32_ofan", "scripts", "gen_derangement.py")
os.makedirs(a.outdir, exist_ok=True)


def draw(seed):
    rng = random.Random(seed * 1000003 + int(a.p_percent * 1000))
    p = a.p_percent / 100.0
    E = {(t, g) for t in range(NTOR) for g in range((t // TPP) * A, (t // TPP) * A + A) if rng.random() < p}
    C = {(g, c) for g in range(NAGG) for c in range(g % A, NCORE, A) if rng.random() < p}
    return E, C


def evaluate(E, C, flows):
    """returns (loads dict, ok). Link keys: ('Eu',tor,agg) ('Cu',agg,core) ('Cd',core,agg) ('Ed',agg,tor)."""
    load = {}
    for s, d in flows:
        ts, td = s // HPT, d // HPT; ps, pd = ts // TPP, td // TPP
        paths = []
        for pos in range(A):
            g, dg = ps * A + pos, pd * A + pos
            if (ts, g) in E or (td, dg) in E:
                continue
            for c in range(pos, NCORE, A):
                if (g, c) in C or (dg, c) in C:
                    continue
                paths.append((g, c, dg))
        if not paths:
            return None
        w = 1.0 / len(paths)
        for g, c, dg in paths:
            for k in (("Eu", ts, g), ("Cu", g, c), ("Cd", c, dg), ("Ed", dg, td)):
                load[k] = load.get(k, 0.0) + w
    return load


attempt = 0
while True:
    seed = a.seed + 7919 * attempt
    E, C = draw(seed)
    wl = os.path.join(a.outdir, "wl.cm")
    subprocess.run([sys.executable, gen, wl, str(NH), str(HPP), str(a.size), str(a.seed)], check=True,
                   stdout=subprocess.DEVNULL)
    flows = []
    for line in open(wl):
        if "->" in line:
            s, rest = line.split("->"); flows.append((int(s), int(rest.split()[0])))
    load = evaluate(E, C, flows)
    if load is not None:
        break
    attempt += 1
mx = max(load.values()) if load else 1.0
rho = min(1.0, 1.0 / mx)
with open(os.path.join(a.outdir, "fail.txt"), "w") as f:
    for g, c in sorted(C): f.write("C %d %d\n" % (g, c))
    for t, g in sorted(E): f.write("E %d %d\n" % (t, g))
json.dump({"p_percent": a.p_percent, "seed": a.seed, "attempts": attempt, "failed_E": len(E), "failed_C": len(C),
           "max_link_load": mx, "rho_max": rho, "ideal_cct_increase_pct": (1.0 / rho - 1.0) * 100.0,
           "nflows": len(flows), "loads": {"%s,%d,%d" % k: v for k, v in load.items()}},
          open(os.path.join(a.outdir, "inst.json"), "w"))
print("p=%.2f%% seed=%d attempts=%d failedE=%d failedC=%d max_load=%.4f rho_max=%.4f ideal_incr=%.2f%%" % (
    a.p_percent, a.seed, attempt, len(E), len(C), mx, rho, (1.0 / rho - 1.0) * 100.0))
