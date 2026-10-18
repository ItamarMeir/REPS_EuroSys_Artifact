#!/usr/bin/env python3
"""
exp28 part 1 — link-count sweep.

X-axis = number of degraded ToR->spine-0 uplinks, D in {0,1,2,4,8,16,32}.
Each D>0 degrades exactly the spine-0 (agg index 0) uplink of D of the 32 ToRs
to 50% linkspeed via `-failed D -skip_asy` (verified: stdout prints
`Failure: LS<tor>->US0 ... set to 200`).

Arms: ops + reps_b{1,2,4,8,16,32}. Seed 42, single seed (exp26/27 convention).
7 D x 7 arms = 49 runs.

Layout (so exp26/scripts/aggregate.py runs unchanged under EXP26_RUNS/EXP26_DATA):
  runs/part1/micro/tornado_deg<D>_s16777216/<cond>/<arm>/stdout.txt
  cond = "healthy" for D=0, "asym<D>" otherwise.

Runs in Docker (reps-artifact), per CLAUDE.md.
"""
from __future__ import annotations

import argparse
import itertools

from common28 import ARMS, DC_DIR, RUNS_DIR, base_flags, run_one, wl_name

# Non-power-of-2 D: -failed D -skip_asy still degrades exactly D spine-0 uplinks
# (fail_every = 32//D picks the ToRs, the degraded_cables<D cap stops at D), the
# selected ToRs are just non-uniformly spaced. Count is what the X-axis means.
# D=11,12,13,15 added to resolve the knee's slope (all share fail_every=32//D==2
# with the existing D=11..16 cluster -- nested ToR subsets, not independently
# placed; the knee is a count effect, not a placement effect).
DS = [0, 1, 2, 4, 5, 7, 8, 10, 11, 12, 13, 14, 15, 16, 20, 25, 32]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", default=",".join(str(d) for d in DS))
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    ds = [int(d) for d in args.ds.split(",")]
    arms = [a for a in ARMS if a in args.arms.split(",")]
    cells = list(itertools.product(ds, arms))
    print(f"part1: {len(cells)} runs  (D={ds}, seed={args.seed})", flush=True)

    fails = 0
    for i, (d, arm) in enumerate(cells, 1):
        cond = "healthy" if d == 0 else f"asym{d}"
        wl = wl_name(f"tornado_deg{d}", args.seed)
        outfile = RUNS_DIR / "part1" / "micro" / wl / cond / arm / "stdout.txt"
        res = run_one(base_flags(arm, d, None, seed=args.seed), outfile, cwd=DC_DIR)
        extra = f"  {res['nflows']} flows, {res['seconds']}s"
        if res["tor_ecn_reenabled"]:
            extra += "  [tor-ecn-reenabled]"   # expected: -disable_tor_ecn omitted
        print(f"[{i}/{len(cells)}] {res['status']:<18} D={d}/{arm}{extra}", flush=True)
        if res["status"].startswith("FAIL"):
            fails += 1

    print(f"\npart1 done: {fails} failures / {len(cells)}", flush=True)


if __name__ == "__main__":
    main()
