#!/usr/bin/env python3
"""
aggregate.py — Parse exp21 run outputs into a tidy CSV.

Output: data/exp21_flows.csv
Columns: algo, cc, seed, flow_id, fct_us, size_bytes, ideal_fct_us, slowdown
"""
import re
import sys
import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
RUNS_DIR   = EXP_DIR / "runs"
DATA_DIR   = EXP_DIR / "data"
OUT_CSV    = DATA_DIR / "exp21_flows.csv"

LINKSPEED_BPS = 400_000 * 1_000_000  # 400 Gbps in bits/s

# htsim output format (from uec.cpp logFinish):
#   "Flow Uec_512_0 flowId 513 uecSrc 512 finished at 192.264 flowSize 8388608 ..."
# FCT is the value after "finished at" (in µs), flow size after "flowSize".
FINISH_RE = re.compile(
    r"finished at\s+([\d.]+)\s+flowSize\s+(\d+)",
    re.IGNORECASE,
)

# Filename formats:
#   8 MB runs:    {algo}_{cc}_s{seed}.out
#   128 MiB runs: {algo}_{cc}_128mib_s{seed}.out
NAME_RE = re.compile(
    r"^(?P<algo>path_static|freezing_b\d+|reps|oblivious64)_"
    r"(?P<cc>nscc|constant)_"
    r"(?P<size>128mib_)?"
    r"s(?P<seed>\d+)\.out$"
)


def parse_run(path: Path):
    algo_match = NAME_RE.match(path.name)
    if not algo_match:
        return []
    algo      = algo_match.group("algo")
    cc        = algo_match.group("cc")
    seed      = int(algo_match.group("seed"))
    workload  = "128mib" if algo_match.group("size") else "8mb"

    rows = []
    with open(path) as f:
        for line in f:
            m = FINISH_RE.search(line)
            if not m:
                continue
            fct_us     = float(m.group(1))
            size_bytes = int(m.group(2))

            ideal_fct_us = (size_bytes * 8) / LINKSPEED_BPS * 1e6
            slowdown     = fct_us / ideal_fct_us if ideal_fct_us > 0 else float("nan")
            rows.append({
                "algo":         algo,
                "cc":           cc,
                "seed":         seed,
                "workload":     workload,
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

    cols = ["algo", "cc", "seed", "workload", "flow_id", "fct_us", "size_bytes", "ideal_fct_us", "slowdown"]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(all_rows)

    print(f"\nWrote {len(all_rows)} rows → {OUT_CSV}")
    # Quick sanity
    combos = {(r["algo"], r["cc"], r["seed"]) for r in all_rows}
    print(f"Distinct (algo,cc,seed) combos: {len(combos)}  (expected 36)")
    flows_per_combo = {k: 0 for k in combos}
    for r in all_rows:
        flows_per_combo[(r["algo"], r["cc"], r["seed"])] += 1
    low = min(flows_per_combo.values())
    high = max(flows_per_combo.values())
    print(f"Flows per combo: min={low}  max={high}  (expected 1024)")


if __name__ == "__main__":
    main()
