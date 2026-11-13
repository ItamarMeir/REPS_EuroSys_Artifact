#!/usr/bin/env python3
"""N sweep: age of recycled EVs and deposits, for the max-FCT host of messages 2-4 (run in the container).
Replays the host's whole stream (messages 1-4 share one buffer per source host, so state is keyed by host = flow index % 128 and all traced flows of hosts 0-7 are read): a bounded FIFO of B fresh EVs (deposit = ACK with ecn 0, full -> overwrite the oldest, pop = oldest) and checks the replayed fresh count against the logged `fresh` at every SEND.
Per (cell, message, age bin) of recycled sends: sends, outcomes (trimmed / ECN-marked / RTT) found by seqno. Also deposits and ACKs of the flow.
usage: python n_age.py <traces_dir> <out.csv> <cfg_substring> <B,B,...>"""
import csv, gzip, re, sys
from collections import deque
from pathlib import Path
TR, OUT, SEL, BS = Path(sys.argv[1]), sys.argv[2], sys.argv[3], {int(b) for b in sys.argv[4].split(",")}
csv.field_size_limit(10 ** 8)
EDGES = [0, 20, 40, 80, 160, 320, 600, 900, 1000, 1050, 1100, 1150, 1200, 1300, 1500, 2000, 1e12]
def bin_of(a):
    for i in range(len(EDGES) - 1):
        if a < EDGES[i + 1]:
            return i
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
            h = max(v, key=v.get); want[m * 128 + h] = m + 1
    q = {h: deque() for h in range(8)}              # per host: fresh EVs (deposit time ns, ev)
    pend = {}                                       # (flow, seqno) -> (send time, bin or None)
    st = {s: {} for s in want}                      # bin -> [sends, answered, nack, acks, ecn, rtt sum]
    dep = {s: [0, 0, 0, 0] for s in want}           # deposits, acks, sends, fresh mismatches
    with gzip.open(TR / p.name.replace(".stdout.txt", ".csv.gz"), "rt") as fh:
        for r in csv.DictReader(fh):
            sid = int(r["src_id"])
            h = sid % 128
            if h >= 8:
                continue
            w = sid in want
            e, t = r["event"], float(r["time_ns"])
            if e in ("SEND", "RTX"):
                b = None
                if r["ev_src"] == "fresh_pop" and q[h]:
                    t0, _ = q[h].popleft()
                    b = bin_of((t - t0) / 1000)
                    if e == "SEND" and w:
                        st[sid].setdefault(b, [0, 0, 0, 0, 0, 0.0])[0] += 1
                if e == "SEND" and w:      # the logged `fresh` is the count after this send's pop
                    dep[sid][2] += 1
                    if len(q[h]) != int(r["fresh"]):
                        dep[sid][3] += 1
                pend[(sid, r["seqno"])] = (t, b)
            elif e in ("ACK", "NACK"):
                s = pend.pop((sid, r["seqno"]), None)
                if s and s[1] is not None and w:
                    a = st[sid].setdefault(s[1], [0, 0, 0, 0, 0, 0.0])
                    a[1] += 1; a[5] += (t - s[0]) / 1000
                    if e == "NACK":
                        a[2] += 1
                    else:
                        a[3] += 1; a[4] += r["ecn"] not in ("0", "", "False")
                if e == "ACK":
                    if w:
                        dep[sid][1] += 1
                    if r["ecn"] in ("0", "", "False"):
                        if w:
                            dep[sid][0] += 1
                        if len(q[h]) >= B:
                            q[h].popleft()
                        q[h].append((t, r["ev"]))
    for sid, m in want.items():
        for b, a in sorted(st[sid].items()):
            rows.append(dict(cfg=cfg.replace("msgNh_", "msgN_"), B=B, seed=seed, msg=m, bin=b, lo=EDGES[b], sends=a[0], answered=a[1], nack=a[2], acks=a[3], ecn=a[4], rtt_sum=round(a[5], 1),
                             deposits=dep[sid][0], acks_all=dep[sid][1], sends_all=dep[sid][2], mism=dep[sid][3]))
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows), "rows")
