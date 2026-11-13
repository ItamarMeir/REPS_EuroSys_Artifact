#!/usr/bin/env python3
"""Buffer state of the REPS sender when each message has finished (run in the container, on the REPS and god traces, hosts 0-15 x messages 1-4 = 64 traced flows per cell).
For every flow (src_id = message * HOSTS + host) the LAST event row of its trace holds the buffer after the final ACK, i.e. when the message finished and before the next one starts (nothing is
sent in between): `slots` = value:isValid:lifetime for all B slots, `fresh` = number of valid slots. Output columns: cfg, B, seed, msg (1..4), host, valid (valid slots),
invalid (B - valid), fresh_col (the trace's own `fresh`, asserted equal to valid), p0..p15 (valid entries per path, path = EV % 16, even = 5% link).
usage: python n_bufstate.py <traces_dir> <out.csv> [cfg_substring]"""
import csv, gzip, re, sys
from pathlib import Path
import params as Pm
TR, OUT = Path(sys.argv[1]), sys.argv[2]
SEL = sys.argv[3] if len(sys.argv) > 3 else ""
csv.field_size_limit(10 ** 8)
rows = []
for p in sorted(TR.glob("*.csv.gz")):
    m = re.match(r"(.+)_B(\d+)_s(\d+)\.csv\.gz", p.name)
    if not m or "queues" in p.name or SEL not in m.group(1):
        continue
    cfg, B, seed = m.group(1), int(m.group(2)), int(m.group(3))
    last = {}
    with gzip.open(p, "rt") as fh:
        for r in csv.DictReader(fh):
            sid = int(r["src_id"])
            if sid % Pm.HOSTS < Pm.NH:
                last[sid] = (r["slots"], r["fresh"], r["buf_size"])
    for sid, (slots, fresh, bs) in sorted(last.items()):
        cnt = [0] * Pm.P
        valid = 0
        for s in slots.split("|"):
            v, ok, _ = s.split(":")
            if ok == "1":
                valid += 1
                cnt[int(v) % Pm.P] += 1
        assert valid == int(fresh), (p.name, sid, valid, fresh)
        assert len(slots.split("|")) == B, (p.name, sid)   # buf_size column is not reliable (0 in some rows at B 1024)
        rows.append(dict(cfg=cfg, B=B, seed=seed, msg=sid // Pm.HOSTS + 1, host=sid % Pm.HOSTS, valid=valid, invalid=B - valid, fresh_col=int(fresh), **{f"p{j}": cnt[j] for j in range(Pm.P)}))
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), "rows")
