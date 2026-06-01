#!/usr/bin/env python3
"""
v7_aggregate.py — exp07 aggregator.

Walks the runs/ directory tree produced by v7_run_matrix.sh and emits three
tidy CSVs to data/:

  v7_fct.csv         — one row per finished flow
  v7_events.csv      — one row per run (event counts + metadata)
  v7_diagnostics.csv — per-ACK rows from reps_state.csv (sources 0, 7, 63)

Tree structure:
  runs/{mode}/{workload}/sev{S}/seed{K}/run.out
  runs/{mode}/{workload}/sev{S}/seed{K}/reps_state.csv

BDP reference constants (400 Gbps, 4-hop RTT at 1 µs/hop, MTU 4150 bytes):
  BDP_PKTS ≈ 48
"""

import re
import csv
import os
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
RUNS_DIR   = EXP_DIR / "runs"
DATA_DIR   = EXP_DIR / "data"

LINK_RATE_BPS = 400_000_000_000
BASE_RTT_US   = 4.0
MTU_BYTES     = 4150
BDP_BYTES     = LINK_RATE_BPS * BASE_RTT_US * 1e-6 / 8   # ~200 000 bytes
BDP_PKTS      = BDP_BYTES / MTU_BYTES                     # ~48 packets

MODES = ["vanilla", "wtd", "sf_md_gain_ecn", "sf_md_gain_fresh",
         "sf_blend_ecn", "sf_blend_fresh"]
WORKLOADS = ["pureperm_8mb", "composite", "perm_32mb", "perm_128mb"]
SEVERITIES = [0, 4]
SEEDS = [42, 43, 44]

# ── Flow utilities ────────────────────────────────────────────────────────────
def ideal_fct_us(size_bytes: int) -> float:
    """Ideal FCT = transmission time + base RTT (in µs)."""
    return size_bytes * 8 / LINK_RATE_BPS * 1e6 + BASE_RTT_US

def classify_flow(workload: str, flow_id: int) -> str:
    """Map (workload, flow_id) → flow_class string."""
    if workload in ("pureperm_8mb", "perm_32mb", "perm_128mb"):
        return "all"
    if workload == "composite":
        # composite.cm layout: ids 1-96 → elephant, 97-352 → mice, 353-416 → incast
        if flow_id <= 96:
            return "elephant"
        if flow_id <= 352:
            return "mice"
        return "incast"
    return "unknown"

# ── Flow-finish parsing ────────────────────────────────────────────────────────
FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+(\d+)\s+\S+\s+\S+\s+finished\s+at\s+(\S+)\s+flowSize\s+(\d+)"
)

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
        n_wtd_lines=0,   # lines mentioning WTD (sanity check, if any debug logging)
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
                elif "[link_failure] failed" in line:
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

