#!/usr/bin/env python3
"""(a) marked share of ACKs on degraded (even) EVs, (b) share of sends on degraded EVs in the last 15% of each flow vs the steady 15-85%, B=8 vs 128, hosts 0-7, seeds 42-44."""
from pathlib import Path
import numpy as np, pandas as pd
T = Path(__file__).resolve().parents[1] / "traces"
rows = []
for c in ("base_h1024_p32", "q394_ecn25", "q394_ecn98", "lat4_bdpq"):
    for B in (8, 128):
        for s in (42, 43, 44):
            x = pd.read_csv(T / f"{c}_B{B}_s{s}.csv.gz", usecols=["time_ns", "src_id", "event", "ev", "ecn"])
            for src in range(8):
                g = x[x.src_id == src]; sd = g[g.event.isin(["SEND", "RTX"])]; a = g[g.event == "ACK"]
                t0, t1 = sd.time_ns.min(), sd.time_ns.max(); rel = (sd.time_ns - t0) / (t1 - t0); ev = sd.ev.to_numpy() % 2 == 0
                ae = a[a.ev % 2 == 0]
                rows.append(dict(cfg=c, B=B, seed=s, src=src, mark_even=(ae.ecn == 1).mean() if len(ae) else np.nan, send_even_steady=ev[((rel >= .15) & (rel <= .85)).to_numpy()].mean(),
                                 send_even_tail=ev[(rel > .85).to_numpy()].mean()))
d = pd.DataFrame(rows); d.to_csv(Path(__file__).parent / "data/tail_share.csv", index=False)
print(d.groupby(["cfg", "B"])[["mark_even", "send_even_steady", "send_even_tail"]].mean().round(3).to_string())
