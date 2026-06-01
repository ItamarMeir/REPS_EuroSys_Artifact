#!/usr/bin/env python3
"""
v10_aggregate.py — exp10 (paper workloads) aggregator.

Walks runs/part_a/ and runs/part_b/ and emits two tidy CSVs:

  data/v10_fct.csv     — one row per finished flow
  data/v10_events.csv  — one row per simulation run

Tree structure:
  runs/part_{a,b}/{axis_tag}/{workload}/sev{S}/seed{K}/run.out

axis_tag:
  Part A: buf_1  buf_2  buf_4  buf_8  buf_1024
  Part B: ev_32  ev_256  ev_65535

Workloads: baseline, perm, hsdp, incast32

Flow-class binning is per-workload (id-based, not size-based):
  baseline: ids 1-4   → ecmp_elephant, ids 5-128 → sprayed_perm
  perm    : all 128   → perm
  hsdp    : all 128   → hsdp_ring
  incast32: all 32    → incast
"""

import re
import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
RUNS_DIR   = EXP_DIR / "runs"
DATA_DIR   = EXP_DIR / "data"

LINK_RATE_BPS = 800_000_000_000
BASE_RTT_US   = 4.0

WORKLOADS  = ["baseline", "perm", "hsdp", "incast32"]
SEVERITIES = [0, 4]
SEEDS      = [42, 43, 44]

PART_A_TAGS = [f"buf_{v}" for v in (1, 2, 4, 8, 1024)]
PART_B_TAGS = [f"ev_{v}"  for v in (32, 256, 65535)]


def ideal_fct_us(size_bytes: int) -> float:
    return size_bytes * 8 / LINK_RATE_BPS * 1e6 + BASE_RTT_US


def classify_flow(workload: str, flow_id: int) -> str:
    if workload == "baseline":
        return "ecmp_elephant" if flow_id <= 4 else "sprayed_perm"
    if workload == "perm":
        return "perm"
    if workload == "hsdp":
        return "hsdp_ring"
    if workload == "incast32":
        return "incast"
    return "unknown"


def axis_val(tag: str) -> int:
    return int(tag.split("_", 1)[1])


def part_label(tag: str) -> str:
    return "buf" if tag.startswith("buf_") else "ev"


FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+(\d+)\s+\S+\s+\S+\s+finished\s+at\s+(\S+)\s+flowSize\s+(\d+)"
)


def parse_run_out(path: Path, meta: dict) -> tuple:
    flow_rows = []
    events = dict(
        n_flows_finished=0,
        n_ecn_acks=0,
        n_clean_acks=0,
        pipe_fails=0,
        pipe_restores=0,
        fz_starts=0,
        fz_exits=0,
    )

    try:
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                m = FLOW_RE.match(line)
                if m:
                    fid   = int(m.group(1))
                    fct   = float(m.group(2))
                    size  = int(m.group(3))
                    ideal = ideal_fct_us(size)
                    flow_rows.append({
                        **meta,
                        "flow_id":      fid,
                        "fct_us":       fct,
                        "size":         size,
                        "flow_class":   classify_flow(meta["workload"], fid),
                        "ideal_fct_us": round(ideal, 3),
                        "slowdown":     round(fct / ideal, 4) if ideal > 0 else None,
                    })
                    events["n_flows_finished"] += 1
                    continue
                if "[link_failure] failed" in line:
                    events["pipe_fails"] += 1
                elif "[link_failure] restored" in line:
                    events["pipe_restores"] += 1
                elif "started freezing mode" in line:
                    events["fz_starts"] += 1
                elif "exited freezing mode" in line:
                    events["fz_exits"] += 1
    except FileNotFoundError:
        pass

    return flow_rows, events


def ecn_from_reps_state(state_path: Path) -> dict:
    n_ecn = 0
    n_high = 0
    n_clean = 0
    try:
        with open(state_path, "r", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    ecn = int(row.get("ecn", 0))
                    counter = int(row.get("ecn_counter", 0))
                    if ecn == 1:
                        n_ecn += 1
                        if counter >= 4:
                            n_high += 1
                    else:
                        n_clean += 1
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        pass
    hcr = round(n_high / n_ecn, 4) if n_ecn > 0 else 0.0
    return dict(n_ecn_acks=n_ecn, n_ecn_high_counter=n_high,
                high_counter_rate=hcr, n_clean_acks=n_clean)


def iter_cells():
    for part_dir, tags in [("part_a", PART_A_TAGS), ("part_b", PART_B_TAGS)]:
        for tag in tags:
            for wname in WORKLOADS:
                for sev in SEVERITIES:
                    for seed in SEEDS:
                        cell_dir = (RUNS_DIR / part_dir / tag / wname
                                    / f"sev{sev}" / f"seed{seed}")
                        meta = dict(
                            part=part_label(tag),
                            axis_val=axis_val(tag),
                            workload=wname,
                            sev=sev,
                            seed=seed,
                        )
                        yield (meta,
                               cell_dir / "run.out",
                               cell_dir / "reps_state.csv")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fct_path = DATA_DIR / "v10_fct.csv"
    ev_path  = DATA_DIR / "v10_events.csv"

    fct_cols = [
        "part", "axis_val", "workload", "sev", "seed",
        "flow_id", "fct_us", "size", "flow_class", "ideal_fct_us", "slowdown",
    ]
    ev_cols = [
        "part", "axis_val", "workload", "sev", "seed",
        "n_flows_finished",
        "n_ecn_acks", "n_ecn_high_counter", "high_counter_rate", "n_clean_acks",
        "pipe_fails", "pipe_restores", "fz_starts", "fz_exits",
    ]

    total_cells   = 0
    missing_cells = 0

    with (open(fct_path, "w", newline="") as fct_fh,
          open(ev_path,  "w", newline="") as ev_fh):

        fct_w = csv.DictWriter(fct_fh, fieldnames=fct_cols, extrasaction="ignore")
        ev_w  = csv.DictWriter(ev_fh,  fieldnames=ev_cols,  extrasaction="ignore")
        fct_w.writeheader()
        ev_w.writeheader()

        for meta, out_path, state_path in iter_cells():
            total_cells += 1
            if not out_path.exists():
                missing_cells += 1
                continue

            flow_rows, events = parse_run_out(out_path, meta)

            if state_path.exists():
                ecn_stats = ecn_from_reps_state(state_path)
                events.update(ecn_stats)
            else:
                events["n_ecn_high_counter"] = 0
                events["high_counter_rate"]  = 0.0

            fct_w.writerows(flow_rows)
            ev_w.writerow({**meta, **events})

            if total_cells % 30 == 0:
                print(f"  processed {total_cells} cells ...", flush=True)

    n_present = total_cells - missing_cells
    print(f"Done. {total_cells} cells expected, {n_present} present, {missing_cells} missing.")
    print(f"  → {fct_path}")
    print(f"  → {ev_path}")


if __name__ == "__main__":
    main()
