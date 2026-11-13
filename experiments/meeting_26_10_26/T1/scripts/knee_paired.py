#!/usr/bin/env python3
"""Paired knee of max FCT per config (T1).

For every cell, the paired excess is fct_max(B, seed) - fct_max(B=128, same seed); per (config, B) the mean over seeds and
its standard error SE = sd / sqrt(n). One-sided rule: B is ok if mean paired excess <= max(0.2% of the B=128 mean,
1.96 * SE); B_fct_paired = the smallest B from which every larger B in the grid is ok. A config with one seed per B is
skipped (no SE). The unpaired rule is plot_common.knee_fct (tolerance = max(CI of that B, CI of B=128, 0.2% of B=128),
differences of means); knee_t1.py writes it to t1_knees.csv. Faster than B=128 never counts against a B.

Writes data/t1_paired_excess.csv (config, B, n, mean excess, SE, tolerance, ok) and data/t1_knees_paired.csv (per config:
paired knee next to the unpaired B_fct of t1_knees.csv). r = 0.01 (Freezing Mode) is not in the page; it is written too,
flagged by its gate column, because t1_knees.csv has it.

    python3 knee_paired.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).resolve().parents[1] / "data"
TOL_REL = 0.002
Z = 1.96


def paired_table(r: pd.DataFrame, key: str) -> pd.DataFrame:
    rows = []
    for cfg, g in r.groupby(key):
        ref = g[g.B == 128].set_index("seed").fct_max
        for B, h in g.groupby("B"):
            h = h.set_index("seed").fct_max
            d = (h - ref.reindex(h.index)).dropna()
            n = len(d)
            if n < 2:
                continue
            se = float(d.std(ddof=1) / np.sqrt(n))
            tol = max(TOL_REL * float(ref.mean()), Z * se)
            rows.append(dict(cfg=cfg, B=int(B), n=n, ref128_mean=float(ref.mean()), excess_mean=float(d.mean()), se=se,
                             tol=tol, ok=bool(d.mean() <= tol)))
    return pd.DataFrame(rows)


def knees(t: pd.DataFrame) -> dict:
    out = {}
    for cfg, g in t.groupby("cfg"):
        g = g.sort_values("B").reset_index(drop=True)
        ok = g.ok.tolist()
        out[cfg] = next((int(g.B[i]) for i in range(len(ok)) if all(ok[i:])), None)
    return out


if __name__ == "__main__":
    r = pd.DataFrame([json.loads(l) for l in (D / "results.jsonl").read_text().splitlines()])
    t = paired_table(r, "fail")
    t.rename(columns={"cfg": "fail"}).to_csv(D / "t1_paired_excess.csv", index=False)
    k = pd.read_csv(D / "t1_knees.csv")[["fail", "gate_clear", "B_fct"]].rename(columns={"B_fct": "B_fct_unpaired"})
    kp = knees(t)
    k["B_fct_paired"] = k.fail.map(kp)
    k.to_csv(D / "t1_knees_paired.csv", index=False)
    print(k.to_string(index=False))
