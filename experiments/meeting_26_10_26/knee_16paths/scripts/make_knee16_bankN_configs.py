#!/usr/bin/env python3
"""Bank size = N variant of the REPS-Bank arm: one cfg per (target arm, latency), bank size = the N of that latency (N = page table), everything else as in make_knee16_bank_configs.py (read from its output, not retyped).
Writes data/configs_knee16_bankN.json and data/bsmap_knee16_bankN.json (B = 8, the REPS buffer unchanged)."""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
N_OF_LAT = {250: 25, 500: 39, 1000: 65, 2000: 113, 4000: 208, 8000: 400, 16000: 788}
cfgs, bs = [], {}
for c in json.loads((DATA / "configs_knee16_bank.json").read_text()):
    L = int(c["name"].rsplit("_lat", 1)[1])
    name = c["name"].replace("Bkauto", "BkNauto").replace("Bktight", "BkNtight")
    cfgs.append(dict(c, name=name, bank=dict(c["bank"], size=N_OF_LAT[L])))
    bs[name] = [8]
json.dump(cfgs, open(DATA / "configs_knee16_bankN.json", "w"), indent=1)
json.dump(bs, open(DATA / "bsmap_knee16_bankN.json", "w"), indent=1)
print(len(cfgs), "cfgs", [(c["name"], c["bank"]["size"]) for c in cfgs][:4])
