#!/usr/bin/env python3
"""Per-cell REPS-Bank numbers of the 16-path 5/95 sweep, from the event trace and (for bank cells) the bank log. Hosts 0-15 (ToR0, the degraded sources), messages 2-4 (src_id >= 512 / flow >= 513).
Also run on the REPS and god traces of the same cells (no bank log there) so the arms are measured by the same code.
Columns: cfg,B,seed + sends by source (fresh_pop, bank_pop, random, other: SEND rows), rtx, sends on even EV = slow links, odd EV = fast links (SEND + RTX rows),
bank log (bank cells only, hosts 0-15, messages 2-4): add/rej_ecn/rej_rtt/nosample/pop/expire/overwrite split by EV class (slow = even path, fast = odd path).
usage (in the container): python bank_summary.py <traces dir> <out.csv> [cfg prefix] [B list, comma]   e.g. python bank_summary.py /k16_bank_auto/traces data/bank_cells_auto.csv h512_p16_msgNhBk"""
import re, sys
from pathlib import Path
import pandas as pd
HOSTS = 512
tdir, out = Path(sys.argv[1]), sys.argv[2]
pfx = sys.argv[3] if len(sys.argv) > 3 else ""
Bs = {int(x) for x in sys.argv[4].split(",")} if len(sys.argv) > 4 else None
rows = []
for p in sorted(tdir.glob("*.csv.gz")):
    m = re.match(r"(.+)_B(\d+)_s(\d+)\.csv\.gz", p.name)
    if not m or m.group(1) in () or not m.group(1).startswith(pfx): continue
    cfg, B, seed = m.group(1), int(m.group(2)), int(m.group(3))
    if Bs and B not in Bs: continue
    t = pd.read_csv(p, usecols=["src_id", "event", "ev", "ev_src"], low_memory=False)
    t = t[t.src_id >= HOSTS]                                   # messages 2-4 of hosts 0-15 (the traced flows)
    s = t[t.event == "SEND"]
    r = dict(cfg=cfg, B=B, seed=seed, sends=len(s), rtx=int((t.event == "RTX").sum()))
    for k in ("fresh_pop", "bank_pop", "random"): r[k] = int((s.ev_src == k).sum())
    r["other"] = r["sends"] - r["fresh_pop"] - r["bank_pop"] - r["random"]
    a = t[t.event.isin(["SEND", "RTX"])]
    r["rtx_bank_pop"] = int((t.event.isin(["RTX", "RTS"]) & (t.ev_src == "bank_pop")).sum())
    r["sent_slow"] = int((a.ev % 2 == 0).sum()); r["sent_fast"] = int((a.ev % 2 == 1).sum())
    bl = tdir / p.name.replace(".csv.gz", ".bank.csv.gz")
    if bl.exists():
        b = pd.read_csv(bl, usecols=["kind", "flow", "srcaddr", "ev"])
        b = b[(b.srcaddr < 16) & (b.flow > HOSTS)]
        b["cls"] = (b.ev % 2).map({0: "slow", 1: "fast"})
        for k in ("ADD", "REJ_ECN", "REJ_RTT", "NOSAMPLE", "POP", "EXPIRE", "OVERWRITE"):
            for c in ("slow", "fast"): r[f"{k.lower()}_{c}"] = int(((b.kind == k) & (b.cls == c)).sum())
    rows.append(r); print(cfg, B, seed, flush=True)
pd.DataFrame(rows).to_csv(out, index=False)
