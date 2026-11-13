#!/usr/bin/env python3
"""T3 inputs: topology files, tornado matrices, 5/95 degrade files and the config table (data/configs/configs.json).

Every config derives its numbers from the topology parameters instead of retyping them:
  H = hosts per ToR (Radix_Down tier 0), U = ToR uplinks (Radix_Up tier 0), P = SRv6 paths (= `-paths`),
  matched rate R = 0.5 * S * U / H (mean degrade ratio 0.5, 1:1 so R = 200G at 400G links),
  -q / -ecn from exp26 get_bdp (2-tier 101 / 25 76, 3-tier 152 / 38 114 at 1 us links),
  degrade file: ToR 0, even agg a -> r, odd agg a -> 1 - r, a in 0..U-1 (mean 0.5, asserted).
2-tier: Radix_Down = Radix_Up = d, ToRs = hosts / d, P = d.  3-tier (existing reps files): ToR0's U aggs are 0..U-1.
Files are written under data/configs/ and copied into the container by the launcher (docker cp), not by this script.
"""
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
T3 = HERE.parent
OUT = T3 / "data" / "configs"
REPO = HERE.parents[3]
DCDIR = REPO / "htsim" / "sim" / "datacenter"
R_LOW = 0.05
FLOW = 16777216
SPEED = 400
BASE_LAT = 1000


def bdp_pkts(tiers, lat_ns, gbps=SPEED):          # exp26/scripts/common.py get_bdp (verbatim formula)
    rtt = lat_ns * (tiers * 2 * 2) + tiers * 2 * (4096 * 8 / gbps)
    return rtt * gbps / 8 / 4096


def topo_2t(nodes, d, lat):
    tors = nodes // d
    assert nodes % d == 0 and d <= 96 and 2 * d <= 128 and tors <= 128
    tier = lambda extra: f"Downlink_speed_Gbps {SPEED}\n{extra}Downlink_Latency_ns {lat}\nSwitch_Latency_ns 0\n"
    return (f"Nodes {nodes}\nTiers 2\nPodsize {nodes}\n\nTier 0\n" + tier(f"Radix_Down {d}\nRadix_Up {d}\n")
            + "\nTier 1\n" + tier(f"Radix_Down {tors}\n"))


def degrade_text(U, r):
    ratios = [r if a % 2 == 0 else 1 - r for a in range(U)]
    assert abs(sum(ratios) / U - 0.5) < 1e-9
    return f"# T3: ToR0 uplinks, even agg {r}, odd agg {round(1 - r, 6)} (mean 0.5)\n" + "".join(f"0 {a} {x}\n" for a, x in enumerate(ratios))


