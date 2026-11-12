"""Add the ACKs-per-send-window fields (aw_hist, aw_mean, aw_n) to data/results.jsonl from the kept traces (no sim rerun)."""
import json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from run_m4 import ack_window_stats

M4 = Path(__file__).resolve().parent.parent
rows = [json.loads(l) for l in open(M4 / "data" / "results.jsonl")]
for r in rows:
    df = pd.read_csv(M4 / "traces" / f"{r['rate']}_{r['fail']}_B{r['B']}_s{r['seed']}.csv.gz",
                     usecols=["src_id", "event"])
    r.update(ack_window_stats(df))
    assert r["aw_n"] == r["draws_post"], (r["rate"], r["fail"], r["B"], r["seed"], r["aw_n"], r["draws_post"])
with open(M4 / "data" / "results.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
print(len(rows), "rows; windows tie out to draws_post in all")
