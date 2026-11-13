#!/usr/bin/env python3
"""Class identity for item 1: the ev column of ACK / NACK rows is the EV of the answered packet, so (ev % 8) % 2 == 0 is the 5% class.
For one cell, all 32 ToR0 flows (message 1 hosts 0-7 from msgN, messages 2-4 hosts 0-7 from msgNh): NACK count of the even class must equal the trims on the even ToR0 uplinks of the same run (queue stats), odd class 0.
usage: python n_class_check.py <cell> [<cell> ...]   (container paths /kneeout_n/traces, /kneeout_nh/traces)"""
import csv, gzip, sys
from collections import Counter
csv.field_size_limit(10 ** 8)


def scan(path, sel):
    c = Counter()
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh):
            if int(r["src_id"]) in sel and r["event"] in ("ACK", "NACK", "SEND", "RTX"):
                c[(r["event"], int(r["ev"]) % 2, r["ecn"])] += 1
    return c


for cell in sys.argv[1:]:
    c = scan(f"/kneeout_n/traces/h128_p8_msgN_{cell}.csv.gz", set(range(8))) + scan(f"/kneeout_nh/traces/h128_p8_msgNh_{cell}.csv.gz", {m * 128 + h for m in (1, 2, 3) for h in range(8)})
    tr = {0: 0, 1: 0}
    with gzip.open(f"/kneeout_n/traces/h128_p8_msgN_{cell}.queues.tsv.gz", "rt") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r["layer"] == "E->A" and r["i"] == "0":
                tr[int(r["j"]) % 2] += int(r["trims"])
    n = {k: sum(v for key, v in c.items() if key[0] == "NACK" and key[1] == k) for k in (0, 1)}
    a = {k: sum(v for key, v in c.items() if key[0] == "ACK" and key[1] == k) for k in (0, 1)}
    m = {k: sum(v for key, v in c.items() if key[0] == "ACK" and key[1] == k and key[2] == "1") for k in (0, 1)}
    s = {k: sum(v for key, v in c.items() if key[0] in ("SEND", "RTX") and key[1] == k) for k in (0, 1)}
    print(cell, "| sends even/odd", s[0], s[1], "| NACK even/odd", n[0], n[1], "vs uplink trims even/odd", tr[0], tr[1],
          "| ACK even/odd", a[0], a[1], "| ACK ecn=1 even/odd", m[0], m[1], "| ecn%% even %.1f odd %.1f" % (100 * m[0] / max(a[0], 1), 100 * m[1] / max(a[1], 1)))
