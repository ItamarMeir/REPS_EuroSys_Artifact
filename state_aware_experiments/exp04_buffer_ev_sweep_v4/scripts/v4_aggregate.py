#!/usr/bin/env python3
"""
v4_aggregate.py — exp04 aggregator.

Walks the runs/ directory tree produced by v4_run_matrix.sh and emits three
tidy CSVs to data/:

  v4_fct.csv    — one row per finished flow
  v4_cwnd.csv   — per-ACK CC/buffer state from reps_state.csv
  v4_events.csv — one row per run (event counts + metadata)

BDP reference constants (400 Gbps, 4-hop RTT at 1 µs/hop, MTU 4150 bytes):
  BDP_PKTS = 48
"""

import re
import sys
import csv
import os
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
RUNS_DIR   = EXP_DIR / "runs"
DATA_DIR   = EXP_DIR / "data"

# BDP = 400e9 b/s × 4e-6 s / 8 / 4150 ≈ 48 packets
LINK_RATE_BPS = 400_000_000_000
BASE_RTT_US   = 4.0
MTU_BYTES     = 4150
BDP_BYTES     = LINK_RATE_BPS * BASE_RTT_US * 1e-6 / 8   # ~200 000 bytes
BDP_PKTS      = BDP_BYTES / MTU_BYTES                     # ~48 packets

# Ideal FCT = flow_size × 8 / link_rate + base_rtt  (in µs)
def ideal_fct_us(size_bytes: int) -> float:
    return size_bytes * 8 / LINK_RATE_BPS * 1e6 + BASE_RTT_US

# ── Flow-finish parsing ────────────────────────────────────────────────────────
FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+(\d+)\s+\S+\s+\S+\s+finished\s+at\s+(\S+)\s+flowSize\s+(\d+)"
)

def classify_flow(workload: str, flow_id: int, size: int) -> str:
    """Map (workload, flow_id) → flow_class string."""
    if workload in ("pureperm_8mb", "perm_32mb", "perm_128mb"):
        return "all"
    if workload == "composite":
        # composite.cm: ids 1-96 → elephant, 97-352 → mice, 353-416 → incast
        if flow_id <= 96:
            return "elephant"
        if flow_id <= 352:
            return "mice"
        return "incast"
    return "unknown"

def parse_run_out(path: Path, meta: dict) -> tuple[list[dict], dict]:
    """
    Parse a single run.out file.
    Returns (flow_rows, event_dict).
    """
    flow_rows = []
    events = dict(
        n_flows_finished=0,
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
                        "flow_id":     fid,
                        "fct_us":      fct,
                        "size":        size,
                        "flow_class":  classify_flow(meta["workload"], fid, size),
                        "ideal_fct_us": round(ideal, 3),
                        "slowdown":    round(fct / ideal, 4) if ideal > 0 else None,
                    })
                    events["n_flows_finished"] += 1
                elif "[link_failure] failed" in line:
                    events["pipe_fails"] += 1
                elif "[link_failure] restored" in line:
                    events["pipe_restores"] += 1
                elif "started freezing mode" in line:
                    events["fz_starts"] += 1
                elif "exited freezing mode" in line:
                    events["fz_exits"] += 1
    except FileNotFoundError:
        pass  # run not yet completed

    return flow_rows, events

# ── REPS state log parsing ─────────────────────────────────────────────────────
CWND_COLS = ["time_us", "src_id", "ecn", "fresh", "recycle",
             "cwnd_pkts", "in_flight_pkts", "exp_avg_ecn"]

