#!/usr/bin/env python3
"""N sweep: what ends the max-FCT host's message (run in the container).
Per (cell, message 2-4, host with the max FCT): start (first SEND), last SEND/RTX time, number of RTX, and the seqno ACKed last: its transmissions, whether it was trimmed (NACK),
its first-send ev_src and the age (us) of its EV if recycled (host-keyed bounded-FIFO replay as in n_age.py), time of its last ACK.
usage: python n_tail.py <traces_dir> <out.csv> <cfg_substring> <B,B,...>"""
import csv, gzip, re, sys
from collections import deque
from pathlib import Path
TR, OUT, SEL, BS = Path(sys.argv[1]), sys.argv[2], sys.argv[3], {int(b) for b in sys.argv[4].split(",")}
csv.field_size_limit(10 ** 8)
rows = []
for p in sorted(TR.glob("*.stdout.txt")):
    mt = re.match(r"(.+)_B(\d+)_s(\d+)\.stdout\.txt", p.name)
    cfg, B, seed = mt.group(1), int(mt.group(2)), int(mt.group(3))
    if SEL not in cfg or B not in BS:
        continue
    f = {}
    for l in p.read_text(errors="ignore").splitlines():
        mm = re.search(r"flowId (\d+) .*uecSrc (\d+) finished at ([0-9.]+)", l)
        if mm and l.startswith("Flow"):
            f[((int(mm.group(1)) - 1) // 128, int(mm.group(2)) % 128)] = float(mm.group(3))
    want = {}
    for m in (1, 2, 3):
        v = {h: t for (mg, h), t in f.items() if mg == m and h < 8}
        if v:
            h = max(v, key=v.get); want[m * 128 + h] = (m + 1, v[h])
    q = {h: deque() for h in range(8)}
    S = {s: dict(start=None, last_send=0.0, rtx=0, sq={}) for s in want}      # sq: seqno -> [n_tx, nacked, first_src, first_age, last_ack]
    with gzip.open(TR / p.name.replace(".stdout.txt", ".csv.gz"), "rt") as fh:
        for r in csv.DictReader(fh):
            sid = int(r["src_id"]); h = sid % 128
            if h >= 8:
                continue
            e, t = r["event"], float(r["time_ns"]); w = S.get(sid)
            if e in ("SEND", "RTX"):
                age = ""
                if r["ev_src"] == "fresh_pop" and q[h]:
                    age = round((t - q[h].popleft()[0]) / 1000, 1)
                if w is not None:
                    if w["start"] is None:
                        w["start"] = t
                    w["last_send"] = t
                    x = w["sq"].setdefault(r["seqno"], [0, 0, r["ev_src"], age, 0.0])
                    x[0] += 1
                    w["rtx"] += e == "RTX"
            elif e in ("ACK", "NACK"):
                if w is not None and r["seqno"] in w["sq"]:
                    x = w["sq"][r["seqno"]]
                    if e == "NACK":
                        x[1] += 1
                    else:
                        x[4] = t
                if e == "ACK" and r["ecn"] in ("0", "", "False"):
                    if len(q[h]) >= B:
                        q[h].popleft()
                    q[h].append((t, r["ev"]))
    for sid, (m, fct) in want.items():
        w = S[sid]
        sq, x = max(w["sq"].items(), key=lambda kv: kv[1][4])
        rows.append(dict(cfg=cfg.replace("msgNh_", "msgN_"), B=B, seed=seed, msg=m, fct=fct, start_us=round(w["start"] / 1000, 2), last_send_us=round((w["last_send"] - w["start"]) / 1000, 2),
                         last_ack_us=round((x[4] - w["start"]) / 1000, 2), rtx=w["rtx"], last_seq=sq, last_ntx=x[0], last_nacked=x[1], last_src=x[2], last_age=x[3]))
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows), "rows")
