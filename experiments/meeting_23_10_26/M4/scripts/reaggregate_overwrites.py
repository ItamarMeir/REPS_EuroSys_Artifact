"""Recompute overwrite fields of data/results.jsonl from the kept traces (no sim rerun)."""
import json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from run_m4 import overwrite_stats

M4 = Path(__file__).resolve().parent.parent
rows = [json.loads(l) for l in open(M4 / "data" / "results.jsonl")]
for r in rows:
    df = pd.read_csv(M4 / "traces" / f"{r['rate']}_{r['fail']}_B{r['B']}_s{r['seed']}.csv.gz",
                     usecols=["n", "src_id", "event", "ecn", "fresh"])
    df["prev_fresh"] = df.groupby("src_id").fresh.shift(1).fillna(0).astype(int)
    r.update(overwrite_stats(df, r["B"]))
with open(M4 / "data" / "results.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
print(len(rows), "rows; add_mismatch!=0:", sum(r["add_mismatch"] != 0 for r in rows))
