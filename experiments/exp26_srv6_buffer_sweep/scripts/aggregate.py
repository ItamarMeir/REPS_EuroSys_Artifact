#!/usr/bin/env python3
"""
aggregate.py — parse exp26 run outputs into tidy CSVs.

Walks runs/<fig>/<workload>/<condition>/<arm>/stdout.txt and emits:

  data/flows.csv.gz one row per finished flow (gzipped: ~800k rows uncompressed)
      fig, workload, condition, arm, buf_size, seed, flow_name, flow_id, src,
      fct_us, size_bytes, ideal_fct_us, slowdown
  data/summary.csv  one row per (fig, workload, condition, arm) cell
      ... n_flows, n_connections, n_expected, unfinished, unfinished_vs_best,
      mean_fct_us, p50_fct_us, p99_fct_us, max_fct_us, mean_slowdown,
      speedup_vs_ops_mean, speedup_vs_ops_max, cm_nodes, tor_ecn_reenabled

Flow counts
-----------
``n_connections`` comes from htsim's own ``Nodes: N Connections: C`` banner —
the exact number of flows the connection matrix defines. Two shortfall columns:

  unfinished         = n_connections - n_flows
                       True shortfall. Includes *structural* losses that hit
                       every arm equally (e.g. fig7/permutation/fail_one_switch,
                       where one host sits behind the failed switch and no LB
                       algorithm can reach it: all 4 arms finish 31/32).
  unfinished_vs_best = max(n_flows in cell) - n_flows
                       LB-attributable shortfall. This is what plot.py annotates,
                       because it isolates "this arm stalled where another arm
                       did not" from the structural floor.

A cell where an arm did not finish every flow has its FCT statistics computed
over the finished subset only, which biases that arm's mean/max *downward* — so
a speedup measured against a short OPS arm understates REPS's advantage.

fig6 has no FCT framing; its per-link time series are handled by plot_fig6.py
directly from the raw_output/ folders. fig6 rows are still emitted so completion
can be checked.
"""
from __future__ import annotations

import csv
import gzip
import os
import re
import statistics as st
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
RUNS_DIR = Path(os.environ.get("EXP26_RUNS", EXP_DIR / "runs"))
DATA_DIR = Path(os.environ.get("EXP26_DATA", EXP_DIR / "data"))

LINKSPEED_BPS = 400_000 * 1_000_000  # 400 Gbps

# "Flow Uec_721_710 flowId 947 uecSrc 946 finished at 177.026 flowSize 8388608 ..."
FINISH_RE = re.compile(
    r"Flow\s+(\S+)\s+flowId\s+(\d+)\s+uecSrc\s+(\d+)\s+"
    r"finished at\s+([\d.]+)\s+flowSize\s+(\d+)", re.IGNORECASE)
# htsim's connection-matrix banner: the exact expected flow count.
HDR_RE = re.compile(r"^Nodes:\s+(\d+)\s+Connections:\s+(\d+)", re.MULTILINE)

SEED = {"fig2": 42, "fig4": 42, "fig6": 5, "fig7": 42, "fig8": 44}
# dc/ai panels of fig2/fig4 use seed 1019
SEED_OVERRIDE = {("fig2", "dc"): 1019, ("fig2", "ai"): 1019,
                 ("fig4", "dc"): 1019, ("fig4", "ai"): 1019}


def buf_size(arm: str) -> str:
    if arm == "ops":
        return ""
    return arm[len("reps_b"):]


