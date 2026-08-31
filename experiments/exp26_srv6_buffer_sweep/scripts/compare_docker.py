#!/usr/bin/env python3
"""
compare_docker.py — check that the Docker-built htsim produces the same FCTs as
the WSL-run binary for fig7.

htsim is deterministic given a seed, so identical binaries -> bit-identical
FCTs. Any mismatch means toolchain skew and the WSL results should be redone.

Reads  data/flows.csv.gz             (WSL run, fig7 rows)
       data_docker_verify/flows.csv.gz  (Docker run, produced with EXP26_DATA)
Prints a per-cell max abs FCT delta and an overall verdict.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

EXP_DIR = Path(__file__).resolve().parents[1]
WSL = EXP_DIR / "data" / "flows.csv.gz"
DOCK = EXP_DIR / "data_docker_verify" / "flows.csv.gz"

KEYS = ["workload", "condition", "arm", "flow_id"]
TOL = 1e-6


def main() -> None:
    if not DOCK.exists():
        sys.exit(f"missing {DOCK} — run fig7 in Docker with EXP26_DATA first")
    a = pd.read_csv(WSL)
    b = pd.read_csv(DOCK)
    a = a[a.fig == "fig7"][KEYS + ["fct_us"]].rename(columns={"fct_us": "fct_wsl"})
    b = b[b.fig == "fig7"][KEYS + ["fct_us"]].rename(columns={"fct_us": "fct_dock"})
    m = a.merge(b, on=KEYS, how="outer", indicator=True)

    only = m[m._merge != "both"]
    if len(only):
        print(f"WARNING {len(only)} flows present in only one run:")
        print(only.groupby(["workload", "condition", "arm", "_merge"]).size())

    both = m[m._merge == "both"].copy()
    both["d"] = (both.fct_wsl - both.fct_dock).abs()
    worst = (both.groupby(["workload", "condition", "arm"]).d.max()
             .sort_values(ascending=False))
    print("\nmax |FCT_wsl - FCT_docker| per cell (top 15):")
    print(worst.head(15).to_string())

    n_bad = int((both.d > TOL).sum())
    print(f"\n{len(both)} flows compared; {n_bad} differ by > {TOL} us; "
          f"global max delta = {both.d.max():.6g} us")
    if n_bad == 0:
        print("VERDICT: Docker == WSL (bit-identical FCTs). WSL fig6/fig7 stand.")
    else:
        frac = n_bad / len(both)
        print(f"VERDICT: {frac:.1%} of flows differ — investigate toolchain skew.")


if __name__ == "__main__":
    main()
