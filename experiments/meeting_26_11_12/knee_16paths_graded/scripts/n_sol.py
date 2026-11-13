#!/usr/bin/env python3
"""Speed of light (SOL) of the N sweep. Run in the container on /kneeout_sol (cfgs h512_p16g_sol_lat*, sol1p_lat*: one connection host 0 -> 256, 4 x 4 MiB, ToR0 uplinks all 0.5, nothing else running).
Writes the per-message FCT of every sim cell, the analytic value (a) and the unloaded RTT of the first / last packet of message 1 from the trace.
Analytic (a): the sender emits one 4150 B packet every s = 4150 * 8 / 200 Gbit/s = 0.166 us, M = 1027 packets per 4 MiB message, so the last packet is sent (M - 1) * s after the first; it then needs the
unloaded path time: 8 * (per-link delay) of propagation (4 links out, 4 back) plus forward serialization (host link 400G 0.083 us, ToR uplink 200G 0.166 us, agg downlink 400G 0.083 us, ToR downlink 400G 0.083 us = 0.415 us)
plus the 64 B ACK (about 0.005 us). The gaps between messages (1000 us) do not enter a per-message FCT while a message ends before the next starts.
usage: python n_sol.py <sol traces dir> <out.csv>"""
import csv, re, sys
from pathlib import Path
import params as Pm
TR, OUT = Path(sys.argv[1]), sys.argv[2]
M, PKT, RATE = 1027, 4150, 200e9
S_US = PKT * 8 / RATE * 1e6
FWD_SER = (PKT * 8 / 400e9 * 3 + PKT * 8 / 200e9) * 1e6
rows = []
for p in sorted(TR.glob("*.stdout.txt")):
    mt = re.match(r"h512_p16g_(sol1?p?)_lat(\d+)_B(\d+)_s(\d+)\.stdout\.txt", p.name)
    var, L, B, seed = mt.group(1), int(mt.group(2)), int(mt.group(3)), int(mt.group(4))
    txt = p.read_text(errors="ignore")
    f = {int(m.group(1)): float(m.group(2)) for m in re.finditer(r"^Flow \S+ flowId (\d+) .*? finished at ([0-9.]+)", txt, re.M)}
    sp = [l for l in txt.splitlines() if l.startswith("Failure:")]
    rows.append(dict(variant=var, lat_ns=L, B=B, seed=seed, n_flows=len(f), fct1=f.get(1), fct2=f.get(2), fct3=f.get(3), fct4=f.get(4),
                     analytic=round((M - 1) * S_US + 8 * L / 1000 + FWD_SER + 0.005, 3), n_speeds_200=sum("linkspeed set to 200" in l for l in sp),
                     srv6="SRv6 source routing enabled" in txt, tor_dl_ecn=("enable on tor downlink 1" in txt), rtos=len(re.findall(r"RTO|timeout", txt))))
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), "rows")
