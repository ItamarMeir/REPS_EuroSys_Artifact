#!/usr/bin/env python3
"""Transient check for the uncapped k tail (B=128 cells, seed 42): k at each SEND vs time since the flow's first send,
whole run vs steady state (drop the first and last TRIM fraction of each source's active span).
Writes data/t3_steady_k.csv and data/t3_k_timeseries.json (max k per 20 us bin, per config)."""
import json, sys, gzip
from pathlib import Path
import numpy as np, pandas as pd
H = Path(__file__).resolve().parents[1]
CFGS = [c["name"] for c in json.loads((H / "data/configs/configs.json").read_text())]
SEEDS = [int(x) for x in sys.argv[1:]] or [42]
TRIM = 0.15; BIN = 20_000  # ns
rows, ts = [], {}
for c, sd in [(c, sd) for c in CFGS for sd in SEEDS if (H / f"traces/{c}_B128_s{sd}.csv.gz").exists()]:
    df = pd.read_csv(H / f"traces/{c}_B128_s{sd}.csv.gz", usecols=["time_ns", "src_id", "event", "fresh"])
    # same k as run_m4.analyze: previous row post-event fresh of the same source, draws SEND/RTX/RTS after the first ACK
    gg = df.groupby("src_id")
    df["k"] = gg.fresh.shift(1).fillna(0).astype(int)
    df["seen_ack"] = gg.event.transform(lambda x: (x == "ACK").cummax())
    s = df[df.event.isin(["SEND", "RTX", "RTS"]) & df.seen_ack].copy()
    g = s.groupby("src_id").time_ns
    t0, t1 = g.transform("min"), g.transform("max")
    rel = (s.time_ns - t0) / (t1 - t0)
    for name, m in (("all", rel >= 0), ("steady", (rel >= TRIM) & (rel <= 1 - TRIM)), ("first", rel < TRIM), ("last", rel > 1 - TRIM)):
        k = s.k[m]
        rows.append(dict(cfg=c, seed=sd, part=name, draws=",".join(f"{e}:{int(((s.event==e)&m).sum())}" for e in ("SEND","RTX","RTS")), n=int(len(k)), p50=float(k.quantile(.5)), p99=float(k.quantile(.99)), p999=float(k.quantile(.999)), max=int(k.max())))
    b = ((s.time_ns - t0) // BIN).astype(int)
    ts[f"{c}|{sd}"] = [int(v) for v in s.k.groupby(b).max().reindex(range(int(b.max()) + 1)).fillna(0)]
pd.DataFrame(rows).to_csv(H / "data/t3_steady_k.csv", index=False)
json.dump(dict(bin_us=BIN / 1000, trim=TRIM, series=ts), open(H / "data/t3_k_timeseries.json", "w"))
print(pd.DataFrame(rows).to_string(index=False))
