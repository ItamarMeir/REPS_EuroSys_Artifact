#!/usr/bin/env python3
"""N sweep: per-cell mechanism numbers from the REPS event traces (host 0 of every message: flow index 0, 512, 1024, 1536 of the 16-path fabric; run in the container).
Per (cfg, B, seed): peak in-flight packets of host 0 in message 1 (the measured N), fresh EVs in the buffer at the first SEND of messages 2-4,
and the share of random EV draws among the first 300 sends of messages 2-4 (the mechanism: about max(0, N - B) of the first RTT).
Gate-failing cells are not dropped here (the page drops them via results.jsonl).
usage: python n_mech.py <traces_dir> <out.csv>"""
import csv, gzip, re, sys
from pathlib import Path
import params as Pm

TR, OUT = Path(sys.argv[1]), sys.argv[2]
csv.field_size_limit(10 ** 8)
rows = []
for p in sorted(TR.glob("*.csv.gz")):
    m = re.match(r"(.+)_B(\d+)_s(\d+)\.csv\.gz", p.name)
    if not m or "queues" in p.name:
        continue
    cfg, B, seed = m.group(1), int(m.group(2)), int(m.group(3))
    peak = 0
    first = {}
    rnd = {1: 0, 2: 0, 3: 0}
    cnt = {1: 0, 2: 0, 3: 0}
    with gzip.open(p, "rt") as fh:
        for r in csv.DictReader(fh):
            if r["srcaddr"] != "0":
                continue
            sid = int(r["src_id"])
            msg = sid // Pm.HOSTS
            if msg == 0:
                peak = max(peak, int(r["inflight_pkts"]))
            if r["event"] != "SEND" or msg == 0:
                continue
            if msg not in first:
                first[msg] = int(r["fresh"])
            if cnt[msg] < 300:
                cnt[msg] += 1
                rnd[msg] += r["ev_src"] == "random"
    rows.append(dict(cfg=cfg, B=B, seed=seed, peak_inflight=peak,
                     **{f"fresh_m{k + 1}": first.get(k) for k in (1, 2, 3)},
                     **{f"rand300_m{k + 1}": rnd[k] for k in (1, 2, 3)}))
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), "cells")
