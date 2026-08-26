#!/usr/bin/env python3
"""
gen_cdf_workloads.py — generate CDF-based TMs for exp09.

Wraps traffic_gen/traffic_gen.py to produce 18 connection-matrix files:
  2 CDFs × 3 loads × 3 seeds = 18 files

Naming: cdf_<name>_l<pct>_s<seed>.cm
  e.g.  cdf_websearch_l60_s42.cm

Output dir: htsim/sim/datacenter/connection_matrices/
Idempotent: skips files that already exist.

Usage:
    python3 gen_cdf_workloads.py [--force]
"""

import argparse
import subprocess
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
REPO_ROOT    = SCRIPT_DIR.parents[2]          # .../REPS_EuroSys_Artifact
TRAFFIC_GEN  = REPO_ROOT / "traffic_gen" / "traffic_gen.py"
CDF_DIR      = REPO_ROOT / "traffic_gen" / "cdf_files"
CM_DIR       = REPO_ROOT / "htsim" / "sim" / "datacenter" / "connection_matrices"

# ── Design axes ───────────────────────────────────────────────────────────────
CDFS = {
    "websearch": CDF_DIR / "WebSearch_distribution.txt",
    "hadoop":    CDF_DIR / "FbHdp_distribution.txt",
}
LOADS = [30, 60, 90]   # percentage (passed as 0.30, 0.60, 0.90)
SEEDS = [42, 43, 44]

# Simulator settings (must match v9_run_matrix.sh)
N_HOSTS    = 128
BANDWIDTH  = "400G"     # per-host uplink bandwidth
DURATION_S = 0.005      # 5 ms window: gives ~few hundred flows at 60% load


def gen_tm(cdf_name: str, cdf_path: Path, load_pct: int, seed: int,
           force: bool) -> bool:
    """Generate one TM file. Returns True if generated, False if skipped."""
    out_name = f"cdf_{cdf_name}_l{load_pct:02d}_s{seed}.cm"
    out_path = CM_DIR / out_name

    if out_path.exists() and not force:
        print(f"  SKIP  {out_name}  (already exists)")
        return False

    cmd = [
        sys.executable, str(TRAFFIC_GEN),
        "-n", str(N_HOSTS),
        "-c", str(cdf_path),
        "-l", f"{load_pct / 100:.2f}",
        "-b", BANDWIDTH,
        "-d", str(DURATION_S),
        "-s", str(seed),
        "-o", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=TRAFFIC_GEN.parent)
    if result.returncode != 0:
        print(f"  ERROR generating {out_name}:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return False

    # Quick sanity: count connections
    with open(out_path) as fh:
        lines = fh.readlines()
    n_conn_header = int(lines[1].split()[1]) if len(lines) > 1 else 0
    n_conn_actual = len(lines) - 2
    print(f"  GEN   {out_name}  (header={n_conn_header}, "
          f"actual={n_conn_actual} flows)")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing files")
    args = parser.parse_args()

    if not TRAFFIC_GEN.exists():
        sys.exit(f"ERROR: traffic_gen.py not found at {TRAFFIC_GEN}")
    CM_DIR.mkdir(parents=True, exist_ok=True)

    generated = skipped = errors = 0
    total = len(CDFS) * len(LOADS) * len(SEEDS)
    print(f"=== gen_cdf_workloads — {total} TMs ===")

    for cdf_name, cdf_path in CDFS.items():
        if not cdf_path.exists():
            print(f"WARNING: CDF file not found: {cdf_path}", file=sys.stderr)
            errors += len(LOADS) * len(SEEDS)
            continue
        for load_pct in LOADS:
            for seed in SEEDS:
                ok = gen_tm(cdf_name, cdf_path, load_pct, seed, args.force)
                if ok is True:
                    generated += 1
                elif ok is False and not args.force:
                    skipped += 1
                else:
                    errors += 1

    print(f"\nDone. {generated} generated, {skipped} skipped, {errors} errors.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
