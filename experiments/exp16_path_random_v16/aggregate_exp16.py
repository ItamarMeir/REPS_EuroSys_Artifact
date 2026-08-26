#!/usr/bin/env python3
"""Parse exp16 .out files into data/fcts.csv.

Filename convention:
  data/exp16_<condition>_tornado_n16_s<size>_seed<seed>.out

Conditions (underscore separator):
  path_rr_constant, path_rr_nscc,
  freezing_constant, freezing_nscc,
  path_random_constant, path_random_nscc

Also pulls 16 MiB data for the 4 baseline conditions from exp14's CSV
(exp14 uses '+' separator; we remap to underscore on load).

Output: data/fcts.csv
  condition, size_bytes, seed, flow_id, src, fct_us, flow_size
"""

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
EXP14_CSV = ROOT.parent / "exp14_path_rr_tornado_v14" / "data" / "fcts.csv"

FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+(\d+)\s+uecSrc\s+(\d+)\s+"
    r"finished at\s+([\d.]+)\s+flowSize\s+(\d+)"
)

VALID_CONDS = {
    "path_rr_constant", "path_rr_nscc",
    "freezing_constant", "freezing_nscc",
    "path_random_constant", "path_random_nscc",
    "ops_constant", "ops_nscc",
    "path_static_constant", "path_static_nscc",  # ===== ADDED (path-static) =====
}

FILE_RE = re.compile(
    r"^exp16_([a-z_]+)_tornado_n16_s(\d+)_seed(\d+)\.out$"
)

ELEPHANT_SIZES = {67108864, 268435456}   # 64 MiB, 256 MiB
SMALL_SIZE     = 16777216                # 16 MiB (pulled from exp14)


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


def load_exp14_16mib():
    """Return rows from exp14 fcts.csv at 16 MiB, remapping '+' to '_' in condition."""
    rows = []
    if not EXP14_CSV.exists():
        print(f"WARN: exp14 CSV not found: {EXP14_CSV}")
        return rows
    with EXP14_CSV.open() as f:
        for row in csv.DictReader(f):
            if int(row["size_bytes"]) != SMALL_SIZE:
                continue
            cond = row["condition"].replace("+", "_")
            if cond not in VALID_CONDS:
                continue
            rows.append(dict(
                condition=cond,
                size_bytes=int(row["size_bytes"]),
                seed=int(row["seed"]),
                flow_id=int(row["flow_id"]),
                src=int(row["src"]),
                fct_us=float(row["fct_us"]),
                flow_size=int(row["flow_size"]),
            ))
    return rows


def main():
    rows = []

    # 1. Baseline 16 MiB data from exp14
    exp14_rows = load_exp14_16mib()
    rows.extend(exp14_rows)
    if exp14_rows:
        print(f"  exp14 (16 MiB baseline): {len(exp14_rows)} rows")

    # 2. All exp16 .out files (64 MiB + 256 MiB for all 6 conditions, plus
    #    any 16 MiB path_random/ops runs from 01_run_exp16.sh / 04_run_exp16_ops.sh)
    for out in sorted(DATA_DIR.glob("exp16_*.out")):
        if "qlog" in out.name:   # skip queue-logging side-outputs
            continue
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
        print("ERROR: no rows — run scripts first")
        return

    out_path = DATA_DIR / "fcts.csv"
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out_path}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()
