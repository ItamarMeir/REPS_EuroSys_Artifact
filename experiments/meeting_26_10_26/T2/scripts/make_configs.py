#!/usr/bin/env python3
"""T2 inputs: degrade files and the config table (configs/configs.json) for the 3-tier k=8 fat tree (128 hosts, 16 paths).

Topology  topologies/reps/fat_tree_128_1os_3t_400g.topo (existing): 8 pods x (4 ToRs x 4 hosts), 4 aggs per pod, 16 cores.
          Pod0 = ToRs 0..3, aggs 0..3. Agg a, uplink l goes to core a + 4*l (fat_tree_topology.cpp, "Upper layer in pod to core").
Traffic   connection_matrices/tornado_128n_16mb.cm: dst = src + 64, every flow crosses the core. Matched rate R = 0.5 * S * U / H = 200G.
Degrade   mean ratio 0.5 on every group of 4 uplinks, pairs inside ONE switch (2 uplinks at r, 2 at 1 - r; even position r, odd 1 - r):
  A (tor_agg):  for each ToR t in pod0, agg a in 0..3:  "t a ratio"            (existing -degrade_links_file key)
  B (agg_core): for each agg a in pod0, uplink l in 0..3: "agg_core a (a+4l) ratio"  (per-link-degrade-agg-core)
Shapes    u50 (0.5/0.5), r025 (25/75), r010 (10/90), r005 (5/95). 1/99 is not run: it entered Freezing Mode in T1.
Files are written under configs/ and copied into the container by setup_container.sh.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
T2 = HERE.parent
OUT = T2 / "configs"
SPEED, LAT, TIERS = 400, 1000, 3
H = U = 4                                   # hosts per ToR, ToR uplinks (also agg radix up/down)
PODSIZE = 16
SHAPES = {"u50": 0.5, "r025": 0.25, "r010": 0.10, "r005": 0.05}
LABEL = {"u50": "uniform 50/50", "r025": "non-uniform 25/75", "r010": "non-uniform 10/90", "r005": "non-uniform 5/95"}


def bdp_pkts(tiers, lat_ns, gbps=SPEED):    # exp26/scripts/common.py get_bdp (verbatim formula, as T3)
    rtt = lat_ns * (tiers * 2 * 2) + tiers * 2 * (4096 * 8 / gbps)
    return rtt * gbps / 8 / 4096


def ratios(r):
    out = [r if i % 2 == 0 else round(1 - r, 6) for i in range(U)]
    assert abs(sum(out) / U - 0.5) < 1e-9
    return out


def degrade_a(r):
    rr = ratios(r)
    return (f"# T2 A: pod0 ToR->agg uplinks, even agg {r}, odd agg {round(1 - r, 6)} (mean 0.5), pairs inside each ToR\n"
            + "".join(f"{t} {a} {rr[a]}\n" for t in range(PODSIZE // H) for a in range(U)))


def degrade_b(r):
    rr = ratios(r)
    return (f"# T2 B: pod0 agg->core uplinks, even uplink {r}, odd uplink {round(1 - r, 6)} (mean 0.5), pairs inside each agg; agg a uplink l -> core a + 4 l\n"
            + "".join(f"agg_core {a} {a + 4 * l} {rr[l]}\n" for a in range(U) for l in range(U)))


def main():
    (OUT / "degrade").mkdir(parents=True, exist_ok=True)
    q = int(bdp_pkts(TIERS, LAT)); lo, hi = round(0.25 * q), round(0.75 * q)
    R = 0.5 * SPEED * U / H
    base = dict(topo="topologies/reps/fat_tree_128_1os_3t_400g.topo", tm="connection_matrices/tornado_128n_16mb.cm", hosts=128, tiers=TIERS, H=H, U=U, P=16,
                pod=PODSIZE, q=q, ecn=[lo, hi], rate_gbps=R, latency_ns=LAT, sack=4000)
    cfgs = [dict(base, name="healthy", sub="ref", shape="healthy", r=None, degrade=None, n_links=0, label="healthy (no degrade file)")]
    for sub, fn in (("a", degrade_a), ("b", degrade_b)):
        for shape, r in SHAPES.items():
            f = f"degrade_{sub}_{shape}.txt"
            text = fn(r); (OUT / "degrade" / f).write_bytes(text.replace("\r\n", "\n").encode())
            n = sum(1 for ln in text.splitlines() if ln and not ln.startswith("#"))
            assert n == 16
            cfgs.append(dict(base, name=f"{sub}_{shape}", sub=sub, shape=shape, r=r, degrade=f"/work/t2/{f}", n_links=n, label=LABEL[shape]))
    (OUT / "configs.json").write_text(json.dumps(cfgs, indent=1))
    for c in cfgs:
        print(f"{c['name']:10s} sub {c['sub']:3s} R {c['rate_gbps']:.0f}G q {c['q']} ecn {c['ecn']} links {c['n_links']} degrade {c['degrade']}")


if __name__ == "__main__":
    main()
