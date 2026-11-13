#!/usr/bin/env python3
"""T2 results.jsonl -> <sub>/data/t2_summary.csv (mean, 95% t-CI over seeds, kdist_*, awdist_*, gate), t2_knees.csv (per config: steady-k
percentiles from the B=128 traces, knees B_fct / B_fct_pod0src / B_fct_p99 / B_ow / B_ks99, gate, speed proof), t2_uplinks.json (pod0 scope links,
seed-mean), t2_steady_k.csv and PNGs. usage: python aggregate_t2.py tor_agg|agg_core   (<sub>/data/results.jsonl, <sub>/traces/ must exist;
the healthy reference rows are part of both)."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

T2 = Path(__file__).resolve().parents[1]
SUB = sys.argv[1]
H = T2 / SUB
CAP = {"u50": 0.5, "r025": 0.25, "r010": 0.10, "r005": 0.05}
LAB = {"healthy": "healthy", "u50": "uniform 50/50", "r025": "non-uniform 25/75", "r010": "non-uniform 10/90", "r005": "non-uniform 5/95"}
df = pd.DataFrame([json.loads(l) for l in (H / "data/results.jsonl").read_text().splitlines()])
df["gate_clear"] = ((df.rtos == 0) & (df.freeze_entries == 0)).astype(int)


def slow_mask(row):
    """True for the degraded link (even position): A: layer E->A, j = agg (even slow); B: layer A->C, j = core, uplink l = (core - agg) / 4 (even slow)."""
    i, j = np.array(row.scope_i), np.array(row.scope_j)
    return (j % 2 == 0) if row.scope_layer == "E->A" else (((j - i) // 4) % 2 == 0)


df["slow_share"] = df.apply(lambda r: 100 * sum(np.array(r.scope_data_pkts)[slow_mask(r)]) / sum(r.scope_data_pkts), axis=1)
# speed proof: achieved Gbps of every scope link vs ratio x 400G (degraded cells only); the slow links must sit at or below their cap, trims only there
def speed_ok(r):
    if r["shape"] == "healthy": return np.nan
    m = slow_mask(r); g = np.array(r.scope_gbps); lo, hi = CAP[r["shape"]] * 400, (1 - CAP[r["shape"]]) * 400
    return float(np.all(g[m] <= lo * 1.005) and np.all(g[~m] <= hi * 1.005) and sum(np.array(r.scope_trims)[~m]) == 0)
df["speed_proof"] = df.apply(speed_ok, axis=1)
df["config_proof"] = ((df.failure_lines == df.n_links) & (df.distinct_paths.apply(lambda v: v == [16])) & (df.n_flow_lines == 128) & (~df.tor_dl_ecn_on) & (~df.trace_capped)
                      & (df.add_mismatch == 0) & (df.recon_mismatch == 0)).astype(int)
METRICS = ["pct_random", "k_mean", "k_ge1", "k_ge2", "k_ge3", "k_ge4", "k_ge8", "k_max", "fct_p50", "fct_p99", "fct_max", "fct_pod0_src_max", "fct_pod0_dst_max", "fct_other_max",
           "rtos", "freeze_entries", "n_freeze_events", "gate_clear", "ecn_acks", "rtx", "ev_overwrites", "pct_overwrite", "clean_acks", "add_mismatch", "recon_mismatch",
           "trims_total", "trims_outside_scope", "slow_share", "speed_proof", "config_proof", "secs"]
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}


def ci(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return T975[len(x) - 1] * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan


KEY = ["cfg", "shape", "B"]
g = df.groupby(KEY)
summ = g[METRICS].mean().add_suffix("_mean").join(g[METRICS].agg(ci).add_suffix("_ci95")).join(g.size().rename("n_seeds")).reset_index()


def share(h): h = np.asarray(h, float); return 100 * h / h.sum()


for col, n, pre in (("k_hist", 65, "kdist_"), ("aw_hist", 9, "awdist_")):
    s = df[col].apply(share)
    d = s.groupby([df[k] for k in KEY]).apply(lambda x: np.mean(np.vstack(list(x)), axis=0)).reset_index(name="_v")
    for i in range(n): d[f"{pre}{i}"] = d["_v"].apply(lambda a, i=i: a[i])
    summ = summ.merge(d.drop(columns="_v"), on=KEY)
summ["order"] = summ["shape"].map({"healthy": 0, "u50": 1, "r025": 2, "r010": 3, "r005": 4})
summ = summ.sort_values(["order", "B"]).drop(columns="order")
summ.to_csv(H / "data/t2_summary.csv", index=False)


def knee(s, key, tol_floor=0.002):
    """One-sided: smallest B such that every B' >= B is within tol of the largest-B value or better (lower)."""
    ref = s.iloc[-1]; ok = []
    for _, r in s.iterrows():
        tol = max(np.nan_to_num(r[f"{key}_ci95"]), np.nan_to_num(ref[f"{key}_ci95"]), tol_floor * ref[f"{key}_mean"])
        ok.append(r[f"{key}_mean"] <= ref[f"{key}_mean"] + tol)
    for i in range(len(ok)):
        if all(ok[i:]): return int(s.iloc[i].B)
    return None


