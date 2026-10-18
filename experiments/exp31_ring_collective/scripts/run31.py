#!/usr/bin/env python3
"""
exp31 runner. Idempotent (skips a cell whose stdout.txt already finished).

  python3 run31.py                       # full matrix (12 scenarios x 3 arms x 3 seeds)
  python3 run31.py --scenarios healthy,fail_one_cable --seeds 42   # smoke

Layout: runs/<scenario>/seed<seed>/<arm>/stdout.txt

Run in Docker (reps-artifact) with the repo bind-mounted, per CLAUDE.md.
"""
from __future__ import annotations

import argparse
import itertools

import common31 as C
from common31 import DC_DIR, RUNS_DIR, base_flags, run_one


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=",".join(C.SCENARIOS))
    ap.add_argument("--arms", default=",".join(C.ARMS))
    ap.add_argument("--seeds", default=",".join(str(s) for s in C.SEEDS))
    args = ap.parse_args()

    C.ensure_cm()
    scenarios = [s for s in C.SCENARIOS if s in args.scenarios.split(",")]
    arms = [a for a in C.ARMS if a in args.arms.split(",")]
    seeds = [int(s) for s in args.seeds.split(",")]

    cells = list(itertools.product(scenarios, seeds, arms))
    print(f"exp31: {len(cells)} runs  (scenarios={scenarios}, arms={arms}, "
          f"seeds={seeds})", flush=True)

    fails = 0
    for i, (scen, seed, arm) in enumerate(cells, 1):
        outfile = RUNS_DIR / scen / f"seed{seed}" / arm / "stdout.txt"
        res = run_one(base_flags(arm, scen, seed), outfile, cwd=DC_DIR,
                      expect_cm_nodes=32)
        extra = f"  {res['nflows']}/{C.N_EXPECTED} flows, {res['seconds']}s"
        if res.get("cm_warn"):
            extra += f"  *** {res['cm_warn']} ***"
        print(f"[{i}/{len(cells)}] {res['status']:<18} {scen}/{arm}/s{seed}{extra}",
              flush=True)
        if res["status"].startswith("FAIL"):
            fails += 1

    print(f"\nexp31 done: {fails} failures / {len(cells)}", flush=True)


if __name__ == "__main__":
    main()
