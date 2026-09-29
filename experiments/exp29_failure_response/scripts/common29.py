#!/usr/bin/env python3
"""
exp29 shared config -- REPS failure-response scaling under a transient ToR
uplink failure.

One fixed fabric / workload (= exp28's, tornado 16 MiB). Independent variables:

  F     : # of ToR0's 32 spine uplinks fully failed for t in (100, 200) us
  arm   : reps_b{1,2,4,8,32}
  ef    : -exit_freeze value in us (100 = failure duration; 250 = "recovery +
          a buffering period", the paper's real-hardware heuristic)

Every run: healthy warm-up (MPRDMA hits cwnd cap by ~9 us), fail F uplinks of
ToR0 at t=100 us (= one min-RTO, so the RTO can fire while the link is down),
restore at t=200 us.

Framing note: the "fastLossRecovery <-> freeze crossover" this experiment was
first designed around does NOT hold -- gate smoke showed freeze fires at every
F (even F=1) and fastLossRecovery never engages (it needs ~a full cwnd of
out-of-order data on one ACK; sparse multi-path loss never piles that up before
the 100 us RTO fires). What exp29 actually measures: how REPS's single
RTO->freeze->rotate response scales with the number of simultaneously-dead
paths F, and whether buffer size B helps or hurts recovery when the buffer's
cached "known-good" EVs are exactly the ones the failure poisoned.

New htsim mechanism `timed-failure` (main_uec.cpp): `-timed_window`,
`-timed_fail_tor_uplinks`, `-log_reps_window`. See experiments/MODIFICATIONS.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(EXP_DIR.parent / "exp26_srv6_buffer_sweep" / "scripts"))

from common import (  # noqa: E402
    DC_DIR, arm_lb_flags, get_bdp, run_one)

RUNS_DIR = EXP_DIR / "runs"

TOPO = "topologies/reps/fat_tree_1024_1os_2t_400g.topo"
N_PATHS = 32
SIZE = 16777216  # 16 MiB -- exp28's size
CM = f"connection_matrices/tornado_n1024_s{SIZE}.cm"

FAIL_US, RECOVER_US = 100, 200       # = one min-RTO window (DEFAULT_UEC_RTO_MIN)
WINDOW_US = 10                       # -log_reps_window interval
# window-log bounds: t0 well before the failure for a healthy baseline, t1 past
# the slowest affected flow (F=31 loses 31/32 capacity for 100us -> FCT ~900us).
# The logger stops re-arming past t1, so it does NOT drag the sim to -end.
WIN_T0, WIN_T1 = 50, 950
FAIL_TOR = 0

_BDP = get_bdp(400000, 2, 1000)          # 2-tier -> 101.66
Q = int(_BDP)                            # 101
ECN = (int(_BDP / 4), int(_BDP * 3 / 4))  # (25, 76)
CWND = int(Q * 1.5)                      # 151
assert (Q, ECN, CWND) == (101, (25, 76), 151), (Q, ECN, CWND)

# B=16 dropped (exp28: nothing resolvable above B=4); B=32 kept as large control.
ARMS = ["reps_b1", "reps_b2", "reps_b4", "reps_b8", "reps_b32", "reps_b8_dual"]
# reps_b8_dual = same LB (freezing, reps_buffer_size=8) as reps_b8, but CC is
# dual_mprdma_reps instead of mprdma (see base_flags below). Added to compare
# the dual-window REPS+MPRDMA mechanism against plain MPRDMA at a fixed B.
FS = [1, 4, 8, 16, 24, 31]
SEEDS = [42, 43, 44]

# -exit_freeze sweep. 100 us = failure duration = paper fig_6 freezing-arm value
# (thaw lands ~50us after link recovery). 250 us = "max failure recovery time +
# a buffering period", the paper's real-hardware heuristic -- host stays frozen
# well past recovery, so "does a too-long timeout cost throughput / does REPS
# re-explore early" becomes observable. 250 only run on a 3-F subset (cost).
EF_US_PRIMARY = 100
EF_US_LADDER = [100, 250]
FS_EF_SECONDARY = [1, 16, 31]


def base_flags(arm: str, failed_uplinks: int, seed: int, window_csv: str,
               exit_freeze_us: int = EF_US_PRIMARY) -> list[str]:
    # "<arm>_dual" reuses <arm>'s LB/buffer flags unchanged and only swaps CC
    # to dual_mprdma_reps -- every other flag below stays byte-identical to
    # the plain-mprdma arm, so the comparison is CC-only, apples to apples.
    is_dual = arm.endswith("_dual")
    base_arm = arm[:-len("_dual")] if is_dual else arm
    cc_algo = "dual_mprdma_reps" if is_dual else "mprdma"
    f = [
        "-connections_mapping", "-disable_trim",
        "-sack_threshold", "4000",
        "-tm", CM,
        "-end", "90000",
        "-seed", str(seed),
        "-sender_cc_only", "-sender_cc_algo", cc_algo,
        "-topo", TOPO,
        "-enable_qa_gate",
        "-linkspeed", "400000",
        "-ecn", str(ECN[0]), str(ECN[1]),
        "-q", str(Q),
        "-cwnd", str(CWND),
        "-exit_freeze", str(int(exit_freeze_us) * 1_000_000),  # us -> ps
        "-timed_window", str(FAIL_US), str(RECOVER_US),
        "-timed_fail_tor_uplinks", str(FAIL_TOR), str(failed_uplinks),
        "-log_reps_window", window_csv, str(WINDOW_US), str(WIN_T0), str(WIN_T1),
    ]
    return f + arm_lb_flags(base_arm, N_PATHS)
