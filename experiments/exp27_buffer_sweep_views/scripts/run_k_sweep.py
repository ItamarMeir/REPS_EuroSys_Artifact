#!/usr/bin/env python3
"""
exp27 plot 3 driver — tornado 4 MiB, SRv6, on the 3-tier fat tree at radix
K = 4, 8, 16, so the SRv6 path count (K/2)^2 sweeps 4 -> 16 -> 64.

Fixes the workload and makes path count the independent variable: does the
REPS-vs-restricted-EV-OPS Max-FCT gap shrink as the fabric gains paths?

Only K=4 and K=8 are run here (10 cells). K=16 tornado 4 MiB (8 arms) is
already produced by run_k16_3t.py and read straight from data/k16_3t/summary.csv
by plot_k_sweep.py.

Same command template as run_k16_3t.py base_flags (exp26 micro, healthy).
Runs in Docker (reps-artifact), per CLAUDE.md.
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(EXP_DIR.parent / "exp26_srv6_buffer_sweep" / "scripts"))

from common import (  # noqa: E402
    DC_DIR, arm_lb_flags, arms_for, b_ladder, get_bdp, run_one)

RUNS_DIR = EXP_DIR / "runs"
SEED = 42
SIZE = 4194304  # 4 MiB

# 3-tier BDP -> q/ecn/cwnd, K-independent (getBDP depends on tiers, not radix).
_BDP = get_bdp(400000, 3, 1000)
Q = int(_BDP)
ECN = (int(_BDP / 4), int(_BDP * 3 / 4))
CWND = int(Q * 1.5)
assert (Q, ECN, CWND) == (152, (38, 114), 228), (Q, ECN, CWND)

# K -> (3-tier topo stem, (K/2)^2 distinct SRv6 paths). K=16 reused, not here.
K_TOPO = {4: "fat_tree_16_1os_3t_400g", 8: "fat_tree_128_1os_3t_400g"}
K_PATHS = {4: 4, 8: 16}


def flags_for(k: int, arm: str) -> list[str]:
    hosts = {4: 16, 8: 128}[k]
    f = [
        "-connections_mapping", "-disable_trim",
        "-sack_threshold", "4000",
        "-tm", f"connection_matrices/tornado_n{hosts}_s{SIZE}.cm",
        "-end", "90000",
        "-seed", str(SEED),
        "-sender_cc_only", "-sender_cc_algo", "mprdma",
        "-topo", f"topologies/reps/{K_TOPO[k]}.topo",
        "-enable_qa_gate",
        "-linkspeed", "400000",
        "-ecn", str(ECN[0]), str(ECN[1]),
        "-q", str(Q),
        "-cwnd", str(CWND),
    ]
    return f + arm_lb_flags(arm, K_PATHS[k])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ks", default="4,8", help="comma list of K values to run")
    ap.add_argument("--arms", default="")
    args = ap.parse_args()

    ks = [int(k) for k in args.ks.split(",")]
    cells = []
    for k in ks:
        arms = arms_for(K_PATHS[k])
        assert b_ladder(K_PATHS[k]) == {4: [1, 2, 4], 8: [1, 2, 4, 8, 16]}[k]
        if args.arms:
            arms = [a for a in arms if a in args.arms.split(",")]
        for arm in arms:
            cells.append((k, arm))

    total = len(cells)
    print(f"k_sweep: {total} runs  (q={Q} ecn={ECN} cwnd={CWND})", flush=True)

    fails = 0
    for i, (k, arm) in enumerate(cells, 1):
        wl = f"tornado_K{k}_s{SIZE}"
        outfile = RUNS_DIR / "fig2" / "micro" / wl / "healthy" / arm / "stdout.txt"
        res = run_one(flags_for(k, arm), outfile, cwd=DC_DIR)
        tag = res["status"]
        dp = ""
        if outfile.exists():
            for ln in outfile.read_text(errors="replace").splitlines():
                if "distinct_paths=" in ln:
                    dp = "  " + ln.split("distinct_paths=")[-1].split()[0] + "paths"
                    break
        extra = f"  {res['nflows']} flows, {res['seconds']}s{dp}"
        if res["tor_ecn_reenabled"]:
            extra += "  [TOR-ECN-REENABLED]"
        print(f"[{i}/{total}] {tag:<18} K={k}/{arm}{extra}", flush=True)
        if tag.startswith("FAIL"):
            fails += 1

    print(f"\nk_sweep done: {fails} failures / {total}", flush=True)


if __name__ == "__main__":
    main()
