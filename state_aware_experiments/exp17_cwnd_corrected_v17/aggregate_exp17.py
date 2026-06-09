#!/usr/bin/env python3
"""Parse exp17 .out files into data/fcts.csv.

Filename: data/exp17_<condition>_tornado_n16_s<size>_seed<seed>.out
Output:   data/fcts.csv  (condition, size_bytes, seed, flow_id, src, fct_us, flow_size)
"""

import csv
import re
from pathlib import Path

ROOT     = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+(\d+)\s+uecSrc\s+(\d+)\s+"
    r"finished at\s+([\d.]+)\s+flowSize\s+(\d+)"
)
FILE_RE = re.compile(r"^exp17_([a-z_]+)_tornado_n16_s(\d+)_seed(\d+)\.out$")

VALID_CONDS = {
    "path_rr_constant", "path_rr_nscc",
    "freezing_constant", "freezing_nscc",
    "path_random_constant", "path_random_nscc",
    "ops_constant", "ops_nscc",
    "path_static_constant", "path_static_nscc",
}


def parse_out(path):
    seen = set()
    with path.open(errors="ignore") as f:
        for line in f:
            m = FLOW_RE.match(line)
            if not m:
                continue
            flowid = int(m.group(1))
            src    = int(m.group(2))
            fct    = float(m.group(3))
            size   = int(m.group(4))
            if (flowid, src) in seen:
                continue
            seen.add((flowid, src))
            yield flowid, src, fct, size


def main():
    rows = []
    for out in sorted(DATA_DIR.glob("exp17_*.out")):
        m = FILE_RE.match(out.name)
        if not m:
            print(f"WARN skip: {out.name}")
            continue
        cond, size_bytes, seed = m.group(1), int(m.group(2)), int(m.group(3))
        if cond not in VALID_CONDS:
            print(f"WARN unknown condition '{cond}': {out.name}")
            continue
        flows = list(parse_out(out))
        if not flows:
            print(f"WARN no flows: {out.name}")
            continue
        for flowid, src, fct_us, flow_size in flows:
            rows.append(dict(
                condition=cond, size_bytes=size_bytes, seed=seed,
                flow_id=flowid, src=src, fct_us=fct_us, flow_size=flow_size,
            ))
        print(f"  {out.name}: {len(flows)} flows")

    if not rows:
        print("ERROR: no rows — run scripts/01_run_exp17.sh first")
        return

    out_path = DATA_DIR / "fcts.csv"
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out_path}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()
