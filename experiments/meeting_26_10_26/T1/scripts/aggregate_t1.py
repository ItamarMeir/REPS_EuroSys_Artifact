#!/usr/bin/env python3
"""T1 results.jsonl (+ reused M4 matched cells) -> data/t1_summary.csv (mean, 95% t-CI over seeds, kdist_*, awdist_*,
gate fields), data/t1_uplinks.json (per-uplink queue stats, seed-mean) and static PNGs."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

H = Path(__file__).resolve().parents[1]
M4 = H.parents[1] / "meeting_23_10_26" / "M4"
t1 = [json.loads(l) for l in (H / "data/results.jsonl").read_text().splitlines()]
m4 = [json.loads(l) for l in (M4 / "data/results.jsonl").read_text().splitlines()]
m4 = [r for r in m4 if r["rate"] == "matched" and r["fail"] in ("uniform50", "nonuniform") and r["seed"] in (42, 43, 44)]
have = {(r["fail"], r["B"], r["seed"]) for r in t1}
df = pd.DataFrame(t1 + [r for r in m4 if (r["fail"], r["B"], r["seed"]) not in have])
df["source"] = np.where(df.apply(lambda r: (r["fail"], r["B"], r["seed"]) in have, axis=1), "t1", "m4_reused")
for c, v in (("n_freeze_events", np.nan), ("frozen_rows", np.nan)):
    if c not in df: df[c] = v
df["gate_clear"] = ((df.rtos == 0) & (df.freeze_entries == 0)).astype(int)
METRICS = ["pct_random", "pct_random_incl_warmup", "k_mean", "k_ge1", "k_ge2", "k_ge3", "k_ge4", "k_ge8", "k_max", "fct_p50", "fct_p99", "fct_max",
           "fct_tor0_mean", "fct_tor0_max", "rtos", "freeze_entries", "n_freeze_events", "frozen_rows", "gate_clear", "ecn_acks", "rtx", "ev_overwrites",
           "pct_overwrite", "clean_acks", "add_mismatch"]
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}
def ci(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return T975[len(x) - 1] * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
KEY = ["rate_gbps", "rate", "fail", "B"]
g = df.groupby(KEY)
summ = g[METRICS].mean().add_suffix("_mean").join(g[METRICS].agg(ci).add_suffix("_ci95")).join(g.size().rename("n_seeds")).reset_index()
def share(h): h = np.asarray(h, float); return 100 * h / h.sum()
for col, n, pre in (("k_hist", 65, "kdist_"), ("aw_hist", 9, "awdist_")):
    s = df[col].apply(share)
    d = s.groupby([df[k] for k in KEY]).apply(lambda x: np.mean(np.vstack(list(x)), axis=0)).reset_index(name="_v")
    for i in range(n): d[f"{pre}{i}"] = d["_v"].apply(lambda a, i=i: a[i])
    summ = summ.merge(d.drop(columns="_v"), on=KEY)
summ.to_csv(H / "data/t1_summary.csv", index=False)
# spray share on the slow (even agg) paths, traced hosts, per cell mean
t = df[df.source == "t1"].copy()
t["slow_share"] = t.send_per_path.apply(lambda v: 100 * sum(v[0::2]) / sum(v))
t.groupby(["fail", "B"]).slow_share.agg(["mean", "std"]).to_csv(H / "data/t1_slow_share.csv")
# per-uplink queue stats from kept queue TSVs (ToR0 -> agg, seed-mean)
import gzip, io
up = {}
for f in sorted((H / "traces").glob("matched_*_s*.queues.tsv.gz")):
    fail, B, seed = f.name.split("_")[1], int(f.name.split("_")[2][1:]), int(f.name.split("_")[3].split(".")[0][1:])
    q = pd.read_csv(io.StringIO(gzip.open(f, "rt").read()), sep="\t")
    q = q[(q.layer == "E->A") & (q.i == 0)].sort_values("j")
    up.setdefault(f"{fail}|{B}", []).append(dict(trims=q.trims.tolist(), data_pkts=q.data_pkts.tolist(), max_q=q.max_q_bytes.tolist()))
json.dump({k: {m: np.mean([r[m] for r in v], axis=0).round(1).tolist() for m in v[0]} for k, v in up.items()}, open(H / "data/t1_uplinks.json", "w"))
# static plots
FAILS = [("uniform50", "r=0.5 (uniform)"), ("nonuniform", "r=0.25"), ("r010", "r=0.10"), ("r005", "r=0.05"), ("r001", "r=0.01")]
def lines(metric, ylabel, fname, logy=False):
    fig, ax = plt.subplots(figsize=(6.5, 4))
    for f, lab in FAILS:
        s = summ[summ.fail == f].sort_values("B")
        if len(s): ax.errorbar(range(len(s)), s[f"{metric}_mean"], s[f"{metric}_ci95"], marker="o", capsize=3, label=lab)
    Bs = sorted(summ.B.unique()); ax.set_xticks(range(len(Bs))); ax.set_xticklabels(Bs); ax.set_xlabel("REPS buffer size B"); ax.set_ylabel(ylabel)
    if logy: ax.set_yscale("log")
    ax.grid(alpha=.3); ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(H / "plots" / fname, dpi=130); plt.close(fig)
lines("fct_max", "max FCT, all flows (us)", "t1_fct_max.png"); lines("fct_p99", "p99 FCT (us)", "t1_fct_p99.png")
lines("pct_overwrite", "valid-EV overwrites (% of clean ACKs)", "t1_pct_overwrite.png"); lines("pct_random", "random draws (%)", "t1_pct_random.png")
print(summ[summ.B == 8][["fail", "fct_max_mean", "pct_random_mean", "pct_overwrite_mean", "rtos_mean", "freeze_entries_mean", "n_seeds"]])