def parse_reps_state(path: Path, meta: dict) -> list[dict]:
    """Parse reps_state.csv; return list of row dicts with derived columns."""
    rows = []
    try:
        with open(path, "r", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    cwnd  = float(row["cwnd_pkts"])
                    inflt = float(row["in_flight_pkts"])
                    rows.append({
                        **meta,
                        "time_us":       float(row["time_us"]),
                        "ecn":           int(row["ecn"]),
                        "fresh":         int(row["fresh"]),
                        "recycle":       int(row["recycle"]),
                        "cwnd_pkts":     cwnd,
                        "in_flight_pkts": inflt,
                        "exp_avg_ecn":   float(row["exp_avg_ecn"]),
                        # Derived utilisation metrics
                        "cwnd_bdp":      round(cwnd / BDP_PKTS, 4),
                        "fill_rate":     round(inflt / cwnd,   4) if cwnd > 0 else 0.0,
                        "net_fill":      round(inflt / BDP_PKTS, 4),
                    })
                except (KeyError, ValueError):
                    continue  # skip malformed rows
    except FileNotFoundError:
        pass
    return rows

# ── Walk the runs tree ─────────────────────────────────────────────────────────
def iter_cells():
    """
    Yields (meta_dict, run_out_path, reps_state_path) for every completed cell.
    Expected tree:
      runs/
        partA/buf{N}/{workload}/sev{S}/seed{K}/run.out
        partA/buf{N}/{workload}/sev{S}/seed{K}/reps_state.csv
        partB/ev{N}/{workload}/sev{S}/seed{K}/run.out
        ...
    """
    for part_dir in sorted(RUNS_DIR.glob("part*")):
        part = part_dir.name  # partA or partB
        for dim_dir in sorted(part_dir.iterdir()):
            dim_name = dim_dir.name  # buf1, buf2, ..., ev1, ev4, ...
            if dim_name.startswith("buf"):
                buf = int(dim_name[3:])
                ev_domain = 16        # fixed in Part A
            elif dim_name.startswith("ev"):
                ev_domain = int(dim_name[2:])
                buf = 1024            # fixed in Part B
            else:
                continue
            for wname_dir in sorted(dim_dir.iterdir()):
                workload = wname_dir.name
                for sev_dir in sorted(wname_dir.iterdir()):
                    sev = int(sev_dir.name.replace("sev", ""))
                    for seed_dir in sorted(sev_dir.iterdir()):
                        seed = int(seed_dir.name.replace("seed", ""))
                        meta = dict(
                            part=part, buf=buf, ev_domain=ev_domain,
                            sev=sev, seed=seed, workload=workload,
                        )
                        yield meta, seed_dir / "run.out", seed_dir / "reps_state.csv"

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    fct_path    = DATA_DIR / "v4_fct.csv"
    cwnd_path   = DATA_DIR / "v4_cwnd.csv"
    events_path = DATA_DIR / "v4_events.csv"

    fct_cols = ["part", "buf", "ev_domain", "sev", "seed", "workload",
                "flow_id", "fct_us", "size", "flow_class",
                "ideal_fct_us", "slowdown"]
    cwnd_cols = ["part", "buf", "ev_domain", "sev", "seed", "workload",
                 "time_us", "ecn", "fresh", "recycle",
                 "cwnd_pkts", "in_flight_pkts", "exp_avg_ecn",
                 "cwnd_bdp", "fill_rate", "net_fill"]
    ev_cols   = ["part", "buf", "ev_domain", "sev", "seed", "workload",
                 "n_flows_finished", "pipe_fails", "pipe_restores",
                 "fz_starts", "fz_exits"]

    total_cells = 0
    missing_cells = 0

    with (open(fct_path, "w", newline="")    as fct_fh,
          open(cwnd_path, "w", newline="")   as cwnd_fh,
          open(events_path, "w", newline="") as ev_fh):

        fct_w    = csv.DictWriter(fct_fh,    fieldnames=fct_cols,    extrasaction="ignore")
        cwnd_w   = csv.DictWriter(cwnd_fh,   fieldnames=cwnd_cols,   extrasaction="ignore")
        ev_w     = csv.DictWriter(ev_fh,     fieldnames=ev_cols,     extrasaction="ignore")
        fct_w.writeheader()
        cwnd_w.writeheader()
        ev_w.writeheader()

        for meta, out_path, state_path in iter_cells():
            total_cells += 1
            if not out_path.exists():
                missing_cells += 1
                continue

            flow_rows, events = parse_run_out(out_path, meta)
            cwnd_rows         = parse_reps_state(state_path, meta)

            fct_w.writerows(flow_rows)
            cwnd_w.writerows(cwnd_rows)
            ev_w.writerow({**meta, **events})

            if total_cells % 50 == 0:
                print(f"  processed {total_cells} cells ...", flush=True)

    print(f"Done. {total_cells} cells found, {missing_cells} missing (runs not yet complete).")
    print(f"  → {fct_path}")
    print(f"  → {cwnd_path}")
    print(f"  → {events_path}")

if __name__ == "__main__":
    main()
