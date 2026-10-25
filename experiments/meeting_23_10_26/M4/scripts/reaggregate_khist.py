"""Recompute k_hist (now 65 bins, k=0..63, last bin 64+) in data/results.jsonl from the kept traces (no sim rerun)."""
import json
from pathlib import Path
import numpy as np, pandas as pd

M4 = Path(__file__).resolve().parent.parent
rows = [json.loads(l) for l in open(M4 / "data" / "results.jsonl")]
for r in rows:
    df = pd.read_csv(M4 / "traces" / f"{r['rate']}_{r['fail']}_B{r['B']}_s{r['seed']}.csv.gz", usecols=["src_id", "event", "fresh"])
    g = df.groupby("src_id")
    df["prev_fresh"] = g.fresh.shift(1).fillna(0).astype(int)
    df["seen_ack"] = g.event.transform(lambda s: (s == "ACK").cummax())
    d = df[df.event.isin(["SEND", "RTX", "RTS"])]
    k = d[d.seen_ack].prev_fresh.to_numpy()
    h = [int(v) for v in np.bincount(np.minimum(k, 64), minlength=65)]
    assert sum(h) == r["draws_post"] and h[:32] == r["k_hist"][:32]
    r["k_hist"] = h
with open(M4 / "data" / "results.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
print(len(rows), "rows; max k seen", max(max(i for i, v in enumerate(r["k_hist"]) if v) for r in rows))
