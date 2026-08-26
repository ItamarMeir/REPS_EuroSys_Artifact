#!/usr/bin/env python3
"""
aggregate.py — Parse exp23 FREEZING_PXR runs into a tidy CSV.

Reads all freezing_pxr_b{1,2,4,8,16,32,64}_{nscc,constant}_s{42,43,44}.out
from runs/ and emits data/exp23_flows.csv.

Output columns: algo, cc, seed, workload, flow_id, fct_us, size_bytes, ideal_fct_us, slowdown
"""
import re
import sys
import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
RUNS_DIR   = EXP_DIR / "runs"
DATA_DIR   = EXP_DIR / "data"
OUT_CSV    = DATA_DIR / "exp23_flows.csv"

LINKSPEED_BPS = 400_000 * 1_000_000  # 400 Gbps in bits/s

FINISH_RE = re.compile(
    r"finished at\s+([\d.]+)\s+flowSize\s+(\d+)",
    re.IGNORECASE,
)

NAME_RE = re.compile(
    r"^(?P<algo>freezing_pxr_b\d+)_"
    r"(?P<cc>nscc|constant)_"
    r"s(?P<seed>\d+)\.out$"
)


def parse_run(path: Path):
    m = NAME_RE.match(path.name)
    if not m:
        return []
    algo = m.group("algo")
    cc   = m.group("cc")
    seed = int(m.group("seed"))

    rows = []
    with open(path) as f:
        for line in f:
            fm = FINISH_RE.search(line)
            if not fm:
                continue
            fct_us     = float(fm.group(1))
            size_bytes = int(fm.group(2))
            ideal_fct_us = (size_bytes * 8) / LINKSPEED_BPS * 1e6
            slowdown     = fct_us / ideal_fct_us if ideal_fct_us > 0 else float("nan")
            rows.append({
                "algo":         algo,
                "cc":           cc,
                "seed":         seed,
                "workload":     "8mb",
                "fct_us":       fct_us,
                "size_bytes":   size_bytes,
                "ideal_fct_us": round(ideal_fct_us, 4),
                "slowdown":     round(slowdown, 4),
            })
    return rows


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_files = sorted(RUNS_DIR.glob("*.out"))
    if not out_files:
        print(f"No .out files found in {RUNS_DIR}", file=sys.stderr)
        sys.exit(1)

    all_rows = []
    for f in out_files:
        rows = parse_run(f)
        if not rows:
            print(f"  SKIP {f.name} (no match or no finished-at lines)")
            continue
        all_rows.extend(rows)
        print(f"  {f.name}: {len(rows)} flows")

    # assign flow_id per (algo, cc, seed) group
    counter: dict = {}
    for row in all_rows:
        key = (row["algo"], row["cc"], row["seed"])
        idx = counter.get(key, 0)
        row["flow_id"] = idx
        counter[key]   = idx + 1

    cols = ["algo", "cc", "seed", "workload", "flow_id",
            "fct_us", "size_bytes", "ideal_fct_us", "slowdown"]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(all_rows)

    print(f"\nWrote {len(all_rows)} rows → {OUT_CSV}")
    combos = {(r["algo"], r["cc"], r["seed"]) for r in all_rows}
    print(f"Distinct (algo,cc,seed) combos: {len(combos)}  (expected 42)")
    flows_per_combo = {k: 0 for k in combos}
    for r in all_rows:
        flows_per_combo[(r["algo"], r["cc"], r["seed"])] += 1
    low  = min(flows_per_combo.values())
    high = max(flows_per_combo.values())
    print(f"Flows per combo: min={low}  max={high}  (expected 1024)")


if __name__ == "__main__":
    main()
