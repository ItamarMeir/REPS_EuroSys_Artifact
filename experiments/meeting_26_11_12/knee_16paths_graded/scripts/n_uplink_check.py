#!/usr/bin/env python3
"""Identities of the 16-path N sweep (SRv6: EV -> _paths[ev % 16] = ToR0 uplink j), per cell, from the trace and the queue stats of the SAME run.
All 16 hosts behind ToR0 are traced (messages 1-4), so ToR0's uplinks carry exactly the traced flows' transmissions:
  (1) sends (SEND + RTX events) per ev % 16 == data_pkts + trims + drops of ToR0 uplink j (layer E->A, i = 0), 0 mismatches;
  (2) the ev column of ACK / NACK rows is the EV of the answered packet, so the NACKs of each class == the trims of the ToR0 uplinks of that class (the 95% links can trim too at large N and B).
usage: python n_uplink_check.py <traces dir> <cfg prefix> <cell> [<cell> ...]   cell = lat16000_B256_s42"""
import csv, gzip, sys
from collections import Counter
from pathlib import Path
import params as Pm
D, PFX = Path(sys.argv[1]), sys.argv[2]
csv.field_size_limit(10 ** 8)
SEL = {m * Pm.HOSTS + h for m in range(Pm.MSGS) for h in range(Pm.NH)}


def uplinks(path):
    d = {}
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r["layer"] == "E->A" and r["i"] == "0":
                d[int(r["j"])] = (int(r["data_pkts"]), int(r["trims"]), int(r["drops"]))
    assert len(d) == Pm.P, len(d)
    return [d[j] for j in range(Pm.P)]


bad = 0
for cell in sys.argv[3:]:
    s = [0] * Pm.P
    nack = Counter()
    with gzip.open(D / f"{PFX}_{cell}.csv.gz", "rt") as fh:
        for r in csv.DictReader(fh):
            if int(r["src_id"]) not in SEL:
                continue
            if r["event"] in ("SEND", "RTX"):
                s[int(r["ev"]) % Pm.P] += 1
            elif r["event"] == "NACK":
                nack[int(r["ev"]) % Pm.P % 2] += 1
    q = uplinks(D / f"{PFX}_{cell}.queues.tsv.gz")
    print(cell)
    print("  j   class   sends(trace)  data_pkts  trims  drops  data+trims+drops  diff")
    tot = 0
    for j in range(Pm.P):
        d, t, dr = q[j]
        tot += abs(s[j] - (d + t + dr))
        print(f"  {j:>2}   {'5%' if Pm.is_bad_ev(j) else '95%'}   {s[j]:>12} {d:>10} {t:>6} {dr:>6} {d + t + dr:>10} {s[j] - (d + t + dr):>6}")
    tr_even = sum(q[j][1] for j in range(0, Pm.P, 2))
    tr_odd = sum(q[j][1] for j in range(1, Pm.P, 2))
    ok2 = nack[0] == tr_even and nack[1] == tr_odd
    print(f"  sum |diff| = {tot}  total sends {sum(s)} | NACK even/odd {nack[0]}/{nack[1]} vs uplink trims even/odd {tr_even}/{tr_odd}: {'PASS' if ok2 else 'FAIL'}")
    bad += tot + (0 if ok2 else 1)
print("IDENTITIES", "PASS" if bad == 0 else "FAIL")
