#!/usr/bin/env python3
"""
exp31 shared config -- REPS buffer size B vs ring all-reduce collective
completion time (CCT), healthy and under failure.

Base recipe = exp26 run_fig7.py's `ai` workload, held exactly:
  topo  fat_tree_32_1os_2t_400g (32 hosts, 4 distinct paths -> -use_srv6 -paths 4)
  wl    a 16-rank ring all-reduce, 4 MB/hop, 496 flows chained via
        send_done_trigger (n_expected = 496). Serially dependent: hop k+1 starts
        only when hop k finishes sending.
        NB: the committed connection_matrices/allreduce.cm fails to parse with the
        current binary ("unknown id: oneshot at line 500" -- some stale
        encoding/version mismatch that cat -A / od / diff don't surface). We
        regenerate an equivalent from gen_allreduce.py (generator seed 42, so the
        ring's host layout is fixed; htsim -seed varies LB/failure randomness
        across the 3 seeds -- same convention as exp13/exp26 fig7).
  flags -connections_mapping -disable_trim -sack_threshold 4000
        -end 90000 -sender_cc_only -sender_cc_algo mprdma
        -linkspeed 400000 -ecn 25 76 -q 101 -other_location -cwnd 151
        [-failures_input ../failures_input/<scenario>.txt]   (omit for healthy)
        + arm_lb_flags(arm, 4)

exp31 adds over exp26 fig7: 3 seeds (42/43/44 -> CI), a healthy baseline cell
(fig7 has none), degradation scenarios, and a CCT + per-ring-step metric.

Arms: reps_b{1,2,4} only (no OPS -- per user; B-vs-B study, matches exp28-30).

Why this experiment: exp26 fig7's single-seed `ai` data shows a consistent
B=1 -> B=2 knee (b2 best CCT) and b4 sometimes WORSE than b2 -- the first hint
that buffer size matters for a serially-dependent collective, which independent
tornado flows (exp28-30) never showed. exp31 tests whether that survives CI.
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

TOPO = "topologies/reps/fat_tree_32_1os_2t_400g.topo"
RING_RANKS = 16
FLOW_BYTES = 4_000_000
_CM_NAME = f"exp31_ring_n32g{RING_RANKS}_4mb.cm"
CM = f"connection_matrices/{_CM_NAME}"
N_PATHS = 4
N_EXPECTED = RING_RANKS * (2 * RING_RANKS - 1)   # 496
END_US = 90000            # -end; a stalled ring never prints -> censor CCT here


def ensure_cm() -> None:
    """Generate the ring all-reduce CM via gen_allreduce.py if it isn't there.
    Generator seed 42 (fixed ring host layout); nodes=32, conns=groupsize=16."""
    cm = DC_DIR / CM
    if cm.exists():
        return
    gen = DC_DIR / "connection_matrices" / "gen_allreduce.py"
    import subprocess
    subprocess.run(["python3", str(gen), str(cm), "32", str(RING_RANKS),
                    str(RING_RANKS), str(FLOW_BYTES), "0", "42"], check=True)
    print(f"generated {cm}")

ARMS = ["reps_b1", "reps_b2", "reps_b4"]
SEEDS = [42, 43, 44]

HEALTHY = "healthy"       # sentinel: no -failures_input
SCENARIOS = [
    HEALTHY,
    # --- fig7 originals (paper fig 7) ---
    "fail_one_cable",
    "fail_one_switch",
    "fail_one_switch_one_cable",
    "5_percent_failed_cables",
    "5_percent_failed_switches",
    "5_percent_failed_switches_and_cables",
    "ber_cable_one_percent",
    "ber_switch_one_percent",
    # --- degradation (slowed, not dead) ---
    "degrade_one_cable",
    "10_percent_degraded_cables",
    # NB: "degrade_one_switch" dropped -- htsim SIGFPE when the switch bitrate is
    # driven to ~1000 bps and a flow's pacing calc divides by it (crashed 2/9
    # cells). degrade_one_cable + 10_percent_degraded_cables cover the regime.
    # --- extreme: one path left, whole ring funnels through it ---
    "fail_all_cables_except_one_path",
]

_BDP = get_bdp(400000, 2, 1000)          # 2-tier -> 101.66
Q = int(_BDP)                            # 101
ECN = (int(_BDP / 4), int(_BDP * 3 / 4))  # (25, 76)
CWND = int(Q * 1.5)                      # 151
assert (Q, ECN, CWND) == (101, (25, 76), 151), (Q, ECN, CWND)


def base_flags(arm: str, scenario: str, seed: int) -> list[str]:
    f = [
        "-connections_mapping",
        "-disable_trim",
        "-sack_threshold", "4000",
        "-tm", CM,
        "-end", str(END_US),
        "-seed", str(seed),
        "-sender_cc_only", "-sender_cc_algo", "mprdma",
        "-topo", TOPO,
        "-linkspeed", "400000",
        "-ecn", str(ECN[0]), str(ECN[1]),
        "-q", str(Q),
        "-other_location",
        "-cwnd", str(CWND),
    ]
    if scenario != HEALTHY:
        f += ["-failures_input", f"../failures_input/{scenario}.txt"]
    return f + arm_lb_flags(arm, N_PATHS)