# steady-state k at B=128 (drop first/last 15% of each traced source's span; same k as run_m4.analyze), all seeds, 16 pod0 hosts
TRIM = 0.15
st = []
for c in df[df.B == 128].cfg.unique():
    for sd in sorted(df[(df.cfg == c) & (df.B == 128)].seed.unique()):
        t = H / f"traces/{c}_B128_s{sd}.csv.gz"
        if not t.exists(): continue
        x = pd.read_csv(t, usecols=["time_ns", "src_id", "event", "fresh"])
        gg = x.groupby("src_id")
        x["k"] = gg.fresh.shift(1).fillna(0).astype(int)
        x["seen_ack"] = gg.event.transform(lambda v: (v == "ACK").cummax())
        d = x[x.event.isin(["SEND", "RTX", "RTS"]) & x.seen_ack]
        gt = d.groupby("src_id").time_ns
        rel = (d.time_ns - gt.transform("min")) / (gt.transform("max") - gt.transform("min"))
        for part, m in (("all", rel >= 0), ("steady", (rel >= TRIM) & (rel <= 1 - TRIM)), ("last", rel > 1 - TRIM)):
            k = d.k[m]; st.append(dict(cfg=c, seed=sd, part=part, n=int(len(k)), p50=float(k.quantile(.5)), p99=float(k.quantile(.99)), max=int(k.max())))
st = pd.DataFrame(st); st.to_csv(H / "data/t2_steady_k.csv", index=False)
sp = st[st.part == "steady"].groupby("cfg")[["p50", "p99", "max"]].mean().add_prefix("k_steady_")
ls = st[st.part == "last"].groupby("cfg")[["max"]].mean().add_prefix("k_drain_")

kn = []
for cfg, s in summ.groupby("cfg", sort=False):
    s = s.sort_values("B"); top = s.iloc[-1]; b8 = s[s.B == 8].iloc[0]
    kn.append(dict(cfg=cfg, shape=top["shape"], n_seeds=int(s.n_seeds.min()), top_B=int(top.B), B_fct=knee(s, "fct_max"), B_fct_pod0src=knee(s, "fct_pod0_src_max"),
                   B_fct_p99=knee(s, "fct_p99"), B_ow=next((int(r.B) for _, r in s.iterrows() if r.pct_overwrite_mean < 0.1), None),
                   fct_max_B8=b8.fct_max_mean, fct_max_top=top.fct_max_mean, fct_p50_B8=b8.fct_p50_mean, pct_random_B8=b8.pct_random_mean, pct_overwrite_B8=b8.pct_overwrite_mean,
                   ecn_acks_B8=b8.ecn_acks_mean, rtx_B8=b8.rtx_mean, trims_B8=b8.trims_total_mean, slow_share_B8=b8.slow_share_mean,
                   gate_clear=bool((s.gate_clear_mean == 1).all()), rtos_max=s.rtos_mean.max(), freeze_max=s.freeze_entries_mean.max(),
                   speed_proof=bool(s.speed_proof_mean.dropna().eq(1).all()) if s.speed_proof_mean.notna().any() else None, config_proof=bool((s.config_proof_mean == 1).all())))
kn = pd.DataFrame(kn).merge(sp, left_on="cfg", right_index=True, how="left").merge(ls, left_on="cfg", right_index=True, how="left")
kn["B_ks99"] = [next((int(b) for b in summ[summ.cfg == c].sort_values("B").B.unique() if b >= np.ceil(p)), None) if p == p else None for c, p in zip(kn.cfg, kn.k_steady_p99)]
kn.to_csv(H / "data/t2_knees.csv", index=False)

up = {}
for (cfg, B), g2 in df.groupby(["cfg", "B"]):
    up[f"{cfg}|{B}"] = {m: np.mean(np.vstack(g2[col].tolist()), axis=0).round(1).tolist()
                        for m, col in (("trims", "scope_trims"), ("data_pkts", "scope_data_pkts"), ("max_q", "scope_max_q"), ("gbps", "scope_gbps"))}
    up[f"{cfg}|{B}"]["i"] = g2.scope_i.iloc[0]; up[f"{cfg}|{B}"]["j"] = g2.scope_j.iloc[0]; up[f"{cfg}|{B}"]["layer"] = g2.scope_layer.iloc[0]
json.dump(up, open(H / "data/t2_uplinks.json", "w"))

(H / "plots").mkdir(exist_ok=True)
Bs = sorted(summ.B.unique()); x = range(len(Bs))
fig, axs = plt.subplots(1, 3, figsize=(17, 4.6))
for a, (m, t) in zip(axs, (("fct_max", "max FCT, all flows (us)"), ("fct_pod0_src_max", "max FCT, pod0 sources (us)"), ("pct_overwrite", "valid-EV overwrites (% of clean ACKs)"))):
    for shape in LAB:
        s = summ[summ["shape"] == shape].sort_values("B")
        if len(s): a.errorbar(x, s[f"{m}_mean"], s[f"{m}_ci95"], marker="o", capsize=3, label=LAB[shape])
    a.set_xticks(list(x)); a.set_xticklabels(Bs); a.set_xlabel("B"); a.set_title(f"{SUB}: {t}"); a.grid(alpha=.3)
    if m == "pct_overwrite": a.set_yscale("symlog", linthresh=0.01)
axs[0].legend(fontsize=8); fig.tight_layout(); fig.savefig(H / "plots/t2_fct_overwrite.png", dpi=110); plt.close(fig)
pd.set_option("display.width", 250)
print(kn.to_string(index=False))
