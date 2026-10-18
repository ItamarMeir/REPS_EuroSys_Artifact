#!/usr/bin/env python3
"""
exp28 second-pass aggregator — per-cell diagnostic metrics.

exp26/scripts/aggregate.py already produces FCT stats (max/p99/p50/mean) and
speedup_vs_ops_* from the same stdout.txt files; run it first with
EXP26_RUNS/EXP26_DATA pointed at this experiment.  This pass re-reads the same
files for the fields exp28's metrics-counters patch appended to the finish line
(rtos / freeze_entries / freeze_us / ev_explore / ev_random) plus ecn_acks and
RTS, and emits one row per (part, workload, condition, arm) cell.

  data/part1/metrics.csv , data/part2/metrics.csv

Columns:
  part, workload, condition, arm, buf_size, n_hosts,
  fct_p95_us,                       # the 95th pct plot.py's summary omits
  ecn_per_host, rto_per_host, rts_per_host,
  freeze_entries_total, freeze_hosts_frac, freeze_us_mean,
  ev_random_per_host, ev_explore_per_host, ev_random_rate
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics as st
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent

# Anchored on the finish-line prefix, then tolerant lookups for the appended
# fields (freeze_us may print in scientific notation for tiny intervals).
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


def buf_size(arm: str) -> str:
    return "" if arm == "ops" else arm[len("reps_b"):]


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


def run(part: str) -> None:
    runs_dir = EXP_DIR / "runs" / part / "micro"
    data_dir = EXP_DIR / "data" / part
    data_dir.mkdir(parents=True, exist_ok=True)
    stdouts = sorted(runs_dir.rglob("stdout.txt"))
    if not stdouts:
        print(f"{part}: no stdout.txt under {runs_dir}")
        return

    cells = []
    for p in stdouts:
        rel = p.relative_to(runs_dir).parts   # <workload>/<cond>/<arm>/stdout.txt
        workload, condition, arm = rel[0], rel[1], rel[2]
        rows = parse(p)
        if not rows:
            print(f"  WARN 0 flows: {'/'.join(rel)}")
            continue
        n = len(rows)
        fcts = [r["fct_us"] for r in rows]
        cells.append(dict(
            part=part, workload=workload, condition=condition, arm=arm,
            buf_size=buf_size(arm), n_hosts=n,
            fct_p95_us=round(float(np.percentile(fcts, 95)), 3),
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

    # Coverage check: every flow exp26's aggregator counted must have matched our
    # extended regex too. A partial match (scientific-notation field, format
    # drift) silently biases the per-host means, so fail loudly.
    summ = data_dir / "summary.csv"
    if summ.exists():
        import csv as _csv
        want = {}
        with open(summ) as f:
            for r in _csv.DictReader(f):
                want[(r["workload"], r["condition"], r["arm"])] = int(r["n_flows"])
        bad = []
        for c in cells:
            k = (c["workload"], c["condition"], c["arm"])
            if k in want and want[k] != c["n_hosts"]:
                bad.append(f"{'/'.join(k)}: regex {c['n_hosts']} vs summary {want[k]}")
        if bad:
            raise SystemExit("aggregate28: finish-line regex under-matched:\n  "
                             + "\n  ".join(bad))
    else:
        print(f"  (no {summ} yet — run exp26 aggregate.py first for coverage check)")

    cols = ["part", "workload", "condition", "arm", "buf_size", "n_hosts",
            "fct_p95_us", "ecn_per_host", "rto_per_host", "rts_per_host",
            "freeze_entries_total", "freeze_hosts_frac", "freeze_us_mean",
            "ev_random_per_host", "ev_explore_per_host", "ev_random_rate"]
    out = data_dir / "metrics.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(sorted(cells, key=lambda c: (c["workload"], c["arm"])))
    print(f"{out}: {len(cells)} cells")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="part1,part2")
    args = ap.parse_args()
    for part in args.parts.split(","):
        run(part)


if __name__ == "__main__":
    main()