# name: (axis, tiers, hosts, d_or_r, latency_ns, sack, existing 3-tier topo, note)
CFGS = [
    ("base_h1024_p32",  "base", 2, 1024, 32, BASE_LAT, 4000,  None, "baseline (= T1 r005)"),
    ("h128_p8",         "A",    2, 128,   8,  BASE_LAT, 4000,  None, "128 hosts, radix 8"),
    ("h256_p16",        "A",    2, 256,  16,  BASE_LAT, 4000,  None, "256 hosts, radix 16"),
    ("h512_p32",        "A",    2, 512,  32,  BASE_LAT, 4000,  None, "512 hosts, radix 32"),
    ("h2048_p32",       "A",    2, 2048, 32,  BASE_LAT, 4000,  None, "2048 hosts, radix 32"),
    ("h1024_p16",       "B",    2, 1024, 16,  BASE_LAT, 4000,  None, "1024 hosts, 16 paths (64 ToRs)"),
    ("h1024_p64",       "B",    2, 1024, 64,  BASE_LAT, 4000,  None, "1024 hosts, 64 paths (16 ToRs)"),
    ("t3_h128_p16",     "C",    3, 128,   4,  BASE_LAT, 4000,  "fat_tree_128_1os_3t_400g.topo", "3-tier 128 hosts, r=4"),
    ("t3_h1024_p64",    "C",    3, 1024,  8,  BASE_LAT, 4000,  "fat_tree_1024_1os_3t_400g.topo", "3-tier 1024 hosts, r=8"),
    ("lat4_h1024_p32",  "D",    2, 1024, 32, 4 * BASE_LAT, 4000, None, "link latency x4"),
    ("lat16_h1024_p32", "D",    2, 1024, 32, 16 * BASE_LAT, 4000, None, "link latency x16"),
    ("lat4_bdpq",       "D2",   2, 1024, 32, 4 * BASE_LAT, 4000, None, "link latency x4, q/ECN scaled to the BDP"),
    ("lat16_bdpq",      "D2",   2, 1024, 32, 16 * BASE_LAT, 4000, None, "link latency x16, q/ECN scaled to the BDP"),
    ("sack8000",        "E",    2, 1024, 32,  BASE_LAT, 8000,  None, "ACK every ~2 packets"),
    ("sack16384",       "E",    2, 1024, 32,  BASE_LAT, 16384, None, "ACK every ~4 packets"),
    # D3: 1 us links, q/ECN set from the x4 BDP (queue 394): separates queue depth / ECN thresholds from RTT
    ("q394_ecn98",      "D3",   2, 1024, 32,  BASE_LAT, 4000,  None, "1 us links, q 394, ECN 98/296 (x4 BDP thresholds)"),
    # F: send rate below matched (lever test of the drift reading, T3/investigate_8): name = r<ratio code>_R<Gbps>
    ("r005_R190",       "F",    2, 1024, 32,  BASE_LAT, 4000,  None, "5/95, 190G per host (below matched 200G)"),
    ("r005_R180",       "F",    2, 1024, 32,  BASE_LAT, 4000,  None, "5/95, 180G per host"),
    ("r025_R200",       "F",    2, 1024, 32,  BASE_LAT, 4000,  None, "25/75, 200G per host (matched)"),
    ("r025_R190",       "F",    2, 1024, 32,  BASE_LAT, 4000,  None, "25/75, 190G per host"),
    ("r010_R200",       "F",    2, 1024, 32,  BASE_LAT, 4000,  None, "10/90, 200G per host (matched)"),
    ("r015_R200",       "F",    2, 1024, 32,  BASE_LAT, 4000,  None, "15/85, 200G per host (matched)"),
    ("r020_R200",       "F",    2, 1024, 32,  BASE_LAT, 4000,  None, "20/80, 200G per host (matched)"),
    ("r035_R200",       "F",    2, 1024, 32,  BASE_LAT, 4000,  None, "35/65, 200G per host (matched)"),
    ("r045_R200",       "F",    2, 1024, 32,  BASE_LAT, 4000,  None, "45/55, 200G per host (matched)"),
    # J: extra one-way latency on ToR0 uplinks (latency_tor_agg lines, per-link-extra-latency): u = every uplink (control, no spread),
    # m = uplinks a with a % 4 in {2, 3} only (spread across paths, balanced over degraded/healthy parity)
    ("lat_u2000",       "J",    2, 1024, 32,  BASE_LAT, 4000,  None, "5/95, +2 us on every ToR0 uplink (control)"),
    ("lat_m2000",       "J",    2, 1024, 32,  BASE_LAT, 4000,  None, "5/95, +2 us on half of ToR0's uplinks (path spread)"),
    ("lat_m5000",       "J",    2, 1024, 32,  BASE_LAT, 4000,  None, "5/95, +5 us on half of ToR0's uplinks (path spread)"),
    ("lat_m20000",      "J",    2, 1024, 32,  BASE_LAT, 4000,  None, "5/95, +20 us on half of ToR0's uplinks (path spread)"),
    ("lat_m50000",      "J",    2, 1024, 32,  BASE_LAT, 4000,  None, "5/95, +50 us on half of ToR0's uplinks (path spread)"),
    ("lat_m5000_r025",  "J",    2, 1024, 32,  BASE_LAT, 4000,  None, "25/75, +5 us on half of ToR0's uplinks (path spread)"),
    ("q394_ecn25",      "D3b",  2, 1024, 32,  BASE_LAT, 4000,  None, "1 us links, q 394, ECN 25/76 (1 us BDP thresholds)"),
]


