#!/usr/bin/env python3
"""C1.1 run driver. Idempotent (skips a cell whose stdout.txt already
finished).

    python3 run_c11.py --anchor              # 400G only, BDP-scaled Q/ECN
    python3 run_c11.py                        # full sweep (4 rates, BDP-scaled)
    python3 run_c11.py --fixed-q              # +2 cells: 100G/800G, fixed Q
"""
from __future__ import annotations

import argparse

import common_c11 as c


def cell_dir(rate_mbps: int, fixed_q: bool, cwnd: int):
    tag = f"{rate_mbps // 1000}g" + ("_fixedq" if fixed_q else "") + f"_cwnd{cwnd}"
    return c.RUNS_DIR / tag


def run_cell(rate_mbps: int, cwnd: int, fixed_q: bool = False) -> dict:
    d = cell_dir(rate_mbps, fixed_q, cwnd)
    d.mkdir(parents=True, exist_ok=True)
    events_csv = str(d / "events.csv")
    flags = (c.base_flags(rate_mbps, cwnd=cwnd, fixed_q=fixed_q)
             + c.event_log_flags(events_csv))
    res = c.run_one(flags, d / "stdout.txt", expect_cm_nodes=1024)
    name = f"{rate_mbps // 1000}g cwnd={cwnd}" + (" fixed_q" if fixed_q else "")
    extra = f"  {res['nflows']} flows, {res['seconds']}s" if res["nflows"] else ""
    if res["tor_ecn_reenabled"]:
        extra += "  [tor-ecn-reenabled]"
    print(f"{res['status']:<20} {name}{extra}", flush=True)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", action="store_true", help="400G only")
    ap.add_argument("--fixed-q", action="store_true",
                     help="also run 100G/800G at fixed (400G) Q/ECN")
    args = ap.parse_args()

    if args.anchor:
        run_cell(400000, c.CWND_START[400000])
        return

    for rate in c.RATES_MBPS:
        run_cell(rate, c.CWND_START[rate])

    if args.fixed_q:
        for rate in (100000, 800000):
            run_cell(rate, c.CWND_START[rate], fixed_q=True)


if __name__ == "__main__":
    main()
