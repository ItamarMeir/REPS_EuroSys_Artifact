#!/usr/bin/env python3
"""Mapping identity for the N sweep (SRv6: EV -> _paths[ev % 8] = ToR0 uplink j).
Per cell: sends (SEND + RTX events) per ev % 8 of all 32 ToR0 flows (hosts 0-7, messages 1-4) versus data_pkts + trims of ToR0 uplink j (layer E->A, i = 0) in the queue stats of the same run.
Message 1 hosts 0-7 come from the msgN trace; messages 2-4 hosts 0-7 from the msgNh trace (twin run, identical FCTs, checked earlier).
usage: python n_uplink_check.py <msgN traces dir> <msgNh traces dir> <cell> [<cell> ...]   cell = lat16000_B256_s42"""
import csv, gzip, sys
from pathlib import Path
DN, DH = Path(sys.argv[1]), Path(sys.argv[2])
csv.field_size_limit(10 ** 8)


def sends(path, sel):
    """counts per ev % 8 of SEND/RTX events of the flows in sel (src_id)"""
    c = [0] * 8
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh):
            if r["event"] in ("SEND", "RTX") and int(r["src_id"]) in sel:
                c[int(r["ev"]) % 8] += 1
    return c


def uplinks(path):
    d = {}
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r["layer"] == "E->A" and r["i"] == "0":
                d[int(r["j"])] = (int(r["data_pkts"]), int(r["trims"]), int(r["drops"]))
    return [d[j] for j in range(8)]


for cell in sys.argv[3:]:
    a = sends(DN / f"h128_p8_msgN_{cell}.csv.gz", set(range(8)))                       # message 1, hosts 0-7
    b = sends(DH / f"h128_p8_msgNh_{cell}.csv.gz", {m * 128 + h for m in (1, 2, 3) for h in range(8)})   # messages 2-4, hosts 0-7
    s = [x + y for x, y in zip(a, b)]
    q = uplinks(DN / f"h128_p8_msgN_{cell}.queues.tsv.gz")
    print(cell)
    print("  j   class   sends(trace)  data_pkts  trims  drops  data+trims  diff")
    tot = 0
    for j in range(8):
        d, t, dr = q[j]
        tot += abs(s[j] - (d + t + dr))
        print(f"  {j}   {'5%' if j % 2 == 0 else '95%'}   {s[j]:>12} {d:>10} {t:>6} {dr:>6} {d + t + dr:>10} {s[j] - (d + t + dr):>6}")
    print("  sum |diff| =", tot, " total sends", sum(s))
