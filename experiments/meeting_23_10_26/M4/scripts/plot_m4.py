"""Aggregate results.jsonl -> summary CSV (mean, 95% t-CI over seeds) and plots."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

H = Path(__file__).resolve().parents[1]
src = Path(sys.argv[1]) if len(sys.argv) > 1 else H / "data/results.jsonl"
df = pd.DataFrame([json.loads(l) for l in src.read_text().splitlines()])
METRICS = ["pct_random", "k_mean", "k_ge1", "k_ge2", "k_ge3", "k_ge4", "k_ge8", "k_max", "spray_width32", "distinct_ev_per_src", "pct_random_incl_warmup", "draws_post", "draws_warmup",
           "fct_p50", "fct_p99", "fct_max", "fct_tor0_mean", "fct_tor0_max", "rtos", "freeze_entries", "ecn_acks", "rtx"]
T975 = {1:12.706,2:4.303,3:3.182,4:2.776,5:2.571,6:2.447,7:2.365,8:2.306,9:2.262}  # t(.975, df)
def ci(x):
    x = np.asarray(x, float)
    return T975[len(x) - 1] * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
g = df.groupby(["rate_gbps", "rate", "fail", "B"])
summ = g[METRICS].mean().add_suffix("_mean").join(g[METRICS].agg(ci).add_suffix("_ci95")).join(g.size().rename("n_seeds")).reset_index()
def kshare(h):
    h = np.asarray(h, float); return 100 * h / h.sum()
df["_ks"] = df.k_hist.apply(kshare)
kd = df.groupby(["rate_gbps", "rate", "fail", "B"])["_ks"].apply(lambda s: np.mean(np.vstack(list(s)), axis=0)).reset_index()
for i in range(33):
    kd[f"kdist_{i}"] = kd["_ks"].apply(lambda a, i=i: a[i])
summ = summ.merge(kd.drop(columns="_ks"), on=["rate_gbps", "rate", "fail", "B"])
summ.to_csv(H / "data/m4_summary.csv", index=False)
RATES = ["under", "matched", "over"]; FAILS = ["healthy", "uniform50", "nonuniform"]
COL = {"under": "tab:blue", "matched": "tab:green", "over": "tab:red"}
LAB = {"under": "under (100G)", "matched": "matched (200G)", "over": "over (400G)"}
def panel(metric, ylabel, fname, logy=False):
    fig, ax = plt.subplots(1, 3, figsize=(14, 3.9), sharey=True)
    for a, f in zip(ax, FAILS):
        for r in RATES:
            s = summ[(summ.fail == f) & (summ.rate == r)].sort_values("B")
            a.errorbar(s.B, s[metric + "_mean"], yerr=s[metric + "_ci95"], marker="o", ms=3, capsize=2, c=COL[r], label=LAB[r])
        a.set_xscale("log", base=2); a.set_title(f); a.set_xlabel("REPS buffer size B"); a.grid(alpha=.3)
        if logy: a.set_yscale("log")
    ax[0].set_ylabel(ylabel); ax[0].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(H / "plots" / fname, dpi=130); plt.close(fig)
panel("pct_random", "% sends with random EV", "m4_pct_random.png")
panel("k_mean", "mean k (valid EVs in buffer at send)", "m4_k_mean.png")
panel("k_ge3", "% sends with k >= 3", "m4_k_ge3.png")
panel("fct_tor0_mean", "mean FCT of ToR0 flows (us)", "m4_fct_tor0.png")
panel("fct_p99", "p99 FCT (us)", "m4_fct_p99.png")
panel("spray_width32", "distinct EVs per 32 sends", "m4_spray_width.png")
print(summ[["rate", "fail", "B", "n_seeds", "pct_random_mean", "k_mean_mean", "fct_tor0_mean_mean", "fct_p99_mean"]].round(2).to_string(index=False))