def lf(path):                                       # the simulator runs on Linux: force LF endings
    Path(path).write_bytes(Path(path).read_bytes().replace(bytes([13, 10]), bytes([10])))


def main():
    (OUT / "topo").mkdir(parents=True, exist_ok=True); (OUT / "tm").mkdir(exist_ok=True); (OUT / "degrade").mkdir(exist_ok=True)
    cfgs, tms = [], {}
    for name, axis, tiers, hosts, d, lat, sack, topo3, note in CFGS:
        U = H = d                                  # 1:1: ToR uplinks = hosts per ToR = radix
        if tiers == 2:
            topo_file = f"topo_{hosts}_d{d}_lat{lat}.topo"
            if not (OUT / "topo" / topo_file).exists():
                (OUT / "topo" / topo_file).write_text(topo_2t(hosts, d, lat))
            topo_rel = f"topologies/t3/{topo_file}"; P = d
        else:
            topo_file = topo3; (OUT / "topo" / topo_file).write_text((DCDIR / "topologies" / "reps" / topo3).read_text())
            topo_rel = f"topologies/t3/{topo_file}"; P = d * d
        tm = f"tornado_n{hosts}_s{FLOW}.cm"
        tms[hosts] = tm
        q = int(bdp_pkts(tiers, lat if axis == 'D2' else 4 * BASE_LAT if axis in ('D3', 'D3b') else BASE_LAT))   # axis D holds q/ecn at the 1 us BDP; D2 scales them with the BDP
        lo, hi = round(0.25 * q), round(0.75 * q)
        if axis == 'D3b': lo, hi = round(0.25 * 101), round(0.75 * 101)      # 25 76: the 1 us BDP thresholds under the deeper queue
        R = 0.5 * SPEED * U / H
        r_low = R_LOW
        if axis == 'F': r_low = int(name[1:4]) / 100.0 if name[1:4].isdigit() else None; assert r_low; R = float(name.split("_R")[1])
        dg = f"degrade_{name}.txt"; dtext = degrade_text(U, 0.25 if name.endswith("_r025") else r_low)
        if axis == 'J':
            ns = int(name.split("_")[1][1:]); sel = (lambda a: True) if name.startswith("lat_u") else (lambda a: a % 4 in (2, 3))
            dtext += "".join(f"latency_tor_agg 0 {a} {ns}" + chr(10) for a in range(U) if sel(a))
        (OUT / "degrade" / dg).write_text(dtext)
        cfgs.append(dict(name=name, axis=axis, tiers=tiers, hosts=hosts, H=H, U=U, P=P, topo=topo_rel, topo_file=topo_file, tm=f"connection_matrices/t3/{tm}",
                         degrade=f"/work/t3/{dg}", q=q, ecn=[lo, hi], sack=sack, rate_gbps=R, latency_ns=lat, note=note, n_tors=hosts // H))
    for hosts, tm in tms.items():
        p = OUT / "tm" / tm
        if not p.exists():
            subprocess.run([sys.executable, str(DCDIR / "connection_matrices" / "gen_tornado.py"), str(p), str(hosts), str(hosts), str(FLOW), "0", "42"], check=True)
    for f in OUT.glob("*/*"):
        lf(f)
    (OUT / "configs.json").write_text(json.dumps(cfgs, indent=1))
    for c in cfgs:
        print(f"{c['name']:18s} axis {c['axis']} tiers {c['tiers']} hosts {c['hosts']:5d} H {c['H']:2d} U {c['U']:2d} P {c['P']:2d} tors {c['n_tors']:3d} "
              f"R {c['rate_gbps']:.0f}G q {c['q']} ecn {c['ecn']} lat {c['latency_ns']} sack {c['sack']}")


if __name__ == "__main__":
    main()
