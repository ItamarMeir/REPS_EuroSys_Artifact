#!/usr/bin/env python3
"""Configs of the 16-path N sweep: topology files (7 link delays), connection matrices, degrade files, configs_knee16.json, the B ladders.
Same experiment as knee/ (8 paths) with a k = 32 fat tree: 512 hosts, 16 hosts per ToR, 16 ToR uplinks. usage: python make_knee16_configs.py
Container layout (copied by launch step): topologies/knee16/*.topo, connection_matrices/knee16/*.cm (under /build/htsim_main/sim/datacenter), /work/knee16/degrade_*.txt."""
import json
from pathlib import Path
import params as Pm
HERE = Path(__file__).resolve().parent
K16 = HERE.parent
DATA = K16 / "data"
OLD = HERE.parents[2] / "meeting_26_10_26" / "knee" / "data"
OLD16 = HERE.parents[2] / "meeting_26_10_26" / "knee_16paths" / "data"
SPEED = 400


def topo(lat):
    d, tors = Pm.NH, Pm.HOSTS // Pm.NH
    t = lambda extra: f"Downlink_speed_Gbps {SPEED}\n{extra}Downlink_Latency_ns {lat}\nSwitch_Latency_ns 0\n"
    return f"Nodes {Pm.HOSTS}\nTiers 2\nPodsize {Pm.HOSTS}\n\nTier 0\n" + t(f"Radix_Down {d}\nRadix_Up {d}\n") + "\nTier 1\n" + t(f"Radix_Down {tors}\n")


def cm(n, k, size, period_us, pairs):
    lines = [f"Nodes {n}", f"Connections {len(pairs) * k}"]
    fid = 1
    for m in range(k):
        for s, d in pairs:
            lines.append(f"{s}->{d} id {fid} start {int(m * period_us * 1e6)} size {size}"); fid += 1
    return "\n".join(lines) + "\n"


def degrade(ratios, comment):
    return comment + "\n" + "".join(f"0 {a} {x}\n" for a, x in enumerate(ratios))


def w(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    open(path, "w", newline="\n").write(text)


cfgs = []
base = dict(axis="E16", tiers=2, hosts=Pm.HOSTS, H=Pm.NH, U=Pm.NH, P=Pm.P, q=101, ecn=[25, 76], sack=4000, rate_gbps=200.0, n_tors=Pm.HOSTS // Pm.NH,
            degrade="/work/knee16/degrade_h512_p16g.txt", note="512 hosts, 16 hosts per ToR, 16 uplinks (k = 32 fat tree)")
# files
for L in Pm.LATS:
    w(DATA / "topo" / f"topo_512_d16_lat{L}.topo", topo(L))
w(DATA / "cm" / "msg_n512_k4_s4M_p1000.cm", cm(Pm.HOSTS, Pm.MSGS, 4194304, 1000, [(i, (i + Pm.PAIR_SHIFT) % Pm.HOSTS) for i in range(Pm.HOSTS)]))
w(DATA / "cm" / "msg_n1_k4_s4M_p1000.cm", cm(Pm.HOSTS, Pm.MSGS, 4194304, 1000, [(0, Pm.PAIR_SHIFT)]))      # speed of light: one connection host 0 -> 256, four messages
r5 = Pm.RATIOS
assert abs(sum(r5) / Pm.P - 0.5) < 1e-9
w(DATA / "degrade" / "degrade_h512_p16g.txt", degrade(r5, "# knee_16paths_graded: ToR0 uplinks even agg 0.05 0.10 0.15 0.20 (twice), odd agg 0.95 0.90 0.85 0.80 (twice), mean 0.5"))
w(DATA / "degrade" / "degrade_h512_p16g_half.txt", degrade([0.5] * Pm.P, "# knee_16paths speed of light: ToR0 uplinks all 0.5 (400G x 0.5 = 200G, equivalent network)"))
srcs = lambda ms, hs: [x for m in ms for h in hs for x in ("-log_reps_events_src", str(m * Pm.HOSTS + h))]
for L in Pm.LATS:
    tp = f"topologies/knee16/topo_512_d16_lat{L}.topo"
    common = dict(base, topo=tp, topo_file=f"topo_512_d16_lat{L}.topo", latency_ns=L, tm="connection_matrices/knee16/msg_n512_k4_s4M_p1000.cm")
    cfgs.append(dict(common, name=f"{Pm.CFG_REPS}_lat{L}", extra=srcs(range(Pm.MSGS), range(Pm.NH))))
    cfgs.append(dict(common, name=f"{Pm.CFG_GOD}_lat{L}", extra=srcs(range(Pm.MSGS), range(Pm.NH)) + ["-reps_draw_weights", "capacity"]))
    sol = dict(common, tm="connection_matrices/knee16/msg_n1_k4_s4M_p1000.cm", degrade="/work/knee16/degrade_h512_p16g_half.txt", extra=[])
    cfgs.append(dict(sol, name=f"{Pm.CFG_SOL}_lat{L}"))
    cfgs.append(dict(sol, name=f"{Pm.CFG_SOL}1p_lat{L}", P=1))
json.dump(cfgs, open(DATA / "configs_knee16.json", "w"), indent=1)
# B ladders: the 8-path N ladder (scales with N) plus B = 2, 4, 8, 16 for BOTH arms, so the REPS-god pairing is complete from the start
bs = {}
for L in Pm.LATS:
    grid = json.load(open(OLD16 / "bsmap_knee16.json"))[f"h512_p16_msgNh_lat{L}"]   # same ladder as the 5/95 run, so cells pair
    bs[f"{Pm.CFG_REPS}_lat{L}"] = grid; bs[f"{Pm.CFG_GOD}_lat{L}"] = grid
    bs[f"{Pm.CFG_SOL}_lat{L}"] = [512]; bs[f"{Pm.CFG_SOL}1p_lat{L}"] = [512]
json.dump(bs, open(DATA / "bsmap_knee16.json", "w"), indent=1)
print(len(cfgs), "configs;", sum(len(v) for k, v in bs.items() if "NhG" not in k and "sol" not in k), "cells per seed per arm")
