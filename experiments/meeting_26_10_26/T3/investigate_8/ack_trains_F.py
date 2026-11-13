#!/usr/bin/env python3
"""Per-cell clean-ACK statistics from B=128 traces (steady window, same trim as T3/scripts/steady_k.py).
Writes investigate_8/data/ack_trains_F.csv. usage: python ack_trains.py"""
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
    x = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "ecn", "seqno", "fresh"])
    out = []
    send_t = x[x.event == "SEND"].drop_duplicates(["src_id", "seqno"]).set_index(["src_id", "seqno"]).time_ns
    for src, g in x.groupby("src_id"):
        g = g.reset_index(drop=True)
        g["k"] = g.fresh.shift(1).fillna(0).astype(int)
        t0, t1 = g.time_ns[g.event == "SEND"].min(), g.time_ns[g.event == "SEND"].max()
        lo, hi = t0 + TRIM * (t1 - t0), t1 - TRIM * (t1 - t0)
        w = g[(g.time_ns >= lo) & (g.time_ns <= hi)]
        a = w[w.event.isin(["ACK", "NACK"])]
        marked = ((a.event == "NACK") | (a.ecn == 1)).to_numpy()
        # clean-ACK run lengths between non-clean ACKs
        runs, c = [], 0
        for m in marked:
            if m: runs.append(c); c = 0
            else: c += 1
        # RTT of clean ACKs
        ack = a[(a.event == "ACK") & (a.ecn != 1)]
        st = send_t.reindex(pd.MultiIndex.from_arrays([ack.src_id, ack.seqno])).to_numpy()
        rtt = ack.time_ns.to_numpy() - st; rtt = rtt[~np.isnan(rtt)]
        # M(t) = clean ACKs - sends on a 1 us grid; std of the change over horizons
        grid = np.arange(lo, hi, 1000.0)
        cum = lambda ts: np.searchsorted(np.sort(ts), grid, side="right")
        M = cum(ack.time_ns.to_numpy()) - cum(w.time_ns[w.event == "SEND"].to_numpy())
        d = {H: np.std(M[H:] - M[:-H]) for H in (5, 20, 100)}
        tt = np.concatenate([ack.time_ns.to_numpy(), w.time_ns[w.event == 'SEND'].to_numpy()]); sg = np.concatenate([np.ones(len(ack)), -np.ones((w.event == 'SEND').sum())])
        o = np.argsort(tt); Mev = np.cumsum(sg[o]); slope = np.polyfit(tt[o], Mev, 1)[0] * 1000; cmean = (Mev - np.minimum.accumulate(Mev)).mean()
        kk = w.k[w.event.isin(["SEND", "RTX", "RTS"])]
        out.append(dict(p=marked.mean(), run_mean=np.mean(runs) if runs else np.nan, run_p50=np.median(runs) if runs else np.nan, run_p99=np.percentile(runs, 99) if runs else np.nan,
                        rtt_std=rtt.std() / 1000, rtt_spread=(np.percentile(rtt, 99) - np.percentile(rtt, 50)) / 1000, M_std5=d[5], M_std20=d[20], M_std100=d[100],
                        slope=slope, c_replay=cmean, k_mean=kk.mean(), k_p90=kk.quantile(.9), k_p99=kk.quantile(.99)))
    return pd.DataFrame(out).mean()


CELLS = [c for c in CELLS if c[0] == 'F']
rows = []
for study, cfg, sh, d, pat in CELLS:
    for s in (42, 43, 44, 45, 46):
        p = d / pat.format(s=s)
        if p.exists():
            r = one(p); r["study"], r["cfg"], r["shape"], r["seed"] = study, cfg, sh, s; rows.append(r); print(cfg, s, flush=True)
df = pd.DataFrame(rows); (Path(__file__).parent / "data").mkdir(exist_ok=True)
df.to_csv(Path(__file__).parent / "data/ack_trains_seeds_F.csv", index=False)
g = df.groupby(["study", "cfg"], sort=False).mean(numeric_only=True).drop(columns="seed"); g["n_seeds"] = df.groupby(["study", "cfg"], sort=False).size()
g.to_csv(Path(__file__).parent / "data/ack_trains_F.csv"); pd.set_option("display.width", 250); print(g.round(2).to_string())
