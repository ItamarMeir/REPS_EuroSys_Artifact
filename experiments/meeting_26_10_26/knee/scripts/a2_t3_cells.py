#!/usr/bin/env python3
"""Phase A2 (advisor checkpoint 1): the random-draw cost model on the T3 cells that broke earlier readings. Per cell and B: overwrites (before the last send), extra random draws vs B=128,
extra draws on degraded-capacity EVs (even) and on extra-latency EVs (ev%4 in {2,3}), draws followed by a kill (ECN/trim: next ACK of that packet marked is not observable here, so we use the share of
random draws whose EV is later absent: skipped), mean FCT excess. usage: python a2_t3_cells.py -> data/a2_cells.csv"""
from pathlib import Path
import numpy as np, pandas as pd
EXP = Path(__file__).resolve().parents[2]
T = EXP / "T3/traces"
CELLS = ["base_h1024_p32", "q394_ecn98", "lat4_bdpq", "lat_m5000", "lat_m20000", "r025_R200", "r020_R200"]
SEEDS = (42, 43, 44)
rows = []
for c in CELLS:
    for B in (2, 4, 6, 8, 12, 16, 32, 128):
        for s in SEEDS:
            p = T / f"{c}_B{B}_s{s}.csv.gz"
            if not p.exists(): continue
            x = pd.read_csv(p, low_memory=False, usecols=["time_ns", "src_id", "event", "ev", "ev_src", "ecn", "fresh"])
            x["pfresh"] = x.groupby("src_id")["fresh"].shift(1)
            for h, g in x.groupby("src_id"):
                if h > 7: continue
                snd = g[g.event.isin(["SEND", "RTX", "RTS"])]; ack = g[g.event == "ACK"]
                rnd = snd[snd.ev_src == "random"]
                clean = ack[(ack.ecn == 0) & (ack.time_ns <= snd.time_ns.max())]
                rows.append(dict(cell=c, B=B, seed=s, host=h, finish_us=ack.time_ns.max() / 1000, rnd=len(rnd), rnd_deg=int((rnd.ev % 2 == 0).sum()),
                                 rnd_slow=int((rnd.ev % 4 >= 2).sum()), ow=int((clean.pfresh >= B).sum()), ecn_acks=int((ack.ecn == 1).sum())))
    print(c, flush=True)
d = pd.DataFrame(rows)
base = d[d.B == 128].set_index(["cell", "seed", "host"])
for k in ("finish_us", "rnd", "rnd_deg", "rnd_slow"):
    d["d_" + k] = d[k].values - base.loc[list(zip(d.cell, d.seed, d.host)), k].values
cells = d.groupby(["cell", "B"]).agg(ow=("ow", "mean"), d_rnd=("d_rnd", "mean"), d_rnd_deg=("d_rnd_deg", "mean"), d_rnd_slow=("d_rnd_slow", "mean"),
                                    d_finish=("d_finish_us", "mean"), rnd=("rnd", "mean"), ecn_acks=("ecn_acks", "mean")).reset_index()
cells["conv"] = cells.d_rnd / cells.ow
cells["us_per_deg_draw"] = cells.d_finish / cells.d_rnd_deg
cells.to_csv(EXP / "knee/data/a2_cells.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print(cells[cells.B.isin([4, 6, 8, 12, 16])].round(2).to_string())
