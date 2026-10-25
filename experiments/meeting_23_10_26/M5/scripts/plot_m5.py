#!/usr/bin/env python3
"""M5 aggregation: REPS (freezing, B=1,2,4) vs OPS (oblivious) on the M4 network. 3 seeds (42-44), mean and 95% t(2) CI.
Writes data/m5_summary.csv, data/m5_table.md and plots/m5_*.png. Run from M5/: python scripts/plot_m5.py"""
import json, numpy as np, pandas as pd
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
H = Path(__file__).resolve().parent.parent; T975 = 4.303
rows = [json.loads(l) for f in ("results_ops.jsonl", "results_reps_rerun.jsonl") for l in open(H / "data" / f)]
df = pd.DataFrame(rows); df["arm"] = np.where(df.lb == "oblivious", "OPS", "REPS B=" + df.B.fillna(0).astype(int).astype(str))
df["trims_tor0_25"] = df.tor0_up_trims.map(lambda v: sum(v[0::2])); df["trims_tor0_75"] = df.tor0_up_trims.map(lambda v: sum(v[1::2]))
M = ["fct_tor0_mean", "fct_tor0_max", "fct_p99", "ecn_acks", "trims_total", "rtx_traced", "maxq_E->A", "rtos"]
g = df.groupby(["rate", "fail", "arm"])
s = g[M].mean().join(g[M].std(ddof=1).mul(T975 / np.sqrt(3)).add_suffix("_ci")).join(g.size().rename("n")).reset_index()
s.to_csv(H / "data" / "m5_summary.csv", index=False)
ARMS = ["REPS B=1", "REPS B=2", "REPS B=4", "OPS"]; RATES = ["under", "matched", "over"]; FAILS = ["healthy", "uniform50", "nonuniform"]
def cell(rate, fail, arm, m, fmt):
    r = s[(s.rate == rate) & (s.fail == fail) & (s.arm == arm)].iloc[0]; return fmt % r[m]
out = []
for m, title, fmt in (("fct_tor0_mean", "ToR0 mean FCT (us)", "%.1f"), ("fct_tor0_max", "ToR0 max FCT (us)", "%.1f"), ("ecn_acks", "ECN-marked ACKs, whole run", "%d"),
                      ("trims_total", "Trimmed packets, whole run (switch queues)", "%d"), ("rtx_traced", "Retransmissions, traced hosts 0-7", "%d")):
    out += [f"\n**{title}** (mean of 3 seeds)\n", "| rate / fail | " + " | ".join(ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for r in RATES:
        for f in FAILS: out.append(f"| {r} / {f} | " + " | ".join(cell(r, f, a, m, fmt) for a in ARMS) + " |")
(H / "data" / "m5_table.md").write_text("\n".join(out))
(H / "plots").mkdir(exist_ok=True)
fig, ax = plt.subplots(1, 3, figsize=(15, 4.2), sharey=False)
col = {"REPS B=1": "#c6dbef", "REPS B=2": "#6baed6", "REPS B=4": "#2171b5", "OPS": "#e6550d"}
for k, r in enumerate(RATES):
    for j, a in enumerate(ARMS):
        y = [s[(s.rate == r) & (s.fail == f) & (s.arm == a)].fct_tor0_mean.iloc[0] for f in FAILS]
        e = [s[(s.rate == r) & (s.fail == f) & (s.arm == a)].fct_tor0_mean_ci.iloc[0] for f in FAILS]
        ax[k].bar(np.arange(3) + j * 0.2 - 0.3, y, 0.2, yerr=[np.minimum(e, y), e], color=col[a], label=a, capsize=2)
    ax[k].set_xticks(range(3)); ax[k].set_xticklabels(FAILS); ax[k].set_title(f"{r} rate"); ax[k].set_ylabel("ToR0 mean FCT (us)"); ax[k].set_ylim(bottom=0)
ax[0].legend(); fig.tight_layout(); fig.savefig(H / "plots" / "m5_fct_tor0.png", dpi=120)
fig, ax = plt.subplots(figsize=(7, 4))
for j, a in enumerate(ARMS):
    y = [s[(s.rate == "matched") & (s.fail == f) & (s.arm == a)].trims_total.iloc[0] for f in FAILS]
    ax.bar(np.arange(3) + j * 0.2 - 0.3, y, 0.2, color=col[a], label=a)
ax.set_yscale("symlog", linthresh=10); ax.set_xticks(range(3)); ax.set_xticklabels(FAILS); ax.set_ylabel("trimmed packets (whole run)"); ax.set_title("matched rate"); ax.legend()
fig.tight_layout(); fig.savefig(H / "plots" / "m5_trims_matched.png", dpi=120)
print((H / "data" / "m5_table.md").read_text())
