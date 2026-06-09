#!/usr/bin/env python3
"""Parse exp14 .out files into data/fcts.csv.

Filename convention:
  data/exp14_<lb>+<cc>_tornado_n16_s<size>_seed<seed>.out

Output: data/fcts.csv
  condition, lb_algo, cc_algo, size_bytes, seed, flow_id, src, fct_us, flow_size
"""

import csv
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

# Flow completion line format:
# Flow <name> flowId <id> uecSrc <src> finished at <fct_us> flowSize <size> ...
FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+(\d+)\s+uecSrc\s+(\d+)\s+"
    r"finished at\s+([\d.]+)\s+flowSize\s+(\d+)"
)

# Output filename: exp14_<lb>+<cc>_tornado_n16_s<size>_seed<seed>.out
FILE_RE = re.compile(
    r"^exp14_([^+]+)\+(\w+)_tornado_n16_s(\d+)_seed(\d+)\.out$"
)


def parse_out(path: Path):
    seen = set()
    with path.open(errors="ignore") as f:
        for line in f:
            m = FLOW_RE.match(line)
            if not m:
                continue
            flowid, src, fct, size = int(m.group(1)), int(m.group(2)), float(m.group(3)), int(m.group(4))
            key = (flowid, src)
            if key in seen:
                continue
            seen.add(key)
            yield flowid, src, fct, size


def main():
    rows = []
    for out in sorted(DATA_DIR.glob("exp14_*.out")):
        m = FILE_RE.match(out.name)
        if not m:
            print(f"WARN skip: {out.name}")
            continue
        lb, cc, size_bytes, seed = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
        cond = f"{lb}+{cc}"
        flows = list(parse_out(out))
        if not flows:
            print(f"WARN no flows: {out.name}")
            continue
        for flowid, src, fct_us, flow_size in flows:
            rows.append(dict(
                condition=cond, lb_algo=lb, cc_algo=cc,
                size_bytes=size_bytes, seed=seed,
                flow_id=flowid, src=src, fct_us=fct_us, flow_size=flow_size,
            ))
        print(f"  {out.name}: {len(flows)} flows")

    if not rows:
        print("ERROR: no rows — run 01_run_exp14.sh first")
        return

    out_path = DATA_DIR / "fcts.csv"
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out_path}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()
