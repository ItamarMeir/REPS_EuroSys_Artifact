#!/usr/bin/env python3
"""
v11_aggregate.py — exp11 paper-workload filter comparison aggregator.

Walks runs/{mode}/{workload}/sev{S}/seed{K}/{run.out,reps_state.csv} and emits:

  data/v11_fct.csv         — one row per finished flow
  data/v11_events.csv      — one row per simulation run
  data/v11_diagnostics.csv — per-ACK rows from reps_state.csv (logged sources)

Flow-class binning (per-workload, id-based):
  baseline: ids 1-4 → ecmp_elephant, ids 5-128 → sprayed_perm
  perm    : all 128 → perm
  hsdp    : all 128 → hsdp_ring
  incast32: all 32  → incast
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

MODES = [
    "vanilla", "wtd",
    "sf_md_gain_ecn", "sf_md_gain_fresh", "sf_md_gain_evhealth",
    "sf_blend_ecn",   "sf_blend_fresh",   "sf_blend_evhealth",
]
WORKLOADS  = ["baseline", "perm", "hsdp", "incast32"]
SEVERITIES = [0, 4]
SEEDS      = [42, 43, 44]


def ideal_fct_us(size_bytes: int) -> float:
    return size_bytes * 8 / LINK_RATE_BPS * 1e6 + BASE_RTT_US


def classify_flow(workload: str, flow_id: int) -> str:
    if workload == "baseline":
        return "ecmp_elephant" if flow_id <= 4 else "sprayed_perm"
    if workload == "perm":     return "perm"
    if workload == "hsdp":     return "hsdp_ring"
    if workload == "incast32": return "incast"
    return "unknown"


FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+(\d+)\s+\S+\s+\S+\s+finished\s+at\s+(\S+)\s+flowSize\s+(\d+)"
)


def parse_run_out(path: Path, meta: dict) -> tuple:
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


def parse_reps_state(path: Path, meta: dict) -> list:
    rows = []
    try:
        with open(path, "r", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    r = {**meta}
                    r["time_us"]          = float(row["time_us"])
                    r["src_id"]           = int(row["src_id"])
                    r["ecn"]              = int(row["ecn"])
                    r["fresh"]            = int(row["fresh"])
                    r["cwnd_pkts"]        = float(row["cwnd_pkts"])
                    r["in_flight_pkts"]   = float(row["in_flight_pkts"])
                    r["exp_avg_ecn"]      = float(row["exp_avg_ecn"])
                    r["buf_size"]         = int(row.get("buf_size", 8))
                    r["ecn_counter"]      = int(row.get("ecn_counter", 0))
                    r["sf_mode"]          = int(row.get("sf_mode", 0))
                    r["sf_counter_used"]  = int(row.get("sf_counter_used", 0))
                    r["sf_ecn_thresh"]    = int(row.get("sf_ecn_thresh", 2))
                    r["sf_gain"]          = float(row.get("sf_gain", 1.0))
                    r["wtd_enabled"]      = int(row.get("wtd_enabled", 0))
                    r["wtd_can_decrease"] = int(row.get("wtd_can_decrease", 1))
                    rows.append(r)
                except (KeyError, ValueError):
                    continue
    except FileNotFoundError:
        pass
    return rows


def diag_stats(rows: list) -> dict:
    n_ecn   = sum(1 for r in rows if r["ecn"] == 1)
    n_clean = sum(1 for r in rows if r["ecn"] == 0)
    n_wtd_blocked = sum(1 for r in rows if r["ecn"] == 1 and r["wtd_can_decrease"] == 0)
    wtd_block_rate = round(n_wtd_blocked / n_ecn, 4) if n_ecn > 0 else 0.0
    n_high = sum(1 for r in rows if r["ecn"] == 1 and r["ecn_counter"] >= 4)
    hcr = round(n_high / n_ecn, 4) if n_ecn > 0 else 0.0
    gains = [r["sf_gain"] for r in rows if r["ecn"] == 1]
    mean_gain = round(sum(gains) / len(gains), 4) if gains else 1.0
    return dict(
        n_ecn_acks=n_ecn, n_clean_acks=n_clean,
        n_wtd_blocked=n_wtd_blocked, wtd_block_rate=wtd_block_rate,
        n_ecn_high_counter=n_high, high_counter_rate=hcr,
        mean_ecn_sf_gain=mean_gain,
    )


def iter_cells():
    for mode in MODES:
        for wname in WORKLOADS:
            for sev in SEVERITIES:
                for seed in SEEDS:
                    cell_dir = (RUNS_DIR / mode / wname
                                / f"sev{sev}" / f"seed{seed}")
                    meta = dict(mode=mode, workload=wname, sev=sev, seed=seed)
                    yield (meta,
                           cell_dir / "run.out",
                           cell_dir / "reps_state.csv")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fct_path  = DATA_DIR / "v11_fct.csv"
    ev_path   = DATA_DIR / "v11_events.csv"
    diag_path = DATA_DIR / "v11_diagnostics.csv"

    fct_cols = [
        "mode", "workload", "sev", "seed",
        "flow_id", "fct_us", "size", "flow_class", "ideal_fct_us", "slowdown",
    ]
    ev_cols = [
        "mode", "workload", "sev", "seed",
        "n_flows_finished", "pipe_fails", "pipe_restores", "fz_starts", "fz_exits",
        "n_ecn_acks", "n_clean_acks", "n_wtd_blocked", "wtd_block_rate",
        "n_ecn_high_counter", "high_counter_rate", "mean_ecn_sf_gain",
    ]
    diag_cols = [
        "mode", "workload", "sev", "seed",
        "time_us", "src_id", "ecn", "fresh", "cwnd_pkts", "in_flight_pkts",
        "exp_avg_ecn", "buf_size", "ecn_counter",
        "sf_mode", "sf_counter_used", "sf_ecn_thresh", "sf_gain",
        "wtd_enabled", "wtd_can_decrease",
    ]

    total_cells   = 0
    missing_cells = 0

    with (open(fct_path,  "w", newline="") as fct_fh,
          open(ev_path,   "w", newline="") as ev_fh,
          open(diag_path, "w", newline="") as diag_fh):

        fct_w  = csv.DictWriter(fct_fh,  fieldnames=fct_cols,  extrasaction="ignore")
        ev_w   = csv.DictWriter(ev_fh,   fieldnames=ev_cols,   extrasaction="ignore")
        diag_w = csv.DictWriter(diag_fh, fieldnames=diag_cols, extrasaction="ignore")
        fct_w.writeheader(); ev_w.writeheader(); diag_w.writeheader()

        for meta, out_path, state_path in iter_cells():
            total_cells += 1
            if not out_path.exists():
                missing_cells += 1
                continue

            flow_rows, events = parse_run_out(out_path, meta)
            diag_rows         = parse_reps_state(state_path, meta)
            ds                = diag_stats(diag_rows)

            fct_w.writerows(flow_rows)
            diag_w.writerows(diag_rows)
            ev_w.writerow({**meta, **events, **ds})

            if total_cells % 30 == 0:
                print(f"  processed {total_cells} cells ...", flush=True)

    print(f"Done. {total_cells} cells expected, "
          f"{total_cells - missing_cells} present, {missing_cells} missing.")
    print(f"  → {fct_path}")
    print(f"  → {ev_path}")
    print(f"  → {diag_path}")


if __name__ == "__main__":
    main()
