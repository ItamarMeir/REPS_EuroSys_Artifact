#!/usr/bin/env python3
"""Per-message FCT per cell for the repeated-message pages, from the stdout of each cell (same parsing as e_knees_tol.py).
message m = (flowId-1)//N, source host = uecSrc % N; max and mean over the degraded sources (hosts < NH). Gate-failing cells are dropped.
usage (in the container): python e_permessage.py <N> <NH> <out.csv> <results.jsonl> <traces_dir> [<results.jsonl> <traces_dir> ...]"""
import csv, json, re, sys
from pathlib import Path
import numpy as np
N, NH, OUT = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
rows = []
args = sys.argv[4:]
for res, tr in zip(args[::2], args[1::2]):
    bad = {(d["cfg"], d["B"], d["seed"]) for d in map(json.loads, Path(res).read_text().splitlines()) if d["rtos"] > 0 or d["freeze_entries"] > 0}
    for p in sorted(Path(tr).glob("*.stdout.txt")):
        m = re.match(r"(.+)_B(\d+)_s(\d+)\.stdout\.txt", p.name)
        cfg, B, s = m.group(1), int(m.group(2)), int(m.group(3))
        if (cfg, B, s) in bad: continue
        f = {}
        for l in p.read_text(errors="ignore").splitlines():
            mm = re.search(r"flowId (\d+) .*uecSrc (\d+) finished at ([0-9.]+)", l)
            if mm and l.startswith("Flow"): f[((int(mm.group(1)) - 1) // N, int(mm.group(2)) % N)] = float(mm.group(3))
        for msg in sorted({k[0] for k in f}):
            v = [t for (mg, h), t in f.items() if mg == msg and h < NH]
            if v: rows.append((cfg, B, s, msg, len(v), np.mean(v), max(v)))
with open(OUT, "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["cfg", "B", "seed", "msg", "n", "mean", "max"]); w.writerows(rows)
print(len(rows))
