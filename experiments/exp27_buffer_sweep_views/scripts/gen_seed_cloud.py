#!/usr/bin/env python3
"""
Extract per-seed REPS-B1 speedup-vs-OPS at one flow size from the raw seed-sweep
stdout, for overlaying as a translucent point cloud on a flow-size-sweep plot.

Used for the 3-tier asym32 tornado 3 MiB point, where B=1's Max-FCT tail is a
single-flow lottery (see exp27 README) and the canonical seed-42 value is not
representative.  Writes data/<out>.csv  (seed, ops_max, b1_max, speedup).
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from statistics import median

RE = re.compile(r"finished at ([\d.]+)")
EXP_DIR = Path(__file__).resolve().parent.parent
RUNS = EXP_DIR / "runs" / "fig4" / "micro"
DATA = EXP_DIR / "data"


def maxfct(p: Path) -> float | None:
    if not p.exists():
        return None
    v = [float(m.group(1)) for m in RE.finditer(p.read_text(errors="replace"))]
    return max(v) if v else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wl-prefix", default="tornado_sf")          # sf / 2t / 2t128
    ap.add_argument("--size", type=int, default=3145728)
    ap.add_argument("--cond", default="asym32")
    ap.add_argument("--canonical-wl", default="tornado_sf3145728_s3145728",
                    help="seed-42 workload dir (no _seed suffix)")
    ap.add_argument("--seeds", default="42,43,44,45,46,47,48,49,50,51,52")
    ap.add_argument("--out", default="fig4_3t_b1_3mib_seeds")
    args = ap.parse_args()

    rows = []
    for seed in [int(s) for s in args.seeds.split(",")]:
        if seed == 42:
            d = RUNS / args.canonical_wl / args.cond
        else:
            d = RUNS / f"{args.wl_prefix}{args.size}_seed{seed}_s{args.size}" / args.cond
        o = maxfct(d / "ops" / "stdout.txt")
        b = maxfct(d / "reps_b1" / "stdout.txt")
        if o and b:
            rows.append(dict(seed=seed, ops_max=round(o, 3), b1_max=round(b, 3),
                             speedup=round(o / b, 4)))
    out = DATA / f"{args.out}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["seed", "ops_max", "b1_max", "speedup"])
        w.writeheader()
        w.writerows(rows)
    sp = sorted(r["speedup"] for r in rows)
    print(f"wrote {out}  ({len(rows)} seeds, speedup "
          f"min={sp[0]:.3f} median={median(sp):.3f} max={sp[-1]:.3f})")


if __name__ == "__main__":
    main()
