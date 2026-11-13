#!/usr/bin/env python3
"""Per-cell clean-ACK statistics from B=128 traces (steady window, same trim as T3/scripts/steady_k.py).
Writes investigate_8/data/ack_trains.csv. usage: python ack_trains.py"""
from pathlib import Path
import numpy as np, pandas as pd
MT = Path(__file__).resolve().parents[2]
TRIM = 0.15
CELLS = []   # (study, cfg, shape, path pattern)
for sh in ("nonuniform", "r010", "r005"):
    CELLS.append(("T1", f"T1 {sh}", sh, MT / "T1/traces", f"matched_{sh}_B128_s{{s}}.csv.gz"))
for sub, pre in (("tor_agg", "a"), ("agg_core", "b")):
    for sh in ("u50", "r025", "r010", "r005"):
        CELLS.append(("T2", f"T2 {sub} {sh}", sh, MT / f"T2/{sub}/traces", f"{pre}_{sh}_B128_s{{s}}.csv.gz"))
CELLS.append(("T2", "T2 healthy", "healthy", MT / "T2/tor_agg/traces", "healthy_B128_s{s}.csv.gz"))
for c in ("base_h1024_p32", "h128_p8", "h256_p16", "h512_p32", "h1024_p16", "h1024_p64", "t3_h128_p16", "t3_h1024_p64", "q394_ecn25", "q394_ecn98", "lat4_bdpq"):
    CELLS.append(("T3", f"T3 {c}", "r005", MT / "T3/traces", f"{c}_B128_s{{s}}.csv.gz"))
for c in ("r005_R190", "r005_R180", "r025_R200", "r025_R190"):
    CELLS.append(("F", f"F {c}", c[:4], MT / "T3/traces", f"{c}_B128_s{{s}}.csv.gz"))


def one(path):
    x = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "fresh", "inflight_pkts"])
    out = []
    for src, g in x.groupby("src_id"):
        sd = g[g.event == "SEND"].time_ns; t0, t1 = sd.min(), sd.max(); lo, hi = t0 + TRIM * (t1 - t0), t1 - TRIM * (t1 - t0)
        k = g.fresh.shift(1).fillna(0).astype(int)
        m = g.event.isin(["SEND", "RTX", "RTS"]) & (g.time_ns >= lo) & (g.time_ns <= hi)
        f = g.inflight_pkts[m].to_numpy(float); kk = k[m]
        dd = np.maximum.accumulate(f) - f
        out.append(dict(inf_mean=f.mean(), inf_std=f.std(), inf_range=np.percentile(f, 95) - np.percentile(f, 5), inf_max_minus_mean=f.max() - f.mean(), dd_mean=dd.mean(), k_mean=kk.mean(), k_p99=kk.quantile(.99)))
    return pd.DataFrame(out).mean()
rows = []
for study, cfg, sh, d, pat in CELLS:
    for s in (42, 43, 44, 45, 46):
        p = d / pat.format(s=s)
        if p.exists():
            r = one(p); r["study"], r["cfg"], r["seed"] = study, cfg, s; rows.append(r); print(cfg, s, flush=True)
df = pd.DataFrame(rows); df.to_csv(Path(__file__).parent / "data/inflight_seeds.csv", index=False)
g = df.groupby(["study", "cfg"], sort=False).mean(numeric_only=True).drop(columns="seed"); g.to_csv(Path(__file__).parent / "data/inflight.csv")
pd.set_option("display.width", 200); print(g.round(2).to_string())
d = df[df.cfg != "T2 healthy"]
for c in ("inf_mean", "inf_std", "inf_range", "inf_max_minus_mean", "dd_mean"): print(c, "pearson", round(np.corrcoef(d[c], d.k_mean)[0, 1], 2), "spearman", round(d[c].rank().corr(d.k_mean.rank()), 2))