# ── REPS state / diagnostics parsing ─────────────────────────────────────────
def parse_reps_state(path: Path, meta: dict) -> list[dict]:
    """
    Parse reps_state.csv. Returns per-ACK row dicts including all smart-filter
    and WTD columns. Used for v7_diagnostics.csv.
    """
    rows = []
    try:
        with open(path, "r", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    r = {**meta}
                    # Core columns (always present)
                    r["time_us"]        = float(row["time_us"])
                    r["src_id"]         = int(row["src_id"])
                    r["ecn"]            = int(row["ecn"])
                    r["fresh"]          = int(row["fresh"])
                    r["cwnd_pkts"]      = float(row["cwnd_pkts"])
                    r["in_flight_pkts"] = float(row["in_flight_pkts"])
                    r["exp_avg_ecn"]    = float(row["exp_avg_ecn"])
                    # Smart-filter columns (present in all new runs)
                    r["buf_size"]       = int(row.get("buf_size", 8))
                    r["ecn_counter"]    = int(row.get("ecn_counter", 0))
                    r["fresh_inv"]      = int(row.get("fresh_inv", 0))
                    r["sf_mode"]        = int(row.get("sf_mode", 0))
                    r["sf_counter_used"]= int(row.get("sf_counter_used", 0))
                    r["sf_ecn_thresh"]  = int(row.get("sf_ecn_thresh", 2))
                    r["sf_gain"]        = float(row.get("sf_gain", 1.0))
                    r["sa_asym"]        = int(row.get("sa_asym", 0))
                    r["cc_ecn_view"]    = int(row.get("cc_ecn_view", 0))
                    # WTD columns
                    r["wtd_enabled"]      = int(row.get("wtd_enabled", 0))
                    r["wtd_can_decrease"] = int(row.get("wtd_can_decrease", 1))
                    rows.append(r)
                except (KeyError, ValueError):
                    continue
    except FileNotFoundError:
        pass
    return rows

# ── Aggregate WTD statistics from diagnostics rows ────────────────────────────
def wtd_stats_from_rows(rows: list[dict]) -> dict:
    """
    Compute per-run WTD diagnostic stats from the per-ACK rows.
    Returns dict with keys: n_ecn_acks, n_wtd_blocked, wtd_block_rate.
    """
    n_ecn = sum(1 for r in rows if r["ecn"] == 1)
    # wtd_can_decrease=0 means WTD was enabled AND exp_avg_ecn < threshold
    n_blocked = sum(1 for r in rows if r["ecn"] == 1 and r["wtd_can_decrease"] == 0)
    rate = round(n_blocked / n_ecn, 4) if n_ecn > 0 else 0.0
    return dict(n_ecn_acks=n_ecn, n_wtd_blocked=n_blocked, wtd_block_rate=rate)

# ── Walk the runs tree ─────────────────────────────────────────────────────────
def iter_cells():
    """
    Yields (meta_dict, run_out_path, reps_state_path) for every cell
    in the design matrix (144 cells). Yields even if files are missing
    so the aggregator can track completeness.

    Tree: runs/{mode}/{workload}/sev{S}/seed{K}/
    """
    for mode in MODES:
        for workload in WORKLOADS:
            for sev in SEVERITIES:
                for seed in SEEDS:
                    cell_dir = RUNS_DIR / mode / workload / f"sev{sev}" / f"seed{seed}"
                    meta = dict(mode=mode, workload=workload, sev=sev, seed=seed)
                    yield meta, cell_dir / "run.out", cell_dir / "reps_state.csv"

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    fct_path   = DATA_DIR / "v7_fct.csv"
    ev_path    = DATA_DIR / "v7_events.csv"
    diag_path  = DATA_DIR / "v7_diagnostics.csv"

    fct_cols = [
        "mode", "workload", "sev", "seed",
        "flow_id", "fct_us", "size", "flow_class", "ideal_fct_us", "slowdown",
    ]
    ev_cols = [
        "mode", "workload", "sev", "seed",
        "n_flows_finished", "pipe_fails", "pipe_restores", "fz_starts", "fz_exits",
        "n_ecn_acks", "n_wtd_blocked", "wtd_block_rate",
    ]
    diag_cols = [
        "mode", "workload", "sev", "seed",
        "time_us", "src_id", "ecn", "fresh", "cwnd_pkts", "in_flight_pkts",
        "exp_avg_ecn", "buf_size", "ecn_counter", "fresh_inv",
        "sf_mode", "sf_counter_used", "sf_ecn_thresh", "sf_gain",
        "sa_asym", "cc_ecn_view", "wtd_enabled", "wtd_can_decrease",
    ]

    total_cells = 0
    missing_cells = 0

    with (open(fct_path,  "w", newline="") as fct_fh,
          open(ev_path,   "w", newline="") as ev_fh,
          open(diag_path, "w", newline="") as diag_fh):

        fct_w  = csv.DictWriter(fct_fh,  fieldnames=fct_cols,  extrasaction="ignore")
        ev_w   = csv.DictWriter(ev_fh,   fieldnames=ev_cols,   extrasaction="ignore")
        diag_w = csv.DictWriter(diag_fh, fieldnames=diag_cols, extrasaction="ignore")
        fct_w.writeheader()
        ev_w.writeheader()
        diag_w.writeheader()

        for meta, out_path, state_path in iter_cells():
            total_cells += 1
            if not out_path.exists():
                missing_cells += 1
                continue

            flow_rows, events = parse_run_out(out_path, meta)
            diag_rows         = parse_reps_state(state_path, meta)

            wtd_s = wtd_stats_from_rows(diag_rows)

            fct_w.writerows(flow_rows)
            diag_w.writerows(diag_rows)
            ev_w.writerow({**meta, **events, **wtd_s})

            if total_cells % 24 == 0:
                print(f"  processed {total_cells}/{total_cells} cells ...", flush=True)

    print(f"Done. {total_cells} cells in matrix, {missing_cells} missing (not yet run).")
    print(f"  → {fct_path}")
    print(f"  → {ev_path}")
    print(f"  → {diag_path}")

if __name__ == "__main__":
    main()
