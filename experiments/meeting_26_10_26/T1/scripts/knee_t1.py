#!/usr/bin/env python3
"""T1 knee table from data/t1_summary.csv -> data/t1_knees.csv. B_fct = smallest B such that every B' >= B has mean max FCT <= the B=128 mean +
max(CI95 at B', CI95 at B=128, 0.2% of the B=128 mean) (one-sided; same rule as T2/scripts/aggregate_t2.py knee()). Also B_fct_ci_only (tolerance
without the 0.2% floor) and the max-FCT means / CIs and pct_random at B = 4, 5, 6, 8, 128. Run after aggregate_t1.py and add_random_stats.py."""
import warnings; warnings.simplefilter("ignore")
from pathlib import Path
import numpy as np, pandas as pd

H = Path(__file__).resolve().parents[1]
s = pd.read_csv(H / "data/t1_summary.csv")
s = s[s.fail.isin(["uniform50", "nonuniform", "r010", "r005", "r001"])]


def knee(g, floor):
    g = g.sort_values("B"); ref = g.iloc[-1]; ok = []
    for _, r in g.iterrows():
        tol = max(np.nan_to_num(r.fct_max_ci95), np.nan_to_num(ref.fct_max_ci95), floor * ref.fct_max_mean)
        ok.append(r.fct_max_mean <= ref.fct_max_mean + tol)
    for i in range(len(ok)):
        if all(ok[i:]): return int(g.iloc[i].B)


rows = []
for f, g in s.groupby("fail"):
    g = g.set_index("B"); d = dict(fail=f, gate_clear=bool((g.gate_clear_mean == 1).all()), B_fct=knee(g.reset_index(), 0.002), B_fct_ci_only=knee(g.reset_index(), 0.0),
                                   fct_max_B128=g.fct_max_mean[128], fct_max_B128_ci95=g.fct_max_ci95[128])
    for B in (4, 5, 6, 7, 8):
        if B in g.index:
            d.update({f"fct_max_B{B}": g.fct_max_mean[B], f"fct_max_B{B}_ci95": g.fct_max_ci95[B], f"pct_random_B{B}": g.pct_random_mean[B],
                      f"pct_overwrite_B{B}": g.pct_overwrite_mean[B]})
    rows.append(d)
k = pd.DataFrame(rows)
k["order"] = k.fail.map({"uniform50": -1, "nonuniform": 0, "r010": 1, "r005": 2, "r001": 3}); k = k.sort_values("order").drop(columns="order")
k.to_csv(H / "data/t1_knees.csv", index=False)
pd.set_option("display.width", 250)
print(k.round(2).T.to_string())
