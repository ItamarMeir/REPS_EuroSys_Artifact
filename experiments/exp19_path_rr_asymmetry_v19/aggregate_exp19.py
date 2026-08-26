#!/usr/bin/env python3
"""Aggregate exp19 simulation outputs into structured CSVs.

Reads:
  data/exp19_{cond}_tornado_n16_s268435456_seed{S}.out  → data/fcts.csv
  data/exp19_{cond}_seed{S}_queues.csv                  → data/queue_integral.csv

fcts.csv columns:        condition, seed, flow_id, fct_us, size_bytes, retransmits
queue_integral.csv cols: condition, seed, agg, core, queue_byte_us
"""

import re
import sys
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# Flow finish line:
# Flow Uec_0_8 flowId 1 uecSrc 0 finished at <fct_us> flowSize <bytes> ... RTS <rts> ...
FLOW_RE = re.compile(
    r"Flow \S+ flowId \d+ uecSrc (\d+) finished at ([\d.]+) flowSize (\d+).*? RTS (\d+)"
)

# Output filename: exp19_{cond}_tornado_n16_s268435456_seed{seed}.out
FILE_RE = re.compile(r"exp19_(\w+)_tornado_n16_s\d+_seed(\d+)\.out")


def parse_out_file(path):
    rows = []
    match = FILE_RE.search(path.name)
    if not match:
        return rows
    cond, seed = match.group(1), int(match.group(2))
    with open(path) as f:
        for line in f:
            m = FLOW_RE.search(line)
            if m:
                rows.append({
                    "condition": cond,
                    "seed": seed,
                    "flow_id": int(m.group(1)),
                    "fct_us": float(m.group(2)),
                    "size_bytes": int(m.group(3)),
                    "retransmits": int(m.group(4)),
                })
    return rows


def queue_integral(path, cond, seed):
    """Compute trapezoid integral (bytes × µs) per (agg, core) pair."""
    df = pd.read_csv(path)
    if df.empty:
        return []
    rows = []
    for (agg, core), grp in df.groupby(["agg", "core"]):
        grp = grp.sort_values("time_us")
        integral = float(np.trapz(grp["bytes"].to_numpy(), grp["time_us"].to_numpy()))
        rows.append({"condition": cond, "seed": seed,
                     "agg": int(agg), "core": int(core),
                     "queue_byte_us": integral})
    return rows


def main():
    out_files = sorted(DATA.glob("exp19_*_tornado_n16_s*_seed*.out"))
    if not out_files:
        print(f"No .out files found in {DATA}. Run scripts/01_run_exp19.sh first.")
        sys.exit(1)

    fct_rows = []
    for p in out_files:
        r = parse_out_file(p)
        if not r:
            print(f"WARNING: no flow lines parsed from {p.name}")
        fct_rows.extend(r)

    fcts = pd.DataFrame(fct_rows)
    fcts.to_csv(DATA / "fcts.csv", index=False)
    print(f"fcts.csv: {len(fcts)} rows  ({fcts['condition'].unique()})")

    q_rows = []
    for p in sorted(DATA.glob("exp19_*_seed*_queues.csv")):
        m = re.search(r"exp19_(\w+)_seed(\d+)_queues", p.name)
        if not m:
            continue
        cond, seed = m.group(1), int(m.group(2))
        q_rows.extend(queue_integral(p, cond, seed))

    if q_rows:
        qi = pd.DataFrame(q_rows)
        qi.to_csv(DATA / "queue_integral.csv", index=False)
        print(f"queue_integral.csv: {len(qi)} rows")
    else:
        print("WARNING: no core queue CSVs found; queue_integral.csv not written")

    tq_rows = []
    for p in sorted(DATA.glob("exp19_*_seed*_tor_queues.csv")):
        m = re.search(r"exp19_(\w+)_seed(\d+)_tor_queues", p.name)
        if not m:
            continue
        cond, seed = m.group(1), int(m.group(2))
        df = pd.read_csv(p)
        if df.empty:
            continue
        for (tor, agg), grp in df.groupby(["tor", "agg"]):
            grp = grp.sort_values("time_us")
            integral = float(np.trapz(grp["bytes"].to_numpy(), grp["time_us"].to_numpy()))
            tq_rows.append({"condition": cond, "seed": seed,
                            "tor": int(tor), "agg": int(agg),
                            "queue_byte_us": integral})

    if tq_rows:
        tqi = pd.DataFrame(tq_rows)
        tqi.to_csv(DATA / "tor_queue_integral.csv", index=False)
        print(f"tor_queue_integral.csv: {len(tqi)} rows")
    else:
        print("WARNING: no ToR queue CSVs found; tor_queue_integral.csv not written")


if __name__ == "__main__":
    main()
