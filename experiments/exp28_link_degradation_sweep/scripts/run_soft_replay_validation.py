#!/usr/bin/env python3
"""
exp28 reps-soft-replay validation -- standalone, NOT part of exp28's existing
part1/part2 statistical matrix (that matrix is `-sender_cc_algo mprdma`; this
is `-sender_cc_algo nscc`, the preferred CC per the user's instruction, so
nothing here is comparable to or mixed with part1/part2's existing CSVs).

Reuses exp28's own workload/topology/severities (common28.py's TOPO/N_PATHS/
SEED/SIZE/CM/Q/ECN/CWND, and the same `-failed`/`-skip_asy`/`-down_ratio`
mechanics run_part1.py/run_part2.py use), fixed at B=8 (reps_b8), across the
severity subset already tabulated in the brainstorm plan's Validation section:
healthy, asym1, asym8, asym16, asym32 (part1-style `-failed D`), asym4_r95
(part2-style `-failed 4 -down_ratio 0.05`).

4 arms, all on top of `reps_b8` + NSCC (see htsim/sim/uec.cpp's
`nextEntropy_freezing` / MODIFICATIONS.md's `reps-soft-replay` entry):
  nscc_baseline        -- today's behavior, flag absent
  nscc_fixed_p1        -- -reps_soft_replay -reps_soft_replay_fixed_p 1.0
  nscc_ewma            -- -reps_soft_replay (P = _exp_avg_ecn, filter on)
  nscc_ewma_nofilter   -- -reps_soft_replay -reps_soft_replay_no_filter

Layout:
  runs/soft_replay_validation/<cond>/<arm>/stdout.txt

    python3 run_soft_replay_validation.py
"""
from __future__ import annotations

import itertools

from common28 import CM, CWND, ECN, EXIT_FREEZE, N_PATHS, Q, TOPO
from common28 import DC_DIR, RUNS_DIR, run_one
from common import arm_lb_flags  # noqa: E402  (path already set by common28)

SEED = 42

SEVERITIES = [
    # (cond, failed, down_ratio)
    ("healthy", 0, None),
    ("asym1", 1, None),
    ("asym8", 8, None),
    ("asym16", 16, None),
    ("asym32", 32, None),
    ("asym4_r95", 4, 0.05),
]

ARMS = {
    "nscc_baseline": [],
    "nscc_fixed_p1": ["-reps_soft_replay", "-reps_soft_replay_fixed_p", "1.0"],
    "nscc_ewma": ["-reps_soft_replay"],
    "nscc_ewma_nofilter": ["-reps_soft_replay", "-reps_soft_replay_no_filter"],
}


def base_flags_nscc(failed: int, down_ratio: float | None) -> list[str]:
    f = [
        "-connections_mapping", "-disable_trim",
        "-sack_threshold", "4000",
        "-tm", CM,
        "-end", "90000",
        "-seed", str(SEED),
        "-sender_cc_only", "-sender_cc_algo", "nscc",
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
    return f + arm_lb_flags("reps_b8", N_PATHS)


def main() -> None:
    cells = list(itertools.product(SEVERITIES, ARMS.items()))
    print(f"soft_replay_validation: {len(cells)} runs "
          f"({len(SEVERITIES)} severities x {len(ARMS)} arms, NSCC, B=8)",
          flush=True)

    fails = 0
    for i, ((cond, failed, down_ratio), (arm, extra)) in enumerate(cells, 1):
        flags = base_flags_nscc(failed, down_ratio) + extra
        outfile = RUNS_DIR / "soft_replay_validation" / cond / arm / "stdout.txt"
        res = run_one(flags, outfile, cwd=DC_DIR)
        extra_s = f"  {res['nflows']} flows, {res['seconds']}s"
        print(f"[{i}/{len(cells)}] {res['status']:<18} {cond}/{arm}{extra_s}",
              flush=True)
        if res["status"].startswith("FAIL"):
            fails += 1

    print(f"\nsoft_replay_validation done: {fails} failures / {len(cells)}",
          flush=True)


if __name__ == "__main__":
    main()
