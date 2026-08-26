#!/usr/bin/env python3
"""Aggregate exp18 FCT data: read all exp18_*.out files, extract flow finish times.

Reads:  data/exp18_*.out
Writes: data/fcts.csv
"""

import csv
import re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+(\d+)\s+uecSrc\s+(\d+)\s+"
    r"finished at\s+([\d.]+)\s+flowSize\s+(\d+)"
)

FILE_RE = re.compile(r"^exp18_(\w+)_tornado_n16_s(\d+)_seed(\d+)\.out$")

def parse_out(path):
    seen = set()
    flows = []
    with path.open(errors="ignore") as f:
        for line in f:
            m = FLOW_RE.match(line)
            if not m:
                continue
            flowid = int(m.group(1))
            src = int(m.group(2))
            fct = float(m.group(3))
            size = int(m.group(4))
            if (flowid, src) in seen:
                continue
            seen.add((flowid, src))
            flows.append((fct, size))
    return flows

def main():
    if not DATA.exists():
        print(f"ERROR: {DATA} not found")
        return

    # Collect all flow data
    rows = []
    for f in sorted(DATA.glob("exp18_*.out")):
        m = FILE_RE.match(f.name)
        if not m:
            print(f"WARN skip: {f.name}")
            continue
        condition = m.group(1)
        size = int(m.group(2))
        seed = int(m.group(3))
        flows = parse_out(f)
        if not flows:
            print(f"WARN no flows: {f.name}")
            continue
        for fct, flow_size in flows:
            rows.append({
                'condition': condition,
                'seed': seed,
                'size_bytes': flow_size,
                'fct_us': fct
            })
        print(f"  {f.name}: {len(flows)} flows")

    # Write CSV
    if rows:
        out_csv = DATA / "fcts.csv"
        with out_csv.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['condition', 'seed', 'size_bytes', 'fct_us'])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nWrote {out_csv}  ({len(rows)} rows)")
    else:
        print("ERROR: no data collected")

if __name__ == "__main__":
    main()
