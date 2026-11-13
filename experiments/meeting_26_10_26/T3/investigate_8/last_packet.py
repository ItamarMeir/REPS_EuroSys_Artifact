#!/usr/bin/env python3
"""Which packet ends each traced flow (hosts 0-7 of ToR0)? For the packet whose ACK arrives last: its EV parity (even = degraded path), how the EV was chosen
(ev_src random vs recycled), its RTT, and the flow's finish time (last ACK time - first send). usage: python last_packet.py"""
from pathlib import Path
import numpy as np, pandas as pd
T = Path(__file__).resolve().parents[1] / "traces"
rows = []
for c in ("base_h1024_p32", "q394_ecn25", "q394_ecn98", "lat4_bdpq"):
    for B in (8, 128):
        for s in (42, 43, 44):
            x = pd.read_csv(T / f"{c}_B{B}_s{s}.csv.gz", usecols=["time_ns", "src_id", "event", "ev", "ev_src", "ecn", "seqno"], dtype={"ev_src": str})
            snd = x[x.event.isin(["SEND", "RTX"])]; ack = x[x.event == "ACK"]
            for src in range(8):
                a = ack[ack.src_id == src]; sd = snd[snd.src_id == src]
                last = a.loc[a.time_ns.idxmax()]
                sent = sd[(sd.seqno == last.seqno)].iloc[0]
                rows.append(dict(cfg=c, B=B, seed=s, src=src, fin=(last.time_ns - sd.time_ns.min()) / 1000, last_even=int(last.ev) % 2 == 0, last_random=sent.ev_src == "random",
                                 last_rtt=(last.time_ns - sent.time_ns) / 1000, last_marked=last.ecn == 1))
d = pd.DataFrame(rows); d.to_csv(Path(__file__).parent / "data/last_packet.csv", index=False)
g = d.groupby(["cfg", "B"]).agg(n=("fin", "size"), fin_mean=("fin", "mean"), last_on_degraded=("last_even", "mean"), last_random=("last_random", "mean"), last_rtt=("last_rtt", "mean"), last_marked=("last_marked", "mean"))
print(g.round(3).to_string())
