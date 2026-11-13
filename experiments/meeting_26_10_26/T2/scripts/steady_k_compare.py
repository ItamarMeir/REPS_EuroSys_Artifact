#!/usr/bin/env python3
"""Steady-state k p99 (B=128 traces; first and last 15% of each traced source's span dropped; same k as run_m4.analyze) on the SAME host subsets,
to compare T2 A (16 pod0 hosts traced) with T3 t3_h128_p16 (hosts 0-3, one ToR degraded) and T1 (hosts 0-7 of ToR0, 2-tier 1024).
Writes T2/data/steady_k_compare.csv. usage: python steady_k_compare.py"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

MT = Path(__file__).resolve().parents[2]
TRIM = 0.15


def steady(path, hosts):
    x = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "fresh"])
    x = x[x.src_id.isin(hosts)]
    gg = x.groupby("src_id")
    x["k"] = gg.fresh.shift(1).fillna(0).astype(int)
    x["seen_ack"] = gg.event.transform(lambda v: (v == "ACK").cummax())
    d = x[x.event.isin(["SEND", "RTX", "RTS"]) & x.seen_ack]
    gt = d.groupby("src_id").time_ns
    rel = (d.time_ns - gt.transform("min")) / (gt.transform("max") - gt.transform("min"))
    k = d.k[(rel >= TRIM) & (rel <= 1 - TRIM)]
    return float(k.quantile(.5)), float(k.quantile(.99)), int(k.max())


rows = []
for sub, pre, shapes in (("tor_agg", "a", ["u50", "r025", "r010", "r005"]), ("agg_core", "b", ["u50", "r025", "r010", "r005"])):
    for sh in shapes:
        for hosts, tag in ((range(16), "T2 all 16 pod0 hosts"), (range(8), "T2 hosts 0-7 (ToR0+ToR1)"), (range(4), "T2 hosts 0-3 (ToR0)")):
            v = [steady(MT / "T2" / sub / "traces" / f"{pre}_{sh}_B128_s{sd}.csv.gz", list(hosts)) for sd in (42, 43, 44, 45, 46)]
            rows.append(dict(source=f"T2 {sub}", shape=sh, hosts=tag, seeds=5, p50=np.mean([a[0] for a in v]), p99=np.mean([a[1] for a in v]), max=np.mean([a[2] for a in v])))
t3 = MT / "T3" / "traces"
for sd in (42, 43, 44):
    p = t3 / f"t3_h128_p16_B128_s{sd}.csv.gz"
    if p.exists():
        a = steady(p, [0, 1, 2, 3]); rows.append(dict(source="T3 t3_h128_p16 (ToR0 only degraded 5/95)", shape="r005", hosts=f"hosts 0-3 seed {sd}", seeds=1, p50=a[0], p99=a[1], max=a[2]))
for sh, f in (("nonuniform", "25/75"), ("r010", "10/90"), ("r005", "5/95")):
    v = []
    for sd in (42, 43, 44):
        p = MT / "T1" / "traces" / f"matched_{sh}_B128_s{sd}.csv.gz"
        if p.exists(): v.append(steady(p, list(range(8))))
    if v:
        rows.append(dict(source="T1 2-tier 1024h", shape=f, hosts="hosts 0-7 (ToR0)", seeds=len(v), p50=np.mean([a[0] for a in v]), p99=np.mean([a[1] for a in v]), max=np.mean([a[2] for a in v])))
out = pd.DataFrame(rows); out.to_csv(MT / "T2" / "data" / "steady_k_compare.csv", index=False)
pd.set_option("display.width", 220); print(out.round(2).to_string(index=False))
