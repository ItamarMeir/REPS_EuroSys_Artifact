#!/usr/bin/env python3
"""Network-parameter dial configs for the knee study. Reads the T3 config table, writes data/configs_knee.json with derived configs.
Dials (none changes REPS): mtu (packet size at constant queue/ECN bytes), see README predictions. usage: python make_knee_configs.py"""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
T3 = json.load(open(HERE.parents[1] / "T3/data/configs/configs.json"))
BASE = {c["name"]: c for c in T3}
out = []
def derive(base, suffix, **kw):
    c = dict(BASE[base]); c["name"] = f"{base}_{suffix}"; c["extra"] = kw.pop("extra", [])
    c.update(kw); out.append(c); return c
for base in ("h128_p8", "base_h1024_p32"):
    for mtu in (1000, 1500, 2075, 4150, 8300):
        f = 4150 / mtu          # keep queue and ECN thresholds constant in bytes (q, ecn are in packets)
        b = BASE[base]
        derive(base, f"mtu{mtu}", extra=["-mtu", str(mtu)], q=round(b["q"] * f), ecn=[round(e * f) for e in b["ecn"]],
               sack=int(4000 * mtu / 4150) // 100 * 100)   # ACK per packet: the receiver SACK threshold must stay below one payload (else one ACK = 2 packets = 1 EV, a token starvation seen in the first smoke cell)
# D2: send rate relative to the host link, matched degradation. Host link is 400G (a ToR cannot change its host-link speed alone: the fat-tree builder derives the uplink count from the tier speeds),
# so the dial is R = 400 / s. Mean degrade ratio m = R/400 keeps the ToR0 uplink capacity equal to the offered load (matched); shape r/(1-r) with r = 0.05 -> even agg 2 m r, odd agg 2 m (1-r).
DEG_DIR = HERE.parents[0] / "data/degrade"; DEG_DIR.mkdir(exist_ok=True)
for base in ("h128_p8",):
    U = BASE[base]["U"]
    for R in (50, 100, 150, 200):
        m = R / 400
        ratios = [2 * m * 0.05 if a % 2 == 0 else 2 * m * 0.95 for a in range(U)]
        assert abs(sum(ratios) / U - m) < 1e-9 and max(ratios) <= 4
        fn = f"degrade_{base}_R{R}.txt"
        open(DEG_DIR / fn, "w", newline="\n").write(f"# knee D2: ToR0 uplinks, shape 5/95, mean ratio {m}\n" + "".join(f"0 {a} {x:.6f}\n" for a, x in enumerate(ratios)))
        derive(base, f"R{R}", rate_gbps=float(R), degrade=f"/work/knee/{fn}")
# D3 slack: rate below matched, degrade file of h128_p8 unchanged (5/95, mean 0.5). D4: number f of degraded uplinks of 8 at depth 0.05, healthy ratio keeps the mean at 0.5.
for R in (140, 160, 180, 190):
    derive("h128_p8", f"slack{R}", rate_gbps=float(R))
for f in (1, 2, 4):
    h = (4 - 0.05 * f) / (8 - f); ratios = [0.05 if a < f else h for a in range(8)]
    assert abs(sum(ratios) - 4) < 1e-9
    fn = f"degrade_h128_p8_f{f}.txt"
    open(DEG_DIR / fn, "w", newline="\n").write(f"# knee D4: ToR0, {f} of 8 uplinks at 0.05, others {h:.6f}\n" + "".join(f"0 {a} {x:.6f}\n" for a, x in enumerate(ratios)))
    derive("h128_p8", f"f{f}", degrade=f"/work/knee/{fn}")
# D5 path-latency spread: extra delay of X us per link on ToR0 uplinks agg % 4 in {2,3} (existing `latency_tor_agg` key), degrade file of h128_p8 otherwise unchanged
orig = (HERE.parents[1] / "T3/data/configs/degrade/degrade_h128_p8.txt").read_text()
for X in (2, 5, 10, 15, 20):
    lines = "".join(f"latency_tor_agg 0 {a} {X * 1000}\n" for a in range(BASE["h128_p8"]["U"]) if a % 4 in (2, 3))
    fn = f"degrade_h128_p8_spread{X}.txt"
    open(DEG_DIR / fn, "w", newline="\n").write(orig + lines)
    derive("h128_p8", f"spread{X}", degrade=f"/work/knee/{fn}")
# E: repeated messages on the same pair (connections_mapping shares the REPS buffer between consecutive messages)
for tmname in ("msg_n128_k4_s1M_p100",):
    derive("h128_p8", tmname, tm=f"connection_matrices/knee/{tmname}.cm")
# D3 on T1's 1024-host fabric: load below capacity (T1 r005 = base_h1024_p32)
for R in (160, 140):
    derive("base_h1024_p32", f"slack{R}", rate_gbps=float(R))
# F: oscillating delay by periodic incast into the receivers of the ToR0 flows
for S in (0, 25000, 50000, 100000, 200000):
    derive("h128_p8", f"incast{S}", tm=f"connection_matrices/knee/incast_s{S}.cm")
T3TOPO = HERE.parents[1] / "T3/data/configs/topo"; TOPO_DIR = HERE.parents[0] / "data/topo"; TOPO_DIR.mkdir(exist_ok=True)
# E: repeated messages on one pair (needs [FIX: connection-info-cwnd-overflow] for the constant sender)
# message matrices: P=100us (idle gap) = msg_n128_k4_s1M_p100 (made earlier), P=60us made by make_messages_cm.py
derive("h128_p8", "msgE_base", tm="connection_matrices/knee/msg_n128_k4_s1M_p100.cm")
derive("h128_p8", "msgE_p60", tm="connection_matrices/knee/msg_n128_k4_s1M_p60.cm")
t = (T3TOPO / BASE["h128_p8"]["topo_file"]).read_text().replace("Downlink_Latency_ns 1000", "Downlink_Latency_ns 2000")
fn = BASE["h128_p8"]["topo_file"].replace("lat1000", "lat2000"); open(TOPO_DIR / fn, "w", newline="\n").write(t)
derive("h128_p8", "msgE_lat2", tm="connection_matrices/knee/msg_n128_k4_s1M_p100.cm", topo=f"topologies/knee/{fn}")
derive("h128_p8", "msgE_mtu2075", tm="connection_matrices/knee/msg_n128_k4_s1M_p100.cm", extra=["-mtu", "2075"], q=round(101 * 4150 / 2075), ecn=[round(e * 4150 / 2075) for e in BASE["h128_p8"]["ecn"]], sack=2000)
derive("h128_p8", "msgE_R100", tm="connection_matrices/knee/msg_n128_k4_s1M_p100.cm", rate_gbps=100.0, degrade="/work/knee/degrade_h128_p8_R100.txt")
derive("h128_p8", "msgE_R100p250", tm="connection_matrices/knee/msg_n128_k4_s1M_p250.cm", rate_gbps=100.0, degrade="/work/knee/degrade_h128_p8_R100.txt")
derive("base_h1024_p32", "msgT1", tm="connection_matrices/knee/msg_n1024_k2_s16M_p900.cm")
# E, N sweep: ONE parameter raises N = rate x RTT / MTU: per-link delay of every fabric link (both tiers; a path has 4 links, RTT = 8 x delay + serialization), 4 MiB messages (1012 packets) every 1000 us (P=600 left 95 us margin at lat 16 us, B=8)
for L in (250, 500, 1000, 2000, 4000, 8000, 16000):
    kw = {}
    if L != 1000:
        t = (T3TOPO / BASE["h128_p8"]["topo_file"]).read_text().replace("Downlink_Latency_ns 1000", f"Downlink_Latency_ns {L}")
        assert t.count(f"Downlink_Latency_ns {L}") == 2   # host links (tier 0) and ToR-agg links (tier 1)
        fn = BASE["h128_p8"]["topo_file"].replace("lat1000", f"lat{L}"); open(TOPO_DIR / fn, "w", newline="\n").write(t); kw["topo"] = f"topologies/knee/{fn}"
    # run_t3 traces sources 0-7 = hosts 0-7 in message 1 only. Add host 0 in messages 2-4 (flow index = message * 128 + host): tracing all 32 flows at B up to 2048
    # (every row prints all B slots) took more than 15 min per cell and made the sweep infeasible
    ex = [x for m in (1, 2, 3) for x in ("-log_reps_events_src", str(m * 128))]
    derive("h128_p8", f"msgN_lat{L}", tm="connection_matrices/knee/msg_n128_k4_s4M_p1000.cm", extra=ex, **kw)
# E, N sweep, mechanism rerun: trace every degraded host (0-7) in messages 2-4 (24 flows), so the random-draw share can be read for the host that had the max FCT (it is host 0 in only 1 of 8 cells)
for L in (250, 500, 1000, 2000, 4000, 8000, 16000):
    b = next(c for c in out if c["name"] == f"h128_p8_msgN_lat{L}")
    d = dict(b); d["name"] = f"h128_p8_msgNh_lat{L}"
    d["extra"] = [x for m in (1, 2, 3) for h in range(8) for x in ("-log_reps_events_src", str(m * 128 + h))]
    out.append(d)
# REPS "god mode" ([ADDED: reps-draw-weights]): the msgNh cells (same workload, topology, seeds) with capacity-weighted random draws; traces hosts 0-7 in ALL 4 messages (32 flows) so warmup (message 1) and messages 2-4 come from one run.
for L in (250, 500, 1000, 2000, 4000, 8000, 16000):
    b = next(c for c in out if c["name"] == f"h128_p8_msgN_lat{L}")
    d = dict(b); d["name"] = f"h128_p8_msgNhG_lat{L}"
    d["extra"] = [x for m in (0, 1, 2, 3) for h in range(8) for x in ("-log_reps_events_src", str(m * 128 + h))] + ["-reps_draw_weights", "capacity"]
    out.append(d)
# Speed of light of the N sweep (user request 2026-11-04): ONE connection host 0 -> 64, 4 messages of 4 MiB every 1000 us (same pair, REPS buffer shared), all 8 ToR0 uplinks at ratio 0.5
# (400G x 0.5 = 200G = the sender rate, the equivalent network of one 200G path), no other traffic. sol = the sweep's REPS over 8 equal paths; sol1p = the same with ONE path (-paths 1).
for L in (250, 500, 1000, 2000, 4000, 8000, 16000):
    kw = {}
    if L != 1000:
        kw["topo"] = f"topologies/knee/{BASE['h128_p8']['topo_file'].replace('lat1000', f'lat{L}')}"
    derive("h128_p8", f"sol_lat{L}", tm="connection_matrices/knee/msg_n1_k4_s4M_p1000.cm", degrade="/work/knee/degrade_h128_p8_half.txt", **kw)
    derive("h128_p8", f"sol1p_lat{L}", tm="connection_matrices/knee/msg_n1_k4_s4M_p1000.cm", degrade="/work/knee/degrade_h128_p8_half.txt", P=1, **kw)
# G: time-varying degradation (needs [ADDED: link-swap])
for T in (8, 16, 30, 60, 120, 250, 500, 1000):
    derive("h128_p8", f"swapT{T}", extra=["-swap_tor_uplinks", "0", str(T), "3000"])
for T in (10, 12, 14, 18, 20, 24):
    derive("h128_p8", f"swapT{T}", extra=["-swap_tor_uplinks", "0", str(T), "3000"])
# G control: no recycling at all (random full-path spray) under the same swap, and static
for T in (16, 18):
    derive("h128_p8", f"swapT{T}_rand", extra=["-load_balancing_algo", "path_random", "-swap_tor_uplinks", "0", str(T), "3000"])
derive("h128_p8", "static_rand", extra=["-load_balancing_algo", "path_random"])
# H: switch queue size at fixed ECN thresholds (deeper queue = more delay a random draw onto a degraded uplink can pick up)
for qm in (0.5, 1, 2, 4):
    derive("h128_p8", f"q{qm:g}x", q=round(BASE["h128_p8"]["q"] * qm))
json.dump(out, open(HERE.parents[0] / "data/configs_knee.json", "w"), indent=1)
print([c["name"] for c in out])
