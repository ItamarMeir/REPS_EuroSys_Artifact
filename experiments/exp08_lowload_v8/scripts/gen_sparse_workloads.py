#!/usr/bin/env python3
"""
gen_sparse_workloads.py — generate sparse permutation TMs for exp08.

Creates:
  perm_128n_2c_8MB_s{42..46}.cm   — 2-flow  (WTD targeted test, Part C)
  perm_128n_16c_8MB_s{42..46}.cm  — 16-flow (low load)
  perm_128n_32c_8MB_s{42..46}.cm  — 32-flow (moderate low load)

All files are written to htsim/sim/datacenter/connection_matrices/.

These use the same gen_permutation.py logic as the existing TMs but with
far fewer concurrent connections, creating the sparse-load regime where
outlier-EV spatial collisions dominate and smart-filter Modes A/B should
have room to help.
"""

import sys
import os
from pathlib import Path
from random import seed as rand_seed, shuffle

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT  = SCRIPT_DIR.parent.parent.parent
CM_DIR     = REPO_ROOT / "htsim" / "sim" / "datacenter" / "connection_matrices"

NODES     = 128
FLOWSIZE  = 8 * 1024 * 1024   # 8 MB
EXTRA_US  = 0                  # no extra start-time jitter (matches existing perm TMs)

CONNS_LIST = [2, 16, 32]
SEEDS      = [42, 43, 44, 45, 46]


def gen_permutation(output: Path, nodes: int, num_conns: int,
                    flowsize_bytes: int, extrastarttime_us: float, randseed: int):
    """Same logic as htsim/sim/datacenter/connection_matrices/gen_permutation.py."""
    srcs = list(range(nodes))
    dsts = list(range(nodes))
    if randseed != 0:
        rand_seed(randseed)
    shuffle(srcs)
    shuffle(dsts)
    # Eliminate self-loops
    for n in range(nodes):
        if srcs[n] == dsts[n]:
            i = (n + 1) % nodes
            dsts[n], dsts[i] = dsts[i], dsts[n]

    with open(output, "w") as f:
        f.write(f"Nodes {nodes}\n")
        f.write(f"Connections {num_conns}\n")
        for n in range(num_conns):
            start_ps = int(extrastarttime_us * 1_000_000)
            f.write(f"{srcs[n]}->{dsts[n]} id {n+1} start {start_ps} size {flowsize_bytes}\n")


def main():
    CM_DIR.mkdir(parents=True, exist_ok=True)
    generated = []
    skipped   = []

    for conns in CONNS_LIST:
        for s in SEEDS:
            fname = f"perm_128n_{conns}c_8MB_s{s}.cm"
            out   = CM_DIR / fname
            if out.exists():
                skipped.append(fname)
                continue
            gen_permutation(out, NODES, conns, FLOWSIZE, EXTRA_US, s)
            generated.append(fname)

    print(f"Generated {len(generated)} TMs:")
    for f in generated:
        print(f"  {CM_DIR / f}")
    if skipped:
        print(f"Skipped (already exist): {len(skipped)}")
        for f in skipped:
            print(f"  {f}")


if __name__ == "__main__":
    main()
