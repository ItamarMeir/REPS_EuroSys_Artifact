#!/usr/bin/env python3
"""T3 results.jsonl -> data/t3_summary.csv (mean, 95% t-CI over seeds, kdist_*, awdist_*, gate), data/t3_knees.csv
(per config: uncapped-k percentiles at the largest B, the three knees B_fct / B_fct_p99 / B_ow / B_k99, gate),
data/t3_slow_share.csv, data/t3_uplinks.json (ToR0 uplink queue stats, seed-mean) and static PNGs."""
import json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

H = Path(__file__).resolve().parents[1]
rows = [json.loads(l) for l in (H / "data/results.jsonl").read_text().splitlines()]
df = pd.DataFrame(rows)
df["gate_clear"] = ((df.rtos == 0) & (df.freeze_entries == 0)).astype(int)
# share of ToR0's data packets on the degraded (even agg) uplinks, from -log_queue_stats (all ToR0 hosts, valid for 2- and 3-tier)
df["slow_share"] = df.uplink_data_pkts.apply(lambda v: 100 * sum(v[0::2]) / sum(v))
df["pct_ack_trim"] = 0.0
METRICS = ["pct_random", "k_mean", "k_ge1", "k_ge2", "k_ge3", "k_ge4", "k_ge8", "k_max", "fct_p50", "fct_p99", "fct_max", "fct_tor0_mean", "fct_tor0_max",
           "rtos", "freeze_entries", "n_freeze_events", "gate_clear", "ecn_acks", "rtx", "ev_overwrites", "pct_overwrite", "clean_acks", "add_mismatch",
           "recon_mismatch", "trims_total", "slow_share", "secs"]
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}
def ci(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return T975[len(x) - 1] * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
KEY = ["cfg", "axis", "hosts", "tiers", "paths", "latency_ns", "sack", "B"]
g = df.groupby(KEY)
summ = g[METRICS].mean().add_suffix("_mean").join(g[METRICS].agg(ci).add_suffix("_ci95")).join(g.size().rename("n_seeds")).reset_index()
def share(h): h = np.asarray(h, float); return 100 * h / h.sum()
for col, n, pre in (("k_hist", 65, "kdist_"), ("aw_hist", 9, "awdist_")):
    s = df[col].apply(share)
    d = s.groupby([df[k] for k in KEY]).apply(lambda x: np.mean(np.vstack(list(x)), axis=0)).reset_index(name="_v")
    for i in range(n): d[f"{pre}{i}"] = d["_v"].apply(lambda a, i=i: a[i])
    summ = summ.merge(d.drop(columns="_v"), on=KEY)
summ.to_csv(H / "data/t3_summary.csv", index=False)

# knees
def pct_from_dist(row, p):
    c = np.cumsum([row[f"kdist_{i}"] for i in range(65)]); c = c / c[-1] * 100
    return int(np.argmax(c >= p))
def knee(s, key, tol_floor=0.002):
    """One-sided: smallest B such that every B' >= B is within tol of the largest-B value or better (lower)."""
    ref = s.iloc[-1]; ok = []
    for _, r in s.iterrows():
        tol = max(np.nan_to_num(r[f"{key}_ci95"]), np.nan_to_num(ref[f"{key}_ci95"]), tol_floor * ref[f"{key}_mean"])
        ok.append(r[f"{key}_mean"] <= ref[f"{key}_mean"] + tol)
    for i in range(len(ok)):
        if all(ok[i:]): return int(s.iloc[i].B)
    return None
kn = []
for cfg, s in summ.groupby("cfg", sort=False):
    s = s.sort_values("B"); top = s.iloc[-1]
    b_ow = next((int(r.B) for _, r in s.iterrows() if r.pct_overwrite_mean < 0.1), None)
    k99 = pct_from_dist(top, 99)
    kn.append(dict(cfg=cfg, axis=top.axis, hosts=top.hosts, tiers=top.tiers, paths=top.paths, latency_ns=top.latency_ns, sack=top.sack, top_B=int(top.B),
                   n_seeds=int(s.n_seeds.min()), k_unc_p50=pct_from_dist(top, 50), k_unc_p90=pct_from_dist(top, 90), k_unc_p99=k99,
                   k_unc_max=top.k_max_mean, k_cap_saturated=bool(top.k_max_mean >= 0.9 * top.B), k_unc_mean=top.k_mean_mean, B_fct=knee(s, "fct_max"), B_fct_p99=knee(s, "fct_p99"), B_ow=b_ow,
                   B_k99=next((int(b) for b in s.B if b >= k99), None), fct_max_B8=float(s[s.B == 8].fct_max_mean.iloc[0]) if (s.B == 8).any() else None,
                   fct_max_top=top.fct_max_mean, fct_p50_top=top.fct_p50_mean, gate_clear=bool((s.gate_clear_mean == 1).all()),
                   rtos_max=s.rtos_mean.max(), slow_share_B8=float(s[s.B == 8].slow_share_mean.iloc[0]) if (s.B == 8).any() else None))
kn = pd.DataFrame(kn)
# steady-state k (scripts/steady_k.py: B=128 traces, drop first/last 15% of each traced source's span; same k as run_m4.analyze)
st = pd.read_csv(H / "data/t3_steady_k.csv")
sp = st[st.part == "steady"].groupby("cfg")[["p50", "p99", "max"]].mean().add_prefix("k_steady_")
al = st[st.part == "all"].groupby("cfg")[["p99", "max"]].mean().add_prefix("k_trace_all_")
ls = st[st.part == "last"].groupby("cfg")[["max"]].mean().add_prefix("k_trace_last_")
kn = kn.merge(sp, left_on="cfg", right_index=True, how="left").merge(al, left_on="cfg", right_index=True, how="left").merge(ls, left_on="cfg", right_index=True, how="left")
kn["B_ks99"] = [next((int(b) for b in summ[summ.cfg == c].sort_values("B").B if b >= np.ceil(p)), None) if p == p else None for c, p in zip(kn.cfg, kn.k_steady_p99)]
b8 = summ[summ.B == 8].set_index("cfg")
for m in ("ecn_acks", "rtx", "pct_random", "trims_total"):
    kn[f"{m}_B8"] = kn.cfg.map(b8[f"{m}_mean"])
kn.to_csv(H / "data/t3_knees.csv", index=False)
up = {}
for (cfg, B), g2 in df.groupby(["cfg", "B"]):
    up[f"{cfg}|{B}"] = {m: np.mean(np.vstack(g2[col].tolist()), axis=0).round(1).tolist()
                        for m, col in (("trims", "uplink_trims"), ("data_pkts", "uplink_data_pkts"), ("max_q", "uplink_max_q"))}
json.dump(up, open(H / "data/t3_uplinks.json", "w"))
df.groupby(["cfg", "B"]).slow_share.agg(["mean", "std"]).to_csv(H / "data/t3_slow_share.csv")

# static plots
(H / "plots").mkdir(exist_ok=True)
AX = [("A", "A: hosts / radix (2-tier)"), ("B", "B: path count, 1024 hosts"), ("C", "C: tiers"), ("D", "D: link latency (q/ECN fixed)"), ("D2", "D2: link latency (q/ECN scaled to BDP)"), ("E", "E: ACK spacing")]
fig, axs = plt.subplots(2, 4, figsize=(19, 8)); axs = axs.ravel()
for a, (axkey, title) in zip(axs, AX):
    for cfg in list(summ[summ.axis == axkey].cfg.unique()) + ["base_h1024_p32"]:
        s = summ[summ.cfg == cfg].sort_values("B")
        a.errorbar(range(len(s)), s.fct_max_mean, s.fct_max_ci95, marker="o", capsize=3, label=cfg)
    Bs = sorted(summ.B.unique()); a.set_xticks(range(len(Bs))); a.set_xticklabels(Bs); a.set_title(title); a.set_xlabel("B"); a.set_ylabel("max FCT (us)")
    a.grid(alpha=.3); a.legend(fontsize=7)
a = axs[6]
for cfg, s in summ.groupby("cfg", sort=False):
    s = s.sort_values("B"); a.plot(range(len(s)), s.pct_overwrite_mean, marker="o", label=cfg)
a.set_yscale("symlog", linthresh=0.01); a.set_xticks(range(len(Bs))); a.set_xticklabels(Bs); a.set_title("overwrites (% of clean ACKs), all configs"); a.grid(alpha=.3)
fig.tight_layout(); fig.savefig(H / "plots/t3_fct_by_axis.png", dpi=110); plt.close(fig)
fig, a = plt.subplots(figsize=(10, 4.5)); x = np.arange(len(kn)); w = 0.2
for i, (k, lab) in enumerate((("k_unc_p99", "uncapped k p99"), ("B_k99", "B_k99"), ("B_ow", "B_ow"), ("B_fct", "B_fct"))):
    a.bar(x + (i - 1.5) * w, kn[k].astype(float), w, label=lab)
a.set_xticks(x); a.set_xticklabels(kn.cfg, rotation=45, ha="right", fontsize=8); a.set_yscale("log"); a.set_ylabel("buffer entries"); a.axhline(8, color="k", lw=.7, ls=":")
a.legend(); fig.tight_layout(); fig.savefig(H / "plots/t3_knees.png", dpi=110); plt.close(fig)
pd.set_option("display.width", 250)
print(kn.drop(columns=["axis", "tiers"]).to_string(index=False))
