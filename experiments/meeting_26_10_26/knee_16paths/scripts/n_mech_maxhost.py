#!/usr/bin/env python3
"""N sweep: share of random EV draws in the first 300 sends of the host that had the max FCT, per message 2-4 (run in the container, on the cfgs msgNh_* that trace hosts 0-15 of every message).
Per (cfg, B, seed): for message m in 1..3 (messages 2-4) the degraded host h with the largest FCT in that message (from stdout, same parsing as e_permessage.py), then the random share
among the first 300 SENDs of flow m*128+h in the REPS event trace. Also writes that message's max FCT, so the run can be checked against the msgN_* run (tracing must not change the FCTs).
Also counts all SENDs of that flow (sends_all, rand_all: whole message) and its RTX events (rtx_all, rtx_rand; retransmissions carry an ev_src label too, mostly fresh_pop).
usage: python n_mech_maxhost.py <traces_dir> <out.csv> [cfg_substring]  (the substring selects one latency, to run in batches)"""
import csv, gzip, re, sys
from pathlib import Path
import params as Pm
TR, OUT = Path(sys.argv[1]), sys.argv[2]
SEL = sys.argv[3] if len(sys.argv) > 3 else ""
csv.field_size_limit(10 ** 8)
rows = []
for p in sorted(TR.glob("*.stdout.txt")):
    mt = re.match(r"(.+)_B(\d+)_s(\d+)\.stdout\.txt", p.name)
    cfg, B, seed = mt.group(1), int(mt.group(2)), int(mt.group(3))
    if SEL not in cfg:
        continue
    f = {}
    for l in p.read_text(errors="ignore").splitlines():
        mm = re.search(r"flowId (\d+) .*uecSrc (\d+) finished at ([0-9.]+)", l)
        if mm and l.startswith("Flow"):
            f[((int(mm.group(1)) - 1) // Pm.HOSTS, int(mm.group(2)) % Pm.HOSTS)] = float(mm.group(3))
    want = {}
    for m in (1, 2, 3):
        v = {h: t for (mg, h), t in f.items() if mg == m and h < Pm.NH}
        if v:
            h = max(v, key=v.get)
            want[m * Pm.HOSTS + h] = (m, h, v[h])
    rnd, cnt = {k: 0 for k in want}, {k: 0 for k in want}
    rall, call = {k: 0 for k in want}, {k: 0 for k in want}
    xall, xrnd = {k: 0 for k in want}, {k: 0 for k in want}
    with gzip.open(TR / p.name.replace(".stdout.txt", ".csv.gz"), "rt") as fh:
        for r in csv.DictReader(fh):
            if r["event"] not in ("SEND", "RTX"):
                continue
            sid = int(r["src_id"])
            if r["event"] == "RTX":
                if sid in want:
                    xall[sid] += 1
                    xrnd[sid] += r["ev_src"] == "random"
                continue
            if sid in want:
                call[sid] += 1
                rall[sid] += r["ev_src"] == "random"
            if sid in want and cnt[sid] < 300:
                cnt[sid] += 1
                rnd[sid] += r["ev_src"] == "random"
    for sid, (m, h, t) in want.items():
        rows.append(dict(cfg=cfg, B=B, seed=seed, msg=m + 1, host=h, fct=t, sends=cnt[sid], rand300=rnd[sid], sends_all=call[sid], rand_all=rall[sid], rtx_all=xall[sid], rtx_rand=xrnd[sid]))
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), "rows")
