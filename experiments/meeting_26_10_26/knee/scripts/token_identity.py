#!/usr/bin/env python3
"""Exact token-conservation identity per traced host, counted up to the last draw (SEND/RTX/RTS):
   random draws = draws - clean ACKs + overwrites + c_final        (c_final = valid EVs in the buffer after the last draw's predecessor events)
Then split the change of random draws between B and the converged reference B_ref into  d(draws) - d(clean ACKs) + d(overwrites) + d(c_final)
to see WHY overwrites do or do not become random draws (e.g. lat_m20000: fewer clean ACKs = more kills; or the reference walk ends higher).
usage: python token_identity.py cell B_ref B [B ...]   (cells under ../../T3/traces, seeds 42-44)"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
T = Path(__file__).resolve().parents[2] / "T3/traces"
cell, bref, Bs = sys.argv[1], int(sys.argv[2]), [int(b) for b in sys.argv[3:]]

def host_rows(B, seed):
    x = pd.read_csv(T / f"{cell}_B{B}_s{seed}.csv.gz", low_memory=False, usecols=["time_ns", "src_id", "event", "ev_src", "ecn", "fresh"])
    x["pf"] = x.groupby("src_id")["fresh"].shift(1)
    out = []
    for h, g in x.groupby("src_id"):
        if h > 7: continue
        dr = g[g.event.isin(["SEND", "RTX", "RTS"])]
        last = dr.time_ns.max()
        a = g[(g.event == "ACK") & (g.ecn == 0) & (g.time_ns <= last)]
        before = g[g.time_ns <= last]
        # c_final: valid EVs after processing everything up to the last draw, the last draw's own pop excluded when it was a fresh pop
        c_final = int(before.fresh.iloc[-1])
        out.append(dict(B=B, seed=seed, host=h, draws=len(dr), rnd=int((dr.ev_src == "random").sum()), clean=len(a), ow=int((a.pf >= B).sum()), c_final=c_final,
                        nacks=int(((g.event == "NACK") & (g.time_ns <= last)).sum()), ecn=int(((g.event == "ACK") & (g.ecn == 1) & (g.time_ns <= last)).sum())))
    return out

rows = [r for B in [bref] + Bs for s in (42, 43, 44) for r in host_rows(B, s)]
d = pd.DataFrame(rows)
d["pred"] = d.draws - d.clean + d.ow + d.c_final
d["resid"] = d.rnd - d.pred
print(cell, "identity residual (random - predicted) per B:", d.groupby("B").resid.agg(["mean", "std", "min", "max"]).round(2).to_dict("index"))
ref = d[d.B == bref].set_index(["seed", "host"])
res = []
for B in Bs:
    x = d[d.B == B].set_index(["seed", "host"])
    dd = x - ref
    res.append(dict(B=B, ow=x.ow.mean(), d_rnd=dd.rnd.mean(), d_draws=dd.draws.mean(), d_clean=dd.clean.mean(), d_ow=dd.ow.mean(), d_cfinal=dd.c_final.mean(), d_ecn=dd.ecn.mean(), d_nack=dd.nacks.mean()))
print(pd.DataFrame(res).round(1).to_string(index=False))
