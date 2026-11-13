#!/usr/bin/env python3
"""Token-pool identity check on B=128 traces: N = buf_size + inflight_pkts (valid EVs in the buffer + packets in flight), host 0..7, steady window.
Prediction: N is a ratchet: it rises by 1 only at a send whose EV was drawn at random (ev_src == 'random', buffer empty) and falls by 1 at a marked/NACK ACK;
between those events it is constant. Reports N's range, share of N steps not explained, and corr of N-range with k."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
MT = Path(__file__).resolve().parents[2]
for name in sys.argv[1:]:
    x = pd.read_csv(MT / f"T3/traces/{name}_B128_s42.csv.gz", usecols=["time_ns", "src_id", "event", "ev_src", "ecn", "fresh", "inflight_pkts"])
    res = []
    for src in range(8):
        g = x[x.src_id == src].reset_index(drop=True)
        s = g.time_ns[g.event == "SEND"]; lo, hi = s.min() + .15 * (s.max() - s.min()), s.max() - .15 * (s.max() - s.min())
        g = g[(g.time_ns >= lo) & (g.time_ns <= hi)].reset_index(drop=True)
        g["kill"] = ((g.event == "NACK") | ((g.event == "ACK") & (g.ecn == 1))).astype(int)
        g["seg"] = (g.event == "SEND").cumsum()                     # kills between consecutive sends
        sd = g[g.event == "SEND"].copy(); sd["kills_before"] = g.groupby("seg").kill.sum().reindex(sd.seg - 1).fillna(0).to_numpy()
        N = (sd.fresh + sd.inflight_pkts).to_numpy(); dN = np.diff(N)
        rnd = (sd.ev_src == "random").to_numpy()[1:]; kill = (sd.kills_before.to_numpy()[1:] > 0)
        res.append(dict(N_mean=N.mean(), N_range=N.max() - N.min(), steps_up=(dN > 0).sum(), steps_dn=(dN < 0).sum(), random_sends=rnd.sum(), kills=kill.sum(),
                        up_at_random=((dN > 0) & rnd).sum(), dn_at_kill=((dN < 0) & kill).sum(), n_sends=len(sd)))
    print(name, pd.DataFrame(res).sum().astype(int).to_dict())
