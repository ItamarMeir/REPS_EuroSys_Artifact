#!/usr/bin/env python3
"""
exp28 shared config — targeted ToR->spine-0 link-degradation sweep.

One fixed fabric / workload; the only independent variables are the failure
knobs:

  part 1  X = # degraded ToR->spine-0 uplinks   (`-failed D -skip_asy`, ratio 0.5)
  part 2  X = degradation %  on 4 fixed uplinks  (`-failed 4 -skip_asy -down_ratio r`)

Everything else is exp26 fig2-micro's own template on
`fat_tree_1024_1os_2t_400g` (1024 hosts, NTOR=32, NAGG=32 spines, 32 SRv6
paths), tornado 16 MiB, seed 42, MPRDMA sender-CC, `-q 101 -ecn 25 76
-cwnd 151`. `-disable_tor_ecn` is deliberately NOT passed (matches exp26/27 /
the paper's run_symmetric.py; every row has tor_ecn_reenabled=1).

Verified 2026-09-03 against `htsim/sim/datacenter/fat_tree_topology.cpp`
(`-failed D -skip_asy` degrades exactly the agg-0 uplink of D ToRs: run stdout
prints `Failure: LS<tor>->US0 ... set to 200`) and `main_uec.cpp:421`
(`-down_ratio` -> `FatTreeTopology::_failed_link_ratio`; the degraded queue gets
speed, buffersize AND ECN thresholds all *= ratio).

Reuses exp26's `common.py` helpers (arm flags, run_one, get_bdp).
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(EXP_DIR.parent / "exp26_srv6_buffer_sweep" / "scripts"))

from common import (  # noqa: E402
    DC_DIR, arm_lb_flags, arms_for, get_bdp, run_one)

RUNS_DIR = EXP_DIR / "runs"

TOPO = "topologies/reps/fat_tree_1024_1os_2t_400g.topo"
N_PATHS = 32
SEED = 42
SIZE = 16777216  # 16 MiB
CM = f"connection_matrices/tornado_n1024_s{SIZE}.cm"
EXIT_FREEZE = "200000000"  # ps; pinned (exp22 lineage) so freeze_us is reproducible

_BDP = get_bdp(400000, 2, 1000)          # 2-tier -> 101.66
Q = int(_BDP)                            # 101
ECN = (int(_BDP / 4), int(_BDP * 3 / 4))  # (25, 76)
CWND = int(Q * 1.5)                      # 151
assert (Q, ECN, CWND) == (101, (25, 76), 151), (Q, ECN, CWND)

# B ladder: full powers of two up to #paths (B=8 kept even though the original
# ask skipped it -- it is the paper default and the 1->2->4->8 knee is the
# headline of the sustained-asymmetry regime, see exp27 F1'/F4).
# OPS is deliberately EXCLUDED (per user, 2026-09-03): this study compares REPS
# buffer sizes only, no oblivious baseline. So no speedup-vs-OPS view either.
ARMS = [a for a in arms_for(N_PATHS) if a != "ops"]   # reps_b{1,2,4,8,16,32}


def wl_name(prefix: str, seed: int = SEED) -> str:
    return f"{prefix}_s{SIZE}" if seed == SEED else f"{prefix}_seed{seed}_s{SIZE}"


def base_flags(arm: str, failed: int, down_ratio: float | None,
                seed: int = SEED) -> list[str]:
    f = [
        "-connections_mapping", "-disable_trim",
        "-sack_threshold", "4000",
        "-tm", CM,
        "-end", "90000",
        "-seed", str(seed),
        "-sender_cc_only", "-sender_cc_algo", "mprdma",
        "-topo", TOPO,
        "-enable_qa_gate",
        "-linkspeed", "400000",
        "-ecn", str(ECN[0]), str(ECN[1]),
        "-q", str(Q),
        "-cwnd", str(CWND),
        "-exit_freeze", EXIT_FREEZE,
    ]
    if failed:
        f += ["-failed", str(failed), "-skip_asy"]
        if down_ratio is not None:
            f += ["-down_ratio", f"{down_ratio:g}"]
    return f + arm_lb_flags(arm, N_PATHS)
