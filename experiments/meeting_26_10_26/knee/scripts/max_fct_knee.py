#!/usr/bin/env python3
"""Knee on the max FCT over all flows (the metric of T1/T2): same one-sided rule as d_knees.py, on fct_max of results.jsonl.
usage: python max_fct_knee.py data/d1_results.jsonl ... -> data/max_fct_knees.csv"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
d = pd.DataFrame(rows)[["cfg", "B", "seed", "fct_max"]].drop_duplicates(["cfg", "B", "seed"])
out = []
for cfg, g in d.groupby("cfg"):
    Bs = sorted(g.B.unique()); top = max(Bs); ref = g[g.B == top].fct_max
    refm = ref.mean(); tol = max(0.002 * refm, 1.96 * ref.std(ddof=1) / np.sqrt(len(ref)) if len(ref) > 1 else 0)
    m = g.groupby("B").fct_max.mean()
    ok = {B: m[B] - refm <= tol for B in Bs}
    knee = next(B for B in Bs if all(ok[b] for b in Bs if b >= B))
    out.append(dict(cfg=cfg, B_fct_max=knee, tol=round(tol, 2), n_seeds=len(ref), floor=round(refm, 1), **{f"x{B}": round(m[B] - refm, 1) for B in (1, 2, 4, 6, 8, 12) if B in m.index}))
r = pd.DataFrame(out); r.to_csv("data/max_fct_knees.csv", index=False)
pd.set_option("display.width", 200); print(r.to_string(index=False))
