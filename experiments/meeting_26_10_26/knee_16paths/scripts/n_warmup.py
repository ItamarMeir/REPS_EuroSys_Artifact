#!/usr/bin/env python3
"""Warmup of REPS in message 1 (hosts 0-15, message 1 of the single traced pass): all SEND events from the start until the first valid-EV send (ev_src fresh_pop), that send excluded.
Per (cfg, B, seed, host): n_warm (sends before the first fresh_pop), the labels seen among them, time of the first ACK, of the first unmarked ACK (first deposit), of the first fresh_pop;
sends in flight at the first fresh_pop; bad_share = share of warmup sends on a 5% path (ev % 16 even).
usage: python n_warmup.py <msgN traces dir> <out.csv> [cfg_substring]"""
import csv, gzip, re, sys
from collections import Counter
from pathlib import Path
import params as Pm
TR, OUT = Path(sys.argv[1]), sys.argv[2]
SEL = sys.argv[3] if len(sys.argv) > 3 else ""
csv.field_size_limit(10 ** 8)
rows = []
for p in sorted(TR.glob("*.csv.gz")):
    mt = re.match(r"(.+)_B(\d+)_s(\d+)\.csv\.gz", p.name)
    if not mt or SEL not in mt.group(1) or p.name.endswith("queues.tsv.gz"):
        continue
    cfg, B, seed = mt.group(1), int(mt.group(2)), int(mt.group(3))
    st = {h: dict(n=0, labels=Counter(), bad=0, t_ack=None, t_dep=None, t_fresh=None, done=False, first_send=None, sends_t_ack=None) for h in range(Pm.NH)}
    with gzip.open(p, "rt") as fh:
        for r in csv.DictReader(fh):
            sid = int(r["src_id"])
            if sid >= Pm.NH:
                continue
            s = st[sid]
            ev = r["event"]
            t = float(r["time_ns"])
            if ev == "SEND":
                if s["done"]:
                    continue
                if s["first_send"] is None:
                    s["first_send"] = t
                if r["ev_src"] == "fresh_pop":
                    s["done"], s["t_fresh"] = True, t
                    continue
                s["n"] += 1
                s["labels"][r["ev_src"]] += 1
                s["bad"] += int(r["ev"]) % 2 == 0
            elif ev == "ACK" and not s["done"]:
                if s["t_ack"] is None:
                    s["t_ack"], s["sends_t_ack"] = t, s["n"]
                if r["ecn"] == "0" and s["t_dep"] is None:
                    s["t_dep"] = t
    for h, s in st.items():
        rows.append(dict(cfg=cfg, B=B, seed=seed, host=h, n_warm=s["n"], labels="|".join(f"{k}:{v}" for k, v in sorted(s["labels"].items())), bad_share=round(s["bad"] / max(s["n"], 1), 4),
                         t_first_send=s["first_send"], t_first_ack=s["t_ack"], sends_at_first_ack=s["sends_t_ack"], t_first_deposit=s["t_dep"], t_first_fresh=s["t_fresh"], found=s["done"]))
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), "rows")
