#!/usr/bin/env python3
"""N sweep, N = 789: per-class (random vs recycled) cost of the sends of the max-FCT host of messages 2-4 (run in the container).
For each send the first later ACK or NACK with the same seqno is its outcome: trimmed (NACK), ECN-marked (ACK ecn), RTT (response time - send time).
usage: python n_cost.py <traces_dir> <out.csv> <cfg_substring> <B,B,...>"""
import csv, gzip, re, sys
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
            h = max(v, key=v.get); want[m * 128 + h] = m + 1
    pend = {}                      # (flow, seqno) -> (time_ns, ev_src), the latest send of that seqno
    st = {}                        # (flow, class) -> [sends, answered, nack, ecn_acks, acks, rtt list]
    with gzip.open(TR / p.name.replace(".stdout.txt", ".csv.gz"), "rt") as fh:
        for r in csv.DictReader(fh):
            sid = int(r["src_id"])
            if sid not in want:
                continue
            e = r["event"]
            if e in ("SEND", "RTX"):
                pend[(sid, r["seqno"])] = (float(r["time_ns"]), r["ev_src"])
                if e == "SEND":
                    st.setdefault((sid, r["ev_src"]), [0, 0, 0, 0, 0, []])[0] += 1
            elif e in ("ACK", "NACK"):
                s = pend.pop((sid, r["seqno"]), None)
                if s is None:
                    continue
                a = st.setdefault((sid, s[1]), [0, 0, 0, 0, 0, []])
                a[1] += 1
                a[5].append((float(r["time_ns"]) - s[0]) / 1000)
                if e == "NACK":
                    a[2] += 1
                else:
                    a[4] += 1
                    a[3] += r["ecn"] not in ("0", "", "False")
    for (sid, cl), a in st.items():
        rt = sorted(a[5])
        rows.append(dict(cfg=cfg.replace("msgNh_", "msgN_"), B=B, seed=seed, msg=want[sid], cls=cl, sends=a[0], answered=a[1], nack=a[2], acks=a[4], ecn=a[3],
                         rtt_mean=round(sum(rt) / len(rt), 2) if rt else "", rtt_p99=round(rt[int(.99 * (len(rt) - 1))], 2) if rt else ""))
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows), "rows")
