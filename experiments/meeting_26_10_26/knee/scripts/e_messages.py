#!/usr/bin/env python3
"""Dial E: per-message FCT of repeated messages on the same src-dst pair (4 messages per pair, one per P us). Reads the stdout of each cell
('Flow ... flowId N uecSrc K ... finished at T': T is the FCT; message m = (N-1)//128, source host = K % 128; hosts 0-7 = ToR0, the degraded ones).
Per (cfg, B, seed): mean FCT of messages 0 (fresh buffer: control) and 1-3 (buffer carried over) for hosts 0-7, paired excess against the same seed at B_ref
(largest B). Knee rule (paired): smallest B from which every larger B has mean paired excess <= max(0.2% of the reference, 1.96 SE of the paired differences).
usage: python e_messages.py <traces_dir> [cfg ...] -> data/e_messages.csv"""
import re, sys
from pathlib import Path
import numpy as np, pandas as pd
TR = Path(sys.argv[1]); only = set(sys.argv[2:])
import json
RES = Path(__file__).resolve().parents[1] / "data/e_results.jsonl"
bad = set()
if RES.exists():   # drop cells that entered Freezing Mode / had RTOs (gate), as everywhere else
    bad = {(d['cfg'], d['B'], d['seed']) for d in map(json.loads, RES.read_text().splitlines()) if d['rtos'] > 0 or d['freeze_entries'] > 0}
rows = []
for p in sorted(TR.glob("*.stdout.txt")):
    m = re.match(r"(.+)_B(\d+)_s(\d+)\.stdout\.txt", p.name)
    cfg, B, s = m.group(1), int(m.group(2)), int(m.group(3))
    if only and cfg not in only: continue
    if (cfg, B, s) in bad: continue
    f = {}
    for l in p.read_text(errors="ignore").splitlines():
        mm = re.search(r"flowId (\d+) .*uecSrc (\d+) finished at ([0-9.]+)", l)
        if mm and l.startswith("Flow"):
            fid, src, t = int(mm.group(1)), int(mm.group(2)), float(mm.group(3))
            f[(( fid - 1) // 128, src % 128)] = t
    for msg in range(4):
        v = [f[(msg, h)] for h in range(8) if (msg, h) in f]
        allv = [t for (mg, h), t in f.items() if mg == msg]
        rows.append(dict(cfg=cfg, B=B, seed=s, msg=msg, n=len(v), mean_tor0=np.mean(v) if v else np.nan, max_all=max(allv) if allv else np.nan))
d = pd.DataFrame(rows)
res = []
for cfg, g in d.groupby("cfg"):
    for label, msgs in (("msg0 (fresh buffer)", [0]), ("msgs1-3 (carried over)", [1, 2, 3])):
        x = g[g.msg.isin(msgs)].groupby(["B", "seed"]).mean_tor0.mean().reset_index()
        Bs = sorted(x.B.unique()); top = max(Bs)
        ref = x[x.B == top].set_index("seed").mean_tor0
        out = {}
        for B in Bs:
            dd = (x[x.B == B].set_index("seed").mean_tor0 - ref).dropna()
            out[B] = (dd.mean(), dd.std(ddof=1) / np.sqrt(len(dd)) if len(dd) > 1 else 0.0)
        t02 = 0.002 * ref.mean()
        knee = next(B for B in Bs if all(out[b][0] <= max(t02, 1.96 * out[b][1]) for b in Bs if b >= B))
        res.append(dict(cfg=cfg, group=label, ref_us=round(ref.mean(), 2), thr02=round(t02, 3), B_fct_paired=knee,
                        **{f"x{B}": f"{out[B][0]:+.2f}({out[B][1]:.2f})" for B in Bs if B < top}))
r = pd.DataFrame(res)
d.to_csv(Path(__file__).resolve().parents[1] / "data/e_messages_cells.csv", index=False)
r.to_csv(Path(__file__).resolve().parents[1] / "data/e_messages.csv", index=False)
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 16)
print(r.to_string(index=False))
