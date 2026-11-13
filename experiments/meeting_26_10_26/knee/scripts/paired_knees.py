#!/usr/bin/env python3
"""Knees with a PAIRED tolerance. Per (cfg, seed, B): mean finish time of the traced ToR0 hosts (and fct_max from results.jsonl). Excess(B) = per-seed difference against the reference B
(the largest B of the cfg, same seed). B is 'ok' if mean excess <= max(0.2% of reference, 1.96 * SE of the paired differences). B_fct = smallest B from which every larger B is ok (one-sided).
B_fct_02 uses the 0.2% threshold only (no noise allowance). usage: python paired_knees.py <hosts_csv...> -> data/paired_knees.csv"""
import sys
import numpy as np, pandas as pd

import json
csvs = [f for f in sys.argv[1:] if f.endswith(".csv")]; jl = [f for f in sys.argv[1:] if f.endswith(".jsonl")]
d = pd.concat([pd.read_csv(f) for f in csvs]).drop_duplicates(["cfg", "B", "seed", "host"])
res = pd.DataFrame([json.loads(l) for f in jl for l in open(f)]).drop_duplicates(["cfg", "B", "seed"])
bad = set(map(tuple, res[(res.rtos > 0) | (res.freeze_entries > 0)][["cfg", "B", "seed"]].values))   # drop cells that entered Freezing Mode / had RTOs
n0 = len(d); d = d[[(c, b, s) not in bad for c, b, s in zip(d.cfg, d.B, d.seed)]]
print(f"dropped {n0 - len(d)} host rows from {len(bad)} gate-failing cells")
ps = d.groupby(["cfg", "B", "seed"]).fin.mean().reset_index()
ow = d.groupby(["cfg", "B"]).apply(lambda g: 100 * g.ow.sum() / g.sends.sum(), include_groups=False).rename("ow_pct").reset_index()
rows = []
for cfg, g in ps.groupby("cfg"):
    Bs = sorted(g.B.unique()); top = max(Bs)
    ref = g[g.B == top].set_index("seed").fin
    out = {}
    for B in Bs:
        x = g[g.B == B].set_index("seed").fin
        diff = (x - ref).dropna()
        n = len(diff)
        se = diff.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
        out[B] = (diff.mean(), se, n)
    refm = ref.mean()
    def knee(tolf):
        ok = {B: out[B][0] <= tolf(out[B][1]) for B in Bs}
        return next(B for B in Bs if all(ok[b] for b in Bs if b >= B))
    t02 = 0.002 * refm
    owc = ow[ow.cfg == cfg].set_index("B").ow_pct
    bow = next((B for B in Bs if all(owc[b] < 0.1 for b in Bs if b >= B)), None)
    rows.append(dict(cfg=cfg, B_fct_paired=knee(lambda se: max(t02, 1.96 * (0 if np.isnan(se) else se))), B_fct_02=knee(lambda se: t02), B_ow=bow, top=top, ref_us=round(refm, 1),
                     thr02=round(t02, 2), **{f"x{B}": f"{out[B][0]:+.1f}({out[B][1]:.1f})" for B in Bs if B <= 64}, ow_top=round(owc[top], 3)))
r = pd.DataFrame(rows)
r.to_csv(sys.argv[0].replace("scripts/paired_knees.py", "data/paired_knees.csv") if "scripts" in sys.argv[0] else "paired_knees.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_colwidth", 20)
print(r.to_string(index=False))
