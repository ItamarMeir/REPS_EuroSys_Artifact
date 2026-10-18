#!/usr/bin/env python3
"""T1 run driver -- path_static arm only (reps_b8_nscc cells already exist in
exp30_packet_trimming_en/runs, read directly from there, no rerun).

Idempotent (skips a cell whose stdout.txt already finished).

  python3 run_t1.py --smoke   # 1 seed, n in {0,32} only, 16 MiB -- sanity check
  python3 run_t1.py           # full: seeds 42/43/44, n in A1_NS, both sizes
"""
from __future__ import annotations

import argparse

import common_t1 as c

SEEDS_FULL = [42, 43, 44]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                     help="1 seed, n in {0,32} only, 16 MiB")
    ap.add_argument("--sizes", type=int, nargs="+", default=None)
    ap.add_argument("--ns", type=int, nargs="+", default=None)
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    args = ap.parse_args()

    if args.smoke:
        sizes = args.sizes or [16777216]
        ns = args.ns or [0, 32]
        seeds = args.seeds or [42]
    else:
        sizes = args.sizes or c.SIZES
        ns = args.ns or c.A1_NS
        seeds = args.seeds or SEEDS_FULL

    cells = [(size, n, seed) for size in sizes for n in ns for seed in seeds]
    total = len(cells)
    print(f"T1 path_static: {total} cells ({sizes=} {ns=} {seeds=})")

    for i, (size, n, seed) in enumerate(cells, 1):
        outdir = (c.RUNS_DIR / "a1" / str(size) / f"x{n}_ef{c.EF_US_A}" /
                  f"seed{seed}" / "path_static")
        outfile = outdir / "stdout.txt"
        flags = c.path_static_flags(size=size, seed=seed, n=n)
        res = c.run_one(flags, outfile, expect_cm_nodes=1024)
        name = f"a1 s{size} n{n} seed{seed} path_static"
        tag = res["status"]
        extra = f"  {res['nflows']} flows, {res['seconds']}s" if res["nflows"] else ""
        if res["tor_ecn_reenabled"]:
            extra += "  [tor-ecn-reenabled]"
        print(f"[{i}/{total}] {tag:<20} {name}{extra}", flush=True)


if __name__ == "__main__":
    main()
