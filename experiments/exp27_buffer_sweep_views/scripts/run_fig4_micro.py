#!/usr/bin/env python3
"""
exp27 F1' — exp26 fig4's micro matrix, rerun on the fig2-micro fabric.

exp26 fig4 micro runs on fat_tree_128_1os_2t_400g (128 hosts, 8 paths,
-failed 4); exp26 fig2 micro / exp27 plot 1 run on fat_tree_1024_1os_2t_400g
(1024 hosts, 32 paths). This rerun puts fig4's micro matrix on the 1024-host
fabric with the failure knob scaled to the same ≈3.1 % of ToR uplinks
(-failed 32 -skip_asy, = fail_every 1 → every ToR loses one uplink), so the
healthy→asym change is the only variable in the micro comparison with plot 1.

Thresholds -q 101 -ecn 25 76 -cwnd 151 (2-tier BDP recipe, tier-based → same as
exp26 fig4 micro and exp27 plot 1/4). Condition string asym32 (matches F4/F5).

3 patterns × 3 sizes × 7 arms = 63 runs. All CMs already exist. Runs in Docker.
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
Q, ECN, CWND = 101, (25, 76), 151

PATTERNS = ["perm", "tornado", "incast"]
SIZES = [4194304, 8388608, 16777216]
ARMS = arms_for(N_PATHS)          # ops, reps_b{1,2,4,8,16,32}


def cm(pat: str, size: int) -> str:
    if pat == "incast":
        return f"connection_matrices/incast_n1024_s{size}_d8.cm"
    return f"connection_matrices/{pat}_n1024_s{size}.cm"


def flags_for(pat: str, size: int, arm: str, failed: int) -> list[str]:
    f = [
        "-connections_mapping", "-disable_trim",
        "-failed", str(failed), "-skip_asy",
        "-sack_threshold", "4000",
        "-tm", cm(pat, size), "-end", "90000", "-seed", str(SEED),
        "-sender_cc_only", "-sender_cc_algo", "mprdma",
        "-topo", TOPO, "-enable_qa_gate", "-linkspeed", "400000",
        "-ecn", str(ECN[0]), str(ECN[1]), "-q", str(Q), "-cwnd", str(CWND),
    ]
    return f + arm_lb_flags(arm, N_PATHS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patterns", default=",".join(PATTERNS))
    ap.add_argument("--sizes", default=",".join(str(s) for s in SIZES))
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--failed", type=int, default=32,
                    help="degrade N ToR->US0 uplinks to 200G (-failed N -skip_asy); "
                         "writes fig4/asym<N>. 32 = every ToR (spine 0 half-dead); "
                         "8 = 25%% of ToRs (geometry-matched to 128-host -failed 4)")
    args = ap.parse_args()
    pats = [p for p in PATTERNS if p in args.patterns.split(",")]
    sizes = [int(s) for s in args.sizes.split(",")]
    arms = [a for a in ARMS if a in args.arms.split(",")]
    failed = args.failed

    cells = list(itertools.product(pats, sizes, arms))
    print(f"fig4_micro: {len(cells)} runs on {TOPO} (-paths {N_PATHS}, "
          f"-failed {failed}, q={Q} ecn={ECN} cwnd={CWND}) [fig4/asym{failed}]",
          flush=True)
    fails = 0
    for i, (pat, size, arm) in enumerate(cells, 1):
        wl = f"{pat}_s{size}"
        out = RUNS_DIR / "fig4" / "micro" / wl / f"asym{failed}" / arm / "stdout.txt"
        res = run_one(flags_for(pat, size, arm, failed), out, cwd=DC_DIR)
        print(f"[{i}/{len(cells)}] {res['status']:<16} {pat}/{size}/{arm}  "
              f"{res['nflows']} flows {res['seconds']}s", flush=True)
        if res["status"].startswith("FAIL"):
            fails += 1
    print(f"\nfig4_micro done: {fails} failures / {len(cells)}", flush=True)


if __name__ == "__main__":
    main()
