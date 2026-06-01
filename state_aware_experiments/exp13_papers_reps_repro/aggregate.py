#!/usr/bin/env python3
"""Parse all *.out files in data/ into tidy CSVs.

Output:
- data/fcts.csv  — one row per finished flow
- data/cct.csv   — one row per (paper, fig, cca/lb, [pct], workload, seed) aggregate

Filename convention (see scripts/lib_common.sh):
  Paper 1: p1_<fig>_<lb>_<tmstem>_s<seed>.out
  Paper 2: p2_<fig>_<cca>[_p<pct>]_s<seed>.out
"""

import csv
import os
import re
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+(\d+)\s+uecSrc\s+(\d+)\s+"
    r"finished at\s+([\d.]+)\s+flowSize\s+(\d+)"
)


def parse_out(path: Path):
    """Yield (flowId, src, fct_us, size_bytes) per finished flow line."""
    seen = set()
    with path.open(errors="ignore") as f:
        for line in f:
            m = FLOW_RE.match(line)
            if not m:
                continue
            flowid = int(m.group(1))
            src = int(m.group(2))
            fct = float(m.group(3))
            size = int(m.group(4))
            # Dedup: some htsim builds emit "Flow ..." twice per finish.
            key = (flowid, src)
            if key in seen:
                continue
            seen.add(key)
            yield flowid, src, fct, size


def classify(name: str):
    """Return (paper, fig, algo, pct_or_none, tmstem, seed)."""
    base = name[:-4] if name.endswith(".out") else name
    parts = base.split("_")
    paper = parts[0]                  # "p1" or "p2"
    fig = parts[1]                    # e.g. "fig02"  (may include sub-tag)

    if paper == "p1":
        # p1_<fig...>_<lb>_<tmstem>_s<seed>.out — fig may be multi-token (e.g.
        # fig02_synth, fig06_5pct_cables_perm8). LB ∈ {freezing, oblivious, ecmp}.
        # Search from the right.
        seed = parts[-1].lstrip("s")
        # Find LB position
        lb_choices = {"freezing", "oblivious", "ecmp", "bitmap", "mprdma", "plb", "flowlet"}
        lb_idx = None
        for i, tok in enumerate(parts[2:], start=2):
            if tok in lb_choices:
                lb_idx = i
                break
        if lb_idx is None:
            return None
        fig_tokens = parts[1:lb_idx]
        fig = "_".join(fig_tokens)
        lb = parts[lb_idx]
        tmstem = "_".join(parts[lb_idx + 1:-1])  # all tokens between lb and seed
        return (paper, fig, lb, None, tmstem, seed)

    elif paper == "p2":
        # p2_<fig>_<cca>[_p<pct>]_s<seed>.out
        seed = parts[-1].lstrip("s")
        # Optional pct token
        pct = None
        if parts[-2].startswith("p") and parts[-2][1:].isdigit():
            pct = parts[-2][1:]
            cca = parts[-3]
            fig = "_".join(parts[1:-3])
        else:
            cca = parts[-2]
            fig = "_".join(parts[1:-2])
        return (paper, fig, cca, pct, "", seed)

    return None


def main():
    fcts_rows = []
    by_run = defaultdict(list)  # (paper,fig,algo,pct,tm,seed) -> [fct]

    for out in sorted(DATA_DIR.glob("*.out")):
        cls = classify(out.name)
        if cls is None:
            print(f"WARN skip unparseable filename: {out.name}")
            continue
        paper, fig, algo, pct, tm, seed = cls

        for flowid, src, fct, size in parse_out(out):
            fcts_rows.append(dict(
                paper=paper, fig=fig, algo=algo, pct=pct or "",
                workload=tm, seed=seed, flow_id=flowid, src=src,
                size_B=size, fct_us=fct,
            ))
            by_run[(paper, fig, algo, pct or "", tm, seed)].append(fct)

    # Write fcts.csv
    fcts_path = DATA_DIR / "fcts.csv"
    if fcts_rows:
        with fcts_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(fcts_rows[0].keys()))
            w.writeheader()
            w.writerows(fcts_rows)
        print(f"wrote {fcts_path}  rows={len(fcts_rows)}")
    else:
        print("WARN: no FCT rows produced — empty data/?")

    # Aggregate to cct.csv
    cct_rows = []
    for (paper, fig, algo, pct, tm, seed), fcts in sorted(by_run.items()):
        if not fcts:
            continue
        fcts_s = sorted(fcts)
        n = len(fcts_s)
        avg = sum(fcts_s) / n
        p50 = fcts_s[n // 2]
        p99 = fcts_s[max(0, int(n * 0.99) - 1)] if n >= 100 else fcts_s[-1]
        mx = max(fcts_s)
        cct_rows.append(dict(
            paper=paper, fig=fig, algo=algo, pct=pct, workload=tm, seed=seed,
            n_flows=n, max_fct=mx, avg_fct=avg, p50_fct=p50, p99_fct=p99,
        ))

    cct_path = DATA_DIR / "cct.csv"
    if cct_rows:
        with cct_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(cct_rows[0].keys()))
            w.writeheader()
            w.writerows(cct_rows)
        print(f"wrote {cct_path}  rows={len(cct_rows)}")


if __name__ == "__main__":
    main()
