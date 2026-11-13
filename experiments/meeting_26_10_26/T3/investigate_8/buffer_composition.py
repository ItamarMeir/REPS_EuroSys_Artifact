#!/usr/bin/env python3
"""Per-EV attribution on B=128 traces (seed 42, hosts 0-7, steady window): valid-EV buffer composition at each SEND, split into
degraded-path EVs (even) and healthy-path EVs (odd) (EV parity = path parity, even agg degraded). usage: python buffer_composition.py cfg ..."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
MT = Path(__file__).resolve().parents[2]
for name in sys.argv[1:]:
    x = pd.read_csv(MT / f"T3/traces/{name}_B128_s42.csv.gz", usecols=["time_ns", "src_id", "event", "ev", "ev_src", "slots"], dtype={"ev_src": str})
    out = []
    for src in range(8):
        g = x[x.src_id == src]; s = g[g.event == "SEND"]
        lo, hi = s.time_ns.min() + .15 * (s.time_ns.max() - s.time_ns.min()), s.time_ns.max() - .15 * (s.time_ns.max() - s.time_ns.min())
        s = s[(s.time_ns >= lo) & (s.time_ns <= hi)]
        ev_even = s.ev.to_numpy() % 2 == 0
        va, vo = [], []
        for sl in s.slots.to_numpy():
            a = o = 0
            for t in sl.split("|"):
                v, ok, _ = t.split(":")
                if ok == "1":
                    if int(v) % 2 == 0: a += 1
                    else: o += 1
            va.append(a); vo.append(o)
        va, vo = np.array(va), np.array(vo); k = va + vo
        out.append(dict(valid_mean=k.mean(), valid_p99=np.percentile(k, 99), slow_in_buf=va.mean(), fast_in_buf=vo.mean(), slow_share_of_buf=va.sum() / max(k.sum(), 1),
                        slow_share_of_sends=ev_even.mean(), slow_share_of_fresh_sends=(ev_even & (s.ev_src != "random").to_numpy()).sum() / max((s.ev_src != "random").sum(), 1)))
    print(name, {k: round(v, 3) for k, v in pd.DataFrame(out).mean().items()}, flush=True)
