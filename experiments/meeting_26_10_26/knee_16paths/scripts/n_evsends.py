#!/usr/bin/env python3
"""Packets sent per EV (run in the container, on the REPS and god traces; hosts 0-15 x messages 1-4 = 64 traced flows per cell, src_id = message * HOSTS + host).
For every flow, the number of transmissions per EV (0..15 = path; even = 5% link) split by event and by where the EV came from:
  sr<e> = SEND with a random EV, sf<e> = SEND with an EV taken from the buffer (ev_src fresh_pop), xr<e> = RTX random, xf<e> = RTX from the buffer.
Any other ev_src would be counted in no column and fails the check sum == number of SEND/RTX rows (asserted).
Output columns: cfg, B, seed, msg (1..4), host, sr0..sr15, sf0..sf15, xr0..xr15, xf0..xf15.
usage: python n_evsends.py <traces_dir> <out.csv> [cfg_substring]"""
import csv, gzip, re, sys
from pathlib import Path
import params as Pm
TR, OUT = Path(sys.argv[1]), sys.argv[2]
SEL = sys.argv[3] if len(sys.argv) > 3 else ""
csv.field_size_limit(10 ** 8)
P = Pm.P
rows = []
for p in sorted(TR.glob("*.csv.gz")):
    m = re.match(r"(.+)_B(\d+)_s(\d+)\.csv\.gz", p.name)
    if not m or "queues" in p.name or SEL not in m.group(1):
        continue
    cfg, B, seed = m.group(1), int(m.group(2)), int(m.group(3))
    cnt, nrow = {}, {}
    with gzip.open(p, "rt") as fh:
        for r in csv.DictReader(fh):
            ev = r["event"]
            if ev != "SEND" and ev != "RTX":
                continue
            sid = int(r["src_id"])
            if sid % Pm.HOSTS >= Pm.NH:
                continue
            c = cnt.get(sid)
            if c is None:
                c = cnt[sid] = [0] * (4 * P); nrow[sid] = 0
            nrow[sid] += 1
            src = r["ev_src"]
            k = (0 if ev == "SEND" else 2) + (0 if src == "random" else 1 if src == "fresh_pop" else -99)
            if k >= 0:
                c[k * P + int(r["ev"]) % P] += 1
    for sid, c in sorted(cnt.items()):
        assert sum(c) == nrow[sid], (p.name, sid, sum(c), nrow[sid])
        d = dict(cfg=cfg, B=B, seed=seed, msg=sid // Pm.HOSTS + 1, host=sid % Pm.HOSTS)
        for k, name in enumerate(("sr", "sf", "xr", "xf")):
            for e in range(P):
                d[f"{name}{e}"] = c[k * P + e]
        rows.append(d)
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), "rows")
