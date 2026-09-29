#!/usr/bin/env python3
"""
exp30 shared config -- REPS buffer size B under *concentrated* path loss.

exp28 (degradation, spread one-uplink-per-ToR) and exp29 (transient full ToR0
uplink failure) both found B does not move FCT. In both, per-flow severity was
tiny: exp28's `-skip_asy` caps degradation at 1 uplink/ToR (any affected flow
loses 1/32 of its paths); exp29 is binary alive/dead and recovers in 100 us.
The 2026-09-06 meeting (Skalosub, Avin) identified the missing regime: a large
*fraction* of ONE flow's own path set in a bad state.

exp30 puts real per-flow severity on the axis:

  Part A  -- static degradation CONCENTRATED on ToR0. `-failed n` WITHOUT
             `-skip_asy` lands all n degraded uplinks on ToR0 (verified
             fat_tree_topology.cpp:862-988: fail_every=NTOR/n, ToR0 keeps
             can_fail, global degraded_cables<n cap fills on ToR0's first n
             aggs). Affected ToR0 flows lose n/32 of their paths.
      A1   severity axis: n in {0,1,2,4,8,16,32}, down_ratio r = 0.5
      A2   ratio axis:    n = 8 (1/4 of 32), r swept over exp28's RATIOS

  Part B  -- STATIC (permanent) real full-kill of F of ToR0's 32 uplinks.
             Reuses exp29's `timed-failure` mechanism (-timed_fail_tor_uplinks
             <tor> <F> + -timed_window <start_us> <recover_us>) but with
             recover <= start (`1 1` -- the block is gated on start_us > 0, so
             `0 0` is a no-op) so the kill is scheduled at t~0 and never
             recovers, unlike exp29's transient 100/200 us blip. This is the
             one cell exp28/29/30-Part-A-v1 never filled: {degrade, kill} x
             {transient, static} -- Part A = static+degrade, exp29 =
             transient+kill, this = static+kill. F in {0,1,2,4,8,16,24,31}
             (31, not 32, so ToR0 keeps one live uplink). Affected group is
             identical to Part A's: ToR0's 32 senders.
             NB: exp30's *original* Part B (`-fail_src_paths <src> <count>`,
             a synthetic single-flow poison) answered a distinct,
             meeting-sanctioned question (Chen Avin, 2026-09-06: "even if
             unrealistic, find a state where B changes") and its finding
             stands; that htsim mechanism is untouched, just no longer used by
             exp30's Part B. See README's Part B section for the full
             two-asks framing.

Two flow sizes: 4 MiB (~10*BDP, the exp27 double-resonance peak where the
healthy REPS burst mechanism is actually live) and 16 MiB (exp28/29 anchor,
in the resonance dead zone). See memory reps_gap_is_bdp_provisioning_not_topology.

Fabric / CC otherwise identical to exp28: fat_tree_1024_1os_2t_400g, tornado,
MPRDMA, -q 101 -ecn 25 76 -cwnd 151, -use_srv6 -paths 32.
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
SIZES = [4194304, 16777216]            # 4 MiB (sensitive), 16 MiB (exp28/29 anchor)
FAIL_TOR = 0                           # concentrate on ToR0; affected src ids 0..31


def cm_for(size: int) -> str:
    return f"connection_matrices/tornado_n1024_s{size}.cm"


_BDP = get_bdp(400000, 2, 1000)          # 2-tier -> 101.66
Q = int(_BDP)                            # 101
ECN = (int(_BDP / 4), int(_BDP * 3 / 4))  # (25, 76)
CWND = int(Q * 1.5)                      # 151
assert (Q, ECN, CWND) == (101, (25, 76), 151), (Q, ECN, CWND)

# Full B ladder -- exp30 is explicitly testing the memo's predicted B knee at 4,
# so B=16 is kept (exp28/29 dropped it as "nothing resolvable above B=4").
ARMS = ["reps_b1", "reps_b2", "reps_b4", "reps_b8", "reps_b16", "reps_b32",
        "reps_b8_dual"]
# reps_b8_dual = same LB (freezing, reps_buffer_size=8) as reps_b8, but CC is
# dual_mprdma_reps instead of mprdma (see base_flags below). Added to compare
# the dual-window REPS+MPRDMA mechanism against plain MPRDMA at a fixed B.
SEEDS = [42, 43, 44]

# --- Part A design matrix ---------------------------------------------------
A1_NS = [0, 1, 2, 4, 8, 16, 32]         # # degraded ToR0 uplinks; 0 = healthy anchor
A1_RATIO = 0.5
A2_FAILED = 8                            # 1/4 of 32
# (down_ratio, degradation-percent label) -- exp28 part-2 RATIOS
A2_RATIOS = [(0.90, 10), (0.75, 25), (0.50, 50), (0.25, 75), (0.10, 90), (0.05, 95)]
EF_US_A = 200                           # match exp28 (-exit_freeze 200 us); degrade
#                                        rarely triggers freeze so near-moot here

# --- Part B design matrix (static real kill of ToR0 uplinks) --------------
B_FS = [0, 1, 2, 4, 8, 16, 24, 31]      # # of ToR0's 32 uplinks permanently dead
B_SIZE_PRIMARY = 4194304
B_SIZE_SECONDARY = 16777216
B_FS_SECONDARY = [0, 1, 2, 4, 8, 16, 24, 31]  # full grid, matches B_FS
B_TIMED_START_US = 1                    # gated on start_us > 0 in main_uec.cpp;
B_TIMED_RECOVER_US = 1                  # recover <= start -> permanent (never thaws)

def base_flags(arm: str, *, part: str, size: int, seed: int,
               n: int = 0, r: float | None = None,
               f_uplinks: int | None = None,
               exit_freeze_us: int = EF_US_A) -> list[str]:
    """part in {'a1','a2','b'}. a1/a2 use concentrated `-failed n` (NO
    -skip_asy); b uses the static real kill: `-timed_fail_tor_uplinks FAIL_TOR
    f_uplinks` + `-timed_window 1 1` (permanent onset at t~0us, never
    recovers)."""
    # "<arm>_dual" reuses <arm>'s LB/buffer flags unchanged and only swaps CC
    # to dual_mprdma_reps -- every other flag below stays byte-identical to
    # the plain-mprdma arm, so the comparison is CC-only, apples to apples.
    is_dual = arm.endswith("_dual")
    base_arm = arm[:-len("_dual")] if is_dual else arm
    cc_algo = "dual_mprdma_reps" if is_dual else "mprdma"
    f = [
        "-connections_mapping", "-disable_trim",
        "-sack_threshold", "4000",
        "-tm", cm_for(size),
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
    ]
    if part in ("a1", "a2"):
        if n:                                   # n=0 -> healthy, no failure flag
            f += ["-failed", str(n)]            # NO -skip_asy: concentrates on ToR0
            if r is not None:
                f += ["-down_ratio", f"{r:g}"]
    elif part == "b":
        assert f_uplinks is not None
        if f_uplinks:
            f += ["-timed_window", str(B_TIMED_START_US), str(B_TIMED_RECOVER_US),
                  "-timed_fail_tor_uplinks", str(FAIL_TOR), str(f_uplinks)]
    else:
        raise ValueError(f"unknown part {part!r}")
    return f + arm_lb_flags(base_arm, N_PATHS)