def parse_stdout(path: Path) -> tuple[list[dict], int, int, bool]:
    """-> (flow rows, n_connections, cm_nodes, tor_ecn_reenabled)."""
    rows = []
    txt = path.read_text(errors="replace")
    tor_ecn = "enable on tor downlink 1" in txt
    hdr = HDR_RE.search(txt)
    cm_nodes = int(hdr.group(1)) if hdr else -1
    n_conns = int(hdr.group(2)) if hdr else -1
    for m in FINISH_RE.finditer(txt):
        fct_us = float(m.group(4))
        size_bytes = int(m.group(5))
        ideal = (size_bytes * 8) / LINKSPEED_BPS * 1e6
        rows.append({
            "flow_name": m.group(1),
            "flow_id": int(m.group(2)),
            "src": int(m.group(3)),
            "fct_us": fct_us,
            "size_bytes": size_bytes,
            "ideal_fct_us": round(ideal, 4),
            "slowdown": round(fct_us / ideal, 4) if ideal else float("nan"),
        })
    return rows, n_conns, cm_nodes, tor_ecn


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stdouts = sorted(RUNS_DIR.rglob("stdout.txt"))
    if not stdouts:
        print(f"no stdout.txt under {RUNS_DIR}")
        return

    flow_rows: list[dict] = []
    cells: dict[tuple, dict] = {}

    for p in stdouts:
        rel = p.relative_to(RUNS_DIR).parts  # <fig>/.../<arm>/stdout.txt
        fig = rel[0]
        arm = rel[-2]
        if fig in ("fig2", "fig4"):
            # <fig>/<panel>/<workload>/<condition>/<arm>/stdout.txt
            panel, workload, condition = rel[1], rel[2], rel[3]
            workload = f"{panel}::{workload}"
        else:
            # <fig>/<workload>/<condition>/<arm>/stdout.txt
            workload, condition = rel[1], rel[2]
            panel = workload
        seed = SEED_OVERRIDE.get((fig, panel), SEED.get(fig, 0))

        rows, n_conns, cm_nodes, tor_ecn = parse_stdout(p)
        key = (fig, workload, condition, arm)
        fcts = [r["fct_us"] for r in rows]
        cells[key] = {
            "fig": fig, "workload": workload, "condition": condition, "arm": arm,
            "buf_size": buf_size(arm), "seed": seed,
            "n_flows": len(rows),
            "n_connections": n_conns,
            "cm_nodes": cm_nodes,
            "mean_fct_us": round(st.mean(fcts), 3) if fcts else "",
            "p50_fct_us": round(st.median(fcts), 3) if fcts else "",
            "p99_fct_us": round(float(np.percentile(fcts, 99)), 3) if fcts else "",
            "max_fct_us": round(max(fcts), 3) if fcts else "",
            "mean_slowdown": round(st.mean(r["slowdown"] for r in rows), 4) if rows else "",
            "tor_ecn_reenabled": int(tor_ecn),
        }
        for r in rows:
            flow_rows.append({
                "fig": fig, "workload": workload, "condition": condition,
                "arm": arm, "buf_size": buf_size(arm), "seed": seed, **r,
            })

    # shortfall + speedup, per (fig, workload, condition) group
    groups: dict[tuple, list[tuple]] = {}
    for key in cells:
        groups.setdefault(key[:3], []).append(key)
    for gkey, keys in groups.items():
        ops_key = gkey + ("ops",)
        ops = cells.get(ops_key)
        ops_mean = ops["mean_fct_us"] if ops and ops["n_flows"] else None
        ops_max = ops["max_fct_us"] if ops and ops["n_flows"] else None
        # best arm in the cell -> the LB-attributable shortfall floor
        n_best = max((cells[k]["n_flows"] for k in keys), default=0)
        for k in keys:
            c = cells[k]
            n_exp = c["n_connections"] if c["n_connections"] > 0 else n_best
            c["n_expected"] = n_exp
            c["unfinished"] = n_exp - c["n_flows"]
            c["unfinished_vs_best"] = n_best - c["n_flows"]
            c["speedup_vs_ops_mean"] = (
                round(ops_mean / c["mean_fct_us"], 4)
                if ops_mean and c["mean_fct_us"] != "" else "")
            c["speedup_vs_ops_max"] = (
                round(ops_max / c["max_fct_us"], 4)
                if ops_max and c["max_fct_us"] != "" else "")

    flow_cols = ["fig", "workload", "condition", "arm", "buf_size", "seed",
                 "flow_name", "flow_id", "src", "fct_us", "size_bytes",
                 "ideal_fct_us", "slowdown"]
    # gzipped: the 128-rank collectives push this past 70 MB in plain text
    with gzip.open(DATA_DIR / "flows.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=flow_cols)
        w.writeheader()
        w.writerows(flow_rows)

    sum_cols = ["fig", "workload", "condition", "arm", "buf_size", "seed",
                "n_flows", "n_connections", "n_expected", "unfinished",
                "unfinished_vs_best", "mean_fct_us", "p50_fct_us", "p99_fct_us",
                "max_fct_us", "mean_slowdown", "speedup_vs_ops_mean",
                "speedup_vs_ops_max", "cm_nodes", "tor_ecn_reenabled"]
    with open(DATA_DIR / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sum_cols, extrasaction="ignore")
        w.writeheader()
        for k in sorted(cells):
            w.writerow(cells[k])

    print(f"flows.csv.gz: {len(flow_rows)} rows")
    print(f"summary.csv : {len(cells)} cells")
    bad = [k for k, c in cells.items() if c["n_flows"] == 0]
    if bad:
        print(f"WARNING {len(bad)} cells with 0 finished flows:")
        for k in bad:
            print("  ", "/".join(k))
    short = [(k, c) for k, c in cells.items() if c["unfinished_vs_best"] > 0]
    if short:
        print(f"{len(short)} arms finished fewer flows than the best arm in "
              f"their cell (LB-attributable):")
        for k, c in sorted(short):
            print(f"   {'/'.join(k[:3]):52s} {k[3]:9s} "
                  f"{c['n_flows']}/{c['n_expected']}")
    struct = sorted({k[:3] for k, c in cells.items()
                     if c["unfinished"] > 0 and c["unfinished_vs_best"] == 0})
    if struct:
        print(f"{len(struct)} cells short for EVERY arm (structural, not LB):")
        for g in struct:
            c = cells[g + ("ops",)]
            print(f"   {'/'.join(g):52s} all arms {c['n_flows']}/{c['n_expected']}")


if __name__ == "__main__":
    main()
