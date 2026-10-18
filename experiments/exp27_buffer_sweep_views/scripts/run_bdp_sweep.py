#!/usr/bin/env python3
"""
exp27 plot 4 driver — BDP-threshold sweep on the exp26 2-tier fabric.

Hypothesis under test: the REPS-vs-OPS Max-FCT gap on a *symmetric* fabric is
set by how tight the ECN/queue provisioning is relative to the synchronized
startup burst, i.e. by the BDP the thresholds are derived from — NOT by the
topology, hop count, or path count.

Fixed: `fat_tree_1024_1os_2t_400g` (1024 hosts, -paths 32, -use_srv6), tornado
4 MiB, seed 42, sender-only MPRDMA — identical to exp26 fig2 micro tornado 4 MiB
(= exp27 plot 1). exp26's own point is BDP=101.

Swept: a synthetic "BDP" B in {50, 75, 101, 152, 250}, feeding the paper's
run_symmetric.py recipe:  -q B   -ecn B/4 3B/4   -cwnd 1.5B.
B=101 reproduces exp26's live values (25/75 vs its 25/76 — 1-packet rounding).

Runs in Docker (reps-artifact).
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(EXP_DIR.parent / "exp26_srv6_buffer_sweep" / "scripts"))

from common import DC_DIR, arm_lb_flags, arms_for, run_one  # noqa: E402

RUNS_DIR = EXP_DIR / "runs"
TOPO = "topologies/reps/fat_tree_1024_1os_2t_400g.topo"
N_PATHS = 32
SEED = 42
CM = "connection_matrices/tornado_n1024_s4194304.cm"

BDPS = [50, 75, 101, 152, 250]
ARMS = arms_for(N_PATHS)          # ops, reps_b{1,2,4,8,16,32}


def flags_for(bdp: int, arm: str, failed: int = 0) -> list[str]:
    q, kmin, kmax, cwnd = bdp, bdp // 4, bdp * 3 // 4, int(bdp * 1.5)
    f = [
        "-connections_mapping", "-disable_trim",
        "-sack_threshold", "4000",
        "-tm", CM,
        "-end", "90000",
        "-seed", str(SEED),
        "-sender_cc_only", "-sender_cc_algo", "mprdma",
        "-topo", TOPO,
        "-enable_qa_gate",
        "-linkspeed", "400000",
        "-ecn", str(kmin), str(kmax),
        "-q", str(q),
        "-cwnd", str(cwnd),
    ]
    if failed:
        f += ["-failed", str(failed), "-skip_asy"]
    return f + arm_lb_flags(arm, N_PATHS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bdps", default=",".join(str(b) for b in BDPS))
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--failed", type=int, default=0,
                    help="degrade N ToR uplinks (-failed N -skip_asy); "
                         "writes fig4/asym<N> instead of fig2/healthy")
    args = ap.parse_args()

    bdps = [int(b) for b in args.bdps.split(",")]
    arms = [a for a in ARMS if a in args.arms.split(",")]
    figseg, cond = (("fig4", f"asym{args.failed}") if args.failed
                    else ("fig2", "healthy"))
    cells = list(itertools.product(bdps, arms))
    print(f"bdp_sweep: {len(cells)} runs on {TOPO} (-paths {N_PATHS}) "
          f"[{figseg}/{cond}]", flush=True)

    fails = 0
    for i, (bdp, arm) in enumerate(cells, 1):
        wl = f"tornado_bdp{bdp}_s4194304"
        outfile = RUNS_DIR / figseg / "micro" / wl / cond / arm / "stdout.txt"
        res = run_one(flags_for(bdp, arm, args.failed), outfile, cwd=DC_DIR)
        extra = f"  {res['nflows']} flows, {res['seconds']}s"
        print(f"[{i}/{len(cells)}] {res['status']:<18} bdp{bdp}/{arm}{extra}",
              flush=True)
        if res["status"].startswith("FAIL"):
            fails += 1
    print(f"\nbdp_sweep done: {fails} failures / {len(cells)}", flush=True)


if __name__ == "__main__":
    main()
