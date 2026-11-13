#!/usr/bin/env python3
"""Paired REPS minus god-mode (positive = god faster): per (latency, B, seed) mean over messages 2-4 of the per-message max FCT (hosts 0-15); mean and 95% CI over seeds. Writes data/god_paired.csv."""
import re, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nsweep_extra as X
D = Path(__file__).resolve().parent.parent / "data"
def load(fs):
    d = pd.concat([pd.read_csv(D / f) for f in fs]); d["lat"] = d.cfg.str.extract(r"lat(\d+)")[0].astype(int)
    d = d[d.msg >= 1].groupby(["lat", "B", "seed"]).max_.mean() if False else d[d.msg >= 1].groupby(["lat", "B", "seed"])["max"].mean()
    return d[~d.index.duplicated()]
r = load(["n_permessage.csv"]); g = load(["n_permessage_god.csv"])
j = pd.concat([r.rename("reps"), g.rename("god")], axis=1).dropna(); j["d"] = j.reps - j.god
rows = []
for (L, B), h in j.groupby(level=[0, 1]):
    rows.append(dict(lat=L, B=B, n=len(h), reps=h.reps.mean(), god=h.god.mean(), d=h.d.mean(), ci=X.ci(h.d.values)))
o = pd.DataFrame(rows); o.to_csv(D / "god_paired.csv", index=False)
pd.set_option("display.width", 200)
for L, h in o.groupby("lat"):
    print("lat", L, "n seeds", h.n.min(), "-", h.n.max())
    print(h[["B", "reps", "god", "d", "ci"]].round(2).to_string(index=False))
