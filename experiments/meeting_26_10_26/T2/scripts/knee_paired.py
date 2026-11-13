#!/usr/bin/env python3
"""Paired knee of max FCT per shape for both T2 scopes (see T1/scripts/knee_paired.py for the rule).

Paired excess = fct_max(B, seed) - fct_max(B=128, same seed); B ok if mean paired excess <= max(0.2% of the B=128 mean,
1.96 * SE of the paired differences); B_fct_paired = smallest B from which every larger B is ok (one-sided). Shapes with
one seed per B are skipped. Reads <sub>/data/results.jsonl; writes <sub>/data/t2_paired_excess.csv and
<sub>/data/t2_knees_paired.csv (next to the unpaired B_fct of t2_knees.csv).

    python3 knee_paired.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

T2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(T2.parents[0] / "T1" / "scripts"))
from knee_paired import paired_table, knees  # noqa: E402

if __name__ == "__main__":
    for sub in ("tor_agg", "agg_core"):
        d = T2 / sub / "data"
        r = pd.DataFrame([json.loads(l) for l in (d / "results.jsonl").read_text().splitlines()])
        t = paired_table(r, "shape")
        t.rename(columns={"cfg": "shape"}).to_csv(d / "t2_paired_excess.csv", index=False)
        k = pd.read_csv(d / "t2_knees.csv")[["shape", "B_fct"]].rename(columns={"B_fct": "B_fct_unpaired"})
        k["B_fct_paired"] = k["shape"].map(knees(t))
        k.to_csv(d / "t2_knees_paired.csv", index=False)
        print(sub); print(k.to_string(index=False))
