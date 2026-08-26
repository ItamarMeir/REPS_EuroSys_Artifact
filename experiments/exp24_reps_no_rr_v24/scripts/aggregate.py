#!/usr/bin/env python3
"""
aggregate.py — Parse exp24's new reps_no_rr .out files and merge with exp21's
already-aggregated flow-level data (path_static, freezing_b8..b64, reps).

Output: data/exp24_flows.csv
Columns: algo, cc, seed, workload, flow_id, fct_us, size_bytes, ideal_fct_us, slowdown
"""
import re
import sys
import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
REPO_ROOT  = EXP_DIR.parent.parent
RUNS_DIR   = EXP_DIR / "runs"
DATA_DIR   = EXP_DIR / "data"
OUT_CSV    = DATA_DIR / "exp24_flows.csv"

EXP21_FLOWS_CSV = (
    REPO_ROOT / "experiments" / "exp21_srv6_buffer_sweep_k16_v21"
    / "data" / "exp21_flows.csv"
)

LINKSPEED_BPS = 400_000 * 1_000_000  # 400 Gbps in bits/s

FINISH_RE = re.compile(
    r"finished at\s+([\d.]+)\s+flowSize\s+(\d+)",
    re.IGNORECASE,
)

NAME_RE = re.compile(
    r"^reps_no_rr_(?P<cc>nscc|constant)_s(?P<seed>\d+)\.out$"
)


def parse_new_runs():
    rows = []
    for path in sorted(RUNS_DIR.glob("*.out")):
        m = NAME_RE.match(path.name)
        if not m:
            print(f"  SKIP {path.name} (name doesn't match)")
            continue
        cc = m.group("cc")
        seed = int(m.group("seed"))
        n = 0
        with open(path) as f:
            for line in f:
                fm = FINISH_RE.search(line)
                if not fm:
                    continue
                fct_us = float(fm.group(1))
                size_bytes = int(fm.group(2))
                ideal_fct_us = (size_bytes * 8) / LINKSPEED_BPS * 1e6
                slowdown = fct_us / ideal_fct_us if ideal_fct_us > 0 else float("nan")
                rows.append({
                    "algo": "reps_no_rr",
                    "cc": cc,
                    "seed": seed,
                    "workload": "8mb",
                    "fct_us": fct_us,
                    "size_bytes": size_bytes,
                    "ideal_fct_us": round(ideal_fct_us, 4),
                    "slowdown": round(slowdown, 4),
                })
                n += 1
        print(f"  {path.name}: {n} flows")
    return rows


def load_exp21_rows():
    """Reuse exp21's already-parsed flow data (path_static, freezing_b*, reps) —
    read-only, exp21's own files are never modified."""
    if not EXP21_FLOWS_CSV.exists():
        print(f"WARNING: {EXP21_FLOWS_CSV} not found, skipping exp21 reuse", file=sys.stderr)
        return []
    rows = []
    with open(EXP21_FLOWS_CSV, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if row["workload"] != "8mb":
                continue
            rows.append({
                "algo": row["algo"],
                "cc": row["cc"],
                "seed": int(row["seed"]),
                "workload": row["workload"],
                "fct_us": float(row["fct_us"]),
                "size_bytes": int(row["size_bytes"]),
                "ideal_fct_us": float(row["ideal_fct_us"]),
                "slowdown": float(row["slowdown"]),
            })
    print(f"  reused {len(rows)} rows from {EXP21_FLOWS_CSV}")
    return rows


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Parsing exp24 reps_no_rr runs:")
    all_rows = parse_new_runs()
    print("Reusing exp21 rows:")
    all_rows.extend(load_exp21_rows())

    counter: dict = {}
    for row in all_rows:
        key = (row["algo"], row["cc"], row["seed"])
        idx = counter.get(key, 0)
        row["flow_id"] = idx
        counter[key] = idx + 1

    cols = ["algo", "cc", "seed", "workload", "flow_id", "fct_us", "size_bytes", "ideal_fct_us", "slowdown"]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(all_rows)

    print(f"\nWrote {len(all_rows)} rows -> {OUT_CSV}")
    combos = {(r["algo"], r["cc"], r["seed"]) for r in all_rows}
    print(f"Distinct (algo,cc,seed) combos: {len(combos)}  (expected 42 = 7 algos x 2 cc x 3 seeds)")
    flows_per_combo = {k: 0 for k in combos}
    for r in all_rows:
        flows_per_combo[(r["algo"], r["cc"], r["seed"])] += 1
    low = min(flows_per_combo.values())
    high = max(flows_per_combo.values())
    print(f"Flows per combo: min={low}  max={high}  (expected 1024)")


if __name__ == "__main__":
    main()
