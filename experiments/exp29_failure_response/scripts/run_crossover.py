#!/usr/bin/env python3
"""
exp29 driver -- F (# failed ToR0 uplinks) x arm x seed x exit_freeze.

Primary batch  : F in {1,4,8,16,24,31}, arm in reps_b{1,2,4,8,32}, seed {42,43,44},
                 exit_freeze 100 us = 90 runs.
Secondary batch: exit_freeze 250 us, F in {1,16,31} only               = 45 runs.
                 (run with --ef 250 --fs 1,16,31)

16 MiB tornado, transient failure t in (100,200) us.

Layout (so exp26/scripts/aggregate.py can run over it too, fig="micro"):
  runs/micro/tornado_F<F>_ef<EF>_s16777216/asymF<F>_seed<seed>/<arm>/stdout.txt
  runs/micro/.../<arm>/window.csv        (per-host metric-delta time series)

Runs in Docker (reps-artifact), per CLAUDE.md.
"""
from __future__ import annotations

import argparse
import itertools

from common29 import (ARMS, DC_DIR, EF_US_PRIMARY, FS, RUNS_DIR, SEEDS, SIZE,
                      base_flags, run_one)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fs", default=",".join(str(x) for x in FS))
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--seeds", default=",".join(str(s) for s in SEEDS))
    ap.add_argument("--ef", type=int, default=EF_US_PRIMARY,
                    help="-exit_freeze in us (100 primary, 250 secondary)")
    args = ap.parse_args()

    fs = [int(x) for x in args.fs.split(",")]
    arms = [a for a in ARMS if a in args.arms.split(",")]
    seeds = [int(s) for s in args.seeds.split(",")]
    ef = args.ef
    cells = list(itertools.product(fs, seeds, arms))
    print(f"exp29: {len(cells)} runs  (F={fs} seeds={seeds} ef={ef}us)", flush=True)

    fails = 0
    for i, (f, seed, arm) in enumerate(cells, 1):
        cond = f"asymF{f}_seed{seed}"
        wl = f"tornado_F{f}_ef{ef}_s{SIZE}"
        arm_dir = RUNS_DIR / "micro" / wl / cond / arm
        win_csv = arm_dir / "window.csv"
        outfile = arm_dir / "stdout.txt"
        res = run_one(base_flags(arm, f, seed, str(win_csv), exit_freeze_us=ef),
                      outfile, cwd=DC_DIR)
        extra = f"  {res['nflows']} flows, {res['seconds']}s"
        print(f"[{i}/{len(cells)}] {res['status']:<18} "
              f"F={f}/ef{ef}/seed{seed}/{arm}{extra}", flush=True)
        if res["status"].startswith("FAIL"):
            fails += 1

    print(f"\nexp29 done: {fails} failures / {len(cells)}", flush=True)


if __name__ == "__main__":
    main()
