#!/usr/bin/env python3
"""
exp28 part 2 — degradation-severity sweep.

Fixed `-failed 4 -skip_asy` (always the spine-0 uplink of ToRs 0/8/16/24).
X-axis = degradation %, swept via `-down_ratio r` where the degraded link keeps
fraction `r` of its capacity (speed, buffer AND ECN thresholds all *= r):

    degradation % = (1 - r) * 100

  r     : 1.0  0.9  0.75  0.5  0.25  0.1  0.05
  deg % :  0    10    25   50    75   90    95

The 0 % point is NOT run here (r=1.0 still routes through the reduced-speed
branch and prints a spurious `Failure:` line) — it is part 1's D=0 `healthy`
cell, which plot_part2.py reads directly. True 100 % (r=0) is degenerate
(zero-speed / zero-depth / zero-ECN queue) so the sweep floors at r=0.05.

Arms: ops + reps_b{1,2,4,8,16,32}. Seed 42. 6 ratios x 7 arms = 42 runs.

Layout:
  runs/part2/micro/tornado_deg4_r<pct>_s16777216/asym4_r<pct>/<arm>/stdout.txt
"""
from __future__ import annotations

import argparse
import itertools

from common28 import ARMS, DC_DIR, RUNS_DIR, base_flags, run_one, wl_name

# (down_ratio, degradation-percent label)
RATIOS = [(0.90, 10), (0.75, 25), (0.50, 50), (0.40, 60), (0.30, 70),
          (0.25, 75), (0.20, 80), (0.10, 90), (0.05, 95)]
FAILED = 4


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcts", default=",".join(str(p) for _, p in RATIOS),
                    help="comma list of degradation-percent points to run")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    want = {int(x) for x in args.pcts.split(",")}
    ratios = [(r, p) for r, p in RATIOS if p in want]
    arms = [a for a in ARMS if a in args.arms.split(",")]
    cells = list(itertools.product(ratios, arms))
    print(f"part2: {len(cells)} runs  (-failed {FAILED}, deg%={sorted(want)}, "
          f"seed={args.seed})", flush=True)

    fails = 0
    for i, ((r, pct), arm) in enumerate(cells, 1):
        cond = f"asym{FAILED}_r{pct:02d}"
        wl = wl_name(f"tornado_deg{FAILED}_r{pct:02d}", args.seed)
        outfile = RUNS_DIR / "part2" / "micro" / wl / cond / arm / "stdout.txt"
        res = run_one(base_flags(arm, FAILED, r, seed=args.seed), outfile, cwd=DC_DIR)
        extra = f"  {res['nflows']} flows, {res['seconds']}s"
        print(f"[{i}/{len(cells)}] {res['status']:<18} deg{pct}%/{arm}{extra}",
              flush=True)
        if res["status"].startswith("FAIL"):
            fails += 1

    print(f"\npart2 done: {fails} failures / {len(cells)}", flush=True)


if __name__ == "__main__":
    main()
