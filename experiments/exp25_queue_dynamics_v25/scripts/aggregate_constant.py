#!/usr/bin/env python3
"""
aggregate_constant.py -- exp25: same collapse as aggregate.py (per-timestep
mean/p95 queue occupancy across the first-16-core-switches downlink queues),
but for the CONSTANT-linerate CC runs (runs/queues_{algo}_constant_s{seed}.csv)
instead of the original NSCC runs. Kept as a separate script/output so the
already-reported NSCC pipeline (aggregate.py / exp25_queue_ts.csv) is
untouched.

Writes data/exp25_queue_ts_constant.csv, same column shape as
exp25_queue_ts.csv.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
RUNS_DIR   = EXP_DIR / "runs"
DATA_DIR   = EXP_DIR / "data"

MTU_BYTES = 4150  # htsim_uec default packet_size (main_uec.cpp)

NAME_RE = re.compile(r"^queues_(?P<algo>freezing_b64|reps)_constant_s(?P<seed>\d+)\.csv$")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    files = sorted(RUNS_DIR.glob("queues_*_constant_s*.csv"))
    if not files:
        print(f"ERROR: no queues_*_constant_s*.csv found in {RUNS_DIR}", file=sys.stderr)
        sys.exit(1)

    for f in files:
        m = NAME_RE.match(f.name)
        if not m:
            print(f"skip (name doesn't match): {f.name}", file=sys.stderr)
            continue
        algo = m.group("algo")
        seed = int(m.group("seed"))
        df = pd.read_csv(f)
        grouped = df.groupby("time_us")["bytes"].agg(
            mean_queue_bytes="mean",
            p95_queue_bytes=lambda s: np.percentile(s, 95),
        ).reset_index()
        grouped["algo"] = algo
        grouped["seed"] = seed
        rows.append(grouped)
        print(f"{f.name}: {len(df)} rows -> {len(grouped)} timesteps")

    out = pd.concat(rows, ignore_index=True)
    out["mean_queue_pkts"] = out["mean_queue_bytes"] / MTU_BYTES
    out["p95_queue_pkts"]  = out["p95_queue_bytes"] / MTU_BYTES
    out = out[["algo", "seed", "time_us", "mean_queue_bytes", "mean_queue_pkts",
               "p95_queue_bytes", "p95_queue_pkts"]]
    out = out.sort_values(["algo", "seed", "time_us"]).reset_index(drop=True)

    out_path = DATA_DIR / "exp25_queue_ts_constant.csv"
    out.to_csv(out_path, index=False)
    print(f"\nWrote {len(out)} rows to {out_path}")


if __name__ == "__main__":
    main()
