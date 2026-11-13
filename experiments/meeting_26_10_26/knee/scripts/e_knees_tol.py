#!/usr/bin/env python3
"""Dial E knees on the metric of T1/T2 (max FCT) and for several tolerances, from the stdout files of repeated-message cells.
For each cfg/B/seed: message m = (flowId-1)//N, source host = uecSrc % N; per message the MAX and the MEAN FCT over the degraded sources (hosts < NH).
Paired excess = per-seed difference against the same seed at the largest B (B_ref). B is 'ok' if mean paired excess <= max(tol * reference, 1.96 * SE);
knee = smallest B from which every larger B is ok; reported for tol = 0.2%, 1%, 2%, 5%. Gate-failing cells (rtos / freeze entries > 0) are dropped.
usage: python e_knees_tol.py <traces_dir> <results.jsonl> <N hosts> <NH degraded sources> <out.csv> [cfg ...]"""
import json, re, sys
from pathlib import Path
import numpy as np, pandas as pd
TR, RES, N, NH, OUT = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
only = set(sys.argv[6:])
bad = {(d["cfg"], d["B"], d["seed"]) for d in map(json.loads, RES.read_text().splitlines()) if d["rtos"] > 0 or d["freeze_entries"] > 0}
rows = []
for p in sorted(TR.glob("*.stdout.txt")):
    m = re.match(r"(.+)_B(\d+)_s(\d+)\.stdout\.txt", p.name)
    cfg, B, s = m.group(1), int(m.group(2)), int(m.group(3))
    if (only and cfg not in only) or (cfg, B, s) in bad: continue
    f = {}
    for l in p.read_text(errors="ignore").splitlines():
        mm = re.search(r"flowId (\d+) .*uecSrc (\d+) finished at ([0-9.]+)", l)
        if mm and l.startswith("Flow"):
            f[((int(mm.group(1)) - 1) // N, int(mm.group(2)) % N)] = float(mm.group(3))
    for msg in sorted({k[0] for k in f}):
        v = [t for (mg, h), t in f.items() if mg == msg and h < NH]
        if v: rows.append(dict(cfg=cfg, B=B, seed=s, msg=msg, n=len(v), mean=np.mean(v), max=max(v)))
d = pd.DataFrame(rows)
res = []
for cfg, g in d.groupby("cfg"):
    for msgs, label in (([0], "message 1 (fresh buffer)"), (sorted(set(g.msg) - {0}), "later messages (carried over)")):
        for metric in ("max", "mean"):
            x = g[g.msg.isin(msgs)].groupby(["B", "seed"])[metric].mean().reset_index()
            Bs = sorted(x.B.unique()); top = max(Bs)
            ref = x[x.B == top].set_index("seed")[metric]
            out = {}
            for B in Bs:
                dd = (x[x.B == B].set_index("seed")[metric] - ref).dropna()
                out[B] = (dd.mean(), dd.std(ddof=1) / np.sqrt(len(dd)) if len(dd) > 1 else 0.0, len(dd))
            r = dict(cfg=cfg, group=label, metric=metric, ref_us=round(ref.mean(), 1), B_ref=top, seeds=len(ref))
            for tol in (0.002, 0.01, 0.02, 0.05):
                r[f"knee_{tol * 100:g}pct"] = next(B for B in Bs if all(out[b][0] <= max(tol * ref.mean(), 1.96 * out[b][1]) for b in Bs if b >= B))
            for B in Bs:
                if B < top: r[f"x{B}"] = f"{out[B][0]:+.1f}({out[B][1]:.1f})"
            res.append(r)
r = pd.DataFrame(res); r.to_csv(OUT, index=False)
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40); pd.set_option("display.max_colwidth", 14)
print(r.to_string(index=False))
