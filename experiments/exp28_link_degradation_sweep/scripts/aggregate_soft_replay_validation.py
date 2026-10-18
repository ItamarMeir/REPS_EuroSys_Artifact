#!/usr/bin/env python3
"""
Aggregator for run_soft_replay_validation.py's standalone matrix. Reuses
aggregate28.py's own finish-line regex/metric set (same metrics-counters
fields every other experiment here parses) so results are directly
comparable in kind, even though this matrix itself (NSCC, not MPRDMA) is
never mixed into exp28's existing part1/part2 CSVs.

  data/soft_replay_validation/metrics.csv

    python3 aggregate_soft_replay_validation.py
"""
from __future__ import annotations

import csv
import re
import statistics as st
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
RUNS_DIR = EXP_DIR / "runs" / "soft_replay_validation"
DATA_DIR = EXP_DIR / "data" / "soft_replay_validation"

FIN_RE = re.compile(
    r"Flow\s+\S+\s+flowId\s+(\d+)\s+uecSrc\s+(\d+)\s+finished at\s+([\d.eE+-]+)\s+"
    r"flowSize\s+(\d+)\s+total packets\s+(\d+).*?"
    r"\bRTS\s+(\d+)\b.*?"
    r"\becn_acks\s+(\d+)\b.*?"
    r"\brtos\s+(\d+)\b.*?"
    r"\bfreeze_entries\s+(\d+)\b.*?"
    r"\bfreeze_us\s+([\d.eE+-]+).*?"
    r"\bev_explore\s+(\d+)\b.*?"
    r"\bev_random\s+(\d+)\b")


def parse(path: Path) -> list[dict]:
    rows = []
    for m in FIN_RE.finditer(path.read_text(errors="replace")):
        rows.append(dict(
            flow_id=int(m.group(1)), src=int(m.group(2)),
            fct_us=float(m.group(3)), size=int(m.group(4)),
            pkts=int(m.group(5)), rts=int(m.group(6)), ecn=int(m.group(7)),
            rtos=int(m.group(8)), freeze_entries=int(m.group(9)),
            freeze_us=float(m.group(10)), ev_explore=int(m.group(11)),
            ev_random=int(m.group(12))))
    return rows


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stdouts = sorted(RUNS_DIR.rglob("stdout.txt"))
    if not stdouts:
        raise SystemExit(f"no stdout.txt under {RUNS_DIR}")

    cells = []
    for p in stdouts:
        rel = p.relative_to(RUNS_DIR).parts  # <cond>/<arm>/stdout.txt
        cond, arm = rel[0], rel[1]
        rows = parse(p)
        if not rows:
            print(f"  WARN 0 flows: {'/'.join(rel)}")
            continue
        n = len(rows)
        fcts = [r["fct_us"] for r in rows]
        cells.append(dict(
            condition=cond, arm=arm, n_hosts=n,
            fct_p50_us=round(float(np.percentile(fcts, 50)), 3),
            fct_p95_us=round(float(np.percentile(fcts, 95)), 3),
            fct_p99_us=round(float(np.percentile(fcts, 99)), 3),
            fct_max_us=round(float(max(fcts)), 3),
            ecn_per_host=round(st.mean(r["ecn"] for r in rows), 3),
            rto_per_host=round(st.mean(r["rtos"] for r in rows), 4),
            rts_per_host=round(st.mean(r["rts"] for r in rows), 4),
            freeze_entries_total=sum(r["freeze_entries"] for r in rows),
            freeze_hosts_frac=round(
                sum(1 for r in rows if r["freeze_entries"] > 0) / n, 4),
            freeze_us_mean=round(st.mean(r["freeze_us"] for r in rows), 4),
            ev_random_per_host=round(st.mean(r["ev_random"] for r in rows), 2),
            ev_explore_per_host=round(st.mean(r["ev_explore"] for r in rows), 2),
            ev_random_rate=round(
                sum(r["ev_random"] + r["ev_explore"] for r in rows)
                / max(1, sum(r["pkts"] for r in rows)), 5),
        ))

    cols = ["condition", "arm", "n_hosts", "fct_p50_us", "fct_p95_us",
            "fct_p99_us", "fct_max_us", "ecn_per_host", "rto_per_host",
            "rts_per_host", "freeze_entries_total", "freeze_hosts_frac",
            "freeze_us_mean", "ev_random_per_host", "ev_explore_per_host",
            "ev_random_rate"]
    out = DATA_DIR / "metrics.csv"
    order = {"healthy": 0, "asym1": 1, "asym8": 2, "asym16": 3, "asym32": 4,
              "asym4_r95": 5}
    arm_order = {"nscc_baseline": 0, "nscc_fixed_p1": 1, "nscc_ewma": 2,
                 "nscc_ewma_nofilter": 3}
    cells.sort(key=lambda c: (order.get(c["condition"], 99),
                               arm_order.get(c["arm"], 99)))
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(cells)
    print(f"{out}: {len(cells)} cells")


if __name__ == "__main__":
    main()
