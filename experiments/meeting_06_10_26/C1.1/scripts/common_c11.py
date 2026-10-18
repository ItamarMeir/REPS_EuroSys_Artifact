#!/usr/bin/env python3
"""C1.1 shared config -- is REPS buffer pile-up (k) predictable from
serialization time + ACK jitter? Sweeps link rate under backlog, B=256
(non-limiting), constant CC (frozen cwnd at each rate's own knee, no
CC-reaction noise). See plan: ``C1.1: is REPS buffer pile-up (k)
predictable from serialization time + ACK jitter?``.

Does NOT touch exp30's ``common30.base_flags`` (hardcodes 400G, asserts
(Q,ECN,CWND)==(101,(25,76),151); C1/C2/T1 depend on that). Flags built
directly here, one per rate via a prebuilt ``.topo`` file at that rate
(``-topo`` + ``-linkspeed`` must agree -- the topo file's own baked-in link
speed is what the simulator actually uses; ``-linkspeed`` only feeds the
host-NIC/pacer/RTT math, confirmed in ``main_uec.cpp:1588-1591``).
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(EXP_DIR.parent.parent / "exp26_srv6_buffer_sweep" / "scripts"))
sys.path.insert(0, str(EXP_DIR.parent.parent / "exp30_packet_trimming_en" / "scripts"))

from common import DC_DIR, get_bdp, run_one  # noqa: E402,F401

RUNS_DIR = EXP_DIR / "runs"
N_PATHS = 32
B = 256
SIZE = 33554432  # 32 MiB -- clears >=40*BDP at every swept rate incl. 800G
CM = f"connection_matrices/tornado_n1024_s{SIZE}.cm"
SEED = 42

RATES_MBPS = [100000, 200000, 400000, 800000]  # Gbps*1000
TOPO_FMT = "topologies/reps/fat_tree_1024_1os_2t_{g}g.topo"

# BDP-scaled Q/ECN/cwnd-start per rate (get_bdp(rate,2,1000), 2-tier, 1us hop)
_BDP = {r: get_bdp(r, 2, 1000) for r in RATES_MBPS}
Q = {r: int(_BDP[r]) for r in RATES_MBPS}
ECN = {r: (int(_BDP[r] / 4), int(_BDP[r] * 3 / 4)) for r in RATES_MBPS}
CWND_START = {r: int(round(_BDP[r] * 1.25)) for r in RATES_MBPS}
# 400G matches C1's own empirically-found knee exactly (127) -- sanity-check
# the formula before trusting it at the other three rates.
assert CWND_START[400000] == 127, CWND_START[400000]

# Fixed-Q secondary check: hold Q/ECN at the 400G packet values at the two
# extreme rates (100G, 800G) instead of scaling with BDP.
FIXED_Q = Q[400000]
FIXED_ECN = ECN[400000]


def topo_path(rate_mbps: int) -> str:
    return TOPO_FMT.format(g=rate_mbps // 1000)


def base_flags(rate_mbps: int, *, cwnd: int, fixed_q: bool = False,
               seed: int = SEED) -> list[str]:
    q = FIXED_Q if fixed_q else Q[rate_mbps]
    ecn0, ecn1 = FIXED_ECN if fixed_q else ECN[rate_mbps]
    return [
        "-connections_mapping",
        "-sack_threshold", "4000",
        "-tm", CM,
        "-end", "90000",
        "-seed", str(seed),
        "-sender_cc_only", "-sender_cc_algo", "constant",
        # required whenever -sender_cc_only is paired with -log_reps_events
        # (experiments/tools/README.md) -- without it ECN silently re-enables
        # on ToR downlinks, contaminating the ECN-driven clean-ACK signal
        # this whole experiment measures (a_i, k). See CLAUDE.md's
        # -disable_tor_ecn gotcha.
        "-disable_tor_ecn",
        "-topo", topo_path(rate_mbps),
        "-linkspeed", str(rate_mbps),
        "-enable_qa_gate",
        "-ecn", str(ecn0), str(ecn1),
        "-q", str(q),
        "-cwnd", str(cwnd),
        "-exit_freeze", str(200 * 1_000_000),
        "-load_balancing_algo", "freezing",
        "-use_srv6", "-paths", str(N_PATHS),
        "-reps_buffer_size", str(B),
    ]


def path_static_flags(rate_mbps: int, *, cwnd: int, fixed_q: bool = False,
                       seed: int = SEED) -> list[str]:
    """Same fabric/CC/degrade-free flags as base_flags, LB swapped to
    path_static (one pinned path per flow, no REPS buffer, no EV draws --
    dedicated path, no multi-flow collision on the paths this group of
    flows uses). Null-hypothesis test: if a_i clustering comes purely from
    cross-flow queueing on shared links, pinning should collapse a_i to
    exactly 1 every slot."""
    base = base_flags(rate_mbps, cwnd=cwnd, fixed_q=fixed_q, seed=seed)
    idx = base.index("-load_balancing_algo")
    return base[:idx] + ["-load_balancing_algo", "path_static",
                          "-use_srv6", "-paths", str(N_PATHS)]


def event_log_flags(out_csv: str, src_ids: range = range(32),
                     max_rows: int = 4_000_000) -> list[str]:
    # 32 MiB @ ~8192 pkts/flow x 32 hosts x ~2 rows/pkt (SEND+ACK) can exceed
    # the 200000-row default (uec.cpp:354) by a wide margin -- raise it.
    flags: list[str] = ["-log_reps_events", out_csv,
                         "-log_reps_events_max", str(max_rows)]
    for s in src_ids:
        flags += ["-log_reps_events_src", str(s)]
    return flags
