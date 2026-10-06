#!/usr/bin/env python3
"""
exp30_packet_trimming_en runner -- exp30 rerun with trim enabled (dropped
-disable_trim; see common30.py docstring). Idempotent (skips a cell whose
stdout.txt already finished).

  python3 run30.py --part a1                 # severity sweep, both sizes
  python3 run30.py --part a2 --sizes 4194304 # ratio sweep, 4 MiB only
  python3 run30.py --part b                  # static real kill of F ToR0 uplinks

Layout: runs/<part>/<size>/x<X>_ef<EF>/seed<seed>/<arm>/stdout.txt

Run in Docker (reps-artifact) with the repo bind-mounted, per CLAUDE.md:
  MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/workspace" \
    -w /workspace/experiments/exp30_packet_trimming_en/scripts \
    reps-artifact:latest bash -lc 'python3 run30.py --part a1'
"""
from __future__ import annotations

import argparse

import common30 as C
from common30 import DC_DIR, RUNS_DIR, base_flags, run_one


def _cells(part: str, sizes: list[int]):
    """Yield (part, size, xlabel, ef_us, kwargs) tuples for base_flags."""
    for size in sizes:
        if part == "a1":
            for n in C.A1_NS:
                yield ("a1", size, n, C.EF_US_A,
                       dict(n=n, r=(C.A1_RATIO if n else None)))
        elif part == "a2":
            for r, pct in C.A2_RATIOS:
                yield ("a2", size, pct, C.EF_US_A,
                       dict(n=C.A2_FAILED, r=r))
        elif part == "b":
            fs = C.B_FS if size == C.B_SIZE_PRIMARY else C.B_FS_SECONDARY
            for f_uplinks in fs:
                yield ("b", size, f_uplinks, C.EF_US_A,
                       dict(f_uplinks=f_uplinks))
        else:
            raise ValueError(part)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["a1", "a2", "b"])
    ap.add_argument("--sizes", default=",".join(str(s) for s in C.SIZES))
    ap.add_argument("--arms", default=",".join(C.ARMS))
    ap.add_argument("--seeds", default=",".join(str(s) for s in C.SEEDS))
    # Restrict to some x points (a1: # degraded uplinks, e.g. 0,32). Empty = all.
    ap.add_argument("--xs", default="",
                    help="comma-separated x values to run (default: all)")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",")]
    arms = [a for a in C.ARMS if a in args.arms.split(",")]
    seeds = [int(s) for s in args.seeds.split(",")]

    xs = {int(x) for x in args.xs.split(",") if x.strip()}
    cells = [(p, sz, x, ef, kw, seed, arm)
             for (p, sz, x, ef, kw) in _cells(args.part, sizes)
             if not xs or int(x) in xs
             for seed in seeds for arm in arms]
    print(f"exp30-trim-en {args.part}: {len(cells)} runs  "
          f"(sizes={sizes}, arms={arms}, seeds={seeds})", flush=True)

    fails = 0
    for i, (p, sz, x, ef, kw, seed, arm) in enumerate(cells, 1):
        outfile = (RUNS_DIR / p / str(sz) / f"x{x}_ef{ef}" / f"seed{seed}"
                   / arm / "stdout.txt")
        flags = base_flags(arm, part=p, size=sz, seed=seed, **kw)
        res = run_one(flags, outfile, cwd=DC_DIR)
        extra = f"  {res['nflows']} flows, {res['seconds']}s"
        if res.get("cm_warn"):
            extra += f"  *** {res['cm_warn']} ***"
        print(f"[{i}/{len(cells)}] {res['status']:<18} "
              f"{p} sz{sz} x{x} ef{ef} {arm} s{seed}{extra}", flush=True)
        if res["status"].startswith("FAIL"):
            fails += 1

    print(f"\nexp30-trim-en {args.part} done: {fails} failures / {len(cells)}", flush=True)


if __name__ == "__main__":
    main()
