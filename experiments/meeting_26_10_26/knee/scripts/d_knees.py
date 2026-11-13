#!/usr/bin/env python3
"""Knees per config from kneeout traces. Per (cfg, B, seed, host 0..H0-1 traced): finish (last ACK), sends, random draws, overwrites (clean ACK before the last draw arriving with a full buffer).
Knee rules: B_fct = smallest B such that for every B' >= B (grid) mean ToR0-traced-host FCT is within max(0.2% of ref, 1.96*SE) of B=128 or better (one-sided); B_ow = smallest B with overwrites < 0.1% of sends.
usage: python d_knees.py <traces_dir> <out_csv> [cfg ...]"""
import sys, re
from pathlib import Path
import numpy as np, pandas as pd
TR = Path(sys.argv[1]); OUT = Path(sys.argv[2]); only = set(sys.argv[3:])
rows = []
for p in sorted(TR.glob("*.csv.gz")):
    if p.name.endswith(".queues.tsv.gz"): continue
    m = re.match(r"(.+)_B(\d+)_s(\d+)\.csv\.gz", p.name)
    cfg, B, s = m.group(1), int(m.group(2)), int(m.group(3))
    if only and cfg not in only: continue
    x = pd.read_csv(p, low_memory=False, usecols=["time_ns", "src_id", "event", "ev", "ev_src", "ecn", "fresh"])
    x["pf"] = x.groupby("src_id")["fresh"].shift(1)
    for h, g in x.groupby("src_id"):
        sn = g[g.event.isin(["SEND", "RTX", "RTS"])]; a = g[g.event == "ACK"]
        cl = a[(a.ecn == 0) & (a.time_ns <= sn.time_ns.max())]
        rows.append(dict(cfg=cfg, B=B, seed=s, host=h, fin=a.time_ns.max() / 1000, sends=len(sn), rnd=int((sn.ev_src == "random").sum()),
                         rnd_deg=int(((sn.ev_src == "random") & (sn.ev % 2 == 0)).sum()), ow=int((cl.pf >= B).sum()), ecn=int((a.ecn == 1).sum())))
d = pd.DataFrame(rows); d.to_csv(OUT.with_name(OUT.stem + "_hosts.csv"), index=False)
res = []
for cfg, g in d.groupby("cfg"):
    ps = g.groupby(["B", "seed"]).agg(fin=("fin", "mean"), fmax=("fin", "max"), sends=("sends", "sum"), ow=("ow", "sum"), rnd=("rnd", "sum"), ecn=("ecn", "sum")).reset_index()
    Bs = sorted(ps.B.unique()); ref = ps[ps.B == max(Bs)].fin
    refm, tol = ref.mean(), max(0.002 * ref.mean(), 1.96 * ref.std(ddof=1) / np.sqrt(len(ref)) if len(ref) > 1 else 0)
    summ = ps.groupby("B").agg(fin=("fin", "mean"), fmax=("fmax", "mean"), ow=("ow", "sum"), sends=("sends", "sum"), rnd=("rnd", "sum"), ecn=("ecn", "mean")).reset_index()
    summ["ow_pct"] = 100 * summ.ow / summ.sends; summ["rnd_pct"] = 100 * summ.rnd / summ.sends
    ok = {r.B: (r.fin - refm) <= tol for r in summ.itertuples()}
    bfct = next((B for B in Bs if all(ok[b] for b in Bs if b >= B)), None)
    bow = next((r.B for r in summ.itertuples() if all(summ[summ.B >= r.B].ow_pct < 0.1)), None)
    for r in summ.itertuples():
        res.append(dict(cfg=cfg, B=r.B, fin=round(r.fin, 2), d_fin=round(r.fin - refm, 2), fmax=round(r.fmax, 2), ow_pct=round(r.ow_pct, 3), rnd_pct=round(r.rnd_pct, 2), ecn=round(r.ecn, 1), B_fct=bfct, B_ow=bow, tol=round(tol, 2)))
r = pd.DataFrame(res); r.to_csv(OUT, index=False)
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 500)
print(r.to_string(index=False))
