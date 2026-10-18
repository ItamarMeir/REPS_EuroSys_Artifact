#!/usr/bin/env python3
"""
T1 shared config -- sanity check: FCT vs lost bandwidth, NSCC.

Reuses exp30_packet_trimming_en's common30.base_flags (trim-on, same base as
C2) for the degrade axis (-failed n -down_ratio r, concentrated on ToR0 --
n=32,r=0.5 degrades ALL of ToR0's 32 uplinks, giving every ToR0-sender flow a
truly halved bandwidth path set, not a diluted spread-degrade).

Two arms at the same A1 grid (n in {0,1,2,4,8,16,32}, r=0.5, affected group =
ToR0 senders src<32):
  - reps_b8_nscc : already run in exp30_packet_trimming_en (no new runs;
    read directly from that experiment's data/fct.csv).
  - path_static  : NEW. Pinned-path ideal reference -- since n=32 degrades
    every one of ToR0's uplinks, a path_static-pinned flow's single path is
    guaranteed to sit on a degraded link at every n. No new htsim code
    (path_static is an existing -load_balancing_algo). base_flags() has no
    path_static case, so this module builds it by taking base_flags(arm=
    "reps_b1", ...) (byte-identical fabric/CC/degrade flags) and swapping its
    LB tail for path_static's.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
EXP30_SCRIPTS = EXP_DIR.parent.parent / "exp30_packet_trimming_en" / "scripts"
sys.path.insert(0, str(EXP30_SCRIPTS))
sys.path.insert(0, str(EXP_DIR.parent.parent / "exp26_srv6_buffer_sweep" / "scripts"))

import common30  # noqa: E402
from common import DC_DIR, get_bdp, run_one  # noqa: E402,F401

RUNS_DIR = EXP_DIR / "runs"
EXP30_DATA = EXP30_SCRIPTS.parent / "data"

N_PATHS = common30.N_PATHS
A1_NS = common30.A1_NS            # [0,1,2,4,8,16,32]
A1_RATIO = common30.A1_RATIO      # 0.5
SIZES = common30.SIZES            # [4194304, 16777216]
EF_US_A = common30.EF_US_A        # 200


def path_static_flags(*, size: int, seed: int, n: int,
                       r: float = A1_RATIO) -> list[str]:
    """Same fabric/degrade flags and NSCC CC as reps_b1_nscc at this A1 cell,
    LB swapped to path_static (pinned single path per flow, no buffer/
    freezing machinery)."""
    base = common30.base_flags(
        "reps_b1_nscc", part="a1", size=size, seed=seed, n=n, r=r,
        exit_freeze_us=EF_US_A)
    idx = base.index("-load_balancing_algo")
    return base[:idx] + ["-load_balancing_algo", "path_static",
                          "-use_srv6", "-paths", str(N_PATHS)]
